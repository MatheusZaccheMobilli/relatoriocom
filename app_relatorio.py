"""Entrypoint do app de Relatório de Comissão — geração + ficha de assinatura.

Audiência: RH e vendedor. Geração mensal do relatório, validação dos dados
de comissão pelo vendedor, exportação em PDF e XLSX.

Para o dashboard comercial e perfil do cliente, ver `app_analytics.py`.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import streamlit as st

from src.ui.pages import relatorio
from src.ui.shared import aplicar_css

st.set_page_config(
    page_title="Comissão Vendedores — Mobílli",
    page_icon="📄",
    layout="wide",
)

# Sem banner "EM CONSTRUÇÃO" — o relatório está em produção.
aplicar_css(em_construcao=False)

relatorio.render()
