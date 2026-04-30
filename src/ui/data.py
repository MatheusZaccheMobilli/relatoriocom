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
    serie_historica,
)
from src.models import CaptacoesComparadas, CaptacoesMes, RelatorioData


# TTL de 30min: dashboard não precisa de dado super-fresco e mantém cache
# por mais tempo entre sessões (free tier do Streamlit Cloud não tem keep-alive).
_TTL_SEGUNDOS = 1800


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


# Bump esta versão SEMPRE que adicionar/remover/renomear campos em
# CaptacoesMes ou CaptacaoItem — invalida cache stale do Streamlit Cloud
# (que persiste pickle entre deploys). Schema atual: v3 (captacoes_flat
# + source_id + cidade + plano_semanal nos itens; faturamento + mix +
# devolvidos_total + captacoes_flat no snapshot).
_SCHEMA_VERSION = 3


@st.cache_data(ttl=_TTL_SEGUNDOS, show_spinner=False)
def serie_historica_cacheada(
    mes_floor: date,
    mes_topo: date,
    vendedores_key: tuple[tuple[int, str], ...],
    schema_version: int = _SCHEMA_VERSION,
) -> list[CaptacoesMes]:
    """Versão cacheada de `serie_historica` (5min).

    Retorna a série completa de meses entre floor e topo. Usado pelos
    gráficos históricos (todos os meses desde março). `schema_version`
    entra na chave do cache: bumpar invalida tudo.
    """
    del schema_version  # apenas pra entrar no hash do cache
    vendedores = dict(vendedores_key)
    return serie_historica(
        mes_floor=mes_floor, mes_topo=mes_topo, vendedores=vendedores
    )


def limpar_cache() -> None:
    """Invalida todo o cache de dados — usado pelo botão 'Atualizar agora'."""
    relatorio_cacheado.clear()
    captacoes_cacheadas.clear()
    captacoes_comparadas_cacheadas.clear()
    serie_historica_cacheada.clear()
