"""Cadastro local de vendedores ativos.

Fonte da verdade enquanto o webhook do Bitrix não tem scope `user`.
Atualizar manualmente quando entrar/sair vendedor.

Email → ASSIGNED_BY_ID extraído de:
  - docs/users.xls (export do Bitrix, departamento "Vendas")
  - confirmação manual com IDs do projeto
"""

from __future__ import annotations

DOMINIO_CORPORATIVO = "mobillirentals.com.br"

# id → nome de exibição (vendedores ATIVOS — usados no dashboard e seletor do relatório)
# Histórico de saídas: Cleysielen Mattos (83302) saiu em mai/2026.
VENDEDORES: dict[int, str] = {
    83700: "Glacio Santos Dapieve",
    83518: "Paulo Henrique Silva Cardoso",
    98314: "Francieli Serra da Silva",
    98316: "Marcio Francisco Beloti",
}

# Lideranças (não são vendedores, mas têm acesso ao dashboard com visão completa)
LIDERES: dict[int, str] = {
    49580: "Thiago Calmon",
}

# Outros captadores conhecidos: aparecem nos dashboards com nome real,
# mas NÃO entram no seletor de vendedor do relatório de comissão.
# Estrutura: id → (nome, papel)
OUTROS_CONHECIDOS: dict[int, tuple[str, str]] = {
    24:    ("Kaian Paganini Belmok", "Sócio"),
    222:   ("Yasmin Julião", "Pós-Vendas"),
    39542: ("Robô Mobílli", "Sistema"),
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
    """Resolve o nome de qualquer captador conhecido (vendedor, líder ou outro)."""
    if vendedor_id in VENDEDORES:
        return VENDEDORES[vendedor_id]
    if vendedor_id in LIDERES:
        return LIDERES[vendedor_id]
    if vendedor_id in OUTROS_CONHECIDOS:
        return OUTROS_CONHECIDOS[vendedor_id][0]
    return None


def papel_por_id(vendedor_id: int) -> str:
    """Retorna o papel exibido no card: Vendedor, Líder, Sócio, Pós-Vendas, Sistema, ou ''."""
    if vendedor_id in VENDEDORES:
        return "Vendedor"
    if vendedor_id in LIDERES:
        return "Líder"
    if vendedor_id in OUTROS_CONHECIDOS:
        return OUTROS_CONHECIDOS[vendedor_id][1]
    return ""


def id_por_email(email: str) -> int | None:
    return EMAIL_TO_ID.get(email.strip().lower())


def tem_visao_completa(vendedor_id: int) -> bool:
    """True se o vendedor pode ver dados de todos os outros (líder/gestor)."""
    return vendedor_id in FULL_VIEW_IDS


def todos_nomes_conhecidos() -> dict[int, str]:
    """Dict completo id→nome (vendedores ativos + líderes + outros)."""
    return {
        **VENDEDORES,
        **LIDERES,
        **{vid: nome for vid, (nome, _papel) in OUTROS_CONHECIDOS.items()},
    }
