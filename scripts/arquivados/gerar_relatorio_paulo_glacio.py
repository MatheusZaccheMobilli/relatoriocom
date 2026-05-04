"""Relatórios de comissão Paulo + Glacio — transição de regra de pagamento (mai/2026).

Mesmo padrão do `gerar_relatorio_cleysielen.py`, mas com janela 1/2 indo até
30/04 (mês de abril fechado), não 20/04. Gera 2 PDFs em `output/`.

Regra:
- Parcela 1/2 (ciclo atual): deals com data_locacao entre 26/03/2026 e 30/04/2026
- Parcela 2/2 (ciclo anterior): deals com data_locacao entre 01/03/2026 e 25/03/2026
- Nível da empresa apurado sobre a janela do ciclo atual (1/2)
- Cap de 4 parcelas/mês no semanal (regra nova de mai/2026)
- Ouro = 132% (regra nova de mai/2026, já em src/business/comissao.py)
"""

import io
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from src.business.comissao import TABELA_COMISSAO, calcular_comissao, calcular_nivel
from src.business.orchestrator import (
    _boletos_no_mes,
    _dedup_locacao,
    _mes_base_parcela,
    _normalize_cpf,
)
from src.data import bitrix, microwork
from src.export.pdf import gerar_pdf
from src.export.xlsx import gerar_xlsx
from src.models import ComissaoItem, Pagamento, RelatorioData, Vendedor

# Janelas de transição
INICIO_1 = date(2026, 3, 26)
FIM_1 = date(2026, 4, 30)
INICIO_2 = date(2026, 3, 1)
FIM_2 = date(2026, 3, 25)

META_EMPRESA = 124
COMPETENCIA = date(2026, 5, 1)  # pagamento em maio/2026 (apuração 26/03 a 30/04)

# Vendedores deste relatório (basename — extensão é adicionada na geração)
VENDEDORES = [
    {"id": 83518, "nome": "Paulo", "basename": "relatorio paulo"},
    {"id": 83700, "nome": "Glacio", "basename": "relatorio glacio"},
]

OUTPUT_DIR = PROJECT_ROOT / "output"


def _tipo_operacao(pipeline_id: int) -> str:
    if pipeline_id in (bitrix.PIPELINE_LOCACAO, bitrix.PIPELINE_LOCACAO_SHOWROOM):
        return "Locação"
    if pipeline_id == bitrix.PIPELINE_VENDA:
        return "Venda 0km"
    return "Outro"


def _buscar_deals_janela(inicio: date, fim: date) -> tuple[list, list]:
    """Busca deals dos 3 pipelines (P48, P0, P40) e dedupa locações.

    P48 (Locação APP) + P0 (Locação Showroom) são unidos e deduplicados por
    (CPF, placa) priorizando P48. P40 (Venda) volta separado.
    """
    loc_app = bitrix.buscar_deals(bitrix.PIPELINE_LOCACAO, inicio, fim)
    loc_showroom = bitrix.buscar_deals(bitrix.PIPELINE_LOCACAO_SHOWROOM, inicio, fim)
    loc = _dedup_locacao(loc_app + loc_showroom)
    venda = bitrix.buscar_deals(bitrix.PIPELINE_VENDA, inicio, fim)
    return loc, venda


def _gerar_para_vendedor(
    vendedor_id: int,
    vendedor_nome: str,
    basename: str,
    deals_atual: list,
    deals_anteriores: list,
    pag_por_cpf: dict[str, list[Pagamento]],
    nivel,
    devolucoes: dict,
) -> None:
    """Monta itens, calcula comissão, gera PDF + XLSX pra um vendedor."""
    print(f"\n{'─' * 70}")
    print(f"  Processando {vendedor_nome} (ID {vendedor_id})")
    print(f"{'─' * 70}")

    deals_v_atual = [d for d in deals_atual if d.assigned_by_id == vendedor_id]
    deals_v_anteriores = [d for d in deals_anteriores if d.assigned_by_id == vendedor_id]

    print(f"  Deals 26/03-30/04 (1/2): {len(deals_v_atual)}")
    print(f"  Deals 01/03-25/03 (2/2): {len(deals_v_anteriores)}")

    todos_deals = [(d, "2/2") for d in deals_v_anteriores] + [
        (d, "1/2") for d in deals_v_atual
    ]
    if not todos_deals:
        print(f"  Sem deals — pulando.")
        return

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
            if deal.valor > 0:
                qtd_parcelas = int(
                    (soma_boletos / deal.valor).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )
                # Cap de 4 parcelas/mês (regra nova de mai/2026)
                if deal.plano_semanal:
                    qtd_parcelas = min(qtd_parcelas, 4)
            else:
                qtd_parcelas = 0
            valor_base = deal.valor * qtd_parcelas
        else:
            valor_base = deal.valor
            qtd_parcelas = 1

        valor_comissao = Decimal("0")
        if not deal_devolvido and nivel.nome in ("Bronze", "Prata", "Ouro"):
            valor_comissao = calcular_comissao(valor_base, tipo_op, nivel.nome)
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

    relatorio = RelatorioData(
        vendedor=Vendedor(id=vendedor_id, nome=vendedor_nome),
        competencia=COMPETENCIA,
        nivel=nivel,
        negocios_fechados=len(itens),
        negocios_encerrados=negocios_encerrados,
        itens=itens,
        total_comissao=total_comissao,
    )

    pdf_bytes = gerar_pdf(relatorio)
    pdf_path = OUTPUT_DIR / f"{basename}.pdf"
    pdf_path.write_bytes(pdf_bytes)

    xlsx_bytes = gerar_xlsx(relatorio)
    xlsx_path = OUTPUT_DIR / f"{basename}.xlsx"
    xlsx_path.write_bytes(xlsx_bytes)

    print(f"  Itens totais: {len(itens)} | Devolvidos: {negocios_encerrados}")
    print(f"  TOTAL A RECEBER: R$ {total_comissao:,.2f}")
    print(f"  PDF:  {pdf_path}")
    print(f"  XLSX: {xlsx_path}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 70}")
    print(f"  RELATÓRIOS PAULO + GLACIO — Transição regra (mai/2026)")
    print(f"  1/2: {INICIO_1} a {FIM_1}  |  2/2: {INICIO_2} a {FIM_2}")
    print(f"{'=' * 70}\n")

    # Apuração do nível da empresa (janela 1/2) — uma vez só, vale pros dois
    print("── Apurando nível da empresa (26/03 a 30/04) ──")
    loc_atual, venda_atual = _buscar_deals_janela(INICIO_1, FIM_1)
    qtd_geral = len(loc_atual) + len(venda_atual)
    print(f"  Locação P48+P0 dedup: {len(loc_atual)}")
    print(f"  Venda P40:            {len(venda_atual)}")
    print(f"  TOTAL: {qtd_geral} captações vs meta {META_EMPRESA}")

    nivel = calcular_nivel(qtd_geral, META_EMPRESA)
    print(f"  Nível: {nivel.nome} ({nivel.percentual_atingido}%)")
    pct_loc = TABELA_COMISSAO["Locação"][nivel.nome] * 100
    pct_venda = TABELA_COMISSAO["Venda 0km"][nivel.nome] * 100
    print(f"  Percentuais: Locação {pct_loc}% | Venda 0km {pct_venda}%\n")

    # Janela anterior (1× pros dois)
    print("── Buscando janela 01/03 a 25/03 (parcelas 2/2) ──")
    loc_ant, venda_ant = _buscar_deals_janela(INICIO_2, FIM_2)
    print(f"  Locação P48+P0 dedup: {len(loc_ant)} | Venda P40: {len(venda_ant)}\n")

    # Pagamentos MicroWork (janela ampla cobre tudo)
    print("── Buscando pagamentos MicroWork (01/03 a 30/04) ──")
    pagamentos = microwork.buscar_recebimentos(INICIO_2, FIM_1)
    print(f"  Total recebimentos: {len(pagamentos)}\n")

    pag_por_cpf: dict[str, list[Pagamento]] = {}
    for p in pagamentos:
        cpf = _normalize_cpf(p.cpf_cnpj)
        if cpf:
            pag_por_cpf.setdefault(cpf, []).append(p)

    # Devoluções — uma busca pra todas as placas dos dois vendedores juntos
    deals_atual_total = loc_atual + venda_atual
    deals_anteriores_total = loc_ant + venda_ant
    placas_relevantes = [
        d.placa for d in (deals_atual_total + deals_anteriores_total)
        if d.placa and d.assigned_by_id in (v["id"] for v in VENDEDORES)
    ]
    print(f"── Buscando devoluções ({len(placas_relevantes)} placas) ──")
    devolucoes = bitrix.buscar_devolucoes_por_placas(placas_relevantes)
    print(f"  Devoluções encontradas: {len(devolucoes)}\n")

    # Gera PDF + XLSX por vendedor
    for v in VENDEDORES:
        _gerar_para_vendedor(
            vendedor_id=v["id"],
            vendedor_nome=v["nome"],
            basename=v["basename"],
            deals_atual=deals_atual_total,
            deals_anteriores=deals_anteriores_total,
            pag_por_cpf=pag_por_cpf,
            nivel=nivel,
            devolucoes=devolucoes,
        )

    print(f"\n{'=' * 70}")
    print(f"  Concluído. PDFs em {OUTPUT_DIR}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
