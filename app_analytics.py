"""Entrypoint do app de Analytics — Dashboard Comercial + Perfil do Cliente.

Audiência: liderança / time comercial. Dados agregados de captação,
performance por vendedor e perfil demográfico dos clientes.

Para o relatório de comissão (RH), ver `app_relatorio.py`.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import streamlit as st

from src.ui.pages import dashboard, perfil
from src.ui.shared import aplicar_css

st.set_page_config(
    page_title="Analytics — Mobílli",
    page_icon="📊",
    layout="wide",
)

aplicar_css(em_construcao=True)

PAGINA_DASHBOARD = st.Page(
    dashboard.render,
    title="Dashboard",
    url_path="dashboard",
    default=True,
)

PAGINA_PERFIL = st.Page(
    perfil.render,
    title="Perfil do Cliente",
    url_path="perfil",
)

nav = st.navigation([PAGINA_DASHBOARD, PAGINA_PERFIL])
nav.run()
