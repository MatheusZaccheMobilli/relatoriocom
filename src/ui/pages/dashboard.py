"""Página: Dashboard Comercial — comparação mês atual × mês anterior + projeção.

Inspirado no dashboard interno da Mobílli (Apps Script). Quatro tabs:
Resumo · Evolução · Vendedores · Produtividade.

Filtro = mês de captação (deals com data_locacao no mês calendário).
"""

from __future__ import annotations

import html
from datetime import date, datetime, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta

import altair as alt
import pandas as pd
import streamlit as st

from src.auth import papel_por_id, tem_visao_completa, todos_nomes_conhecidos
from src.auth.vendedores import VENDEDORES
from src.business.orchestrator import cmp_de_serie
from src.data.bitrix import label_source
from src.models import (
    CaptacoesComparadas,
    CaptacoesMes,
    CaptacoesVendedor,
    FrotaSnapshot,
)
from src.ui.data import frota_cacheada, limpar_cache, serie_historica_cacheada
from src.ui.shared import (
    PRIMEIRO_MES_CAPTACAO,
    agora_brt,
    classe_delta,
    formatar_brl,
    formatar_data,
    formatar_pct,
    mes_ano_label,
    mes_curto,
    opcoes_de_mes,
    variacao_pct,
)


# Meta de captações do time, ajustada manualmente a cada mês pelo RH.
# Trocar este valor antes do primeiro dia útil do mês seguinte.
META_TIME: int = 184


def _brl_compacto(v: Decimal | float | int) -> str:
    """Formata R$ de forma compacta para card: R$ 312k, R$ 1,2M, R$ 850."""
    f = float(v)
    if f >= 1_000_000:
        return f"R$ {f / 1_000_000:.1f}M".replace(".", ",")
    if f >= 10_000:
        return f"R$ {int(round(f / 1_000))}k"
    if f >= 1_000:
        return f"R$ {f / 1_000:.1f}k".replace(".", ",")
    return f"R$ {int(round(f))}"


def _md(html_str: str) -> None:
    """Renderiza HTML via st.markdown stripando leading whitespace por linha.

    Streamlit's markdown parser trata 4+ espaços de indentação como bloco de
    código, fazendo o HTML aparecer cru na tela. Stripar cada linha resolve.
    """
    cleaned = "\n".join(line.lstrip() for line in html_str.splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


# ─── helpers ────────────────────────────────────────────────────────────
def _eh_nome_desconhecido(nome: str) -> bool:
    return nome.startswith("Vendedor #") or nome.startswith("Consultor #")


def _iniciais(nome: str) -> str:
    if _eh_nome_desconhecido(nome):
        return "—"
    partes = [p for p in nome.split() if p]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][0].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def _primeiro_nome(nome: str) -> str:
    if _eh_nome_desconhecido(nome):
        return nome  # mantém "Vendedor #12345" no eixo do gráfico
    return nome.split()[0] if nome else "?"


def _delta_badge(pct: float) -> str:
    return f'<span class="mob-delta {classe_delta(pct)}">{html.escape(formatar_pct(pct))}</span>'


def _locacoes_emp(snap: CaptacoesMes) -> int:
    return snap.locacoes_total


def _vendas_emp(snap: CaptacoesMes) -> int:
    return snap.vendas_total


def _total_emp(snap: CaptacoesMes) -> int:
    return snap.total_empresa


# ─── header ─────────────────────────────────────────────────────────────
def _hero(mes: date, atualizado_em: datetime) -> None:
    _md(f"""
        <div class="mob-hero">
            <div>
                <h1>Dashboard Comercial</h1>
                <div class="mob-hero-sub">Mobílli Rentals · Serra/ES</div>
            </div>
            <div class="mob-hero-meta">
                <b>{html.escape(mes_ano_label(mes))}</b><br/>
                Atualizado {atualizado_em.strftime('%d/%m %H:%M')}
            </div>
        </div>
    """)


def _ytd_totais(serie: list[CaptacoesMes], ate_mes: date) -> tuple[int, int, int, int]:
    """Soma captações desde Mar/2026 até o mês selecionado (inclusive).

    Retorna (locacoes, vendas, total, qtd_meses).
    """
    selecionados = [
        s for s in serie
        if PRIMEIRO_MES_CAPTACAO <= s.mes <= ate_mes
    ]
    loc = sum(s.locacoes_total for s in selecionados)
    vnd = sum(s.vendas_total for s in selecionados)
    return loc, vnd, loc + vnd, len(selecionados)


def _highlights(
    cmp_: CaptacoesComparadas,
    meta: int,
    hoje: date,
    serie: list[CaptacoesMes],
) -> None:
    """4 destaques: captações · faturamento R$ · projeção · acumulado YTD.

    Card 2 mostra R$ que rodou no mês (MicroWork — boletos de aluguel
    com movimento no mês) com delta MoM e projeção fim-de-mês.
    Card 4 mostra captações acumuladas desde Mar/2026.
    """
    total_atual = _total_emp(cmp_.atual)
    mes_at = cmp_.atual.mes
    nome_at = mes_curto(mes_at)
    nome_ant = mes_curto(cmp_.anterior.mes)

    # Card 1: Mês atual com dia parcial
    fim_at = (mes_at.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    em_curso = hoje <= fim_at and hoje.year == mes_at.year and hoje.month == mes_at.month
    sub_atual = (
        f"até dia {hoje.day:02d}/{mes_at.month:02d}" if em_curso else "mês fechado"
    )

    # Card 2: Faturamento real (MicroWork)
    fat_atual = cmp_.atual.faturamento
    fat_anterior = cmp_.anterior.faturamento
    pct_fat = variacao_pct(float(fat_atual), float(fat_anterior))
    proj_fat = cmp_.projecao_faturamento
    sub_fat = (
        f"{html.escape(nome_ant)}: {_brl_compacto(fat_anterior)} · proj. {_brl_compacto(proj_fat)}"
        if em_curso
        else f"{html.escape(nome_ant)}: {_brl_compacto(fat_anterior)}"
    )

    # Tooltip explicando como o faturamento é calculado
    if em_curso:
        fat_tip = (
            "<b>Como o faturamento é calculado</b><br/>"
            "Soma dos boletos de aluguel pagos no MicroWork "
            "com data de movimento dentro do mês — vem da frota "
            "inteira de contratos ativos, não só das captações novas."
            "<br/><br/>"
            "Filtro: espécie OUTROS + documento no padrão "
            "<i>dealID-NP - seq</i>. Descarta NF-E, franquia, multa, "
            "reembolso e qualquer boleto fora desse padrão."
            "<br/><br/>"
            f"Mês em curso ({hoje.day:02d}/{mes_at.month:02d}): "
            f"valor exibido é parcial. A projeção "
            f"({_brl_compacto(proj_fat)}) usa a mesma regra dos "
            "dias úteis decorridos × dias úteis totais."
        )
    else:
        fat_tip = (
            "<b>Como o faturamento é calculado</b><br/>"
            "Soma dos boletos de aluguel pagos no MicroWork "
            "com data de movimento dentro do mês — vem da frota "
            "inteira de contratos ativos, não só das captações novas."
            "<br/><br/>"
            "Filtro: espécie OUTROS + documento no padrão "
            "<i>dealID-NP - seq</i>. Descarta NF-E, franquia, multa, "
            "reembolso e qualquer boleto fora desse padrão."
            "<br/><br/>"
            "Mês fechado — valor é o realizado final."
        )

    # Card 3: Projeção + nudge "faltam X pra próximo nível"
    proj = cmp_.projecao_total
    if meta > 0:
        prata_alvo = meta
        ouro_alvo = int(meta * 1.32)
        if proj >= ouro_alvo:
            nudge = f"projeção bate Ouro com folga"
        elif proj >= prata_alvo:
            falta_ouro = ouro_alvo - proj
            nudge = f"+{falta_ouro} pra projetar Ouro"
        else:
            falta_prata = prata_alvo - proj
            falta_ouro = ouro_alvo - proj
            nudge = f"+{falta_prata} pra Prata · +{falta_ouro} pra Ouro"
    else:
        nudge = "informe a meta no sidebar"

    # Tooltip explicando como a projeção é calculada
    du_dec = cmp_.du_decorridos_atual
    du_tot = cmp_.du_mes_atual
    if em_curso and du_dec > 0:
        du_dec_str = f"{du_dec:.1f}".replace(".", ",")
        du_tot_str = f"{du_tot:.1f}".replace(".", ",")
        proj_tip = (
            "<b>Como a projeção é calculada</b><br/>"
            "Captações até hoje ÷ dias úteis decorridos × "
            "dias úteis totais do mês."
            "<br/><br/>"
            f"Hoje: {total_atual} ÷ {du_dec_str} × {du_tot_str} ≈ {proj}"
            "<br/><br/>"
            "Dias úteis ponderados (Seg–Sex = 1, Sáb = 0,5, "
            "Dom/feriado = 0). Quanto mais o mês avança, mais "
            "precisa fica a estimativa."
        )
    else:
        proj_tip = (
            "<b>Mês fechado</b><br/>"
            f"Não há mais dias úteis no mês — a projeção é igual "
            f"ao total realizado ({total_atual})."
        )

    # Card 4: Acumulado YTD desde Mar/2026
    _, _, ytd_total, ytd_meses = _ytd_totais(serie, mes_at)
    primeiro = mes_curto(PRIMEIRO_MES_CAPTACAO)
    sub_ytd = (
        f"{ytd_meses} mês acumulado · {html.escape(primeiro)}"
        if ytd_meses == 1
        else f"{ytd_meses} meses · {html.escape(primeiro)} → {html.escape(nome_at)}"
    )

    _md(f"""
        <div class="mob-hl-row cols-4">
            <div class="mob-hl">
                <div class="mob-hl-lbl">{html.escape(nome_at)} · captações</div>
                <div class="mob-hl-val">{total_atual}</div>
                <div class="mob-hl-sub">{html.escape(sub_atual)}</div>
            </div>
            <div class="mob-hl parcial">
                <div class="mob-hl-lbl">{html.escape(nome_at)} · faturamento<span class="mob-hl-info" tabindex="0">!<span class="mob-hl-tip">{fat_tip}</span></span></div>
                <div class="mob-hl-val">{_brl_compacto(fat_atual)} {_delta_badge(pct_fat)}</div>
                <div class="mob-hl-sub">{sub_fat}</div>
            </div>
            <div class="mob-hl proj">
                <div class="mob-hl-lbl">Projeção fim de {html.escape(nome_at)}<span class="mob-hl-info" tabindex="0">!<span class="mob-hl-tip">{proj_tip}</span></span></div>
                <div class="mob-hl-val">~{proj}</div>
                <div class="mob-hl-sub">{html.escape(nudge)}</div>
            </div>
            <div class="mob-hl ytd">
                <div class="mob-hl-lbl">Acumulado YTD</div>
                <div class="mob-hl-val">{ytd_total}</div>
                <div class="mob-hl-sub">{sub_ytd}</div>
            </div>
        </div>
    """)


# ─── FROTA (SPA Inventário) ────────────────────────────────────────────
def _frota_card(frota: FrotaSnapshot) -> None:
    """4 mini-cards com o estado atual da frota.

    Independente do mês selecionado — sempre snapshot de hoje. Tooltips
    detalham as variantes de manutenção e os estados em "Outros".
    """
    ativa = frota.ativa
    if ativa == 0:
        return  # sem dados, não polui a tela

    pct_alug = frota.alugadas / ativa * 100
    pct_manut = frota.manutencao / ativa * 100

    manut_detalhes = sorted(
        ((label, qtd) for label, qtd in frota.por_estado.items()
         if label.startswith("Manutenção")),
        key=lambda x: -x[1],
    )
    manut_tip = (
        "<b>Variantes de manutenção</b><br/>"
        + "<br/>".join(
            f"{html.escape(label)}: {qtd}" for label, qtd in manut_detalhes
        )
    ) if manut_detalhes else "Sem motos em manutenção no momento."

    outros_detalhes = sorted(
        ((label, qtd) for label, qtd in frota.por_estado.items()
         if label not in ("Alugada", "Disponíveis")
         and not label.startswith("Manutenção")),
        key=lambda x: -x[1],
    )
    outros_tip = (
        "<b>Estados em \"Outros\"</b><br/>"
        + "<br/>".join(
            f"{html.escape(label)}: {qtd}" for label, qtd in outros_detalhes
        )
    ) if outros_detalhes else "Sem motos em estados secundários."

    sub_alug = (
        f"{pct_alug:.0f}% da frota · {frota.disponiveis} disponível"
        if frota.disponiveis == 1
        else f"{pct_alug:.0f}% da frota · {frota.disponiveis} disponíveis"
    )

    _md(f"""
        <div class="mob-hl-row cols-4">
            <div class="mob-hl">
                <div class="mob-hl-lbl">Frota ativa</div>
                <div class="mob-hl-val">{ativa}</div>
                <div class="mob-hl-sub">total na operação</div>
            </div>
            <div class="mob-hl">
                <div class="mob-hl-lbl">Alugadas</div>
                <div class="mob-hl-val">{frota.alugadas}</div>
                <div class="mob-hl-sub">{html.escape(sub_alug)}</div>
            </div>
            <div class="mob-hl">
                <div class="mob-hl-lbl">Em manutenção<span class="mob-hl-info" tabindex="0">!<span class="mob-hl-tip">{manut_tip}</span></span></div>
                <div class="mob-hl-val">{frota.manutencao}</div>
                <div class="mob-hl-sub">{pct_manut:.0f}% da frota</div>
            </div>
            <div class="mob-hl">
                <div class="mob-hl-lbl">Outros estados<span class="mob-hl-info" tabindex="0">!<span class="mob-hl-tip">{outros_tip}</span></span></div>
                <div class="mob-hl-val">{frota.outros}</div>
                <div class="mob-hl-sub">preparação · trânsito · sinistro · etc.</div>
            </div>
        </div>
    """)


# ─── META + NÍVEL ──────────────────────────────────────────────────────
_NIVEL_VISUAL: dict[str, tuple[str, str]] = {
    "Bronze": ("🥉", "bronze"),
    "Prata": ("🥈", "prata"),
    "Ouro": ("🥇", "ouro"),
    "Sem Meta": ("🎯", "bronze"),
}


def _classificar_nivel(atingido: int, meta: int) -> str:
    """TM-018: Bronze < 100% · Prata ≥ 100% · Ouro ≥ 132%."""
    if meta <= 0:
        return "Sem Meta"
    pct = atingido / meta * 100
    if pct >= 132:
        return "Ouro"
    if pct >= 100:
        return "Prata"
    return "Bronze"


def _meta_progresso(cmp_: CaptacoesComparadas, meta: int, hoje: date) -> None:
    """Faixa horizontal: progresso do mês atual contra a meta + badge de nível."""
    total_atual = _total_emp(cmp_.atual)
    projecao = cmp_.projecao_total
    nivel_atual = _classificar_nivel(total_atual, meta)
    nivel_proj = _classificar_nivel(projecao, meta)
    emoji, cls = _NIVEL_VISUAL[nivel_atual]
    emoji_proj, _ = _NIVEL_VISUAL[nivel_proj]

    pct_atual = (total_atual / meta * 100) if meta > 0 else 0
    largura = min(pct_atual, 140)  # cap visual em 140% pra não estourar a barra

    pct_str = f"{pct_atual:.0f}%" if meta > 0 else "—"
    proj_html = (
        f'<div class="mob-hl-sub" style="margin-top:6px;">projeção {projecao} '
        f'({html.escape(nivel_proj)} {emoji_proj})</div>'
        if meta > 0 and projecao != total_atual
        else ""
    )

    bloco = (
        '<div class="mob-meta-wrap">'
        '<div class="mob-meta-info">'
        '<div class="mob-meta-head">'
        f'<span class="mob-meta-title">Meta do time — {html.escape(mes_curto(cmp_.atual.mes))}</span>'
        f'<span class="mob-meta-num"><b>{total_atual}</b> / {meta} captações &nbsp;·&nbsp; {pct_str}</span>'
        '</div>'
        '<div class="mob-meta-bar">'
        f'<div class="mob-meta-fill {cls}" style="width:{largura:.1f}%"></div>'
        '</div>'
        '<div class="mob-meta-marks">'
        '<span>0</span>'
        f'<span>Prata · 100% ({meta})</span>'
        f'<span>Ouro · 132% ({int(meta * 1.32)})</span>'
        '</div>'
        f'{proj_html}'
        '</div>'
        f'<div class="mob-nivel-badge {cls}">'
        f'<div class="mob-nivel-emoji">{emoji}</div>'
        f'<div class="mob-nivel-name">{html.escape(nivel_atual)}</div>'
        '<div class="mob-nivel-pct">nível atual</div>'
        '</div>'
        '</div>'
    )
    st.markdown(bloco, unsafe_allow_html=True)


# ─── ABA: RESUMO ────────────────────────────────────────────────────────
def _bar_comparativa(label: str, barras: list[tuple[str, int, str]], max_val: int) -> str:
    """Renderiza linha 'Locação' com barras (label, valor, classe-css).

    `barras` é uma lista ordenada de tuplas: ("MAR", 100, "prev"),
    ("ABR", 89, "curr"), ("PROJEÇÃO", 89, "proj"). A classe define a cor
    (prev = cinza, curr = laranja, proj = laranja hachurado).
    """
    parts: list[str] = []
    for nome, valor, cls in barras:
        pct = (valor / max_val * 100) if max_val > 0 else 0
        parts.append(
            f'<div class="mob-cmp-mini">'
            f'<span>{html.escape(nome.upper())}</span>'
            f'<span><b>{valor}</b></span>'
            f'</div>'
            f'<div class="mob-cmp-bar">'
            f'<div class="mob-cmp-fill {cls}" style="width:{pct:.1f}%"></div>'
            f'</div>'
        )
    return (
        '<div class="mob-cmp-row">'
        '<div class="mob-cmp-head">'
        f'<span class="mob-cmp-label">{html.escape(label)}</span>'
        '</div>'
        + "".join(parts)
        + '</div>'
    )


def _bloco_mix_e_saude(cmp_: CaptacoesComparadas, nome_ant: str, nome_at: str) -> None:
    """Linha de 3 cards: mix Locação semanal/mensal + % devolução, todos com MoM.

    Mix mostra a fração semanal vs mensal das locações captadas no mês.
    Devolução mostra a taxa de captações que viraram devolução (P22).
    """
    atual = cmp_.atual
    anterior = cmp_.anterior

    # Mix Locação — só faz sentido se houve locação
    sem_at, men_at = atual.locacoes_semanal, atual.locacoes_mensal
    sem_ant, men_ant = anterior.locacoes_semanal, anterior.locacoes_mensal
    loc_at = sem_at + men_at
    loc_ant = sem_ant + men_ant

    pct_sem_at = (sem_at / loc_at * 100) if loc_at else 0
    pct_men_at = (men_at / loc_at * 100) if loc_at else 0
    pct_sem_ant = (sem_ant / loc_ant * 100) if loc_ant else 0
    delta_sem = pct_sem_at - pct_sem_ant  # variação em pontos percentuais

    # % Devolução
    dev_at = atual.devolvidos_total
    dev_ant = anterior.devolvidos_total
    pct_dev_at = (dev_at / atual.total_empresa * 100) if atual.total_empresa else 0
    pct_dev_ant = (dev_ant / anterior.total_empresa * 100) if anterior.total_empresa else 0
    delta_dev = variacao_pct(dev_at, dev_ant)

    # Devolução: queda é POSITIVA (verde), por isso inverto o sinal pro classe_delta
    classe_dev = classe_delta(-delta_dev) if dev_ant else "ne"
    badge_dev_html = (
        f'<span class="mob-delta {classe_dev}">{html.escape(formatar_pct(delta_dev))}</span>'
    )

    # Layout: 3 colunas pareadas (Mix Semanal, Mix Mensal, Devolução)
    col_sem, col_men, col_dev = st.columns(3)
    with col_sem:
        _md(f"""
            <div class="mob-kpi">
                <div class="mob-kpi-label">Plano semanal · {html.escape(nome_at)}</div>
                <div class="mob-kpi-value">{sem_at}<span style="font-size:18px;color:#6b7280;font-weight:400;"> ({pct_sem_at:.0f}%)</span></div>
                <div class="mob-kpi-help">{sem_ant} em {html.escape(nome_ant)} ({pct_sem_ant:.0f}%) · Δ {delta_sem:+.0f}p.p.</div>
            </div>
        """)
    with col_men:
        _md(f"""
            <div class="mob-kpi">
                <div class="mob-kpi-label">Plano mensal · {html.escape(nome_at)}</div>
                <div class="mob-kpi-value">{men_at}<span style="font-size:18px;color:#6b7280;font-weight:400;"> ({pct_men_at:.0f}%)</span></div>
                <div class="mob-kpi-help">{men_ant} em {html.escape(nome_ant)} · base {loc_at} locações</div>
            </div>
        """)
    with col_dev:
        _md(f"""
            <div class="mob-kpi">
                <div class="mob-kpi-label">Devolução · {html.escape(nome_at)}</div>
                <div class="mob-kpi-value">{pct_dev_at:.1f}%{badge_dev_html}</div>
                <div class="mob-kpi-help">{dev_at} de {atual.total_empresa} · {html.escape(nome_ant)}: {pct_dev_ant:.1f}% ({dev_ant})</div>
            </div>
        """)


def _tab_resumo(cmp_: CaptacoesComparadas) -> None:
    loc_ant = _locacoes_emp(cmp_.anterior)
    loc_atual = _locacoes_emp(cmp_.atual)
    vnd_ant = _vendas_emp(cmp_.anterior)
    vnd_atual = _vendas_emp(cmp_.atual)

    pct_loc = variacao_pct(loc_atual, loc_ant)
    pct_vnd = variacao_pct(vnd_atual, vnd_ant)

    nome_ant = mes_curto(cmp_.anterior.mes)
    nome_at = mes_curto(cmp_.atual.mes)

    # Cards Mar/Abr lado a lado
    col1, col2 = st.columns(2)
    with col1:
        _md(f"""
            <div class="mob-kpi">
                <div class="mob-kpi-label">Locações {html.escape(nome_ant)} → {html.escape(nome_at)}</div>
                <div class="mob-kpi-value">{loc_atual} {_delta_badge(pct_loc)}</div>
                <div class="mob-kpi-help">{loc_ant} em {html.escape(nome_ant)}</div>
            </div>
        """)
    with col2:
        _md(f"""
            <div class="mob-kpi accent-dark">
                <div class="mob-kpi-label">Vendas {html.escape(nome_ant)} → {html.escape(nome_at)}</div>
                <div class="mob-kpi-value">{vnd_atual} {_delta_badge(pct_vnd)}</div>
                <div class="mob-kpi-help">{vnd_ant} em {html.escape(nome_ant)}</div>
            </div>
        """)

    st.markdown("&nbsp;")
    _bloco_mix_e_saude(cmp_, nome_ant, nome_at)

    st.markdown("&nbsp;")
    _md('<div class="mob-section-title">Comparativo geral (Locação · Venda)</div>')

    max_loc = max(loc_ant, loc_atual, cmp_.projecao_locacoes, 1)
    max_vnd = max(vnd_ant, vnd_atual, cmp_.projecao_vendas, 1)

    col_l, col_v = st.columns(2)
    with col_l:
        _md(_bar_comparativa(
            "Locação",
            [
                (nome_ant, loc_ant, "prev"),
                (nome_at, loc_atual, "curr"),
                ("Projeção", cmp_.projecao_locacoes, "proj"),
            ],
            max_loc,
        ))
    with col_v:
        _md(_bar_comparativa(
            "Venda",
            [
                (nome_ant, vnd_ant, "prev"),
                (nome_at, vnd_atual, "curr"),
                ("Projeção", cmp_.projecao_vendas, "proj"),
            ],
            max_vnd,
        ))

    # Tabela resumo
    st.markdown("&nbsp;")
    _md('<div class="mob-section-title">Tabela resumo</div>')

    total_ant = loc_ant + vnd_ant
    total_atual = loc_atual + vnd_atual
    pct_total = variacao_pct(total_atual, total_ant)

    rows = [
        ("Locação", loc_ant, loc_atual, cmp_.projecao_locacoes, pct_loc),
        ("Venda", vnd_ant, vnd_atual, cmp_.projecao_vendas, pct_vnd),
    ]

    body_rows = "".join(
        f'<tr><td>{html.escape(nome)}</td>'
        f'<td class="num">{ant}</td>'
        f'<td class="num">{at}</td>'
        f'<td class="num">~{proj}</td>'
        f'<td class="num">{_delta_badge(pct)}</td></tr>'
        for nome, ant, at, proj, pct in rows
    )
    body_rows += (
        f'<tr class="total"><td>TOTAL</td>'
        f'<td class="num">{total_ant}</td>'
        f'<td class="num">{total_atual}</td>'
        f'<td class="num">~{cmp_.projecao_total}</td>'
        f'<td class="num">{_delta_badge(pct_total)}</td></tr>'
    )

    _md(
        '<table class="mob-tab">'
        '<thead><tr>'
        '<th>Modalidade</th>'
        f'<th class="num">{html.escape(nome_ant)}</th>'
        f'<th class="num">{html.escape(nome_at)} parcial</th>'
        '<th class="num">Projeção</th>'
        '<th class="num">Var.</th>'
        '</tr></thead>'
        f'<tbody>{body_rows}</tbody>'
        '</table>'
    )


# ─── ABA: EVOLUÇÃO ─────────────────────────────────────────────────────
def _acumulado_diario(snap: CaptacoesMes) -> dict[int, int]:
    """Mapa dia → captações acumuladas até o dia (inclusive)."""
    acum: dict[int, int] = {}
    total = 0
    for dia in range(1, 32):
        total += snap.captacoes_por_dia.get(dia, 0)
        acum[dia] = total
    return acum


def _historico_mensal(serie: list[CaptacoesMes]) -> None:
    """Renderiza dois charts: linha por tipo (Loc/Vnd/Total) ao longo dos meses,
    e dual-axis (barras mensais + linha acumulada YTD).
    """
    _md('<div class="mob-section-title">Histórico mensal — desde Mar/2026</div>')

    rows = []
    for snap in serie:
        rotulo = mes_curto(snap.mes)
        rows.append({"Mês": rotulo, "ord": snap.mes.toordinal(),
                     "Tipo": "Locação", "Captações": snap.locacoes_total})
        rows.append({"Mês": rotulo, "ord": snap.mes.toordinal(),
                     "Tipo": "Venda", "Captações": snap.vendas_total})
        rows.append({"Mês": rotulo, "ord": snap.mes.toordinal(),
                     "Tipo": "Total", "Captações": snap.total_empresa})
    df_serie = pd.DataFrame(rows)
    ordem_meses = [mes_curto(s.mes) for s in serie]

    # Chart 1: linha por tipo (Loc/Vnd/Total)
    chart_serie = (
        alt.Chart(df_serie)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=80), strokeWidth=3)
        .encode(
            x=alt.X("Mês:N", title=None, sort=ordem_meses,
                    axis=alt.Axis(labelFontSize=12, domain=False, ticks=False, labelColor="#1a1a1a")),
            y=alt.Y("Captações:Q", title=None,
                    axis=alt.Axis(grid=True, gridColor="#eef0f3", domain=False, labelColor="#1a1a1a")),
            color=alt.Color(
                "Tipo:N",
                scale=alt.Scale(
                    domain=["Total", "Locação", "Venda"],
                    range=["#1a1a1a", "#FF6600", "#6b7280"],
                ),
                legend=alt.Legend(orient="top", title=None, labelFontSize=13, labelColor="#1a1a1a"),
            ),
            tooltip=["Mês", "Tipo", "Captações"],
        )
        .properties(height=300, background="#ffffff")
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor="#1a1a1a", titleColor="#1a1a1a")
        .configure_legend(labelColor="#1a1a1a", labelFontSize=13)
    )
    st.altair_chart(chart_serie, use_container_width=True)

    # Chart 2: dual-axis — barras (mês) + linha (acumulado YTD)
    st.markdown("&nbsp;")
    _md('<div class="mob-section-title">Captações do mês × acumulado</div>')

    acumulado = 0
    rows_dual = []
    for snap in serie:
        acumulado += snap.total_empresa
        rows_dual.append({
            "Mês": mes_curto(snap.mes),
            "ord": snap.mes.toordinal(),
            "Captações": snap.total_empresa,
            "Acumulado": acumulado,
        })
    df_dual = pd.DataFrame(rows_dual)

    base = alt.Chart(df_dual).encode(
        x=alt.X("Mês:N", title=None, sort=ordem_meses,
                axis=alt.Axis(labelFontSize=12, domain=False, ticks=False, labelColor="#1a1a1a")),
    )
    cor_serie = alt.Scale(
        domain=["Captações no mês", "Acumulado YTD"],
        range=["#FF6600", "#1a1a1a"],
    )
    barras = base.mark_bar(cornerRadiusEnd=4, size=40).encode(
        y=alt.Y("Captações:Q", title="Captações no mês",
                axis=alt.Axis(grid=True, gridColor="#eef0f3", domain=False,
                              titleColor="#FF6600", labelColor="#1a1a1a")),
        color=alt.Color(
            "serie:N",
            scale=cor_serie,
            legend=alt.Legend(
                orient="top", title=None, labelFontSize=13,
                labelColor="#1a1a1a", symbolSize=120,
            ),
        ),
        tooltip=["Mês", "Captações"],
    ).transform_calculate(serie='"Captações no mês"')
    linha = base.mark_line(
        point=alt.OverlayMarkDef(filled=True, size=80),
        strokeWidth=3,
    ).encode(
        y=alt.Y("Acumulado:Q", title="Acumulado",
                axis=alt.Axis(grid=False, domain=False,
                              titleColor="#1a1a1a", labelColor="#1a1a1a", orient="right")),
        color=alt.Color("serie:N", scale=cor_serie, legend=None),
        tooltip=["Mês", "Acumulado"],
    ).transform_calculate(serie='"Acumulado YTD"')
    chart_dual = (
        alt.layer(barras, linha)
        .resolve_scale(y="independent")
        .properties(height=280, background="#ffffff")
        .configure_view(strokeWidth=0)
        .configure_axis(titleFontSize=11, titleFontWeight="bold")
        .configure_legend(labelColor="#1a1a1a", labelFontSize=13)
    )
    st.altair_chart(chart_dual, use_container_width=True)


def _tab_evolucao(cmp_: CaptacoesComparadas, serie: list[CaptacoesMes]) -> None:
    nome_ant = mes_curto(cmp_.anterior.mes)
    nome_at = mes_curto(cmp_.atual.mes)

    # ─── Histórico mensal (todos os meses desde março) ─────────
    if len(serie) >= 2:
        _historico_mensal(serie)
        st.markdown("&nbsp;")
    else:
        st.info(
            "**Histórico mensal vai aparecer aqui** quando houver pelo menos "
            "2 meses fechados a partir de Mar/2026."
        )
        st.markdown("&nbsp;")

    # ─── Acumulado dia a dia (recorte do mês atual vs anterior) ─
    acum_ant = _acumulado_diario(cmp_.anterior)
    acum_at = _acumulado_diario(cmp_.atual)

    # Pontos só para dias ímpares (1, 3, 5… 29) — alinhado ao dashboard ref
    dias = list(range(1, 30, 2))
    df = pd.DataFrame([
        {"Dia": d, "Mês": nome_ant, "Captações": acum_ant.get(d, 0)} for d in dias
    ] + [
        {"Dia": d, "Mês": nome_at, "Captações": acum_at.get(d, 0)} for d in dias
    ])

    _md(f'<div class="mob-section-title">Acumulado dia a dia — {html.escape(nome_ant)} × {html.escape(nome_at)}</div>')

    chart = (
        alt.Chart(df)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=80), strokeWidth=3)
        .encode(
            x=alt.X("Dia:O", title="Dia",
                    axis=alt.Axis(labelFontSize=11, domain=False, ticks=False, labelColor="#1a1a1a", titleColor="#1a1a1a")),
            y=alt.Y("Captações:Q", title=None,
                    axis=alt.Axis(grid=True, gridColor="#eef0f3", domain=False, tickColor="#eef0f3", labelColor="#1a1a1a")),
            color=alt.Color(
                "Mês:N",
                scale=alt.Scale(
                    domain=[nome_ant, nome_at],
                    range=["#6b7280", "#FF6600"],
                ),
                legend=alt.Legend(orient="top", title=None, labelFontSize=13, labelColor="#1a1a1a", symbolStrokeWidth=0, symbolSize=200),
            ),
            tooltip=["Mês", "Dia", "Captações"],
        )
        .properties(height=320, background="#ffffff")
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor="#1a1a1a", titleColor="#1a1a1a")
        .configure_legend(labelColor="#1a1a1a", titleColor="#1a1a1a", labelFontSize=13)
    )
    st.altair_chart(chart, use_container_width=True)

    # Por semana
    st.markdown("&nbsp;")
    _md('<div class="mob-section-title">Por semana</div>')

    semanas = [(1, 7), (8, 14), (15, 21), (22, 28), (29, 31)]
    rows_sem = []
    for i, (ini, fim) in enumerate(semanas, start=1):
        capt_ant = sum(cmp_.anterior.captacoes_por_dia.get(d, 0) for d in range(ini, fim + 1))
        capt_at = sum(cmp_.atual.captacoes_por_dia.get(d, 0) for d in range(ini, fim + 1))
        rows_sem.append(
            {"Semana": f"Sem {i} ({ini}–{fim})", "Mês": nome_ant, "Captações": capt_ant}
        )
        rows_sem.append(
            {"Semana": f"Sem {i} ({ini}–{fim})", "Mês": nome_at, "Captações": capt_at}
        )

    df_sem = pd.DataFrame(rows_sem)
    chart_sem = (
        alt.Chart(df_sem)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("Semana:N", title=None, axis=alt.Axis(labelAngle=0, domain=False, labelColor="#1a1a1a")),
            xOffset="Mês:N",
            y=alt.Y("Captações:Q", title=None, axis=alt.Axis(grid=True, gridColor="#eef0f3", domain=False, labelColor="#1a1a1a")),
            color=alt.Color(
                "Mês:N",
                scale=alt.Scale(domain=[nome_ant, nome_at], range=["#6b7280", "#FF6600"]),
                legend=alt.Legend(orient="top", title=None, labelFontSize=13, labelColor="#1a1a1a"),
            ),
            tooltip=["Semana", "Mês", "Captações"],
        )
        .properties(height=240, background="#ffffff")
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor="#1a1a1a", titleColor="#1a1a1a")
        .configure_legend(labelColor="#1a1a1a", labelFontSize=13)
    )
    st.altair_chart(chart_sem, use_container_width=True)


# ─── ABA: VENDEDORES ──────────────────────────────────────────────────
def _card_vendedor(
    v_at: CaptacoesVendedor,
    v_ant: CaptacoesVendedor,
    label_ant: str,
    label_at: str,
) -> None:
    eh_lider = tem_visao_completa(v_at.vendedor_id)
    cls_avatar = "mob-avatar lider" if eh_lider else "mob-avatar"
    pct = variacao_pct(v_at.total, v_ant.total)

    if _eh_nome_desconhecido(v_at.nome):
        nome_curto = v_at.nome
        role = "Não cadastrado"
    else:
        nome_curto = " ".join(v_at.nome.split()[:2])
        role = papel_por_id(v_at.vendedor_id) or "Vendedor"

    _md(f"""
        <div class="mob-vend">
            <div class="mob-vend-head">
                <div class="{cls_avatar}">{html.escape(_iniciais(v_at.nome))}</div>
                <div>
                    <div class="mob-vend-name">{html.escape(nome_curto)}</div>
                    <div class="mob-vend-role">{html.escape(role)}</div>
                </div>
            </div>
            <div class="mob-vend-stats">
                <div class="mob-vend-stat">
                    <div class="mob-vend-stat-num" style="color:#6b7280;">{v_ant.total}</div>
                    <div class="mob-vend-stat-lbl">{html.escape(label_ant)}</div>
                </div>
                <div class="mob-vend-stat">
                    <div class="mob-vend-stat-num">{v_at.total}</div>
                    <div class="mob-vend-stat-lbl">{html.escape(label_at)}</div>
                </div>
            </div>
            <div style="margin-top:2px;">{_delta_badge(pct)}</div>
        </div>
    """)


def _ytd_por_vendedor(serie: list[CaptacoesMes], ate_mes: date) -> dict[int, int]:
    """Mapa vendedor_id → total acumulado (Mar/26 até o mês selecionado)."""
    acumulado: dict[int, int] = {}
    for snap in serie:
        if not (PRIMEIRO_MES_CAPTACAO <= snap.mes <= ate_mes):
            continue
        for v in snap.por_vendedor:
            acumulado[v.vendedor_id] = acumulado.get(v.vendedor_id, 0) + v.total
    return acumulado


def _tab_vendedores(cmp_: CaptacoesComparadas, serie: list[CaptacoesMes]) -> None:
    nome_ant = mes_curto(cmp_.anterior.mes)
    nome_at = mes_curto(cmp_.atual.mes)

    ant_by_id = {v.vendedor_id: v for v in cmp_.anterior.por_vendedor}
    ytd_by_id = _ytd_por_vendedor(serie, cmp_.atual.mes)
    ord_atual = [v for v in cmp_.atual.por_vendedor if v.total > 0]
    ord_atual.sort(key=lambda v: v.total, reverse=True)

    # Cards: TODOS os vendedores ativos (mesmo com 0 captações), ordenados
    # por total decrescente. Quem captou aparece primeiro (incluindo IDs
    # auto-descobertos do orchestrator); ativos sem captação no mês entram
    # no fim com 0 — confirmação visual de cadastro.
    ids_com_captacao = {v.vendedor_id for v in ord_atual}
    cards_ativos = list(ord_atual)
    for vid, nome in VENDEDORES.items():
        if vid not in ids_com_captacao:
            cards_ativos.append(CaptacoesVendedor(vendedor_id=vid, nome=nome))

    TOP_N = 8
    cards = cards_ativos[:TOP_N]
    n_desconhecidos = sum(1 for v in cards if _eh_nome_desconhecido(v.nome))

    if cards:
        for i in range(0, len(cards), 4):
            sub_cols = st.columns(4)
            for col, v in zip(sub_cols, cards[i:i + 4]):
                v_ant = ant_by_id.get(v.vendedor_id, CaptacoesVendedor(v.vendedor_id, v.nome))
                with col:
                    _card_vendedor(v, v_ant, label_ant=nome_ant, label_at=nome_at)
    else:
        st.info(
            f"**Nenhum vendedor ativo cadastrado.** "
            "Adicione em `src/auth/vendedores.py`."
        )
        return

    if len(cards_ativos) > TOP_N:
        st.caption(
            f"Exibindo top {TOP_N} vendedores. Restante na tabela abaixo."
        )

    if n_desconhecidos:
        st.caption(
            f"{n_desconhecidos} vendedor(es) sem nome cadastrado — "
            "edite `src/auth/vendedores.py` para mapear o ID."
        )

    # Chart "Top vendedores" — só faz sentido quando há captações no mês
    if ord_atual:
        st.markdown("&nbsp;")
        _md(
            f'<div class="mob-section-title">Top {min(TOP_N, len(ord_atual))} vendedores — '
            f'{html.escape(nome_ant)} × {html.escape(nome_at)}</div>'
        )

        chart_set = ord_atual[:TOP_N]
        rows = []
        for v in chart_set:
            v_ant = ant_by_id.get(v.vendedor_id, CaptacoesVendedor(v.vendedor_id, v.nome))
            rows.append({"Vendedor": _primeiro_nome(v.nome), "Mês": nome_ant, "Captações": v_ant.total})
            rows.append({"Vendedor": _primeiro_nome(v.nome), "Mês": nome_at, "Captações": v.total})
        df = pd.DataFrame(rows)

        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadiusEnd=3, height=14)
            .encode(
                y=alt.Y("Vendedor:N", title=None, sort="-x",
                        axis=alt.Axis(labelFontSize=12, domain=False, ticks=False, labelColor="#1a1a1a")),
                yOffset="Mês:N",
                x=alt.X("Captações:Q", title=None,
                        axis=alt.Axis(grid=True, gridColor="#eef0f3", domain=False, labelColor="#1a1a1a")),
                color=alt.Color(
                    "Mês:N",
                    scale=alt.Scale(domain=[nome_ant, nome_at], range=["#6b7280", "#FF6600"]),
                    legend=alt.Legend(orient="top", title=None, labelFontSize=13, labelColor="#1a1a1a"),
                ),
                tooltip=["Vendedor", "Mês", "Captações"],
            )
            .properties(height=max(200, 50 * len(chart_set)), background="#ffffff")
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor="#1a1a1a", titleColor="#1a1a1a")
            .configure_legend(labelColor="#1a1a1a", labelFontSize=13)
        )
        st.altair_chart(chart, use_container_width=True)

    # Tabela: Vendedor · Ant · Atual · Var. · YTD · Loc. · Vnd.
    # Inclui TODOS os vendedores ativos (mesmo com 0 no mês selecionado),
    # pra confirmação visual de quem está cadastrado no time.
    st.markdown("&nbsp;")
    _md('<div class="mob-section-title">Detalhamento</div>')

    tabela_vendedores = list(ord_atual)
    ids_existentes = {v.vendedor_id for v in tabela_vendedores}
    for vid, nome in VENDEDORES.items():
        if vid not in ids_existentes:
            tabela_vendedores.append(CaptacoesVendedor(vendedor_id=vid, nome=nome))

    body_rows_v = "".join(
        (
            f'<tr><td>{html.escape(v.nome)}</td>'
            f'<td class="num">{v_ant.total}</td>'
            f'<td class="num">{v.total}</td>'
            f'<td class="num">{_delta_badge(variacao_pct(v.total, v_ant.total))}</td>'
            f'<td class="num">{ytd_by_id.get(v.vendedor_id, 0)}</td>'
            f'<td class="num">{sum(1 for i in v.itens if i.tipo_operacao == "Locação")}</td>'
            f'<td class="num">{v.total - sum(1 for i in v.itens if i.tipo_operacao == "Locação")}</td>'
            f'</tr>'
        )
        for v in tabela_vendedores
        for v_ant in [ant_by_id.get(v.vendedor_id, CaptacoesVendedor(v.vendedor_id, v.nome))]
    )

    _md(
        '<table class="mob-tab">'
        '<thead><tr>'
        '<th>Vendedor</th>'
        f'<th class="num">{html.escape(nome_ant)}</th>'
        f'<th class="num">{html.escape(nome_at)}</th>'
        '<th class="num">Var.</th>'
        '<th class="num">YTD</th>'
        '<th class="num">Loc.</th>'
        '<th class="num">Vnd.</th>'
        '</tr></thead>'
        f'<tbody>{body_rows_v}</tbody>'
        '</table>'
    )


# ─── ABA: PRODUTIVIDADE ────────────────────────────────────────────────
def _tab_produtividade(cmp_: CaptacoesComparadas) -> None:
    nome_ant = mes_curto(cmp_.anterior.mes)
    nome_at = mes_curto(cmp_.atual.mes)

    total_ant = _total_emp(cmp_.anterior)
    total_at = _total_emp(cmp_.atual)
    prod_ant = total_ant / cmp_.du_mes_anterior if cmp_.du_mes_anterior else 0
    prod_at = total_at / cmp_.du_decorridos_atual if cmp_.du_decorridos_atual else 0
    pct_prod = variacao_pct(prod_at, prod_ant)

    col1, col2, col3 = st.columns(3)
    with col1:
        _md(f"""
            <div class="mob-kpi accent-dark">
                <div class="mob-kpi-label">Dias úteis</div>
                <div class="mob-kpi-value">{cmp_.du_decorridos_atual:.1f} <span style="font-size:18px;color:#6b7280;">/ {cmp_.du_mes_atual:.0f}</span></div>
                <div class="mob-kpi-help">{html.escape(nome_at)} (decorridos/total)</div>
            </div>
        """)
    with col2:
        _md(f"""
            <div class="mob-kpi">
                <div class="mob-kpi-label">Produtividade {html.escape(nome_ant)}</div>
                <div class="mob-kpi-value">{prod_ant:.1f}</div>
                <div class="mob-kpi-help">negócios por dia útil</div>
            </div>
        """)
    with col3:
        _md(f"""
            <div class="mob-kpi">
                <div class="mob-kpi-label">Produtividade {html.escape(nome_at)}</div>
                <div class="mob-kpi-value">{prod_at:.1f} {_delta_badge(pct_prod)}</div>
                <div class="mob-kpi-help">negócios por dia útil</div>
            </div>
        """)

    st.markdown("&nbsp;")
    _md('<div class="mob-section-title">Produtividade por vendedor</div>')

    ant_by_id = {v.vendedor_id: v for v in cmp_.anterior.por_vendedor}
    ord_atual = [v for v in cmp_.atual.por_vendedor if v.total > 0]
    ord_atual.sort(key=lambda v: v.total, reverse=True)

    body_rows_p = ""
    for v in ord_atual:
        v_ant = ant_by_id.get(v.vendedor_id, CaptacoesVendedor(v.vendedor_id, v.nome))
        loc_v = sum(1 for i in v.itens if i.tipo_operacao == "Locação")
        vnd_v = v.total - loc_v
        prod_v = v.total / cmp_.du_decorridos_atual if cmp_.du_decorridos_atual else 0
        prod_v_ant = v_ant.total / cmp_.du_mes_anterior if cmp_.du_mes_anterior else 0
        body_rows_p += (
            f'<tr><td>{html.escape(v.nome)}</td>'
            f'<td class="num">{v.total}</td>'
            f'<td class="num">{prod_v:.1f}</td>'
            f'<td class="num" style="color:#6b7280;">{prod_v_ant:.1f}</td>'
            f'<td class="num">{loc_v}</td>'
            f'<td class="num">{vnd_v}</td>'
            f'</tr>'
        )

    _md(
        '<table class="mob-tab">'
        '<thead><tr>'
        '<th>Vendedor</th>'
        f'<th class="num">Total {html.escape(nome_at)}</th>'
        f'<th class="num">Neg./du {html.escape(nome_at)}</th>'
        f'<th class="num">Neg./du {html.escape(nome_ant)}</th>'
        '<th class="num">Loc.</th>'
        '<th class="num">Vnd.</th>'
        '</tr></thead>'
        f'<tbody>{body_rows_p}</tbody>'
        '</table>'
    )


# ─── ABA: CONSOLIDADO ──────────────────────────────────────────────────
def _normalize_cidade(s: str) -> str:
    if not s:
        return ""
    return " ".join(s.split()).title()


def _tab_consolidado(serie: list[CaptacoesMes]) -> None:
    """Tabela consolidada: todos os negócios fechados desde Mar/2026.

    Header com 4 cards de totais reativos aos filtros (negócios, locação,
    venda, devolvidos). Filtros: mês, vendedor, tipo, plano, status, origem,
    cidade. Busca livre por cliente ou placa. Export CSV com nome refletindo
    os filtros aplicados.
    """
    rows = []
    for snap in serie:
        for v in snap.por_vendedor:
            for item in v.itens:
                if item.tipo_operacao == "Locação":
                    plano = "Semanal" if item.plano_semanal else "Mensal"
                else:
                    plano = "—"
                # tipo_operacao vem como "Locação" / "Venda 0km" / "Venda Usado".
                # Normaliza pra "Locação"/"Venda" e expõe a granularidade no Subtipo.
                tipo = "Locação" if item.tipo_operacao == "Locação" else "Venda"
                subtipo = (
                    "—" if item.tipo_operacao == "Locação"
                    else item.tipo_operacao.replace("Venda ", "")
                )
                rows.append({
                    "Mês": mes_ano_label(snap.mes),
                    "_mes_ord": snap.mes.toordinal(),
                    "Data": item.data_locacao,
                    "Vendedor": v.nome,
                    "Cliente": item.nome_cliente,
                    "Placa": item.placa or "—",
                    "Tipo": tipo,
                    "Subtipo": subtipo,
                    "Plano": plano,
                    "Origem": label_source(item.source_id),
                    "Cidade": _normalize_cidade(item.cidade) or "—",
                    "Status": "Devolvido" if item.devolvido else "Ativo",
                    "Devolução": item.data_devolucao,
                })

    if not rows:
        st.info("Nenhum negócio fechado no período.")
        return

    df = pd.DataFrame(rows)
    df = df.sort_values("Data", ascending=False, na_position="last").reset_index(drop=True)

    # Lista de meses ordenada do mais recente pro mais antigo
    meses_unicos = (
        df.drop_duplicates("Mês")
        .sort_values("_mes_ord", ascending=False)["Mês"]
        .tolist()
    )

    with st.expander("Filtros e busca", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            f_mes = st.multiselect("Mês", meses_unicos, default=[])
        with col2:
            f_vend = st.multiselect(
                "Vendedor", sorted(df["Vendedor"].unique()), default=[]
            )
        with col3:
            f_tipo = st.multiselect(
                "Tipo", sorted(df["Tipo"].unique()), default=[]
            )
        with col4:
            f_plano = st.multiselect(
                "Plano", sorted(df["Plano"].unique()), default=[]
            )

        col5, col6, col7 = st.columns(3)
        with col5:
            f_status = st.multiselect("Status", ["Ativo", "Devolvido"], default=[])
        with col6:
            f_origem = st.multiselect(
                "Origem", sorted(df["Origem"].unique()), default=[]
            )
        with col7:
            f_cidade = st.multiselect(
                "Cidade", sorted(df["Cidade"].unique()), default=[]
            )

        f_busca = st.text_input(
            "Buscar por cliente ou placa",
            placeholder="ex: João Silva, ABC1D23",
        )

    df_f = df.copy()
    if f_mes:
        df_f = df_f[df_f["Mês"].isin(f_mes)]
    if f_vend:
        df_f = df_f[df_f["Vendedor"].isin(f_vend)]
    if f_tipo:
        df_f = df_f[df_f["Tipo"].isin(f_tipo)]
    if f_plano:
        df_f = df_f[df_f["Plano"].isin(f_plano)]
    if f_status:
        df_f = df_f[df_f["Status"].isin(f_status)]
    if f_origem:
        df_f = df_f[df_f["Origem"].isin(f_origem)]
    if f_cidade:
        df_f = df_f[df_f["Cidade"].isin(f_cidade)]
    if f_busca:
        s = f_busca.strip().lower()
        df_f = df_f[
            df_f["Cliente"].str.lower().str.contains(s, na=False)
            | df_f["Placa"].str.lower().str.contains(s, na=False)
        ]

    # ── Header com 4 cards de totais (reativo aos filtros) ──
    n_total = len(df)
    n_filtrado = len(df_f)
    n_loc = int((df_f["Tipo"] == "Locação").sum())
    n_vnd = int((df_f["Tipo"] == "Venda").sum())
    n_dev = int((df_f["Status"] == "Devolvido").sum())
    pct_dev = (n_dev / n_filtrado * 100) if n_filtrado > 0 else 0
    pct_loc = (n_loc / n_filtrado * 100) if n_filtrado > 0 else 0
    pct_vnd = (n_vnd / n_filtrado * 100) if n_filtrado > 0 else 0

    sub_total = (
        f"de {n_total} no recorte total"
        if n_filtrado != n_total
        else "todos os meses desde Mar/2026"
    )

    _md(f"""
        <div class="mob-hl-row cols-4">
            <div class="mob-hl">
                <div class="mob-hl-lbl">Negócios</div>
                <div class="mob-hl-val">{n_filtrado}</div>
                <div class="mob-hl-sub">{html.escape(sub_total)}</div>
            </div>
            <div class="mob-hl parcial">
                <div class="mob-hl-lbl">Locação</div>
                <div class="mob-hl-val">{n_loc}</div>
                <div class="mob-hl-sub">{pct_loc:.1f}% do recorte</div>
            </div>
            <div class="mob-hl ytd">
                <div class="mob-hl-lbl">Venda</div>
                <div class="mob-hl-val">{n_vnd}</div>
                <div class="mob-hl-sub">{pct_vnd:.1f}% do recorte</div>
            </div>
            <div class="mob-hl proj">
                <div class="mob-hl-lbl">Devolvidos</div>
                <div class="mob-hl-val">{n_dev}</div>
                <div class="mob-hl-sub">{pct_dev:.1f}% do recorte</div>
            </div>
        </div>
    """)

    # ── Tabela (oculta a coluna helper _mes_ord) ──
    df_show = df_f.drop(columns=["_mes_ord"])
    st.dataframe(
        df_show,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "Data": st.column_config.DateColumn(
                "Data locação", format="DD/MM/YYYY"
            ),
            "Devolução": st.column_config.DateColumn(
                "Data devolução", format="DD/MM/YYYY"
            ),
        },
    )

    # ── Nome do CSV reflete filtros principais ──
    nome_partes = ["consolidado"]
    if f_mes and len(f_mes) <= 3:
        nome_partes.append(
            "_".join(m.lower().replace("/", "-") for m in f_mes)
        )
    if f_vend and len(f_vend) == 1:
        nome_partes.append(f_vend[0].split()[0].lower())
    if f_tipo and len(f_tipo) == 1:
        nome_partes.append(f_tipo[0].lower())
    nome_partes.append(date.today().strftime("%Y-%m-%d"))
    nome_csv = "_".join(nome_partes) + ".csv"

    csv = df_show.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Baixar CSV",
        csv,
        file_name=nome_csv,
        mime="text/csv",
        type="secondary",
    )


# ─── ABA: REVISÃO ──────────────────────────────────────────────────────
# Bitrix24 link template — quando alguém corrige o ASSIGNED_BY no CRM,
# o deal sai automaticamente desta aba na próxima atualização do cache.
_BITRIX_DEAL_URL = "https://mobilli.bitrix24.com.br/crm/deal/details/{}/"


def _tab_revisao(snap: CaptacoesMes) -> None:
    """Lista deals do MÊS SELECIONADO atribuídos a quem NÃO é vendedor ativo.

    Read-only: serve pra identificar deals que precisam ter o ASSIGNED_BY
    corrigido no Bitrix24. Quando alguém corrige no CRM, o deal sai daqui
    automaticamente na próxima atualização do cache.
    """
    rows = []
    for v in snap.por_vendedor:
        if v.vendedor_id in VENDEDORES:
            continue  # vendedor ativo — fora do escopo de revisão
        papel = papel_por_id(v.vendedor_id) or "Desconhecido"
        for item in v.itens:
            tipo = "Locação" if item.tipo_operacao == "Locação" else "Venda"
            if tipo == "Locação":
                plano = "Semanal" if item.plano_semanal else "Mensal"
            else:
                plano = "—"
            rows.append({
                "Data": item.data_locacao,
                "Responsável atual": v.nome,
                "Papel": papel,
                "Cliente": item.nome_cliente,
                "Placa": item.placa or "—",
                "Tipo": tipo,
                "Plano": plano,
                "Origem": label_source(item.source_id),
                "Cidade": _normalize_cidade(item.cidade) or "—",
                "Status": "Devolvido" if item.devolvido else "Ativo",
                "Bitrix": _BITRIX_DEAL_URL.format(item.deal_id),
            })

    nome_mes = mes_ano_label(snap.mes)

    if not rows:
        st.success(
            f"**Tudo certo em {nome_mes}.** Nenhum deal atribuído a "
            "não-vendedor neste mês. Se aparecer, vai listar aqui automaticamente."
        )
        return

    df = pd.DataFrame(rows)
    df = df.sort_values("Data", ascending=False, na_position="last").reset_index(drop=True)

    # Cards de totais — agrupa por papel
    n_total = len(df)
    por_papel = df["Papel"].value_counts().to_dict()
    papel_str = " · ".join(f"{papel}: {qtd}" for papel, qtd in por_papel.items())

    _md(f"""
        <div class="mob-hl-row">
            <div class="mob-hl proj">
                <div class="mob-hl-lbl">Deals pra revisar em {html.escape(nome_mes)}</div>
                <div class="mob-hl-val">{n_total}</div>
                <div class="mob-hl-sub">atribuídos a não-vendedores</div>
            </div>
            <div class="mob-hl">
                <div class="mob-hl-lbl">Por responsável</div>
                <div class="mob-hl-val" style="font-size:14px; line-height:1.4; padding-top:6px;">{html.escape(papel_str)}</div>
                <div class="mob-hl-sub">corrija no Bitrix → some daqui</div>
            </div>
            <div class="mob-hl ytd">
                <div class="mob-hl-lbl">Como funciona</div>
                <div class="mob-hl-val" style="font-size:14px; line-height:1.4; padding-top:6px;">Clique em "Bitrix"</div>
                <div class="mob-hl-sub">e troque o responsável pelo vendedor real</div>
            </div>
        </div>
    """)

    # Filtros opcionais (papel e tipo apenas — mês já filtrado no sidebar)
    with st.expander("Filtros", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            f_papel = st.multiselect(
                "Papel", sorted(df["Papel"].unique()), default=[], key="revisao_papel"
            )
        with col2:
            f_tipo = st.multiselect(
                "Tipo", sorted(df["Tipo"].unique()), default=[], key="revisao_tipo"
            )

    df_f = df.copy()
    if f_papel:
        df_f = df_f[df_f["Papel"].isin(f_papel)]
    if f_tipo:
        df_f = df_f[df_f["Tipo"].isin(f_tipo)]

    df_show = df_f

    # Renderiza como HTML manual: o LinkColumn do Streamlit às vezes não
    # navega corretamente dentro do iframe do Streamlit Cloud. Com <a> e
    # target="_blank" explícito, abre garantido em nova aba.
    if df_show.empty:
        st.info("Nenhum deal corresponde aos filtros selecionados.")
        return

    cols_visiveis = [c for c in df_show.columns if c != "Bitrix"]
    headers_html = "".join(
        f"<th>{html.escape(c)}</th>" for c in cols_visiveis
    ) + "<th>Bitrix</th>"

    rows_html_list = []
    for _, row in df_show.iterrows():
        cells = []
        for c in cols_visiveis:
            val = row[c]
            if c == "Data" and val is not None:
                txt = val.strftime("%d/%m/%Y") if hasattr(val, "strftime") else str(val)
            else:
                txt = "" if val is None else str(val)
            cells.append(f"<td>{html.escape(txt)}</td>")
        url = html.escape(str(row["Bitrix"]), quote=True)
        cells.append(
            f'<td><a href="{url}" target="_blank" rel="noopener noreferrer" '
            f'class="mob-deal-link">abrir deal ↗</a></td>'
        )
        rows_html_list.append(f"<tr>{''.join(cells)}</tr>")

    table_html = (
        '<div class="mob-tab-revisao-wrap">'
        '<table class="mob-tab">'
        f'<thead><tr>{headers_html}</tr></thead>'
        f'<tbody>{"".join(rows_html_list)}</tbody>'
        '</table>'
        '</div>'
        '<style>'
        '.mob-tab-revisao-wrap { max-height: 520px; overflow: auto; '
        'border-radius: 8px; border: 1px solid #e5e7eb; }'
        '.mob-tab-revisao-wrap .mob-tab { border: none; border-radius: 0; }'
        '.mob-tab-revisao-wrap thead th { position: sticky; top: 0; z-index: 1; }'
        '.mob-deal-link { color: #FF6600; font-weight: 600; '
        'text-decoration: none; white-space: nowrap; }'
        '.mob-deal-link:hover { text-decoration: underline; }'
        '</style>'
    )
    st.markdown(table_html, unsafe_allow_html=True)


# ─── render principal ──────────────────────────────────────────────────
def render() -> None:
    st.sidebar.markdown("## Dashboard")

    # Seletor de mês — default é o mês corrente. Permite voltar até Mar/2026
    # (PRIMEIRO_MES_CAPTACAO). Para meses fechados, "Em curso" vira "Fechado"
    # automaticamente via `em_curso` em _highlights.
    mes_atual_default = date.today().replace(day=1)
    meses_disp = opcoes_de_mes(
        ate_mes_seguinte=False, desde=PRIMEIRO_MES_CAPTACAO
    )
    if mes_atual_default not in meses_disp:
        meses_disp = [mes_atual_default] + meses_disp

    mes = st.sidebar.selectbox(
        "Mês de referência",
        meses_disp,
        index=meses_disp.index(mes_atual_default)
        if mes_atual_default in meses_disp
        else 0,
        format_func=mes_ano_label,
    )

    meta = META_TIME
    st.sidebar.markdown(
        f"**Meta do time:** {meta} captações"
    )

    st.sidebar.caption("Atualização automática a cada 30 min")

    # ── carrega dados ──────────────────────────────────────────────
    # Vendedores ativos + líderes + outros captadores conhecidos (sócio, robô, pós-venda).
    # IDs sem mapeamento entram como "Vendedor #ID" (auto-descobertos).
    todos_conhecidos = todos_nomes_conhecidos()
    vendedores_key = tuple(sorted(todos_conhecidos.items()))
    hoje = date.today()
    try:
        # Único fetch ao Bitrix: a série histórica. O comparativo MoM é
        # derivado dessa série sem refetch (era 12 chamadas Bitrix → agora 6).
        # Inclui mês_anterior pra cobrir corner case quando atual = mes_floor.
        floor_efetivo = min(
            PRIMEIRO_MES_CAPTACAO,
            (mes.replace(day=1) - relativedelta(months=1)).replace(day=1),
        )
        # mes_topo sempre vai até hoje (mês corrente) pra não perder histórico
        # quando o usuário navega pra um mês passado: a série completa fica
        # disponível, e _ytd_totais filtra por `mes` selecionado.
        mes_topo = max(mes, mes_atual_default)
        with st.spinner("Carregando dados de vendas..."):
            serie = serie_historica_cacheada(
                mes_floor=floor_efetivo,
                mes_topo=mes_topo,
                vendedores_key=vendedores_key,
            )
            cmp_ = cmp_de_serie(serie, mes_atual=mes, hoje=hoje)
    except Exception as exc:  # noqa: BLE001
        # Bitrix instável (503/timeout) ou rede caiu — UX amigável + ação clara.
        st.error(
            "**Não consegui carregar os dados do CRM agora.**  \n"
            f"Causa: `{type(exc).__name__}: {exc}`"
        )
        st.info(
            "Bitrix24 costuma responder com **503** quando recebe muitas chamadas "
            "simultâneas. Já tentei 4× com backoff. Aguarde alguns segundos e clique "
            "**Atualizar dados**."
        )
        if st.button("Tentar novamente", type="primary"):
            limpar_cache()
            st.rerun()
        st.stop()

    _hero(mes, agora_brt())
    _highlights(cmp_, meta, hoje, serie)

    # Slot reservado pro card de Frota — popula no fim do render pra
    # não bloquear o resto do dashboard enquanto a SPA Inventário
    # paginar (~6s no cold start, instant após cacheado).
    frota_slot = st.empty()

    _meta_progresso(cmp_, meta, hoje)

    tab_resumo, tab_evol, tab_vend, tab_prod, tab_cons, tab_rev = st.tabs(
        ["Resumo", "Evolução", "Vendedores", "Produtividade", "Consolidado", "Revisão"]
    )

    with tab_resumo:
        _tab_resumo(cmp_)
    with tab_evol:
        _tab_evolucao(cmp_, serie)
    with tab_vend:
        _tab_vendedores(cmp_, serie)
    with tab_prod:
        _tab_produtividade(cmp_)
    with tab_cons:
        _tab_consolidado(serie)
    with tab_rev:
        _tab_revisao(cmp_.atual)

    # Frota: fetch só agora pra deixar o resto do dashboard interativo
    # primeiro. Falha silenciosa se a SPA não responder.
    try:
        frota = frota_cacheada()
    except Exception:  # noqa: BLE001
        frota = None
    if frota is not None:
        with frota_slot.container():
            _frota_card(frota)
