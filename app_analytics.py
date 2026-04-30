"""Entrypoint do app de Analytics — Dashboard Comercial + Perfil do Cliente.

Audiência: liderança / time comercial. Dados agregados de captação,
performance por vendedor e perfil demográfico dos clientes.

Para o relatório de comissão (RH), ver `app_relatorio.py`.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import streamlit as st

from src.ui.pages import dashboard
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


def _perfil_placeholder() -> None:
    st.title("Perfil do Cliente")
    st.info(
        "**Em construção.** Análise demográfica e contratual dos clientes — "
        "idade, cidade, origem do lead, tipo de plano. "
        "Dados desde Mar/2026."
    )


PAGINA_PERFIL = st.Page(
    _perfil_placeholder,
    title="Perfil do Cliente",
    url_path="perfil",
)

nav = st.navigation([PAGINA_DASHBOARD, PAGINA_PERFIL])
nav.run()
