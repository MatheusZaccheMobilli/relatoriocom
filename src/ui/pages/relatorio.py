"""Página: Relatório de Comissão — apuração + ficha de assinatura."""

from __future__ import annotations

import html

import streamlit as st

from src.auth import VENDEDORES
from src.export.pdf import gerar_pdf
from src.export.xlsx import gerar_xlsx
from src.ui.data import relatorio_cacheado
from src.ui.shared import (
    formatar_brl,
    formatar_data,
    mes_ano_label,
    opcoes_de_mes,
)


_NIVEL_VISUAL: dict[str, tuple[str, str]] = {
    "Ouro": ("🥇", "ouro"),
    "Prata": ("🥈", "prata"),
    "Bronze": ("🥉", "bronze"),
    "Sem Meta": ("🎯", "bronze"),
}


def _kpi(label: str, value: str, help_: str = "", accent: bool = False) -> str:
    cls = "mob-kpi accent-dark" if accent else "mob-kpi"
    help_html = f'<div class="mob-kpi-help">{html.escape(help_)}</div>' if help_ else ""
    return f"""
    <div class="{cls}">
        <div class="mob-kpi-label">{html.escape(label)}</div>
        <div class="mob-kpi-value">{value}</div>
        {help_html}
    </div>
    """


def _nivel_card(nome_nivel: str, pct: float, qtd_atingida: int, qtd_meta: int) -> str:
    emoji, cls = _NIVEL_VISUAL.get(nome_nivel, _NIVEL_VISUAL["Bronze"])
    pct_str = f"{pct:.0f}% da meta" if qtd_meta > 0 else "sem meta definida"
    return f"""
    <div class="mob-nivel-badge {cls}" style="height:100%;">
        <div class="mob-nivel-emoji">{emoji}</div>
        <div class="mob-nivel-name">{html.escape(nome_nivel)}</div>
        <div class="mob-nivel-pct">{html.escape(pct_str)} · {qtd_atingida}/{qtd_meta}</div>
    </div>
    """


def _tabela_itens(itens: list, total_comissao) -> None:
    """Tabela HTML responsiva com Status sempre visível."""
    if not itens:
        st.warning("Nenhum item de comissão encontrado para este período.")
        return

    rows_html = ""
    for item in itens:
        if item.tipo_operacao == "Locação":
            plano = "Semanal" if item.plano_semanal else "Mensal"
            parcelas = str(item.qtd_parcelas_pagas)
        else:
            plano = "—"
            parcelas = "—"

        status_cls = "dn" if item.devolvido else "up"
        status_txt = "DEVOLVIDO" if item.devolvido else "Ativo"
        row_cls = "row-devolvido" if item.devolvido else ""

        rows_html += f"""
        <tr class="{row_cls}">
            <td>{html.escape(item.tipo_operacao)}</td>
            <td class="num">{html.escape(item.parcela)}</td>
            <td>{html.escape(plano)}</td>
            <td>{html.escape(item.nome_cliente)}</td>
            <td>{html.escape(item.placa or '—')}</td>
            <td>{formatar_data(item.data_locacao)}</td>
            <td>{formatar_data(item.data_devolucao)}</td>
            <td class="num">{formatar_brl(item.valor_base)}</td>
            <td class="num">{parcelas}</td>
            <td class="num"><b>{formatar_brl(item.valor_comissao)}</b></td>
            <td><span class="mob-delta {status_cls}" style="margin-left:0;">{status_txt}</span></td>
        </tr>
        """

    st.markdown(
        f"""
        <div style="overflow-x:auto;">
        <table class="mob-tab mob-tab-itens">
            <thead>
                <tr>
                    <th>Tipo</th>
                    <th class="num">Parc.</th>
                    <th>Plano</th>
                    <th>Cliente</th>
                    <th>Placa</th>
                    <th>Locação</th>
                    <th>Devolução</th>
                    <th class="num">Valor base</th>
                    <th class="num">Pgs.</th>
                    <th class="num">Comissão</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
            <tfoot>
                <tr class="total">
                    <td colspan="9">TOTAL A RECEBER</td>
                    <td class="num">{formatar_brl(total_comissao)}</td>
                    <td></td>
                </tr>
            </tfoot>
        </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render() -> None:
    # ── Sidebar ─────────────────────────────────────────────────────
    st.sidebar.title("Filtros")

    mes_pagamento = st.sidebar.selectbox(
        "Mês de pagamento",
        opcoes_de_mes(ate_mes_seguinte=True),
        index=None,
        placeholder="Selecione o mês...",
        format_func=mes_ano_label,
    )

    vendedor_nome = st.sidebar.selectbox(
        "Vendedor",
        list(VENDEDORES.values()),
        index=None,
        placeholder="Selecione o vendedor...",
    )

    qtd_meta = st.sidebar.number_input(
        "Meta mensal do vendedor (qtd captações)",
        min_value=0,
        value=35,
        step=1,
        help="Bronze < 100% · Prata ≥ 100% · Ouro ≥ 125%",
    )

    gerar = st.sidebar.button(
        "Gerar Relatório", type="primary", use_container_width=True
    )

    # ── Header da página ────────────────────────────────────────────
    st.markdown(
        """
        <div class="mob-hero">
            <div>
                <h1>Relatório de Comissão</h1>
                <div class="mob-hero-sub">Mobílli Rentals — apuração mensal + ficha de assinatura</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not gerar:
        st.info(
            "Selecione **mês**, **vendedor** e **meta** na barra lateral, e clique em "
            "**Gerar Relatório**."
        )
        return

    if not mes_pagamento:
        st.error("Selecione o **mês de pagamento**.")
        return
    if not vendedor_nome:
        st.error("Selecione o **vendedor**.")
        return
    if qtd_meta <= 0:
        st.error("Informe a **meta mensal** (valor maior que zero).")
        return

    vendedor_id = next(k for k, v in VENDEDORES.items() if v == vendedor_nome)

    try:
        with st.spinner("Buscando dados do CRM e MicroWork..."):
            relatorio = relatorio_cacheado(
                vendedor_id=vendedor_id,
                vendedor_nome=vendedor_nome,
                mes_referencia=mes_pagamento,
                qtd_meta=qtd_meta,
            )
    except Exception as exc:  # noqa: BLE001
        st.error(
            "**Não consegui montar o relatório agora.**  \n"
            f"Causa: `{type(exc).__name__}: {exc}`"
        )
        st.info(
            "Tente novamente em alguns segundos. Se persistir, me chama no terminal."
        )
        return

    # ── Identificação do vendedor ──────────────────────────────────
    cpf_str = relatorio.vendedor.cpf or "<i style='color:#9ca3af;'>(CPF não cadastrado no Bitrix)</i>"
    st.markdown(
        f"""
        <div class="mob-meta-wrap" style="margin-top:6px;">
            <div class="mob-meta-info">
                <div class="mob-meta-title">Vendedor</div>
                <div style="font-size:22px;font-weight:700;color:#1a1a1a;margin-top:4px;">
                    {html.escape(relatorio.vendedor.nome)}
                </div>
                <div style="font-size:13px;color:#4b5563;margin-top:2px;">
                    CPF: {cpf_str}
                </div>
                <div style="font-size:13px;color:#4b5563;margin-top:2px;">
                    Pagamento: <b>{html.escape(mes_ano_label(relatorio.competencia))}</b>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── KPIs (Meta · Atingido · % · Devolvidos) ────────────────────
    pct = float(relatorio.nivel.percentual_atingido)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(
            _kpi("Meta", str(relatorio.nivel.qtd_meta), "captações no mês"),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            _kpi(
                "Atingido",
                str(relatorio.nivel.qtd_atingida),
                f"{pct:.0f}% da meta",
                accent=True,
            ),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            _kpi(
                "Itens p/ comissão",
                str(relatorio.negocios_fechados),
                "parcelas pagas neste mês",
            ),
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            _nivel_card(
                relatorio.nivel.nome,
                pct,
                relatorio.nivel.qtd_atingida,
                relatorio.nivel.qtd_meta,
            ),
            unsafe_allow_html=True,
        )

    if relatorio.negocios_encerrados > 0:
        st.markdown(
            f"""
            <div style="margin-top:14px;padding:10px 14px;background:#fef2f2;
                        border:1px solid #fecaca;border-radius:8px;font-size:13px;color:#7f1d1d;">
                ⚠️ <b>{relatorio.negocios_encerrados}</b> deal(s) devolvido(s) no período —
                veja a tabela abaixo (linhas marcadas em vermelho).
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Tabela ──────────────────────────────────────────────────────
    st.markdown(
        '<div class="mob-section-title" style="margin-top:24px;">Lista de Verificação de Pagamento</div>',
        unsafe_allow_html=True,
    )
    _tabela_itens(relatorio.itens, relatorio.total_comissao)

    # Termo de ciência + assinatura ficam APENAS no PDF (não na tela).

    # ── Downloads ───────────────────────────────────────────────────
    pdf_bytes = gerar_pdf(relatorio)
    xlsx_bytes = gerar_xlsx(relatorio)
    base_nome = (
        f"comissao_{vendedor_nome.replace(' ', '_')}_{mes_ano_label(mes_pagamento)}"
    )

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            "📄 Baixar PDF",
            pdf_bytes,
            file_name=f"{base_nome}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    with col_dl2:
        st.download_button(
            "📊 Baixar Excel",
            xlsx_bytes,
            file_name=f"{base_nome}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
