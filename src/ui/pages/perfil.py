"""Página: Perfil do Cliente — análise demográfica e contratual.

Responde 3 perguntas-chave do time comercial:
- De onde vêm meus leads? (origem)
- Onde estão meus clientes? (geografia)
- Que produto eles assinam? (plano + tipo de operação)

Filtra por tipo de operação (Locação/Venda/Tudo) e usa toda a série
histórica disponível (Mar/2026 em diante) cacheada.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime

import altair as alt
import pandas as pd
import streamlit as st

from src.auth import todos_nomes_conhecidos
from src.data.bitrix import label_source
from src.models import CaptacaoItem, CaptacoesMes
from src.ui.data import serie_historica_cacheada
from src.ui.shared import PRIMEIRO_MES_CAPTACAO, mes_ano_label, mes_curto


def _md(html_str: str) -> None:
    cleaned = "\n".join(line.lstrip() for line in html_str.splitlines() if line.strip())
    st.markdown(cleaned, unsafe_allow_html=True)


def _flatten(serie: list[CaptacoesMes]) -> list[CaptacaoItem]:
    """Junta captações de todos os meses da série numa lista única.

    Usa `getattr` com default `[]` pra resistir a snapshots antigos vindos
    de cache do Streamlit Cloud (cache_data persiste pickle entre deploys
    e instâncias antigas não têm o campo `captacoes_flat`).
    """
    out: list[CaptacaoItem] = []
    for snap in serie:
        out.extend(getattr(snap, "captacoes_flat", []))
    return out


def _filtrar_por_tipo(itens: list[CaptacaoItem], tipo: str) -> list[CaptacaoItem]:
    """tipo ∈ {'Tudo', 'Locação', 'Venda'}. Venda casa 'Venda 0km' e variações."""
    if tipo == "Tudo":
        return itens
    if tipo == "Locação":
        return [i for i in itens if i.tipo_operacao == "Locação"]
    return [i for i in itens if i.tipo_operacao.startswith("Venda")]


# ─── HEADER ─────────────────────────────────────────────────────────────
def _hero(periodo_label: str, atualizado_em: datetime, total: int) -> None:
    _md(f"""
        <div class="mob-hero">
            <div>
                <h1>Perfil do Cliente</h1>
                <div class="mob-hero-sub">Mobílli Rentals — análise de origem, geografia e plano · {periodo_label}</div>
            </div>
            <div class="mob-hero-meta">
                <b>{total} captações</b><br/>
                Atualizado {atualizado_em.strftime('%d/%m %H:%M')}
            </div>
        </div>
    """)


def _kpis_topo(itens: list[CaptacaoItem]) -> None:
    """3 KPIs: total · cidade líder · origem líder."""
    total = len(itens)

    cidades = Counter(i.cidade for i in itens if i.cidade)
    cidade_top, cidade_n = cidades.most_common(1)[0] if cidades else ("—", 0)
    pct_cidade = (cidade_n / total * 100) if total else 0

    fontes = Counter(i.source_id for i in itens)
    fonte_top_id, fonte_n = fontes.most_common(1)[0] if fontes else ("", 0)
    fonte_top = label_source(fonte_top_id)
    pct_fonte = (fonte_n / total * 100) if total else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        _md(f"""
            <div class="mob-kpi">
                <div class="mob-kpi-label">Captações no período</div>
                <div class="mob-kpi-value">{total}</div>
                <div class="mob-kpi-help">total filtrado</div>
            </div>
        """)
    with col2:
        _md(f"""
            <div class="mob-kpi accent-dark">
                <div class="mob-kpi-label">Cidade líder</div>
                <div class="mob-kpi-value">{cidade_top}</div>
                <div class="mob-kpi-help">{cidade_n} captações ({pct_cidade:.0f}%)</div>
            </div>
        """)
    with col3:
        _md(f"""
            <div class="mob-kpi">
                <div class="mob-kpi-label">Origem líder</div>
                <div class="mob-kpi-value">{fonte_top}</div>
                <div class="mob-kpi-help">{fonte_n} captações ({pct_fonte:.0f}%)</div>
            </div>
        """)


# ─── ABA: ORIGEM ────────────────────────────────────────────────────────
def _tab_origem(itens: list[CaptacaoItem]) -> None:
    """Ranking de origens (SOURCE_ID) com breakdown por tipo de operação."""
    if not itens:
        st.info("Sem captações no período.")
        return

    # Agrupar por origem (label legível) + tipo
    rows = []
    for i in itens:
        rows.append({
            "Origem": label_source(i.source_id),
            "Tipo": "Locação" if i.tipo_operacao == "Locação" else "Venda",
            "Captações": 1,
        })
    df = pd.DataFrame(rows).groupby(["Origem", "Tipo"], as_index=False).sum()

    # Total por origem para ordenar
    totais = df.groupby("Origem", as_index=False)["Captações"].sum()
    totais = totais.sort_values("Captações", ascending=False)
    ordem = totais["Origem"].tolist()
    total_geral = totais["Captações"].sum()

    _md('<div class="mob-section-title">Ranking de origens</div>')

    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=3, height=18)
        .encode(
            y=alt.Y("Origem:N", title=None, sort=ordem,
                    axis=alt.Axis(labelFontSize=12, domain=False, ticks=False, labelColor="#1a1a1a")),
            x=alt.X("Captações:Q", title=None, stack="zero",
                    axis=alt.Axis(grid=True, gridColor="#eef0f3", domain=False, labelColor="#1a1a1a")),
            color=alt.Color(
                "Tipo:N",
                scale=alt.Scale(domain=["Locação", "Venda"], range=["#FF6600", "#1a1a1a"]),
                legend=alt.Legend(orient="top", title=None, labelFontSize=13, labelColor="#1a1a1a"),
            ),
            tooltip=["Origem", "Tipo", "Captações"],
        )
        .properties(height=max(220, 35 * len(ordem)), background="#ffffff")
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor="#1a1a1a", titleColor="#1a1a1a")
        .configure_legend(labelColor="#1a1a1a", labelFontSize=13)
    )
    st.altair_chart(chart, use_container_width=True)

    # Tabela detalhada
    st.markdown("&nbsp;")
    _md('<div class="mob-section-title">Detalhamento</div>')

    rows_tab = []
    for origem in ordem:
        n = int(totais[totais["Origem"] == origem]["Captações"].iloc[0])
        loc = int(df[(df["Origem"] == origem) & (df["Tipo"] == "Locação")]["Captações"].sum())
        vnd = int(df[(df["Origem"] == origem) & (df["Tipo"] == "Venda")]["Captações"].sum())
        pct = n / total_geral * 100 if total_geral else 0
        rows_tab.append((origem, n, loc, vnd, pct))

    body = "".join(
        f'<tr><td>{origem}</td>'
        f'<td class="num">{n}</td>'
        f'<td class="num">{loc}</td>'
        f'<td class="num">{vnd}</td>'
        f'<td class="num">{pct:.1f}%</td>'
        f'</tr>'
        for origem, n, loc, vnd, pct in rows_tab
    )
    _md(
        '<table class="mob-tab">'
        '<thead><tr>'
        '<th>Origem</th>'
        '<th class="num">Total</th>'
        '<th class="num">Locação</th>'
        '<th class="num">Venda</th>'
        '<th class="num">% do total</th>'
        '</tr></thead>'
        f'<tbody>{body}</tbody>'
        '</table>'
    )


# ─── ABA: GEOGRAFIA ─────────────────────────────────────────────────────
def _tab_geografia(itens: list[CaptacaoItem]) -> None:
    """Top cidades — barras horizontais com breakdown loc/vnd."""
    com_cidade = [i for i in itens if i.cidade]
    sem_cidade = len(itens) - len(com_cidade)

    if not com_cidade:
        st.info("Nenhuma cidade preenchida nos deals do período.")
        return

    rows = []
    for i in com_cidade:
        rows.append({
            "Cidade": i.cidade,
            "Tipo": "Locação" if i.tipo_operacao == "Locação" else "Venda",
            "Captações": 1,
        })
    df = pd.DataFrame(rows).groupby(["Cidade", "Tipo"], as_index=False).sum()

    totais = df.groupby("Cidade", as_index=False)["Captações"].sum()
    totais = totais.sort_values("Captações", ascending=False).head(15)
    ordem = totais["Cidade"].tolist()
    df_top = df[df["Cidade"].isin(ordem)]
    total_top = totais["Captações"].sum()

    _md('<div class="mob-section-title">Top 15 cidades</div>')

    chart = (
        alt.Chart(df_top)
        .mark_bar(cornerRadiusEnd=3, height=18)
        .encode(
            y=alt.Y("Cidade:N", title=None, sort=ordem,
                    axis=alt.Axis(labelFontSize=12, domain=False, ticks=False, labelColor="#1a1a1a")),
            x=alt.X("Captações:Q", title=None, stack="zero",
                    axis=alt.Axis(grid=True, gridColor="#eef0f3", domain=False, labelColor="#1a1a1a")),
            color=alt.Color(
                "Tipo:N",
                scale=alt.Scale(domain=["Locação", "Venda"], range=["#FF6600", "#1a1a1a"]),
                legend=alt.Legend(orient="top", title=None, labelFontSize=13, labelColor="#1a1a1a"),
            ),
            tooltip=["Cidade", "Tipo", "Captações"],
        )
        .properties(height=max(280, 32 * len(ordem)), background="#ffffff")
        .configure_view(strokeWidth=0)
        .configure_axis(labelColor="#1a1a1a", titleColor="#1a1a1a")
        .configure_legend(labelColor="#1a1a1a", labelFontSize=13)
    )
    st.altair_chart(chart, use_container_width=True)

    st.caption(
        f"Top 15 = {total_top} captações de {len(com_cidade)} com cidade preenchida. "
        f"{sem_cidade} sem cidade no cadastro."
    )


# ─── ABA: PLANO & TIPO ──────────────────────────────────────────────────
def _tab_plano(itens: list[CaptacaoItem]) -> None:
    """Mix de plano (semanal × mensal — só locação) + tipo de operação."""
    locacoes = [i for i in itens if i.tipo_operacao == "Locação"]
    vendas = [i for i in itens if i.tipo_operacao.startswith("Venda")]
    n_loc = len(locacoes)
    n_vnd = len(vendas)
    total = len(itens)

    col_op, col_plano = st.columns(2)

    # Tipo de operação (donut)
    with col_op:
        _md('<div class="mob-section-title">Tipo de operação</div>')
        if total == 0:
            st.info("Sem captações.")
        else:
            df_op = pd.DataFrame([
                {"Tipo": "Locação", "Captações": n_loc},
                {"Tipo": "Venda", "Captações": n_vnd},
            ])
            chart_op = (
                alt.Chart(df_op)
                .mark_arc(innerRadius=70, stroke="#ffffff", strokeWidth=3)
                .encode(
                    theta="Captações:Q",
                    color=alt.Color(
                        "Tipo:N",
                        scale=alt.Scale(domain=["Locação", "Venda"], range=["#FF6600", "#1a1a1a"]),
                        legend=alt.Legend(orient="bottom", title=None, labelFontSize=13, labelColor="#1a1a1a"),
                    ),
                    tooltip=["Tipo", "Captações"],
                )
                .properties(height=280, background="#ffffff")
                .configure_view(strokeWidth=0)
                .configure_legend(labelColor="#1a1a1a", labelFontSize=13)
            )
            st.altair_chart(chart_op, use_container_width=True)
            pct_loc = n_loc / total * 100
            st.caption(
                f"**{n_loc}** locações ({pct_loc:.0f}%) · **{n_vnd}** vendas ({100 - pct_loc:.0f}%)"
            )

    # Plano semanal × mensal (só locação)
    with col_plano:
        _md('<div class="mob-section-title">Plano (locação)</div>')
        if n_loc == 0:
            st.info("Sem locações no período.")
        else:
            n_sem = sum(1 for i in locacoes if i.plano_semanal)
            n_men = n_loc - n_sem
            df_plano = pd.DataFrame([
                {"Plano": "Semanal", "Captações": n_sem},
                {"Plano": "Mensal", "Captações": n_men},
            ])
            chart_plano = (
                alt.Chart(df_plano)
                .mark_arc(innerRadius=70, stroke="#ffffff", strokeWidth=3)
                .encode(
                    theta="Captações:Q",
                    color=alt.Color(
                        "Plano:N",
                        scale=alt.Scale(domain=["Semanal", "Mensal"], range=["#FF6600", "#6b7280"]),
                        legend=alt.Legend(orient="bottom", title=None, labelFontSize=13, labelColor="#1a1a1a"),
                    ),
                    tooltip=["Plano", "Captações"],
                )
                .properties(height=280, background="#ffffff")
                .configure_view(strokeWidth=0)
                .configure_legend(labelColor="#1a1a1a", labelFontSize=13)
            )
            st.altair_chart(chart_plano, use_container_width=True)
            pct_sem = n_sem / n_loc * 100
            st.caption(
                f"**{n_sem}** semanais ({pct_sem:.0f}%) · **{n_men}** mensais ({100 - pct_sem:.0f}%)"
            )


# ─── render principal ──────────────────────────────────────────────────
def render() -> None:
    st.sidebar.markdown("## Perfil do Cliente")

    tipo = st.sidebar.selectbox(
        "Tipo de operação",
        options=["Tudo", "Locação", "Venda"],
        index=0,
    )

    st.sidebar.caption("Atualização automática a cada 30 min")

    todos_conhecidos = todos_nomes_conhecidos()
    vendedores_key = tuple(sorted(todos_conhecidos.items()))

    hoje = date.today()
    mes_topo = hoje.replace(day=1)

    try:
        with st.spinner("Carregando perfil dos clientes..."):
            serie = serie_historica_cacheada(
                mes_floor=PRIMEIRO_MES_CAPTACAO,
                mes_topo=mes_topo,
                vendedores_key=vendedores_key,
            )
    except Exception as exc:  # noqa: BLE001
        st.error(
            "**Não consegui carregar os dados do CRM agora.**  \n"
            f"Causa: `{type(exc).__name__}: {exc}`"
        )
        st.stop()

    todas = _flatten(serie)
    filtradas = _filtrar_por_tipo(todas, tipo)

    if serie:
        periodo_label = (
            f"{mes_curto(serie[0].mes)} → {mes_curto(serie[-1].mes)}"
            if len(serie) > 1
            else mes_ano_label(serie[0].mes)
        )
    else:
        periodo_label = "—"

    _hero(periodo_label, datetime.now(), len(filtradas))
    _kpis_topo(filtradas)
    st.markdown("&nbsp;")

    tab_origem, tab_geo, tab_plano = st.tabs(["Origem", "Geografia", "Plano & Tipo"])
    with tab_origem:
        _tab_origem(filtradas)
    with tab_geo:
        _tab_geografia(filtradas)
    with tab_plano:
        _tab_plano(filtradas)
