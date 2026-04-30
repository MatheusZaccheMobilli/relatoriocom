"""Shim de compatibilidade — Streamlit Cloud aponta pra `app.py` por padrão.

O app foi separado em dois entrypoints (`app_analytics.py` + `app_relatorio.py`).
Este arquivo existe apenas para que o deploy atual no Streamlit Cloud, que está
fixado em `app.py`, continue funcionando sem precisar recriar o app.

Comportamento: serve o Relatório de Comissão (mesmo que `app_relatorio.py`).

Para o novo app de Analytics (Dashboard + Perfil), criar um app separado no
Streamlit Cloud apontando para `app_analytics.py`.
"""

# Apenas executa o entrypoint do relatório.
import runpy
import os

runpy.run_path(
    os.path.join(os.path.dirname(__file__), "app_relatorio.py"),
    run_name="__main__",
)
