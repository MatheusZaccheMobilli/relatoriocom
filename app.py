"""Relatório de Comissão de Vendedores — Mobílli."""

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import streamlit as st
import pandas as pd
from dateutil.relativedelta import relativedelta

from src.business.orchestrator import montar_relatorio
from src.models import RelatorioData
from src.export.pdf import gerar_pdf

# ── Config ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Comissão Vendedores — Mobílli",
    page_icon="🏍️",
    layout="wide",
)

# ── CSS customizado — identidade Mobílli ────────────────────────────
st.markdown("""
<style>
    /* Esconder menu Deploy e hamburger */
    .stDeployButton, #MainMenu {
        display: none !important;
    }
    /* Header bar */
    header[data-testid="stHeader"] {
        background-color: #FF6600;
    }
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #1a1a1a;
    }
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stNumberInput label,
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] p {
        color: #ffffff !important;
    }
    /* Botão primário */
    .stButton > button[kind="primary"] {
        background-color: #FF6600 !important;
        border-color: #FF6600 !important;
        color: white !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #CC5200 !important;
        border-color: #CC5200 !important;
    }
    /* Download button */
    .stDownloadButton > button {
        background-color: #FF6600 !important;
        border-color: #FF6600 !important;
        color: white !important;
    }
    /* Metrics */
    [data-testid="stMetricValue"] {
        color: #FF6600 !important;
    }
    /* Subheaders */
    .stMarkdown h2, .stMarkdown h3 {
        color: #CC5200 !important;
    }
</style>
""", unsafe_allow_html=True)

VENDEDORES = {
    83302: "Cleysielen Mattos Silva",
    83700: "Glacio Santos Dapieve",
    83518: "Paulo Henrique Silva Cardoso",
}

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def formatar_brl(valor: Decimal) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_data(d: date | None) -> str:
    if not d:
        return "-"
    return d.strftime("%d/%m/%Y")


def mes_ano_label(d: date) -> str:
    return f"{MESES_PT[d.month]}/{d.year}"


# ── Sidebar: Logo + Filtros ────────────────────────────────────────
logo_path = Path(__file__).parent / "logo-mobilli.png"
if logo_path.exists():
    st.sidebar.image(str(logo_path), use_container_width=True)

st.sidebar.title("Filtros")

hoje = date.today()
meses_opcoes = []
for i in range(-1, 12):
    m = hoje.replace(day=1) - relativedelta(months=i)
    meses_opcoes.append(m)

mes_pagamento = st.sidebar.selectbox(
    "Mês de pagamento",
    meses_opcoes,
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

gerar = st.sidebar.button("Gerar Relatório", type="primary", use_container_width=True)

# ── Main ────────────────────────────────────────────────────────────
st.title("Relatório de Comissão")
st.caption("Mobílli Rentals - Apuração de comissão de vendedores")

if not gerar:
    st.info("Selecione os filtros na barra lateral e clique em **Gerar Relatório**.")
    st.stop()

# Validar filtros preenchidos
if not mes_pagamento:
    st.error("Selecione o **mês de pagamento**.")
    st.stop()
if not vendedor_nome:
    st.error("Selecione o **vendedor**.")
    st.stop()
if qtd_meta <= 0:
    st.error("Informe a **meta mensal** (valor maior que zero).")
    st.stop()

vendedor_id = [k for k, v in VENDEDORES.items() if v == vendedor_nome][0]

with st.spinner("Buscando dados do CRM e MicroWork..."):
    relatorio = montar_relatorio(
        vendedor_id=vendedor_id,
        vendedor_nome=vendedor_nome,
        mes_referencia=mes_pagamento,
        qtd_meta=qtd_meta,
    )

# ── Cabeçalho ───────────────────────────────────────────────────────
st.divider()
col1, col2 = st.columns(2)

with col1:
    st.markdown(f"**Vendedor:** {relatorio.vendedor.nome}")
    if relatorio.vendedor.cpf:
        st.markdown(f"**CPF:** {relatorio.vendedor.cpf}")

with col2:
    st.markdown(f"**Pagamento em:** {mes_ano_label(relatorio.competencia)}")

# ── Bloco de Meta ───────────────────────────────────────────────────
st.divider()
st.subheader("Meta")

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("Meta", f"{relatorio.nivel.qtd_meta} captações")
col_m2.metric("Total geral", f"{relatorio.nivel.qtd_atingida} captações")
col_m3.metric("% Atingido", f"{relatorio.nivel.percentual_atingido}%")

nivel_cor = {
    "Ouro": "🥇 Ouro",
    "Prata": "🥈 Prata",
    "Bronze": "🥉 Bronze",
    "Sem Meta": "-",
}
col_m4.metric("Nível", nivel_cor.get(relatorio.nivel.nome, relatorio.nivel.nome))

# ── Indicadores ─────────────────────────────────────────────────────
st.divider()
col_i1, col_i2 = st.columns(2)
col_i1.metric("Itens para comissão", relatorio.negocios_fechados)
col_i2.metric("Devolvidos", relatorio.negocios_encerrados)

# ── Lista de Verificação de Pagamento ───────────────────────────────
st.divider()
st.subheader("Lista de Verificação de Pagamento")

if not relatorio.itens:
    st.warning("Nenhum item de comissão encontrado para este período.")
else:
    linhas = []
    for item in relatorio.itens:
        linha = {
            "Tipo": item.tipo_operacao,
            "Parcela": item.parcela,
            "Nome do Cliente": item.nome_cliente,
            "Placa": item.placa,
            "Data Locação": formatar_data(item.data_locacao),
            "Data Devolução": formatar_data(item.data_devolucao),
            "Valor Base": formatar_brl(item.valor_base),
            "Comissão": formatar_brl(item.valor_comissao),
            "Status": "DEVOLVIDO" if item.devolvido else "Ativo",
        }
        linhas.append(linha)

    df = pd.DataFrame(linhas)

    def highlight_devolvido(row):
        if row["Status"] == "DEVOLVIDO":
            return ["background-color: #ffcccc"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df.style.apply(highlight_devolvido, axis=1),
        use_container_width=True,
        hide_index=True,
    )

# ── Total ───────────────────────────────────────────────────────────
st.divider()
st.markdown(f"### Total a receber: {formatar_brl(relatorio.total_comissao)}")

# ── Download PDF ────────────────────────────────────────────────────
pdf_bytes = gerar_pdf(relatorio)
st.download_button(
    "Baixar Relatório PDF",
    pdf_bytes,
    file_name=f"comissao_{vendedor_nome.replace(' ', '_')}_{mes_ano_label(mes_pagamento)}.pdf",
    mime="application/pdf",
    use_container_width=True,
)

