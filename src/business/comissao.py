"""Motor de cálculo de comissão — funções puras, sem dependência de API."""

from decimal import Decimal, ROUND_HALF_UP

from src.models import NivelMeta


# Tabela TM-018 — percentuais B2C
TABELA_COMISSAO = {
    "Venda 0km": {"Bronze": Decimal("0.0100"), "Prata": Decimal("0.0120"), "Ouro": Decimal("0.0130")},
    "Venda Usado": {"Bronze": Decimal("0.0340"), "Prata": Decimal("0.0400"), "Ouro": Decimal("0.0480")},
    "Locação": {"Bronze": Decimal("0.0800"), "Prata": Decimal("0.0900"), "Ouro": Decimal("0.1000")},
}


def calcular_nivel(qtd_atingida: int, qtd_meta: int) -> NivelMeta:
    """Calcula o nível de meta atingido por quantidade de motos.

    Bronze: >= 75% da meta
    Prata:  >= 100% da meta
    Ouro:   >= 125% da meta
    """
    if qtd_meta <= 0:
        return NivelMeta(
            nome="Sem Meta",
            percentual_atingido=Decimal("0"),
            qtd_meta=qtd_meta,
            qtd_atingida=qtd_atingida,
        )

    percentual = (Decimal(qtd_atingida) / Decimal(qtd_meta) * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if percentual >= Decimal("125"):
        nome = "Ouro"
    elif percentual >= Decimal("100"):
        nome = "Prata"
    else:
        nome = "Bronze"

    return NivelMeta(
        nome=nome,
        percentual_atingido=percentual,
        qtd_meta=qtd_meta,
        qtd_atingida=qtd_atingida,
    )


def calcular_comissao(
    valor_base: Decimal,
    tipo_operacao: str,
    nivel: str,
) -> Decimal:
    """Calcula o valor da comissão para um item.

    Args:
        valor_base: valor sobre o qual incide a comissão
        tipo_operacao: "Venda 0km", "Venda Usado" ou "Locação"
        nivel: "Bronze", "Prata" ou "Ouro"

    Returns:
        Valor da comissão em R$. Zero se nível for "Abaixo" ou "Sem Meta".
    """
    tabela = TABELA_COMISSAO.get(tipo_operacao)
    if not tabela:
        return Decimal("0")

    percentual = tabela.get(nivel, Decimal("0"))
    return (valor_base * percentual).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
