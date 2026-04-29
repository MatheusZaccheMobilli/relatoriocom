"""Cadastro local de vendedores ativos.

Fonte da verdade enquanto o webhook do Bitrix não tem scope `user`.
Atualizar manualmente quando entrar/sair vendedor.

Email → ASSIGNED_BY_ID extraído de:
  - users.xls (export do Bitrix, departamento "Vendas")
  - confirmação manual com IDs do projeto
"""

from __future__ import annotations

DOMINIO_CORPORATIVO = "mobillirentals.com.br"

# id → nome de exibição (vendedores ATIVOS — usados no dashboard e seletor do relatório)
VENDEDORES: dict[int, str] = {
    83700: "Glacio Santos Dapieve",
    83518: "Paulo Henrique Silva Cardoso",
}

# Lideranças (não são vendedores, mas têm acesso ao dashboard com visão completa)
LIDERES: dict[int, str] = {
    49580: "Thiago Calmon",
}

# email corporativo → ASSIGNED_BY_ID (usado para auth quando habilitar login)
EMAIL_TO_ID: dict[str, int] = {
    "glacio.dapieve@mobillirentals.com.br": 83700,
    "paulo.cardoso@mobillirentals.com.br": 83518,
    "thiago.vasconcelos@mobillirentals.com.br": 49580,
}

# IDs com visualização completa (lideranças que veem todos os vendedores)
FULL_VIEW_IDS: set[int] = {
    49580,  # Thiago Calmon — Líder de Vendas
}


def nome_por_id(vendedor_id: int) -> str | None:
    return VENDEDORES.get(vendedor_id) or LIDERES.get(vendedor_id)


def id_por_email(email: str) -> int | None:
    return EMAIL_TO_ID.get(email.strip().lower())


def tem_visao_completa(vendedor_id: int) -> bool:
    """True se o vendedor pode ver dados de todos os outros (líder/gestor)."""
    return vendedor_id in FULL_VIEW_IDS
