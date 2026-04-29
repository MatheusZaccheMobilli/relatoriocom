"""Página: Relatório de Comissão (extraído do app.py original)."""

from __future__ import annotations

import streamlit as st
import pandas as pd

from src.auth import VENDEDORES
from src.export.pdf import gerar_pdf
from src.export.xlsx import gerar_xlsx
from src.ui.data import relatorio_cacheado
from src.ui.shared import (
    NIVEL_BADGES,
    formatar_brl,
    formatar_data,
    mes_ano_label,
    opcoes_de_mes,
)


def render() -> None:
    # ── Sidebar: filtros ────────────────────────────────────────────
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
        "Informar meta mensal (qtd captações)",
        min_value=0,
        value=0,
        step=1,
    )

    gerar = st.sidebar.button(
        "Gerar Relatório", type="primary", use_container_width=True
    )

    # ── Main ────────────────────────────────────────────────────────
    st.title("Relatório de Comissão")
    st.caption("Mobílli Rentals — Apuração de comissão de vendedores")

    if not gerar:
        st.info(
            "Selecione os filtros na barra lateral e clique em **Gerar Relatório**."
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

    with st.spinner("Buscando dados do CRM e MicroWork..."):
        relatorio = relatorio_cacheado(
            vendedor_id=vendedor_id,
            vendedor_nome=vendedor_nome,
            mes_referencia=mes_pagamento,
            qtd_meta=qtd_meta,
        )

    # ── Cabeçalho ──────────────────────────────────────────────────
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Vendedor:** {relatorio.vendedor.nome}")
        if relatorio.vendedor.cpf:
            st.markdown(f"**CPF:** {relatorio.vendedor.cpf}")
    with col2:
        st.markdown(f"**Pagamento em:** {mes_ano_label(relatorio.competencia)}")

    # ── Bloco de Meta ──────────────────────────────────────────────
    st.divider()
    st.subheader("Meta")
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Meta", f"{relatorio.nivel.qtd_meta} captações")
    col_m2.metric("Total geral", f"{relatorio.nivel.qtd_atingida} captações")
    col_m3.metric("% Atingido", f"{relatorio.nivel.percentual_atingido}%")
    col_m4.metric(
        "Nível", NIVEL_BADGES.get(relatorio.nivel.nome, relatorio.nivel.nome)
    )

    # ── Indicadores ────────────────────────────────────────────────
    st.divider()
    col_i1, col_i2 = st.columns(2)
    col_i1.metric("Itens para comissão", relatorio.negocios_fechados)
    col_i2.metric("Devolvidos", relatorio.negocios_encerrados)

    # ── Lista de Verificação de Pagamento ──────────────────────────
    st.divider()
    st.subheader("Lista de Verificação de Pagamento")

    if not relatorio.itens:
        st.warning("Nenhum item de comissão encontrado para este período.")
    else:
        linhas = []
        for item in relatorio.itens:
            if item.tipo_operacao == "Locação":
                plano_str = "Semanal" if item.plano_semanal else "Mensal"
                parcelas_str = str(item.qtd_parcelas_pagas)
            else:
                plano_str = "—"
                parcelas_str = "—"

            linhas.append({
                "Tipo": item.tipo_operacao,
                "Parcela": item.parcela,
                "Plano": plano_str,
                "Nome do Cliente": item.nome_cliente,
                "Placa": item.placa,
                "Data Locação": formatar_data(item.data_locacao),
                "Data Devolução": formatar_data(item.data_devolucao),
                "Valor Base": formatar_brl(item.valor_base),
                "Parcelas": parcelas_str,
                "Comissão": formatar_brl(item.valor_comissao),
                "Status": "DEVOLVIDO" if item.devolvido else "Ativo",
            })

        df = pd.DataFrame(linhas)

        def _highlight(row):
            if row["Status"] == "DEVOLVIDO":
                return ["background-color: #ffcccc"] * len(row)
            return [""] * len(row)

        st.dataframe(
            df.style.apply(_highlight, axis=1),
            use_container_width=True,
            hide_index=True,
        )

    # ── Total ──────────────────────────────────────────────────────
    st.divider()
    st.markdown(
        f"### Total a receber: {formatar_brl(relatorio.total_comissao)}"
    )

    # ── Download PDF + XLSX ────────────────────────────────────────
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
