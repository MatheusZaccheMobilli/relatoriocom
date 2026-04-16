"""Dataclasses centrais — nenhum dict cru cruza fronteiras de camada."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class Pagamento:
    """Um recebimento vindo do MicroWork."""

    cpf_cnpj: str
    empresa: str
    documento: str
    especie: str
    emissao: date
    vencimento: date
    movimento: date  # data do pagamento efetivo
    pessoa: str
    valor_parcela: Decimal
    valor_lancamento: Decimal
    juros: Decimal
    multa: Decimal
    desconto: Decimal
    valor_total: Decimal
    nota_fiscal: str = ""
    rg: str = ""


@dataclass(frozen=True)
class Deal:
    """Um deal (negócio) vindo do Bitrix24."""

    id: int
    titulo: str
    pipeline_id: int  # 48=Locação, 40=Venda
    stage_id: str
    assigned_by_id: int  # vendedor (user ID)
    contact_id: Optional[int]
    cpf_cnpj_deal: str  # UF_CRM_1730135950688
    valor: Decimal
    data_locacao: Optional[date]  # UF_CRM_1743092456783
    placa: str  # UF_CRM_1749815964662 (deal) ou UF_CRM_1723028259246 (contato)
    plano_semanal: bool  # UF_CRM_WEEKLY_SUBSCRIPTION != "não"
    data_fechamento: Optional[date]


@dataclass(frozen=True)
class Vendedor:
    """Dados do vendedor (user do Bitrix)."""

    id: int
    nome: str
    cpf: str = ""  # pode não estar disponível (scope limitado)


@dataclass(frozen=True)
class NivelMeta:
    """Resultado do cálculo de nível de meta."""

    nome: str  # Bronze, Prata, Ouro ou Abaixo
    percentual_atingido: Decimal
    qtd_meta: int  # quantidade de motos da meta
    qtd_atingida: int  # quantidade de motos fechadas no mês


@dataclass(frozen=True)
class ComissaoItem:
    """Uma linha na lista de verificação de pagamento."""

    parcela: str  # ex: "1/2"
    nome_cliente: str
    cpf_cliente: str
    placa: str
    data_locacao: Optional[date]
    data_retorno: Optional[date]
    valor_base: Decimal  # valor sobre o qual incide a comissão
    valor_comissao: Decimal
    tipo_operacao: str  # "Locação", "Venda 0km", "Venda Usado"
    data_devolucao: Optional[date] = None  # preenchido se houve rescisão
    devolvido: bool = False  # True = parcela não é paga


@dataclass(frozen=True)
class RelatorioData:
    """Dados completos para gerar o relatório — consumido pelo preview e PDF."""

    vendedor: Vendedor
    competencia: date  # mês/ano de referência (mês de pagamento)
    nivel: NivelMeta
    negocios_fechados: int
    negocios_encerrados: int
    itens: list[ComissaoItem] = field(default_factory=list)
    total_comissao: Decimal = Decimal("0")
