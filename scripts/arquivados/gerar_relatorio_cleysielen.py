"""Relatório de comissão Cleysielen — transição de regra de pagamento.

Regra antiga (apuração 26→25):
- Parcela 1/2 (ciclo atual, captações que agora começam a pagar):
  deals com data_locacao entre 26/03/2026 e 20/04/2026
- Parcela 2/2 (ciclo anterior, 2ª parcela dos deals que já pagaram 1/2):
  deals com data_locacao entre 01/03/2026 e 25/03/2026

Nível da empresa é apurado sobre a janela do ciclo atual (26/03-20/04).
"""

import io
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from src.business.comissao import TABELA_COMISSAO, calcular_comissao, calcular_nivel
from src.business.orchestrator import (
    _boletos_no_mes,
    _mes_base_parcela,
    _normalize_cpf,
)
from src.data import bitrix, microwork
from src.export.pdf import gerar_pdf
from src.models import ComissaoItem, Pagamento, RelatorioData, Vendedor

CLEYSIELEN_ID = 83302
CLEYSIELEN_NOME = "Cleysielen"

# Janela 1/2 — ciclo atual (usada também p/ cálculo de nível da empresa)
INICIO_1 = date(2026, 3, 26)
FIM_1 = date(2026, 4, 20)

# Janela 2/2 — ciclo anterior (deals antigos, 2ª parcela)
INICIO_2 = date(2026, 3, 1)
FIM_2 = date(2026, 3, 25)

META_EMPRESA = 124
COMPETENCIA = date(2026, 4, 1)  # pagamento referente a abril/2026
OUT_PATH = Path(__file__).parent / "relatorio_cleysielen_26mar_20abr.pdf"


def _tipo_operacao(pipeline_id: int) -> str:
    if pipeline_id == bitrix.PIPELINE_LOCACAO:
        return "Locação"
    if pipeline_id == bitrix.PIPELINE_VENDA:
        return "Venda 0km"
    return "Outro"


def _buscar_deals_janela(inicio: date, fim: date) -> tuple[list, list]:
    loc = bitrix.buscar_deals(bitrix.PIPELINE_LOCACAO, inicio, fim)
    venda = bitrix.buscar_deals(bitrix.PIPELINE_VENDA, inicio, fim)
    return loc, venda


def main() -> None:
    print(f"\n{'=' * 70}")
    print(f"  RELATÓRIO CLEYSIELEN — Transição regra antiga")
    print(f"  1/2: {INICIO_1} a {FIM_1}  |  2/2: {INICIO_2} a {FIM_2}")
    print(f"{'=' * 70}\n")

    # ── 1. Apuração do nível (empresa, janela ciclo atual) ──
    print("── Apurando nível (empresa — janela 26/03 a 20/04) ──")
    loc_atual, venda_atual = _buscar_deals_janela(INICIO_1, FIM_1)
    qtd_geral = len(loc_atual) + len(venda_atual)
    print(f"  Pipeline 48 (Locação): {len(loc_atual)}")
    print(f"  Pipeline 40 (Venda):   {len(venda_atual)}")
    print(f"  TOTAL: {qtd_geral} captações vs meta {META_EMPRESA}")

    nivel = calcular_nivel(qtd_geral, META_EMPRESA)
    print(f"  Nível: {nivel.nome} ({nivel.percentual_atingido}%)\n")

    # ── 2. Deals da Cleysielen nas duas janelas ──
    deals_atual = [
        d for d in (loc_atual + venda_atual) if d.assigned_by_id == CLEYSIELEN_ID
    ]

    print("── Apurando janela anterior (01/03 a 25/03) ──")
    loc_ant, venda_ant = _buscar_deals_janela(INICIO_2, FIM_2)
    deals_anteriores = [
        d for d in (loc_ant + venda_ant) if d.assigned_by_id == CLEYSIELEN_ID
    ]
    print(f"  Deals 01/03-25/03 da Cleysielen: {len(deals_anteriores)}")
    print(f"  Deals 26/03-20/04 da Cleysielen: {len(deals_atual)}\n")

    todos_deals = [(d, "2/2") for d in deals_anteriores] + [
        (d, "1/2") for d in deals_atual
    ]
    for d, parc in todos_deals:
        print(
            f"  [{parc}] #{d.id} | {d.data_locacao} | pipeline {d.pipeline_id} | "
            f"{d.titulo[:40]} | placa={d.placa}"
        )
    print()

    # ── 3. Pagamentos MicroWork (janela ampla p/ cobrir tudo) ──
    print("── Buscando pagamentos MicroWork ──")
    pagamentos = microwork.buscar_recebimentos(INICIO_2, FIM_1)
    print(f"  Total recebimentos: {len(pagamentos)}")

    pag_por_cpf: dict[str, list[Pagamento]] = {}
    for p in pagamentos:
        cpf = _normalize_cpf(p.cpf_cnpj)
        if cpf:
            pag_por_cpf.setdefault(cpf, []).append(p)

    # ── 4. Devoluções ──
    placas = [d.placa for d, _ in todos_deals if d.placa]
    devolucoes = bitrix.buscar_devolucoes_por_placas(placas)

    # ── 5. Montar itens ──
    itens: list[ComissaoItem] = []
    negocios_encerrados = 0

    for deal, parcela in todos_deals:
        cpf_deal = _normalize_cpf(deal.cpf_cnpj_deal)
        if not cpf_deal and deal.contact_id:
            cpf_deal = bitrix.buscar_cpf_contato(deal.contact_id)

        placa = deal.placa
        if not placa and deal.contact_id:
            placa = bitrix.buscar_placa_contato(deal.contact_id)

        deal_devolvido = False
        data_devolucao = None
        if placa and placa in devolucoes and deal.data_locacao:
            devs_posteriores = [
                dev for dev in devolucoes[placa]
                if dev["data_devolucao"] > deal.data_locacao
                and dev.get("contact_id") == deal.contact_id
            ]
            if devs_posteriores:
                dev_proxima = min(devs_posteriores, key=lambda d: d["data_devolucao"])
                deal_devolvido = True
                data_devolucao = dev_proxima["data_devolucao"]
                negocios_encerrados += 1

        nome_cliente = deal.titulo
        pagamentos_cliente = pag_por_cpf.get(cpf_deal, [])
        if pagamentos_cliente:
            nome_cliente = pagamentos_cliente[0].pessoa

        tipo_op = _tipo_operacao(deal.pipeline_id)
        if deal.pipeline_id == bitrix.PIPELINE_LOCACAO:
            if deal.plano_semanal:
                mes_base = _mes_base_parcela(deal.data_locacao, parcela)
            else:
                mes_base = deal.data_locacao.replace(day=1)
            boletos = _boletos_no_mes(
                pag_por_cpf, cpf_deal, mes_base, apenas_aluguel=True
            )
            soma_boletos = sum((b.valor_total for b in boletos), Decimal("0"))
            # qtd efetiva = soma / card arredondada (descarta juros, reconhece multi-período)
            if deal.valor > 0:
                qtd_parcelas = int(
                    (soma_boletos / deal.valor).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )
            else:
                qtd_parcelas = 0
            valor_base = deal.valor * qtd_parcelas
        else:
            valor_base = deal.valor
            qtd_parcelas = 1

        valor_comissao = Decimal("0")
        if not deal_devolvido and nivel.nome in ("Bronze", "Prata", "Ouro"):
            valor_comissao = calcular_comissao(valor_base, tipo_op, nivel.nome)
            # Mensal: comissão dividida em 2 parcelas iguais
            if (
                deal.pipeline_id == bitrix.PIPELINE_LOCACAO
                and not deal.plano_semanal
            ):
                valor_comissao = (valor_comissao / Decimal("2")).quantize(
                    Decimal("0.01")
                )

        itens.append(
            ComissaoItem(
                parcela=parcela,
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

    itens.sort(key=lambda i: (i.parcela, i.data_locacao or date.min))
    total_comissao = sum((item.valor_comissao for item in itens), Decimal("0"))

    # ── 6. Gerar PDF ──
    relatorio = RelatorioData(
        vendedor=Vendedor(id=CLEYSIELEN_ID, nome=CLEYSIELEN_NOME),
        competencia=COMPETENCIA,
        nivel=nivel,
        negocios_fechados=len(itens),
        negocios_encerrados=negocios_encerrados,
        itens=itens,
        total_comissao=total_comissao,
    )

    pdf_bytes = gerar_pdf(relatorio)
    OUT_PATH.write_bytes(pdf_bytes)

    # ── 7. Resumo ──
    print(f"\n{'=' * 70}")
    print(f"  RESUMO")
    print(f"{'=' * 70}")
    print(f"  Vendedor: {CLEYSIELEN_NOME} (ID {CLEYSIELEN_ID})")
    print(f"  1/2: {INICIO_1} a {FIM_1} ({len(deals_atual)} deals)")
    print(f"  2/2: {INICIO_2} a {FIM_2} ({len(deals_anteriores)} deals)")
    print(f"  Nível: {nivel.nome} ({nivel.percentual_atingido}% de {META_EMPRESA})")
    pct_loc = TABELA_COMISSAO["Locação"][nivel.nome] * 100
    pct_venda = TABELA_COMISSAO["Venda 0km"][nivel.nome] * 100
    print(f"  Percentuais: Locação {pct_loc}% | Venda 0km {pct_venda}%")
    print(f"  Itens totais: {len(itens)} | Devolvidos: {negocios_encerrados}")
    print(f"  TOTAL A RECEBER: R$ {total_comissao:,.2f}")
    print(f"\n  PDF gerado: {OUT_PATH}")


if __name__ == "__main__":
    main()
