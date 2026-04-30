"""Página: Dashboard Comercial — comparação mês atual × mês anterior + projeção.

Inspirado no dashboard interno da Mobílli (Apps Script). Quatro tabs:
Resumo · Evolução · Consultores · Produtividade.

Filtro = mês de captação (deals com data_locacao no mês calendário).
"""

from __future__ import annotations

import html
from datetime import date, datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from src.auth import LIDERES, VENDEDORES, tem_visao_completa
from src.models import CaptacoesComparadas, CaptacoesMes, CaptacoesVendedor
from src.ui.data import captacoes_comparadas_cacheadas, limpar_cache
from src.ui.shared import (
    PRIMEIRO_MES_CAPTACAO,
    classe_delta,
    formatar_data,
    formatar_pct,
    mes_ano_label,
    mes_curto,
    opcoes_de_mes,
    variacao_pct,
)


# ─── helpers ────────────────────────────────────────────────────────────
def _eh_nome_desconhecido(nome: str) -> bool:
    return nome.startswith("Consultor #")


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
        return nome  # mantém "Consultor #12345" no eixo do gráfico
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
    st.markdown(
        f"""
        <div class="mob-hero">
            <div>
                <h1>Dashboard Comercial</h1>
                <div class="mob-hero-sub">Mobílli Rentals — {html.escape(mes_curto(mes - timedelta(days=1)))} vs {html.escape(mes_curto(mes))} · Serra/ES</div>
            </div>
            <div class="mob-hero-meta">
                <b>{html.escape(mes_ano_label(mes))}</b><br/>
                Atualizado {atualizado_em.strftime('%d/%m %H:%M')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _highlights(cmp_: CaptacoesComparadas, hoje: date) -> None:
    """3 destaques no topo: anterior · atual · projeção. Empresa-wide."""
    total_ant = _total_emp(cmp_.anterior)
    total_atual = _total_emp(cmp_.atual)
    pct_proj = variacao_pct(cmp_.projecao_total, total_ant)

    mes_ant = cmp_.anterior.mes
    mes_at = cmp_.atual.mes

    fim_at = (mes_at.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    # "Em curso" inclui o último dia do mês (hoje ainda pode entrar deals)
    mes_em_curso = (
        hoje <= fim_at and hoje.year == mes_at.year and hoje.month == mes_at.month
    )

    sub_ant = "mês fechado"
    sub_atual = (
        f"parcial até {hoje.day:02d}/{mes_at.month:02d}"
        if mes_em_curso
        else "mês fechado" if hoje > fim_at else "ainda não iniciado"
    )
    sub_proj = (
        f"estimativa de fechamento — {cmp_.du_decorridos_atual:.1f}/{cmp_.du_mes_atual:.0f} dias úteis decorridos"
        if mes_em_curso
        else "mês já fechado — sem projeção"
    )

    st.markdown(
        f"""
        <div class="mob-hl-row">
            <div class="mob-hl">
                <div class="mob-hl-lbl">{html.escape(mes_curto(mes_ant))}</div>
                <div class="mob-hl-val">{total_ant}</div>
                <div class="mob-hl-sub">{html.escape(sub_ant)}</div>
            </div>
            <div class="mob-hl parcial">
                <div class="mob-hl-lbl">{html.escape(mes_curto(mes_at))}</div>
                <div class="mob-hl-val">{total_atual}</div>
                <div class="mob-hl-sub">{html.escape(sub_atual)}</div>
            </div>
            <div class="mob-hl proj">
                <div class="mob-hl-lbl">Projeção fim de {html.escape(mes_curto(mes_at))}</div>
                <div class="mob-hl-val">~{cmp_.projecao_total} {_delta_badge(pct_proj)}</div>
                <div class="mob-hl-sub">{html.escape(sub_proj)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── META + NÍVEL ──────────────────────────────────────────────────────
_NIVEL_VISUAL: dict[str, tuple[str, str]] = {
    "Bronze": ("🥉", "bronze"),
    "Prata": ("🥈", "prata"),
    "Ouro": ("🥇", "ouro"),
    "Sem Meta": ("🎯", "bronze"),
}


def _classificar_nivel(atingido: int, meta: int) -> str:
    """TM-018: Bronze < 100% · Prata ≥ 100% · Ouro ≥ 125%."""
    if meta <= 0:
        return "Sem Meta"
    pct = atingido / meta * 100
    if pct >= 125:
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
    largura = min(pct_atual, 130)  # cap visual em 130% pra não estourar a barra

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
        f'<span>Ouro · 125% ({int(meta * 1.25)})</span>'
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
def _bar_comparativa(label: str, valores: dict[str, int], max_val: int) -> str:
    """Renderiza HTML de uma linha tipo 'Locação' com 3 barras Mar/Abr/Proj."""
    rows = ""
    cls_map = {"prev": "prev", "curr": "curr", "proj": "proj"}
    for nome, valor in valores.items():
        pct = (valor / max_val * 100) if max_val > 0 else 0
        cls = cls_map.get(nome, "curr")
        rows += f"""
        <div class="mob-cmp-mini">
            <span>{html.escape(nome.upper())}</span>
            <span><b>{valor}</b></span>
        </div>
        <div class="mob-cmp-bar">
            <div class="mob-cmp-fill {cls}" style="width:{pct:.1f}%"></div>
        </div>
        """
    return f"""
    <div class="mob-cmp-row">
        <div class="mob-cmp-head">
            <span class="mob-cmp-label">{html.escape(label)}</span>
        </div>
        {rows}
    </div>
    """


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
        st.markdown(
            f"""
            <div class="mob-kpi">
                <div class="mob-kpi-label">Locações {html.escape(nome_ant)} → {html.escape(nome_at)}</div>
                <div class="mob-kpi-value">{loc_atual} {_delta_badge(pct_loc)}</div>
                <div class="mob-kpi-help">{loc_ant} em {html.escape(nome_ant)} (cheio)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div class="mob-kpi accent-dark">
                <div class="mob-kpi-label">Vendas {html.escape(nome_ant)} → {html.escape(nome_at)}</div>
                <div class="mob-kpi-value">{vnd_atual} {_delta_badge(pct_vnd)}</div>
                <div class="mob-kpi-help">{vnd_ant} em {html.escape(nome_ant)} (cheio)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("&nbsp;")
    st.markdown('<div class="mob-section-title">Comparativo geral (Locação · Venda)</div>',
                unsafe_allow_html=True)

    max_loc = max(loc_ant, loc_atual, cmp_.projecao_locacoes, 1)
    max_vnd = max(vnd_ant, vnd_atual, cmp_.projecao_vendas, 1)

    col_l, col_v = st.columns(2)
    with col_l:
        st.markdown(
            _bar_comparativa(
                "Locação",
                {nome_ant: loc_ant, nome_at: loc_atual, "Projeção": cmp_.projecao_locacoes},
                max_loc,
            ),
            unsafe_allow_html=True,
        )
    with col_v:
        st.markdown(
            _bar_comparativa(
                "Venda",
                {nome_ant: vnd_ant, nome_at: vnd_atual, "Projeção": cmp_.projecao_vendas},
                max_vnd,
            ),
            unsafe_allow_html=True,
        )

    # Tabela resumo
    st.markdown("&nbsp;")
    st.markdown('<div class="mob-section-title">Tabela resumo</div>', unsafe_allow_html=True)

    total_ant = loc_ant + vnd_ant
    total_atual = loc_atual + vnd_atual
    pct_total = variacao_pct(total_atual, total_ant)

    rows = [
        ("Locação", loc_ant, loc_atual, cmp_.projecao_locacoes, pct_loc),
        ("Venda", vnd_ant, vnd_atual, cmp_.projecao_vendas, pct_vnd),
    ]

    html_rows = ""
    for nome, ant, at, proj, pct in rows:
        html_rows += f"""
        <tr>
            <td>{html.escape(nome)}</td>
            <td class="num">{ant}</td>
            <td class="num">{at}</td>
            <td class="num">~{proj}</td>
            <td class="num">{_delta_badge(pct)}</td>
        </tr>
        """
    html_rows += f"""
    <tr class="total">
        <td>TOTAL</td>
        <td class="num">{total_ant}</td>
        <td class="num">{total_atual}</td>
        <td class="num">~{cmp_.projecao_total}</td>
        <td class="num">{_delta_badge(pct_total)}</td>
    </tr>
    """

    st.markdown(
        f"""
        <table class="mob-tab">
            <thead>
                <tr>
                    <th>Modalidade</th>
                    <th class="num">{html.escape(nome_ant)}</th>
                    <th class="num">{html.escape(nome_at)} parcial</th>
                    <th class="num">Projeção</th>
                    <th class="num">Var.</th>
                </tr>
            </thead>
            <tbody>{html_rows}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
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


def _tab_evolucao(cmp_: CaptacoesComparadas) -> None:
    nome_ant = mes_curto(cmp_.anterior.mes)
    nome_at = mes_curto(cmp_.atual.mes)

    acum_ant = _acumulado_diario(cmp_.anterior)
    acum_at = _acumulado_diario(cmp_.atual)

    # Pontos só para dias ímpares (1, 3, 5… 29) — alinhado ao dashboard ref
    dias = list(range(1, 30, 2))
    df = pd.DataFrame([
        {"Dia": d, "Mês": nome_ant, "Captações": acum_ant.get(d, 0)} for d in dias
    ] + [
        {"Dia": d, "Mês": nome_at, "Captações": acum_at.get(d, 0)} for d in dias
    ])

    st.markdown('<div class="mob-section-title">Acumulado dia a dia</div>',
                unsafe_allow_html=True)

    chart = (
        alt.Chart(df)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=80), strokeWidth=3)
        .encode(
            x=alt.X("Dia:O", title="Dia",
                    axis=alt.Axis(labelFontSize=11, domain=False, ticks=False)),
            y=alt.Y("Captações:Q", title=None,
                    axis=alt.Axis(grid=True, gridColor="#eef0f3", domain=False, tickColor="#eef0f3")),
            color=alt.Color(
                "Mês:N",
                scale=alt.Scale(
                    domain=[nome_ant, nome_at],
                    range=["#9ca3af", "#FF6600"],
                ),
                legend=alt.Legend(orient="top", title=None, labelFontSize=12),
            ),
            tooltip=["Mês", "Dia", "Captações"],
        )
        .properties(height=320)
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor="#6b7280", titleColor="#6b7280")
        .configure_legend(labelColor="#1a1a1a", titleColor="#1a1a1a")
    )
    st.altair_chart(chart, use_container_width=True)

    # Por semana
    st.markdown("&nbsp;")
    st.markdown('<div class="mob-section-title">Por semana</div>',
                unsafe_allow_html=True)

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
            x=alt.X("Semana:N", title=None, axis=alt.Axis(labelAngle=0, domain=False)),
            xOffset="Mês:N",
            y=alt.Y("Captações:Q", title=None, axis=alt.Axis(grid=True, gridColor="#eef0f3", domain=False)),
            color=alt.Color(
                "Mês:N",
                scale=alt.Scale(domain=[nome_ant, nome_at], range=["#9ca3af", "#FF6600"]),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=["Semana", "Mês", "Captações"],
        )
        .properties(height=240)
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor="#6b7280")
    )
    st.altair_chart(chart_sem, use_container_width=True)


# ─── ABA: CONSULTORES ──────────────────────────────────────────────────
def _card_consultor(
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
    elif eh_lider:
        nome_curto = " ".join(v_at.nome.split()[:2])
        role = "Líder"
    else:
        nome_curto = " ".join(v_at.nome.split()[:2])
        role = "Vendedor"

    st.markdown(
        f"""
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
                    <div class="mob-vend-stat-num" style="color:#9ca3af;">{v_ant.total}</div>
                    <div class="mob-vend-stat-lbl">{html.escape(label_ant)}</div>
                </div>
                <div class="mob-vend-stat">
                    <div class="mob-vend-stat-num">{v_at.total}</div>
                    <div class="mob-vend-stat-lbl">{html.escape(label_at)}</div>
                </div>
            </div>
            <div style="margin-top:2px;">{_delta_badge(pct)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _tab_consultores(cmp_: CaptacoesComparadas) -> None:
    nome_ant = mes_curto(cmp_.anterior.mes)
    nome_at = mes_curto(cmp_.atual.mes)

    ant_by_id = {v.vendedor_id: v for v in cmp_.anterior.por_vendedor}
    ord_atual = [v for v in cmp_.atual.por_vendedor if v.total > 0]
    ord_atual.sort(key=lambda v: v.total, reverse=True)

    # Cards: top N (rest goes to table). Grid 4 cols, máx 8 cards.
    TOP_N = 8
    cards = ord_atual[:TOP_N]
    n_desconhecidos = sum(1 for v in cards if _eh_nome_desconhecido(v.nome))

    if cards:
        # 4 cards por linha
        for i in range(0, len(cards), 4):
            sub_cols = st.columns(4)
            for col, v in zip(sub_cols, cards[i:i + 4]):
                v_ant = ant_by_id.get(v.vendedor_id, CaptacoesVendedor(v.vendedor_id, v.nome))
                with col:
                    _card_consultor(v, v_ant, label_ant=nome_ant, label_at=nome_at)
        # Preenche colunas vazias da última linha pra manter grid
        resto = (len(cards) % 4)
        if resto:
            for _ in range(4 - resto):
                pass  # streamlit ignora cols vazias

    if len(ord_atual) > TOP_N:
        st.caption(f"Exibindo top {TOP_N} consultores. Restante na tabela abaixo.")

    if n_desconhecidos:
        st.caption(
            f"{n_desconhecidos} consultor(es) sem nome cadastrado — "
            "edite `src/auth/vendedores.py` para mapear o ID."
        )

    st.markdown("&nbsp;")

    # Barras horizontais por consultor — 2 séries (anterior vs atual). Limita ao top N.
    st.markdown(
        f'<div class="mob-section-title">Top {min(TOP_N, len(ord_atual))} consultores — {html.escape(nome_ant)} × {html.escape(nome_at)}</div>',
        unsafe_allow_html=True,
    )

    chart_set = ord_atual[:TOP_N]
    rows = []
    for v in chart_set:
        v_ant = ant_by_id.get(v.vendedor_id, CaptacoesVendedor(v.vendedor_id, v.nome))
        rows.append({"Consultor": _primeiro_nome(v.nome), "Mês": nome_ant, "Captações": v_ant.total})
        rows.append({"Consultor": _primeiro_nome(v.nome), "Mês": nome_at, "Captações": v.total})
    df = pd.DataFrame(rows)

    if not df.empty and df["Captações"].sum() > 0:
        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadiusEnd=3, height=14)
            .encode(
                y=alt.Y("Consultor:N", title=None, sort="-x",
                        axis=alt.Axis(labelFontSize=12, domain=False, ticks=False)),
                yOffset="Mês:N",
                x=alt.X("Captações:Q", title=None,
                        axis=alt.Axis(grid=True, gridColor="#eef0f3", domain=False)),
                color=alt.Color(
                    "Mês:N",
                    scale=alt.Scale(domain=[nome_ant, nome_at], range=["#9ca3af", "#FF6600"]),
                    legend=alt.Legend(orient="top", title=None, labelFontSize=12),
                ),
                tooltip=["Consultor", "Mês", "Captações"],
            )
            .properties(height=max(200, 50 * len(chart_set)))
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor="#6b7280")
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Sem captações no período para comparar.")

    # Tabela completa: Consultor · Ant · Atual · Var. · Loc. · Vnd.
    st.markdown("&nbsp;")
    st.markdown('<div class="mob-section-title">Detalhamento</div>', unsafe_allow_html=True)

    html_rows = ""
    for v in ord_atual:
        v_ant = ant_by_id.get(v.vendedor_id, CaptacoesVendedor(v.vendedor_id, v.nome))
        loc_v = sum(1 for i in v.itens if i.tipo_operacao == "Locação")
        vnd_v = v.total - loc_v
        pct_v = variacao_pct(v.total, v_ant.total)
        html_rows += f"""
        <tr>
            <td>{html.escape(v.nome)}</td>
            <td class="num">{v_ant.total}</td>
            <td class="num">{v.total}</td>
            <td class="num">{_delta_badge(pct_v)}</td>
            <td class="num">{loc_v}</td>
            <td class="num">{vnd_v}</td>
        </tr>
        """

    st.markdown(
        f"""
        <table class="mob-tab">
            <thead>
                <tr>
                    <th>Consultor</th>
                    <th class="num">{html.escape(nome_ant)}</th>
                    <th class="num">{html.escape(nome_at)}</th>
                    <th class="num">Var.</th>
                    <th class="num">Loc.</th>
                    <th class="num">Vnd.</th>
                </tr>
            </thead>
            <tbody>{html_rows}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
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
        st.markdown(
            f"""
            <div class="mob-kpi accent-dark">
                <div class="mob-kpi-label">Dias úteis</div>
                <div class="mob-kpi-value">{cmp_.du_decorridos_atual:.1f} <span style="font-size:18px;color:#9ca3af;">/ {cmp_.du_mes_atual:.0f}</span></div>
                <div class="mob-kpi-help">{html.escape(nome_at)} (decorridos/total)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div class="mob-kpi">
                <div class="mob-kpi-label">Produtividade {html.escape(nome_ant)}</div>
                <div class="mob-kpi-value">{prod_ant:.1f}</div>
                <div class="mob-kpi-help">negócios por dia útil</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f"""
            <div class="mob-kpi">
                <div class="mob-kpi-label">Produtividade {html.escape(nome_at)}</div>
                <div class="mob-kpi-value">{prod_at:.1f} {_delta_badge(pct_prod)}</div>
                <div class="mob-kpi-help">negócios por dia útil</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("&nbsp;")
    st.markdown('<div class="mob-section-title">Produtividade por consultor</div>',
                unsafe_allow_html=True)

    ant_by_id = {v.vendedor_id: v for v in cmp_.anterior.por_vendedor}
    ord_atual = [v for v in cmp_.atual.por_vendedor if v.total > 0]
    ord_atual.sort(key=lambda v: v.total, reverse=True)

    html_rows = ""
    for v in ord_atual:
        v_ant = ant_by_id.get(v.vendedor_id, CaptacoesVendedor(v.vendedor_id, v.nome))
        loc_v = sum(1 for i in v.itens if i.tipo_operacao == "Locação")
        vnd_v = v.total - loc_v
        prod_v = v.total / cmp_.du_decorridos_atual if cmp_.du_decorridos_atual else 0
        prod_v_ant = v_ant.total / cmp_.du_mes_anterior if cmp_.du_mes_anterior else 0
        html_rows += f"""
        <tr>
            <td>{html.escape(v.nome)}</td>
            <td class="num">{v.total}</td>
            <td class="num">{prod_v:.1f}</td>
            <td class="num" style="color:#9ca3af;">{prod_v_ant:.1f}</td>
            <td class="num">{loc_v}</td>
            <td class="num">{vnd_v}</td>
        </tr>
        """

    st.markdown(
        f"""
        <table class="mob-tab">
            <thead>
                <tr>
                    <th>Consultor</th>
                    <th class="num">Total {html.escape(nome_at)}</th>
                    <th class="num">Neg./du {html.escape(nome_at)}</th>
                    <th class="num">Neg./du {html.escape(nome_ant)}</th>
                    <th class="num">Loc.</th>
                    <th class="num">Vnd.</th>
                </tr>
            </thead>
            <tbody>{html_rows}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )


# ─── render principal ──────────────────────────────────────────────────
def render() -> None:
    st.sidebar.markdown("## Dashboard")

    opcoes = opcoes_de_mes(ate_mes_seguinte=False, desde=PRIMEIRO_MES_CAPTACAO)
    if not opcoes:
        st.error("Nenhum mês disponível.")
        return

    mes = st.sidebar.selectbox(
        "Mês de captação",
        opcoes,
        index=0,
        format_func=mes_ano_label,
        help="Filtra deals fechados nesse mês calendário (data de locação).",
    )

    meta = st.sidebar.number_input(
        "Meta do time (qtd captações)",
        min_value=0,
        value=124,
        step=1,
        help="Meta mensal de captações do time. Padrão: 124. Bronze < 100% · Prata ≥ 100% · Ouro ≥ 125%.",
    )

    if st.sidebar.button("Atualizar dados", use_container_width=True):
        limpar_cache()
        st.rerun()

    st.sidebar.caption("Atualização automática a cada 5 min")

    # ── carrega dados ──────────────────────────────────────────────
    # Inclui ativos + líderes — o restante dos consultores é auto-descoberto.
    todos_conhecidos = {**VENDEDORES, **LIDERES}
    vendedores_key = tuple(sorted(todos_conhecidos.items()))
    hoje = date.today()
    try:
        with st.spinner("Carregando dados de vendas..."):
            cmp_ = captacoes_comparadas_cacheadas(
                mes_atual=mes,
                vendedores_key=vendedores_key,
                hoje=hoje,
            )
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

    _hero(mes, datetime.now())
    _highlights(cmp_, hoje)
    _meta_progresso(cmp_, meta, hoje)

    tab_resumo, tab_evol, tab_cons, tab_prod = st.tabs(
        ["Resumo", "Evolução", "Consultores", "Produtividade"]
    )

    with tab_resumo:
        _tab_resumo(cmp_)
    with tab_evol:
        _tab_evolucao(cmp_)
    with tab_cons:
        _tab_consultores(cmp_)
    with tab_prod:
        _tab_produtividade(cmp_)
