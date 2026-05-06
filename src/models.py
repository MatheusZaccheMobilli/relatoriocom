"""Dataclasses centrais — nenhum dict cru cruza fronteiras de camada."""

from __future__ import annotations

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
    source_id: str = ""  # SOURCE_ID — origem do lead (ver bitrix.SOURCES_LABELS)
    cidade: str = ""  # UF_CRM_1744638028 — cidade do cliente (replicada no deal)


@dataclass(frozen=True)
class Vendedor:
    """Dados do vendedor (user do Bitrix)."""

    id: int
    nome: str
    cpf: str = ""  # pode não estar disponível (scope limitado)


@dataclass(frozen=True)
class InventarioMoto:
    """Uma moto na SPA Inventário (entityTypeId=1072) do Bitrix.

    Pipeline 28 é o único da SPA. `deal_id` (parentId2) liga a moto ao deal
    de locação ativo; `cadastro_id` aponta pra SPA Cadastro (1076), que é o
    catálogo permanente das motos da frota.
    """

    id: int
    placa: str
    modelo: str
    cor: str
    base: str  # label legível (Serra galpão, Vila Velha APP, ...)
    stage_id: str  # ex: "DT1072_28:UC_S400BR"
    stage_label: str  # ex: "Alugada"
    deal_id: Optional[int] = None  # parentId2 — deal vinculado, se houver
    cadastro_id: Optional[int] = None  # ufCrm16_1749580517 — catálogo
    moved_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    local_locacao: str = ""


@dataclass(frozen=True)
class FrotaSnapshot:
    """Snapshot agregado da frota — usado pelo card de Frota no dashboard.

    `ativa` exclui terminais (Vendida, Cancelada). `outros` é tudo que está
    ativo mas não cai em alugadas/disponíveis/manutenção (preparação,
    trânsito, MKT, parceiros, sinistro, etc.) — detalhado em `por_estado`.
    """

    ativa: int
    alugadas: int
    disponiveis: int
    manutencao: int
    outros: int
    por_estado: dict[str, int] = field(default_factory=dict)


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
    plano_semanal: bool = False  # True = plano semanal; False = mensal
    qtd_parcelas_pagas: int = 0  # qtd de boletos que entraram na base


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


# ─── Dashboard (ótica diferente do relatório) ──────────────────────────
@dataclass(frozen=True)
class CaptacaoItem:
    """Uma captação (deal fechado) num mês calendário — para o dashboard.

    Diferente de `ComissaoItem`: não tem valor de comissão, é só sobre o ato
    de captar (o vendedor fechou um negócio, independente de quando paga).
    """
    deal_id: int
    tipo_operacao: str  # "Locação" | "Venda 0km"
    nome_cliente: str
    placa: Optional[str]
    data_locacao: Optional[date]
    data_devolucao: Optional[date] = None
    devolvido: bool = False
    source_id: str = ""  # SOURCE_ID — origem do lead (ver bitrix.SOURCES_LABELS)
    cidade: str = ""  # cidade do cliente (UF_CRM_1744638028 do deal)
    plano_semanal: bool = False  # True só faz sentido em locação


@dataclass(frozen=True)
class CaptacoesVendedor:
    """Captações de um vendedor num mês calendário."""
    vendedor_id: int
    nome: str
    itens: list[CaptacaoItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.itens)

    @property
    def devolvidos(self) -> int:
        return sum(1 for i in self.itens if i.devolvido)


@dataclass(frozen=True)
class CaptacoesMes:
    """Snapshot de captações da empresa num mês calendário."""
    mes: date  # primeiro dia do mês
    total_empresa: int  # captações de TODOS (vendedores + outros assigned)
    locacoes_total: int = 0
    vendas_total: int = 0
    # Mapa dia (1..31) -> captações do time naquele dia
    captacoes_por_dia: dict[int, int] = field(default_factory=dict)
    por_vendedor: list[CaptacoesVendedor] = field(default_factory=list)
    # Faturamento real do mês (MicroWork): soma de boletos de aluguel
    # com data de movimento dentro do mês calendário. Não é o `Deal.valor`.
    faturamento: Decimal = Decimal("0")
    # Mix de plano (locação): semanal vs mensal. Soma = locacoes_total.
    locacoes_semanal: int = 0
    locacoes_mensal: int = 0
    # Total de captações devolvidas (pipeline 22) detectadas neste mês.
    devolvidos_total: int = 0
    # Lista flat de TODAS as captações (mesmo orphans sem vendedor),
    # consumida pela página de Perfil do Cliente para agregações por
    # source/cidade/tipo. Inclui source_id, cidade e plano_semanal.
    captacoes_flat: list[CaptacaoItem] = field(default_factory=list)


@dataclass(frozen=True)
class CaptacoesComparadas:
    """Snapshot comparativo: mês atual vs mês anterior + projeção."""
    atual: CaptacoesMes
    anterior: CaptacoesMes
    # Projeção do mês atual = parcial / du_decorridos × du_mes_total
    projecao_total: int
    projecao_locacoes: int
    projecao_vendas: int
    projecao_faturamento: Decimal = Decimal("0")
    # Dias úteis ponderados (regra Seg=1, Sáb=0.5, Dom=0, Feriado=0)
    du_mes_atual: float = 0.0
    du_decorridos_atual: float = 0.0
    du_mes_anterior: float = 0.0
