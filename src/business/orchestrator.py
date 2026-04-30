"""Orquestrador — conecta dados do Bitrix + MicroWork e monta o RelatorioData."""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from dateutil.relativedelta import relativedelta

from src.models import (
    CaptacaoItem,
    CaptacoesComparadas,
    CaptacoesMes,
    CaptacoesVendedor,
    ComissaoItem,
    Deal,
    Pagamento,
    RelatorioData,
    Vendedor,
)
from src.data import bitrix, microwork
from src.business.comissao import calcular_nivel, calcular_comissao
from src.business.dias_uteis import du_ate_hoje, du_mes


# Padrão do documento MicroWork para boletos de aluguel:
#   {deal_id}-{parcela}[P] - {seq}
# Ex: "29146-1P - 001", "33266-2 - 001", "35294-104P - 001"
_DOC_ALUGUEL_RE = re.compile(r"^\d{4,}-\d+P?\s*-\s*\d+$")


def _eh_boleto_aluguel(pagamento: Pagamento) -> bool:
    """Verifica se o pagamento é um boleto de aluguel (locação).

    Regra: especie = OUTROS e documento casa com padrão dealID-NP - seq.
    Exclui automaticamente NF-E (taxas/emplacamento), FRANQUIA, MULTA,
    REEMBOLSO, RECEBIINDEVIDO, etc. pois esses não seguem o padrão.
    """
    if pagamento.especie != "OUTROS":
        return False
    return bool(_DOC_ALUGUEL_RE.match(pagamento.documento.strip()))


def _normalize_cpf(raw: str) -> str:
    return "".join(c for c in raw if c.isdigit())


def _tipo_operacao_do_pipeline(pipeline_id: int) -> str:
    if pipeline_id in (bitrix.PIPELINE_LOCACAO, bitrix.PIPELINE_LOCACAO_SHOWROOM):
        return "Locação"
    if pipeline_id == bitrix.PIPELINE_VENDA:
        return "Venda 0km"  # TODO: distinguir 0km vs Usado
    return "Outro"


def _primeiro_dia_mes(d: date) -> date:
    return d.replace(day=1)


def _ultimo_dia_mes(d: date) -> date:
    proximo = d.replace(day=1) + relativedelta(months=1)
    return proximo - relativedelta(days=1)


def _total_pago_por_cpf(
    pagamentos_por_cpf: dict[str, list[Pagamento]],
    cpf: str,
) -> Decimal:
    """Soma o valor total pago por um CPF no MicroWork (sem filtro de mês)."""
    pagamentos = pagamentos_por_cpf.get(cpf, [])
    return sum((p.valor_total for p in pagamentos), Decimal("0"))


def _boletos_no_mes(
    pagamentos_por_cpf: dict[str, list[Pagamento]],
    cpf: str,
    mes: date,
    apenas_aluguel: bool = False,
) -> list[Pagamento]:
    """Lista pagamentos de um CPF dentro do mês calendário informado.

    Se apenas_aluguel=True, filtra somente boletos no padrão de aluguel
    (descarta taxas NF-E, franquia, multa, etc).
    """
    inicio = _primeiro_dia_mes(mes)
    fim = _ultimo_dia_mes(mes)
    pagamentos = pagamentos_por_cpf.get(cpf, [])
    return [
        p
        for p in pagamentos
        if inicio <= p.movimento <= fim
        and (not apenas_aluguel or _eh_boleto_aluguel(p))
    ]


def _pago_no_mes(
    pagamentos_por_cpf: dict[str, list[Pagamento]],
    cpf: str,
    mes: date,
    apenas_aluguel: bool = False,
) -> Decimal:
    """Soma o valor dos pagamentos de um CPF no mês calendário informado."""
    return sum(
        (p.valor_total for p in _boletos_no_mes(
            pagamentos_por_cpf, cpf, mes, apenas_aluguel
        )),
        Decimal("0"),
    )


def _mes_base_parcela(data_locacao: date, parcela: str) -> date:
    """Retorna o mês de referência para a base de cálculo de uma parcela.

    - 1/2 e 1/1: mês do fechamento (data_locacao)
    - 2/2: mês seguinte ao fechamento
    """
    if parcela == "2/2":
        return data_locacao + relativedelta(months=1)
    return data_locacao


def _dedup_locacao(deals: list[Deal]) -> list[Deal]:
    """Remove duplicatas de locação por (CPF, placa).

    Mesmo (CPF, placa) em P48 (APP) e P0 (Showroom) = mesmo deal cadastrado em
    dois lugares. Mantém o do P48 (fluxo principal).

    Deals sem CPF ou sem placa não são deduplicados (mantidos individualmente).
    """
    PRIORIDADE = {bitrix.PIPELINE_LOCACAO: 0, bitrix.PIPELINE_LOCACAO_SHOWROOM: 1}

    by_key: dict[tuple[str, str], Deal] = {}
    sem_chave: list[Deal] = []

    for d in deals:
        cpf = _normalize_cpf(d.cpf_cnpj_deal)
        placa = (d.placa or "").strip().upper()
        if not cpf or not placa:
            sem_chave.append(d)
            continue
        key = (cpf, placa)
        existente = by_key.get(key)
        if existente is None:
            by_key[key] = d
        elif PRIORIDADE.get(d.pipeline_id, 99) < PRIORIDADE.get(existente.pipeline_id, 99):
            by_key[key] = d

    return list(by_key.values()) + sem_chave


def _buscar_deals_ambos_pipelines(mes_referencia: date) -> list[Deal]:
    """Busca deals de TODOS os pipelines de comissão.

    Pipelines:
      P48 — Locação APP (fluxo principal)
      P0  — Locação Showroom (presencial)
      P40 — Venda

    Pagamento em mês M:
      Locação (P48 + P0): M-2 (parcela 2/2) e M-1 (parcela 1/2)
      Venda (P40):        M-1 (parcela 1/1)

    Locação é deduplicada por (CPF, placa) com prioridade P48 > P0.
    """
    # Locação: M-2 a M-1
    inicio_loc = _primeiro_dia_mes(mes_referencia - relativedelta(months=2))
    fim_loc = _ultimo_dia_mes(mes_referencia - relativedelta(months=1))
    deals_locacao_app = bitrix.buscar_deals(bitrix.PIPELINE_LOCACAO, inicio_loc, fim_loc)
    deals_locacao_showroom = bitrix.buscar_deals(
        bitrix.PIPELINE_LOCACAO_SHOWROOM, inicio_loc, fim_loc
    )
    deals_locacao = _dedup_locacao(deals_locacao_app + deals_locacao_showroom)

    # Venda: M-1 (paga no mês seguinte ao fechamento)
    inicio_venda = _primeiro_dia_mes(mes_referencia - relativedelta(months=1))
    fim_venda = _ultimo_dia_mes(mes_referencia - relativedelta(months=1))
    deals_venda = bitrix.buscar_deals(bitrix.PIPELINE_VENDA, inicio_venda, fim_venda)

    return deals_locacao + deals_venda


def _contar_deals_geral_mes(mes_referencia: date) -> int:
    """Conta o total de deals WON em M-1 (todos pipelines, todos vendedores).

    Meta é mensal: pagamento em maio → nível baseado nos deals de abril (M-1).
    Locação é deduplicada (P48 vs P0) por (CPF, placa).
    """
    inicio = _primeiro_dia_mes(mes_referencia - relativedelta(months=1))
    fim = _ultimo_dia_mes(mes_referencia - relativedelta(months=1))

    deals_loc_app = bitrix.buscar_deals(bitrix.PIPELINE_LOCACAO, inicio, fim)
    deals_loc_showroom = bitrix.buscar_deals(bitrix.PIPELINE_LOCACAO_SHOWROOM, inicio, fim)
    deals_locacao = _dedup_locacao(deals_loc_app + deals_loc_showroom)
    deals_venda = bitrix.buscar_deals(bitrix.PIPELINE_VENDA, inicio, fim)

    return len(deals_locacao) + len(deals_venda)


def montar_relatorio(
    vendedor_id: int,
    vendedor_nome: str,
    mes_referencia: date,
    qtd_meta: int,
) -> RelatorioData:
    """Monta os dados completos do relatório de comissão de um vendedor.

    - Locação + Venda no mesmo relatório.
    - Nível calculado pelo total GERAL de captações da empresa no mês.
    - Meta informada pelo RH = Prata (100%). Bronze=75%, Ouro=125%.
    - Comissão calculada sobre valor pago (MicroWork).
    """

    # 1. Buscar deals de ambos os pipelines para comissão do vendedor
    todos_deals = _buscar_deals_ambos_pipelines(mes_referencia)
    deals_vendedor = [d for d in todos_deals if d.assigned_by_id == vendedor_id]

    # 2. Vendedor — nome vem do app (webhook sem scope user)
    vendedor = Vendedor(id=vendedor_id, nome=vendedor_nome)

    # 3. Buscar pagamentos do MicroWork — período amplo
    inicio_pagamentos = _primeiro_dia_mes(mes_referencia - relativedelta(months=2))
    fim_pagamentos = _ultimo_dia_mes(mes_referencia)
    pagamentos = microwork.buscar_recebimentos(inicio_pagamentos, fim_pagamentos)

    pagamentos_por_cpf: dict[str, list[Pagamento]] = {}
    for p in pagamentos:
        cpf = _normalize_cpf(p.cpf_cnpj)
        if cpf:
            pagamentos_por_cpf.setdefault(cpf, []).append(p)

    # 4. Calcular nível — total GERAL da empresa no mês vs meta
    qtd_geral = _contar_deals_geral_mes(mes_referencia)
    nivel = calcular_nivel(qtd_geral, qtd_meta)

    # 5. negocios_fechados será calculado após montar itens (mesmo universo)

    # 6. Buscar devoluções por placa (Pipeline 22)
    placas_vendedor = [d.placa for d in deals_vendedor if d.placa]
    devolucoes = bitrix.buscar_devolucoes_por_placas(placas_vendedor)

    # 7. Montar itens de comissão
    itens: list[ComissaoItem] = []
    negocios_encerrados = 0

    for deal in deals_vendedor:
        data_ref = deal.data_locacao or deal.data_fechamento
        if not data_ref:
            continue

        meses_diff = (
            (mes_referencia.year - data_ref.year) * 12
            + mes_referencia.month - data_ref.month
        )

        # Parcela depende do tipo de operação
        if deal.pipeline_id == bitrix.PIPELINE_LOCACAO:
            parcela_num = meses_diff
            if parcela_num < 1 or parcela_num > 2:
                continue
            parcela_str = f"{parcela_num}/2"
        else:
            # Venda: parcela única, paga em M+1
            if meses_diff != 1:
                continue
            parcela_str = "1/1"

        # CPF do deal para cruzar com MicroWork
        cpf_deal = _normalize_cpf(deal.cpf_cnpj_deal)
        if not cpf_deal and deal.contact_id:
            cpf_deal = bitrix.buscar_cpf_contato(deal.contact_id)

        # Placa
        placa = deal.placa
        if not placa and deal.contact_id:
            placa = bitrix.buscar_placa_contato(deal.contact_id)

        # Devolução pela placa + mesmo contato + cronologia
        deal_devolvido = False
        data_devolucao = None
        if placa and placa in devolucoes and deal.data_locacao:
            devs_posteriores = [
                dev for dev in devolucoes[placa]
                if dev["data_devolucao"] > deal.data_locacao
                and dev.get("contact_id") == deal.contact_id
            ]
            if devs_posteriores:
                dev_mais_proxima = min(devs_posteriores, key=lambda d: d["data_devolucao"])
                deal_devolvido = True
                data_devolucao = dev_mais_proxima["data_devolucao"]
                negocios_encerrados += 1

        # Nome do cliente
        nome_cliente = deal.titulo
        pagamentos_cliente = pagamentos_por_cpf.get(cpf_deal, [])
        if pagamentos_cliente:
            nome_cliente = pagamentos_cliente[0].pessoa

        # Base de cálculo:
        # - Locação SEMANAL: cada parcela olha seu próprio mês-base
        #   1/2 = boletos do mês do fechamento
        #   2/2 = boletos do mês seguinte ao fechamento
        # - Locação MENSAL: ambas parcelas usam o mês do fechamento (1 boleto mensal)
        #   e a comissão total é dividida igualmente em 1/2 e 2/2.
        # - Venda: base = deal.valor (card Bitrix direto).
        tipo_op = _tipo_operacao_do_pipeline(deal.pipeline_id)
        if deal.pipeline_id == bitrix.PIPELINE_LOCACAO:
            if deal.plano_semanal:
                mes_base = _mes_base_parcela(data_ref, parcela_str)
            else:
                # Mensal: ambas as parcelas calculam sobre o mesmo mês (fechamento)
                mes_base = _primeiro_dia_mes(data_ref)
            boletos = _boletos_no_mes(
                pagamentos_por_cpf, cpf_deal, mes_base, apenas_aluguel=True
            )
            soma_boletos = sum((b.valor_total for b in boletos), Decimal("0"))
            if deal.plano_semanal:
                # Semanal: quantidade efetiva = soma pago / card (arredondado).
                # - Descarta juros/multa (pagou R$833 com card R$276 → 3 parcelas, não 4)
                # - Protege pagamento parcial (pagou R$176 de R$276 → 1 parcela)
                # - Reconhece boleto multi-período (1 boleto de R$552 = 2 semanas)
                # - Teto de 4 semanas/mês: cliente que pagou 5+ semanalidades no mês
                #   não infla a comissão — base máxima é 4× o card.
                if deal.valor > 0:
                    qtd_parcelas = int(
                        (soma_boletos / deal.valor).quantize(
                            Decimal("1"), rounding=ROUND_HALF_UP
                        )
                    )
                    qtd_parcelas = min(qtd_parcelas, 4)
                else:
                    qtd_parcelas = 0
            else:
                # Mensal: 1 boleto por mês é o esperado.
                # Se o cliente antecipou a próxima mensalidade no mesmo mês,
                # isso NÃO infla a comissão — base continua sendo 1× o card.
                # qtd = 1 se pagou pelo menos 1 boleto de aluguel, 0 caso contrário.
                qtd_parcelas = 1 if boletos else 0
            valor_base = deal.valor * qtd_parcelas
        else:
            valor_base = deal.valor
            qtd_parcelas = 1  # venda = 1 parcela (o próprio card)

        # Comissão — zero se devolvido
        valor_comissao = Decimal("0")
        if not deal_devolvido and nivel.nome in ("Bronze", "Prata", "Ouro"):
            valor_comissao = calcular_comissao(valor_base, tipo_op, nivel.nome)
            # Mensal: comissão total dividida em 2 parcelas iguais
            if (
                deal.pipeline_id == bitrix.PIPELINE_LOCACAO
                and not deal.plano_semanal
            ):
                valor_comissao = (valor_comissao / Decimal("2")).quantize(
                    Decimal("0.01")
                )

        itens.append(
            ComissaoItem(
                parcela=parcela_str,
                nome_cliente=nome_cliente,
                cpf_cliente=cpf_deal,
                placa=placa,
                data_locacao=deal.data_locacao,
                data_retorno=None,
                valor_base=valor_base,
                valor_comissao=valor_comissao,
                tipo_operacao=tipo_op,
                data_devolucao=data_devolucao,
                devolvido=deal_devolvido,
                plano_semanal=deal.plano_semanal,
                qtd_parcelas_pagas=qtd_parcelas,
            )
        )

    itens.sort(key=lambda i: i.data_locacao or date.min)
    total_comissao = sum((item.valor_comissao for item in itens), Decimal("0"))
    negocios_fechados = len(itens)

    return RelatorioData(
        vendedor=vendedor,
        competencia=mes_referencia,
        nivel=nivel,
        negocios_fechados=negocios_fechados,
        negocios_encerrados=negocios_encerrados,
        itens=itens,
        total_comissao=total_comissao,
    )


# ─── Dashboard ─────────────────────────────────────────────────────────
def _deals_captados_no_mes(mes_captacao: date) -> list[Deal]:
    """Busca todos os deals (Locação P48+P0 dedup, Venda P40) com data de
    captação dentro do mês calendário."""
    inicio = _primeiro_dia_mes(mes_captacao)
    fim = _ultimo_dia_mes(mes_captacao)

    deals_loc_app = bitrix.buscar_deals(bitrix.PIPELINE_LOCACAO, inicio, fim)
    deals_loc_showroom = bitrix.buscar_deals(bitrix.PIPELINE_LOCACAO_SHOWROOM, inicio, fim)
    deals_locacao = _dedup_locacao(deals_loc_app + deals_loc_showroom)
    deals_venda = bitrix.buscar_deals(bitrix.PIPELINE_VENDA, inicio, fim)

    return deals_locacao + deals_venda


def captacoes_no_mes(
    mes_captacao: date,
    vendedores: dict[int, str],
) -> CaptacoesMes:
    """Snapshot do dashboard — captações da empresa no mês calendário.

    Diferente de `montar_relatorio` (mês de pagamento, M-1/M-2 lookback):
    aqui o filtro é mês de captação puro. Filtrar abril/2026 retorna só
    deals com data_locacao em 01/04 a 30/04.

    Não toca no MicroWork — é um agregado leve (Bitrix only).
    """
    todos_deals = _deals_captados_no_mes(mes_captacao)

    # Devoluções pelas placas dos deals captados
    placas = [d.placa for d in todos_deals if d.placa]
    devolucoes_por_placa = bitrix.buscar_devolucoes_por_placas(placas) if placas else {}

    # Totais empresa-wide por tipo
    locacoes_total = sum(
        1 for d in todos_deals
        if d.pipeline_id in (bitrix.PIPELINE_LOCACAO, bitrix.PIPELINE_LOCACAO_SHOWROOM)
    )
    vendas_total = sum(1 for d in todos_deals if d.pipeline_id == bitrix.PIPELINE_VENDA)

    # Captações do TIME por dia do mês (1..31)
    captacoes_por_dia: dict[int, int] = {}
    for d in todos_deals:
        if d.assigned_by_id in vendedores and d.data_locacao:
            dia = d.data_locacao.day
            captacoes_por_dia[dia] = captacoes_por_dia.get(dia, 0) + 1

    # Agrupa por vendedor (só os que estão no mapa de ativos)
    por_vid: dict[int, list[CaptacaoItem]] = {vid: [] for vid in vendedores}

    for d in todos_deals:
        if d.assigned_by_id not in vendedores:
            continue

        # Detecta devolução: placa coincide + contato coincide + posterior à locação
        deal_devolvido = False
        data_dev: date | None = None
        if d.placa and d.data_locacao and d.placa in devolucoes_por_placa:
            posteriores = [
                dev for dev in devolucoes_por_placa[d.placa]
                if dev["data_devolucao"] > d.data_locacao
                and dev.get("contact_id") == d.contact_id
            ]
            if posteriores:
                mais_proxima = min(posteriores, key=lambda x: x["data_devolucao"])
                deal_devolvido = True
                data_dev = mais_proxima["data_devolucao"]

        por_vid[d.assigned_by_id].append(CaptacaoItem(
            deal_id=d.id,
            tipo_operacao=_tipo_operacao_do_pipeline(d.pipeline_id),
            nome_cliente=d.titulo,
            placa=d.placa or None,
            data_locacao=d.data_locacao,
            data_devolucao=data_dev,
            devolvido=deal_devolvido,
        ))

    por_vendedor = [
        CaptacoesVendedor(
            vendedor_id=vid,
            nome=nome,
            itens=sorted(itens, key=lambda i: i.data_locacao or date.min, reverse=True),
        )
        for vid, nome in vendedores.items()
        for itens in [por_vid[vid]]
    ]

    return CaptacoesMes(
        mes=_primeiro_dia_mes(mes_captacao),
        total_empresa=len(todos_deals),
        locacoes_total=locacoes_total,
        vendas_total=vendas_total,
        captacoes_por_dia=captacoes_por_dia,
        por_vendedor=por_vendedor,
    )


def _projetar(parcial: int, du_decorridos: float, du_total: float) -> int:
    """Projeta um total de mês a partir do parcial e dos dias úteis decorridos."""
    if du_decorridos <= 0:
        return parcial
    return int(round(parcial / du_decorridos * du_total))


def _fetch_deals_paralelo(meses: list[date]) -> dict[date, list[Deal]]:
    """Busca deals (P48 + P0 dedup + P40) para vários meses em paralelo.

    Faz 3 chamadas Bitrix POR mês, todas disparadas simultaneamente.
    Para 2 meses = 6 chamadas paralelas em vez de 6 sequenciais.
    """
    janelas: list[tuple[date, int, date, date]] = []
    for mes in meses:
        ini = _primeiro_dia_mes(mes)
        fim = _ultimo_dia_mes(mes)
        for pid in (
            bitrix.PIPELINE_LOCACAO,
            bitrix.PIPELINE_LOCACAO_SHOWROOM,
            bitrix.PIPELINE_VENDA,
        ):
            janelas.append((mes, pid, ini, fim))

    def _do(args):
        mes, pid, ini, fim = args
        return mes, pid, bitrix.buscar_deals(pid, ini, fim)

    out: dict[date, dict[int, list[Deal]]] = {m: {} for m in meses}
    with ThreadPoolExecutor(max_workers=len(janelas)) as ex:
        for mes, pid, deals in ex.map(_do, janelas):
            out[mes][pid] = deals

    final: dict[date, list[Deal]] = {}
    for mes in meses:
        loc = _dedup_locacao(
            out[mes][bitrix.PIPELINE_LOCACAO]
            + out[mes][bitrix.PIPELINE_LOCACAO_SHOWROOM]
        )
        venda = out[mes][bitrix.PIPELINE_VENDA]
        final[mes] = loc + venda
    return final


def _build_captacoes_mes_de_deals(
    mes_captacao: date,
    todos_deals: list[Deal],
    devolucoes_por_placa: dict[str, list[dict]],
    vendedores: dict[int, str],
    faturamento_mes: Decimal = Decimal("0"),
) -> CaptacoesMes:
    """Variante de `captacoes_no_mes` que recebe deals + devoluções já buscados.

    Permite reutilizar buscas paralelizadas (atual + anterior compartilham
    o pool de devoluções).

    `faturamento_mes` é a soma de boletos de aluguel (MicroWork) com data de
    movimento dentro do mês — calculada externamente e injetada aqui.
    """
    locacoes_total = sum(
        1 for d in todos_deals
        if d.pipeline_id in (bitrix.PIPELINE_LOCACAO, bitrix.PIPELINE_LOCACAO_SHOWROOM)
    )
    vendas_total = sum(1 for d in todos_deals if d.pipeline_id == bitrix.PIPELINE_VENDA)

    # Mix semanal × mensal — só tem semântica em locação (venda é parcela única)
    locacoes_semanal = sum(
        1 for d in todos_deals
        if d.pipeline_id in (bitrix.PIPELINE_LOCACAO, bitrix.PIPELINE_LOCACAO_SHOWROOM)
        and d.plano_semanal
    )
    locacoes_mensal = locacoes_total - locacoes_semanal

    # Captações por dia — empresa toda (não só o time conhecido)
    captacoes_por_dia: dict[int, int] = {}
    for d in todos_deals:
        if d.data_locacao:
            dia = d.data_locacao.day
            captacoes_por_dia[dia] = captacoes_por_dia.get(dia, 0) + 1

    # Auto-descobre TODOS os captadores que aparecem nos deals
    captadores_ids: set[int] = {d.assigned_by_id for d in todos_deals if d.assigned_by_id}
    por_vid: dict[int, list[CaptacaoItem]] = {vid: [] for vid in captadores_ids}
    captacoes_flat: list[CaptacaoItem] = []
    devolvidos_total = 0

    for d in todos_deals:
        deal_devolvido = False
        data_dev: date | None = None
        if d.placa and d.data_locacao and d.placa in devolucoes_por_placa:
            posteriores = [
                dev for dev in devolucoes_por_placa[d.placa]
                if dev["data_devolucao"] > d.data_locacao
                and dev.get("contact_id") == d.contact_id
            ]
            if posteriores:
                mais_proxima = min(posteriores, key=lambda x: x["data_devolucao"])
                deal_devolvido = True
                data_dev = mais_proxima["data_devolucao"]

        if deal_devolvido:
            devolvidos_total += 1

        item = CaptacaoItem(
            deal_id=d.id,
            tipo_operacao=_tipo_operacao_do_pipeline(d.pipeline_id),
            nome_cliente=d.titulo,
            placa=d.placa or None,
            data_locacao=d.data_locacao,
            data_devolucao=data_dev,
            devolvido=deal_devolvido,
            source_id=d.source_id,
            cidade=d.cidade,
            plano_semanal=d.plano_semanal,
        )
        captacoes_flat.append(item)

        if d.assigned_by_id:
            por_vid[d.assigned_by_id].append(item)

    # Nome: VENDEDORES → LIDERES → fallback "Vendedor #ID"
    por_vendedor = [
        CaptacoesVendedor(
            vendedor_id=vid,
            nome=vendedores.get(vid, f"Vendedor #{vid}"),
            itens=sorted(por_vid[vid], key=lambda i: i.data_locacao or date.min, reverse=True),
        )
        for vid in sorted(captadores_ids, key=lambda v: -len(por_vid[v]))
    ]

    return CaptacoesMes(
        mes=_primeiro_dia_mes(mes_captacao),
        total_empresa=len(todos_deals),
        locacoes_total=locacoes_total,
        vendas_total=vendas_total,
        captacoes_por_dia=captacoes_por_dia,
        por_vendedor=por_vendedor,
        faturamento=faturamento_mes,
        locacoes_semanal=locacoes_semanal,
        locacoes_mensal=locacoes_mensal,
        devolvidos_total=devolvidos_total,
        captacoes_flat=captacoes_flat,
    )


def _faturamento_por_mes(
    pagamentos: list[Pagamento],
    meses: list[date],
) -> dict[date, Decimal]:
    """Agrupa boletos de aluguel (filtro `_eh_boleto_aluguel`) por mês de movimento.

    Retorna `{primeiro_dia_do_mes: soma_valor_total}`. Meses sem pagamento
    aparecem com Decimal("0") pra evitar KeyError no consumidor.

    Importante: usa o mesmo filtro do orchestrator de comissão pra garantir
    consistência — descarta NF-E (taxas), franquia, multa, reembolso, etc.
    """
    out: dict[date, Decimal] = {_primeiro_dia_mes(m): Decimal("0") for m in meses}
    for p in pagamentos:
        if not _eh_boleto_aluguel(p):
            continue
        chave = _primeiro_dia_mes(p.movimento)
        if chave in out:
            out[chave] += p.valor_total
    return out


def _projetar_dec(parcial: Decimal, du_decorridos: float, du_total: float) -> Decimal:
    """Projeta valor monetário a partir do parcial e dos dias úteis decorridos."""
    if du_decorridos <= 0:
        return parcial
    fator = Decimal(str(du_total / du_decorridos))
    return (parcial * fator).quantize(Decimal("0.01"))


def captacoes_comparadas(
    mes_atual: date,
    vendedores: dict[int, str],
    hoje: date | None = None,
) -> CaptacoesComparadas:
    """Compara captações do mês atual com o mês anterior + projeção.

    Performance: 6 chamadas Bitrix de deals em paralelo + 1 fetch
    consolidado de pagamentos MicroWork + 1 chamada consolidada
    de devoluções (já paralelizada internamente por placa).
    """
    if hoje is None:
        hoje = date.today()

    mes_anterior = (mes_atual - relativedelta(months=1)).replace(day=1)

    # 1. Busca deals dos 2 meses em paralelo (6 chamadas Bitrix simultâneas)
    deals_por_mes = _fetch_deals_paralelo([mes_atual, mes_anterior])

    # 2. Pagamentos MicroWork — 1 fetch único cobrindo a janela inteira
    inicio_pgto = _primeiro_dia_mes(mes_anterior)
    fim_pgto = _ultimo_dia_mes(mes_atual)
    pagamentos = microwork.buscar_recebimentos(inicio_pgto, fim_pgto)
    fat_por_mes = _faturamento_por_mes(pagamentos, [mes_anterior, mes_atual])

    # 3. Devoluções: consolida placas dos 2 meses numa única chamada
    todas_placas = [
        d.placa
        for ds in deals_por_mes.values()
        for d in ds
        if d.placa
    ]
    devolucoes_por_placa = (
        bitrix.buscar_devolucoes_por_placas(todas_placas) if todas_placas else {}
    )

    atual = _build_captacoes_mes_de_deals(
        mes_atual, deals_por_mes[mes_atual], devolucoes_por_placa, vendedores,
        faturamento_mes=fat_por_mes[_primeiro_dia_mes(mes_atual)],
    )
    anterior = _build_captacoes_mes_de_deals(
        mes_anterior, deals_por_mes[mes_anterior], devolucoes_por_placa, vendedores,
        faturamento_mes=fat_por_mes[_primeiro_dia_mes(mes_anterior)],
    )

    du_total = du_mes(mes_atual)
    du_total_ant = du_mes(mes_anterior)

    # Se o mês escolhido já é passado, du_decorridos = du_total (sem projeção)
    fim_mes = _ultimo_dia_mes(mes_atual)
    if hoje >= fim_mes:
        du_decorridos = du_total
    else:
        du_decorridos = du_ate_hoje(mes_atual, hoje)

    # Projeções a partir do EMPRESA total (não só time conhecido)
    return CaptacoesComparadas(
        atual=atual,
        anterior=anterior,
        projecao_total=_projetar(atual.total_empresa, du_decorridos, du_total),
        projecao_locacoes=_projetar(atual.locacoes_total, du_decorridos, du_total),
        projecao_vendas=_projetar(atual.vendas_total, du_decorridos, du_total),
        projecao_faturamento=_projetar_dec(atual.faturamento, du_decorridos, du_total),
        du_mes_atual=du_total,
        du_decorridos_atual=du_decorridos,
        du_mes_anterior=du_total_ant,
    )


def _meses_ate(mes_floor: date, mes_topo: date) -> list[date]:
    """Lista de primeiros-dia-do-mês de `mes_floor` até `mes_topo`, inclusivo."""
    floor = _primeiro_dia_mes(mes_floor)
    topo = _primeiro_dia_mes(mes_topo)
    out: list[date] = []
    m = floor
    while m <= topo:
        out.append(m)
        m = (m + relativedelta(months=1)).replace(day=1)
    return out


def cmp_de_serie(
    serie: list[CaptacoesMes],
    mes_atual: date,
    hoje: date | None = None,
) -> CaptacoesComparadas:
    """Constrói CaptacoesComparadas reusando uma série já materializada.

    Evita refetch quando o dashboard já chamou `serie_historica` — o mês
    atual e o anterior estão na série, e a projeção é só aritmética em
    cima dos dias úteis.
    """
    if hoje is None:
        hoje = date.today()

    mes_atual = _primeiro_dia_mes(mes_atual)
    mes_anterior = (mes_atual - relativedelta(months=1)).replace(day=1)

    snap_por_mes = {s.mes: s for s in serie}
    atual = snap_por_mes.get(mes_atual)
    anterior = snap_por_mes.get(mes_anterior)

    if atual is None or anterior is None:
        # Mês fora da janela da série — sinaliza com snapshot vazio
        # pra UI cair nos empty states em vez de quebrar.
        from src.models import CaptacoesMes as _CM
        if atual is None:
            atual = _CM(mes=mes_atual, total_empresa=0, locacoes_total=0,
                        vendas_total=0, captacoes_por_dia={}, por_vendedor=[])
        if anterior is None:
            anterior = _CM(mes=mes_anterior, total_empresa=0, locacoes_total=0,
                           vendas_total=0, captacoes_por_dia={}, por_vendedor=[])

    du_total = du_mes(mes_atual)
    du_total_ant = du_mes(mes_anterior)

    fim_mes = _ultimo_dia_mes(mes_atual)
    du_decorridos = du_total if hoje >= fim_mes else du_ate_hoje(mes_atual, hoje)

    return CaptacoesComparadas(
        atual=atual,
        anterior=anterior,
        projecao_total=_projetar(atual.total_empresa, du_decorridos, du_total),
        projecao_locacoes=_projetar(atual.locacoes_total, du_decorridos, du_total),
        projecao_vendas=_projetar(atual.vendas_total, du_decorridos, du_total),
        projecao_faturamento=_projetar_dec(atual.faturamento, du_decorridos, du_total),
        du_mes_atual=du_total,
        du_decorridos_atual=du_decorridos,
        du_mes_anterior=du_total_ant,
    )


def serie_historica(
    mes_floor: date,
    mes_topo: date,
    vendedores: dict[int, str],
) -> list[CaptacoesMes]:
    """Série de CaptacoesMes mês-a-mês do `mes_floor` até `mes_topo` (inclusivo).

    Tudo em paralelo (3 chamadas Bitrix por mês × N meses, gated em 4
    conexões simultâneas pelo semáforo do bitrix client) + 1 fetch
    MicroWork consolidado pra toda a janela (faturamento por mês) +
    1 chamada consolidada de devoluções pra todas as placas da janela.

    Para 6 meses: 18 chamadas Bitrix em ondas de 4 + 1 MicroWork (em
    paralelo com o primeiro batch de Bitrix) + 1 devoluções.
    """
    meses = _meses_ate(mes_floor, mes_topo)
    if not meses:
        return []

    # Roda Bitrix (deals) e MicroWork (pagamentos) em paralelo: o MicroWork
    # é uma única chamada de ~5-15s que cabe dentro da janela do Bitrix.
    inicio_pgto = _primeiro_dia_mes(meses[0])
    fim_pgto = _ultimo_dia_mes(meses[-1])

    with ThreadPoolExecutor(max_workers=2) as ex:
        fut_deals = ex.submit(_fetch_deals_paralelo, meses)
        fut_pagamentos = ex.submit(microwork.buscar_recebimentos, inicio_pgto, fim_pgto)
        deals_por_mes = fut_deals.result()
        pagamentos = fut_pagamentos.result()

    fat_por_mes = _faturamento_por_mes(pagamentos, meses)

    todas_placas = [
        d.placa
        for ds in deals_por_mes.values()
        for d in ds
        if d.placa
    ]
    devolucoes_por_placa = (
        bitrix.buscar_devolucoes_por_placas(todas_placas) if todas_placas else {}
    )

    return [
        _build_captacoes_mes_de_deals(
            mes, deals_por_mes[mes], devolucoes_por_placa, vendedores,
            faturamento_mes=fat_por_mes[_primeiro_dia_mes(mes)],
        )
        for mes in meses
    ]
