"""Wrappers cacheados para chamadas custosas (Bitrix + MicroWork).

Mantém o `st.cache_data` confinado à camada de UI — o orchestrator
permanece independente de Streamlit.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.business.orchestrator import (
    captacoes_comparadas,
    captacoes_no_mes,
    montar_relatorio,
)
from src.models import CaptacoesComparadas, CaptacoesMes, RelatorioData


# TTL de 5min: equilibra atualização frequente com peso na API.
_TTL_SEGUNDOS = 300


@st.cache_data(ttl=_TTL_SEGUNDOS, show_spinner=False)
def relatorio_cacheado(
    vendedor_id: int,
    vendedor_nome: str,
    mes_referencia: date,
    qtd_meta: int,
) -> RelatorioData:
    """Versão cacheada de `montar_relatorio` (5min)."""
    return montar_relatorio(
        vendedor_id=vendedor_id,
        vendedor_nome=vendedor_nome,
        mes_referencia=mes_referencia,
        qtd_meta=qtd_meta,
    )


@st.cache_data(ttl=_TTL_SEGUNDOS, show_spinner=False)
def captacoes_cacheadas(
    mes_captacao: date,
    vendedores_key: tuple[tuple[int, str], ...],
) -> CaptacoesMes:
    """Versão cacheada de `captacoes_no_mes` (5min)."""
    vendedores = dict(vendedores_key)
    return captacoes_no_mes(mes_captacao=mes_captacao, vendedores=vendedores)


@st.cache_data(ttl=_TTL_SEGUNDOS, show_spinner=False)
def captacoes_comparadas_cacheadas(
    mes_atual: date,
    vendedores_key: tuple[tuple[int, str], ...],
    hoje: date,
) -> CaptacoesComparadas:
    """Versão cacheada de `captacoes_comparadas` (5min).

    `hoje` na chave de cache permite invalidação automática ao virar o dia.
    """
    vendedores = dict(vendedores_key)
    return captacoes_comparadas(
        mes_atual=mes_atual, vendedores=vendedores, hoje=hoje
    )


def limpar_cache() -> None:
    """Invalida todo o cache de dados — usado pelo botão 'Atualizar agora'."""
    relatorio_cacheado.clear()
    captacoes_cacheadas.clear()
    captacoes_comparadas_cacheadas.clear()
