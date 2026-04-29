"""Entrypoint do app — navegação entre páginas (Relatório / Dashboard)."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import streamlit as st

from src.ui.pages import dashboard, relatorio
from src.ui.shared import aplicar_css

st.set_page_config(
    page_title="Comissão Vendedores — Mobílli",
    page_icon="🏍️",
    layout="wide",
)

aplicar_css()

PAGINA_DASHBOARD = st.Page(
    dashboard.render,
    title="Dashboard",
    icon="📊",
    url_path="dashboard",
    default=True,
)
PAGINA_RELATORIO = st.Page(
    relatorio.render,
    title="Relatório de Comissão",
    icon="📄",
    url_path="relatorio",
)

nav = st.navigation([PAGINA_DASHBOARD, PAGINA_RELATORIO])
nav.run()
