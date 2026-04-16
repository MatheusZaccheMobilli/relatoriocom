"""Orquestrador — conecta dados do Bitrix + MicroWork e monta o RelatorioData."""

from datetime import date
from decimal import Decimal
from dateutil.relativedelta import relativedelta

from src.models import ComissaoItem, Deal, Pagamento, RelatorioData, Vendedor
from src.data import bitrix, microwork
from src.business.comissao import calcular_nivel, calcular_comissao


def _normalize_cpf(raw: str) -> str:
    return "".join(c for c in raw if c.isdigit())


def _tipo_operacao_do_pipeline(pipeline_id: int) -> str:
    if pipeline_id == bitrix.PIPELINE_LOCACAO:
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
    """Soma o valor total pago por um CPF no MicroWork."""
    pagamentos = pagamentos_por_cpf.get(cpf, [])
    return sum((p.valor_total for p in pagamentos), Decimal("0"))


def _buscar_deals_ambos_pipelines(mes_referencia: date) -> list[Deal]:
    """Busca deals de AMBOS os pipelines para comissão.

    Pagamento em mês M:
      Locação: M-2 (parcela 2/2) e M-1 (parcela 1/2)
      Venda:   M-1 (parcela 1/1)
    """
    # Locação: M-2 a M-1
    inicio_loc = _primeiro_dia_mes(mes_referencia - relativedelta(months=2))
    fim_loc = _ultimo_dia_mes(mes_referencia - relativedelta(months=1))
    deals_locacao = bitrix.buscar_deals(bitrix.PIPELINE_LOCACAO, inicio_loc, fim_loc)

    # Venda: M-1 (paga no mês seguinte ao fechamento)
    inicio_venda = _primeiro_dia_mes(mes_referencia - relativedelta(months=1))
    fim_venda = _ultimo_dia_mes(mes_referencia - relativedelta(months=1))
    deals_venda = bitrix.buscar_deals(bitrix.PIPELINE_VENDA, inicio_venda, fim_venda)

    return deals_locacao + deals_venda


def _contar_deals_geral_mes(mes_referencia: date) -> int:
    """Conta o total de deals WON em M-1 (ambos pipelines, todos vendedores).

    Meta é mensal: pagamento em maio → nível baseado nos deals de abril (M-1).
    """
    inicio = _primeiro_dia_mes(mes_referencia - relativedelta(months=1))
    fim = _ultimo_dia_mes(mes_referencia - relativedelta(months=1))

    deals_loc = bitrix.buscar_deals(bitrix.PIPELINE_LOCACAO, inicio, fim)
    deals_venda = bitrix.buscar_deals(bitrix.PIPELINE_VENDA, inicio, fim)

    return len(deals_loc) + len(deals_venda)


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

        # Valor base = MicroWork, fallback = deal
        tipo_op = _tipo_operacao_do_pipeline(deal.pipeline_id)
        valor_base = _total_pago_por_cpf(pagamentos_por_cpf, cpf_deal)
        if valor_base == Decimal("0"):
            valor_base = deal.valor

        # Comissão — zero se devolvido
        valor_comissao = Decimal("0")
        if not deal_devolvido and nivel.nome in ("Bronze", "Prata", "Ouro"):
            valor_comissao = calcular_comissao(valor_base, tipo_op, nivel.nome)

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
