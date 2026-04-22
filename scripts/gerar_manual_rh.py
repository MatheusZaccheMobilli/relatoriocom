"""Manual do RH — explicação do Relatório de Comissão Mobílli.

Gera um PDF com:
- Visão geral do processo
- Fontes de dados
- Regra de meta e níveis
- Tabela de percentuais
- Regras de parcela (locação vs venda)
- Base de cálculo (MicroWork)
- Devoluções
- Exemplos práticos (incluindo plano semanal)
- FAQ
"""

import io
import sys
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from fpdf import FPDF

# Paleta Mobílli
LARANJA = (255, 102, 0)
LARANJA_ESCURO = (204, 82, 0)
BRANCO = (255, 255, 255)
CINZA_CLARO = (240, 240, 240)
CINZA_MEDIO = (200, 200, 200)
PRETO = (30, 30, 30)
VERDE = (39, 139, 57)
VERMELHO = (170, 40, 40)

ROOT = Path(__file__).resolve().parents[1]
LOGO_PATH = ROOT / "logo-mobilli.png"
FONTS_DIR = ROOT / "src" / "export" / "fonts"
OUT_PATH = ROOT / "output" / "manual_relatorio_comissao.pdf"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)


class ManualPDF(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="P", format="A4")
        self.add_font("DejaVu", "", str(FONTS_DIR / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(FONTS_DIR / "DejaVuSans-Bold.ttf"))
        self.add_font("DejaVu", "I", str(FONTS_DIR / "DejaVuSans-Oblique.ttf"))
        self.set_auto_page_break(auto=True, margin=18)

    def header(self) -> None:
        self.set_fill_color(*LARANJA_ESCURO)
        self.rect(0, 0, self.w, 22, "F")

        if LOGO_PATH.exists():
            self.image(str(LOGO_PATH), 8, 3, w=10, h=16)

        self.set_font("DejaVu", "B", 12)
        self.set_text_color(*BRANCO)
        self.set_xy(24, 5)
        self.cell(0, 6, "Manual — Relatório de Comissão de Vendedores", align="L")
        self.set_font("DejaVu", "", 8)
        self.set_xy(24, 12)
        self.cell(0, 5, "Guia para o RH: como o relatório é construído e interpretado", align="L")

        self.set_font("DejaVu", "", 7)
        self.set_xy(self.w - 55, 5)
        self.cell(45, 5, f"Emitido em {date.today().strftime('%d/%m/%Y')}", align="R")

        self.set_fill_color(*LARANJA)
        self.rect(0, 22, self.w, 1.2, "F")
        self.set_y(28)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("DejaVu", "I", 7)
        self.set_text_color(130, 130, 130)
        self.cell(0, 10, f"Mobílli Rentals — Manual Comissão — Página {self.page_no()}", align="C")

    # ── helpers ───────────────────────────────────────────────────────
    def h1(self, txt: str) -> None:
        self.ln(2)
        self.set_fill_color(*LARANJA_ESCURO)
        self.set_text_color(*BRANCO)
        self.set_font("DejaVu", "B", 13)
        self.cell(0, 9, "  " + txt, new_x="LMARGIN", new_y="NEXT", fill=True)
        self.ln(3)

    def h2(self, txt: str) -> None:
        self.ln(1)
        self.set_text_color(*LARANJA_ESCURO)
        self.set_font("DejaVu", "B", 11)
        self.cell(0, 7, txt, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*LARANJA)
        self.set_line_width(0.3)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(3)

    def paragraph(self, txt: str) -> None:
        self.set_text_color(*PRETO)
        self.set_font("DejaVu", "", 9.5)
        self.multi_cell(0, 5, txt)
        self.ln(1)

    def bullet(self, txt: str) -> None:
        self.set_text_color(*PRETO)
        self.set_font("DejaVu", "", 9.5)
        x_ini = self.get_x()
        self.cell(5, 5, "•", align="C")
        self.multi_cell(0, 5, txt)
        self.set_x(x_ini)

    def nota(self, txt: str) -> None:
        x = self.get_x()
        y = self.get_y()
        self.set_fill_color(255, 240, 220)
        self.set_draw_color(*LARANJA)
        self.set_line_width(0.3)
        self.set_font("DejaVu", "B", 9)
        self.set_text_color(*LARANJA_ESCURO)
        self.multi_cell(0, 5, "  " + txt, border=1, fill=True)
        self.ln(2)

    def tabela(self, headers: list[tuple[str, int]], rows: list[list[str]]) -> None:
        # header
        self.set_fill_color(*LARANJA_ESCURO)
        self.set_text_color(*BRANCO)
        self.set_font("DejaVu", "B", 9)
        for nome, w in headers:
            self.cell(w, 7, nome, align="C", fill=True, border=1)
        self.ln()

        self.set_font("DejaVu", "", 9)
        for i, row in enumerate(rows):
            if i % 2 == 0:
                self.set_fill_color(*BRANCO)
            else:
                self.set_fill_color(*CINZA_CLARO)
            self.set_text_color(*PRETO)
            for (_, w), val in zip(headers, row):
                self.cell(w, 6.5, val, align="C", fill=True, border=1)
            self.ln()
        self.ln(2)

    def exemplo_box(self, titulo: str, linhas: list[tuple[str, str]]) -> None:
        """Caixa com título destacado e pares chave:valor."""
        self.set_fill_color(*LARANJA)
        self.set_text_color(*BRANCO)
        self.set_font("DejaVu", "B", 10)
        self.cell(0, 7, "  " + titulo, new_x="LMARGIN", new_y="NEXT", fill=True, border=1)

        self.set_font("DejaVu", "", 9)
        for k, v in linhas:
            self.set_fill_color(*CINZA_CLARO)
            self.set_text_color(*PRETO)
            self.cell(55, 6, "  " + k, fill=True, border=1)
            self.set_fill_color(*BRANCO)
            self.cell(0, 6, " " + v, new_x="LMARGIN", new_y="NEXT", fill=True, border=1)
        self.ln(3)


def build() -> None:
    pdf = ManualPDF()
    pdf.add_page()

    # ═════════════════════════════════════════════════════════════════
    # 1. VISÃO GERAL
    # ═════════════════════════════════════════════════════════════════
    pdf.h1("1. Visão Geral")
    pdf.paragraph(
        "O Relatório de Comissão de Vendedores é um documento mensal, gerado "
        "automaticamente, que consolida todos os negócios fechados pelo vendedor "
        "no período de apuração. Ele serve como base para o pagamento da comissão "
        "e é assinado pelo vendedor como termo de ciência."
    )
    pdf.paragraph(
        "O relatório é construído a partir de DOIS sistemas que se cruzam:"
    )
    pdf.bullet(
        "Bitrix24 (CRM): fonte de verdade dos negócios — quem fechou, com qual "
        "cliente, qual veículo, qual data, qual valor contratado, e se o negócio "
        "foi devolvido/rescindido."
    )
    pdf.bullet(
        "MicroWork (ERP): fonte dos PAGAMENTOS efetivamente recebidos do cliente. "
        "É sobre esse valor que a comissão incide (e não sobre o valor do contrato)."
    )
    pdf.ln(2)
    pdf.nota(
        "Princípio central: o vendedor só ganha comissão sobre o que foi "
        "efetivamente pago pelo cliente. Contrato no papel não paga comissão — "
        "pagamento reconhecido no MicroWork paga."
    )

    # ═════════════════════════════════════════════════════════════════
    # 2. META E NÍVEIS
    # ═════════════════════════════════════════════════════════════════
    pdf.h1("2. Meta da Empresa e Níveis")
    pdf.paragraph(
        "A meta é uma QUANTIDADE DE CAPTAÇÕES da empresa inteira (soma de todos "
        "os vendedores, pipelines Locação e Venda GW12). O RH informa a meta no "
        "início do processo. O nível atingido determina o PERCENTUAL de comissão "
        "que todos os vendedores receberão naquele mês."
    )

    pdf.h2("Faixas de nível")
    pdf.tabela(
        [("Nível", 45), ("Atingimento da meta", 95), ("Efeito", 50)],
        [
            ["Bronze", "De 75% até 99% da meta", "Percentual base"],
            ["Prata", "De 100% até 124% da meta", "Percentual intermediário"],
            ["Ouro", "125% ou mais da meta", "Percentual máximo"],
        ],
    )
    pdf.nota(
        "Atingimento abaixo de 75% → nível Bronze (padrão). Nunca há comissão zerada "
        "por não bater meta — o percentual Bronze sempre é aplicado."
    )

    # ═════════════════════════════════════════════════════════════════
    # 3. TABELA DE COMISSÃO
    # ═════════════════════════════════════════════════════════════════
    pdf.h1("3. Percentuais de Comissão (TM-018)")
    pdf.paragraph(
        "O percentual aplicado depende do TIPO DE OPERAÇÃO e do NÍVEL atingido:"
    )
    pdf.tabela(
        [
            ("Tipo de operação", 60),
            ("Bronze", 40),
            ("Prata", 40),
            ("Ouro", 40),
        ],
        [
            ["Locação", "8,00%", "9,00%", "10,00%"],
            ["Venda 0km", "1,00%", "1,20%", "1,30%"],
            ["Venda Usado", "3,40%", "4,00%", "4,80%"],
        ],
    )

    # ═════════════════════════════════════════════════════════════════
    # 4. REGRA DE PARCELAS
    # ═════════════════════════════════════════════════════════════════
    pdf.h1("4. Regra de Parcelas")
    pdf.paragraph(
        "A comissão de LOCAÇÃO é dividida em DUAS parcelas, pagas em meses "
        "consecutivos. A comissão de VENDA é paga em PARCELA ÚNICA."
    )

    pdf.h2("Locação (2 parcelas)")
    pdf.bullet("Deal fechado no mês X → 1/2 paga no mês X+1, 2/2 paga no mês X+2")
    pdf.bullet(
        "Isto significa que, em um mês qualquer, o vendedor recebe:"
    )
    pdf.paragraph(
        "   → 1/2 dos negócios que ele fechou NO MÊS ANTERIOR (M-1)\n"
        "   → 2/2 dos negócios que ele fechou DOIS MESES ATRÁS (M-2)"
    )

    pdf.h2("Venda GW12 (1 parcela)")
    pdf.bullet("Deal fechado no mês X → parcela única paga no mês X+1")

    pdf.nota(
        "A data que conta é a DATA DA LOCAÇÃO (ou DATA DA VENDA), não a data "
        "de entrada do lead ou a data do primeiro contato."
    )

    pdf.add_page()

    # ═════════════════════════════════════════════════════════════════
    # 5. BASE DE CÁLCULO
    # ═════════════════════════════════════════════════════════════════
    pdf.h1("5. Base de Cálculo da Comissão")
    pdf.paragraph(
        "A base de cálculo depende do tipo de operação:"
    )

    pdf.h2("Locação — a base depende do PLANO (semanal ou mensal)")
    pdf.paragraph(
        "A comissão de locação incide sobre os boletos de ALUGUEL que o cliente "
        "efetivamente pagou no MicroWork. Mas a forma de calcular MUDA conforme "
        "o plano do contrato seja SEMANAL ou MENSAL:"
    )
    pdf.tabela(
        [("Plano", 30), ("1/2 (paga em M+1)", 72), ("2/2 (paga em M+2)", 72)],
        [
            [
                "Semanal",
                "Boletos do MÊS DO FECHAMENTO × %",
                "Boletos do MÊS SEGUINTE × %",
            ],
            [
                "Mensal",
                "(Mensalidade do MÊS DO FECHAMENTO × %) ÷ 2",
                "(Mensalidade do MÊS DO FECHAMENTO × %) ÷ 2",
            ],
        ],
    )
    pdf.paragraph(
        "Por que a diferença? No plano SEMANAL o cliente paga 4-5 boletos por "
        "mês, então cada parcela da comissão olha um mês diferente (o vendedor "
        "acompanha o cliente em 2 meses). No plano MENSAL o cliente paga UMA "
        "mensalidade por mês — então a comissão é calculada sobre a primeira "
        "mensalidade paga e dividida igualmente em 2 parcelas."
    )
    pdf.paragraph(
        "O sistema identifica boletos de ALUGUEL pelo padrão do documento no "
        'MicroWork: "{ID do deal}-{nº parcela}P - {sequência}". Exemplo: '
        '"29146-1P - 001" indica o primeiro boleto do deal 29146. Isso filtra '
        "automaticamente taxas de emplacamento (NF-E), multas, franquias, "
        "reembolsos e outros lançamentos que NÃO são aluguel."
    )

    pdf.h2("Venda GW12 — base = valor do card Bitrix")
    pdf.paragraph(
        "Para venda, a comissão incide diretamente sobre o valor contratado no "
        "card Bitrix (campo OPPORTUNITY). O sistema NÃO consulta o MicroWork "
        "para venda, porque os pagamentos podem vir por canais externos como "
        "financiamento bancário que não passam pelo ERP."
    )

    pdf.h2("Exemplo rápido")
    pdf.paragraph(
        "Contrato de locação semanal fechado em 28/março a R$ 276/semana. "
        "A parcela 1/2 (paga em abril) usa como base APENAS os boletos de aluguel "
        "desse cliente que caíram em MARÇO (só o de 28/03 = R$ 276). A parcela 2/2 "
        "(paga em maio) usa como base APENAS os boletos de ABRIL (4 boletos = "
        "R$ 1.104). Taxa de emplacamento cobrada em NF-E separada NÃO entra na base."
    )
    pdf.nota(
        "Se o cliente atrasa o pagamento, o valor sai do mês esperado e entra no "
        "mês seguinte — parte da comissão pode deslocar de parcela. Se o cliente "
        "não paga aluguel no mês-base, a comissão daquela parcela é zero."
    )

    # ═════════════════════════════════════════════════════════════════
    # 6. DEVOLUÇÕES / RESCISÕES
    # ═════════════════════════════════════════════════════════════════
    pdf.h1("6. Devoluções e Rescisões")
    pdf.paragraph(
        "Quando uma moto é devolvida (rescisão do contrato), o negócio entra no "
        "Pipeline 22 (Devolução) do Bitrix. O sistema cruza pela PLACA do veículo "
        "e pelo MESMO CLIENTE, marcando o deal como DEVOLVIDO."
    )
    pdf.bullet("Um deal devolvido aparece no relatório destacado em vermelho.")
    pdf.bullet("A comissão dele é ZERADA naquele mês.")
    pdf.bullet(
        'No indicador "Devolvidos" do topo do relatório fica contabilizado.'
    )
    pdf.nota(
        "A devolução só zera a comissão do mês corrente. Parcelas já pagas em meses "
        "anteriores não são estornadas retroativamente."
    )

    # ═════════════════════════════════════════════════════════════════
    # 7. PLANO SEMANAL vs MENSAL
    # ═════════════════════════════════════════════════════════════════
    pdf.h1("7. Plano Semanal vs. Plano Mensal")
    pdf.paragraph(
        "A regra de parcelas é a MESMA para plano semanal e mensal. O que muda "
        "é a cadência de pagamento do cliente — e, como a comissão incide sobre "
        "o valor efetivamente pago, isso afeta diretamente o valor da parcela."
    )
    pdf.bullet(
        "Plano mensal: cliente paga 1 boleto grande por mês → base de cálculo "
        "tende a ser maior concentrada em uma data."
    )
    pdf.bullet(
        "Plano semanal: cliente paga 4–5 boletos pequenos ao longo do mês → "
        "base de cálculo é a SOMA dos boletos recebidos no período."
    )

    # ═════════════════════════════════════════════════════════════════
    # 8. EXEMPLOS PRÁTICOS
    # ═════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.h1("8. Exemplos Práticos")

    # ── Exemplo 1 ────────────────────────────────────────────────────
    pdf.h2("Exemplo 1 — Locação MENSAL fechada no meio do mês")
    pdf.paragraph(
        "Cenário: vendedor fecha locação mensal em 15/março. Aluguel de "
        "R$ 1.200/mês. Cliente paga a 1ª mensalidade no mesmo dia (15/03)."
    )
    pdf.exemplo_box(
        "Cálculo da comissão (regra do MENSAL: comissão total ÷ 2)",
        [
            ("Base (1ª mensalidade paga em março)", "R$ 1.200,00"),
            ("Comissão total (Bronze 8%)", "R$ 96,00"),
            ("Parcela 1/2 (paga em abril)", "R$ 96,00 ÷ 2 = R$ 48,00"),
            ("Parcela 2/2 (paga em maio)", "R$ 96,00 ÷ 2 = R$ 48,00"),
            ("TOTAL recebido pelo vendedor", "R$ 96,00 (em 2 meses)"),
        ],
    )
    pdf.nota(
        "Mensal: o vendedor ganha comissão UMA vez por contrato (sobre a "
        "primeira mensalidade paga), dividida em 2 parcelas mensais. "
        "Mensalidades subsequentes que o cliente paga não geram nova comissão."
    )
    pdf.exemplo_box(
        "E se o cliente NÃO pagar a primeira mensalidade?",
        [
            ("Base (mês do fechamento)", "R$ 0,00 (nenhum boleto caiu)"),
            ("Comissão 1/2", "R$ 0,00"),
            ("Comissão 2/2", "R$ 0,00"),
        ],
    )

    # ── Exemplo 2 — o que o usuário perguntou ───────────────────────
    pdf.h2("Exemplo 2 — Plano SEMANAL fechado na última semana do mês")
    pdf.paragraph(
        "Cenário: vendedor fecha plano semanal em 28/março. Aluguel de R$ 300/semana. "
        "Este é o caso mais importante para entender a regra por parcela."
    )
    pdf.exemplo_box(
        "Fluxo de pagamento do cliente",
        [
            ("Data da locação", "28/março (sexta da última semana do mês)"),
            ("1º boleto semanal pago", "28/março → MicroWork em MARÇO"),
            ("2º boleto", "04/abril → MicroWork em ABRIL"),
            ("3º boleto", "11/abril → MicroWork em ABRIL"),
            ("4º boleto", "18/abril → MicroWork em ABRIL"),
            ("5º boleto", "25/abril → MicroWork em ABRIL"),
            ("6º boleto", "02/maio → MicroWork em MAIO"),
        ],
    )
    pdf.exemplo_box(
        "Parcela 1/2 — paga em ABRIL (Bronze 8%)",
        [
            ("Regra da base", "Mês do fechamento = MARÇO"),
            ("Boletos desse CPF em março", "APENAS 1 boleto (o de 28/03)"),
            ("Base de cálculo", "R$ 300,00"),
            ("Comissão 1/2", "8% × R$ 300 = R$ 24,00"),
        ],
    )
    pdf.exemplo_box(
        "Parcela 2/2 — paga em MAIO (Bronze 8%)",
        [
            ("Regra da base", "Mês SEGUINTE ao fechamento = ABRIL"),
            ("Boletos desse CPF em abril", "4 boletos (04, 11, 18 e 25 de abril)"),
            ("Base de cálculo", "4 × R$ 300 = R$ 1.200,00"),
            ("Comissão 2/2", "8% × R$ 1.200 = R$ 96,00"),
        ],
    )
    pdf.exemplo_box(
        "Resumo final deste contrato",
        [
            ("Total recebido pela empresa (abr+mai)", "R$ 1.500,00 (5 boletos)"),
            ("Total de comissão paga ao vendedor", "R$ 24,00 + R$ 96,00 = R$ 120,00"),
            ("% efetivo", "8% sobre o recebido nos meses-base"),
        ],
    )
    pdf.nota(
        "Por isso fechar no FIM do mês penaliza a parcela 1/2: só entra na base "
        "o(s) boleto(s) que cair(em) até o dia 31. A parcela 2/2 compensa, "
        "porque o mês inteiro seguinte conta."
    )

    pdf.add_page()

    # ── Exemplo 3 ────────────────────────────────────────────────────
    pdf.h2("Exemplo 3 — Venda GW12 0km")
    pdf.paragraph(
        "Cenário: vendedor vende uma moto 0km em 10/março, card Bitrix com valor "
        "de R$ 14.000 (valor da moto sem emplacamento/taxas)."
    )
    pdf.exemplo_box(
        "Cálculo",
        [
            ("Data da venda", "10/março"),
            ("Parcela única 1/1 paga em", "Abril (M+1)"),
            ("Regra da base", "Valor do card Bitrix (direto)"),
            ("Base de cálculo", "R$ 14.000 (não consulta MicroWork)"),
            ("Comissão Bronze (1%)", "R$ 140,00"),
            ("Comissão Prata (1,20%)", "R$ 168,00"),
            ("Comissão Ouro (1,30%)", "R$ 182,00"),
        ],
    )
    pdf.nota(
        "Para venda o sistema NÃO olha o MicroWork — usa o valor do card direto. "
        "Isso evita inflar a base com emplacamento, taxas ou encargos que "
        "aparecem junto na NF-E do financeiro."
    )

    # ── Exemplo 4 ────────────────────────────────────────────────────
    pdf.h2("Exemplo 4 — Devolução no meio do ciclo")
    pdf.paragraph(
        "Cenário: locação fechada em 10/fevereiro. 1/2 já foi paga em março. "
        "Em 20/abril o cliente devolve a moto — antes da 2/2 ser processada."
    )
    pdf.exemplo_box(
        "Impacto",
        [
            ("Parcela 1/2 (paga em março)", "✓ Já foi paga e NÃO é estornada"),
            ("Parcela 2/2 (a pagar em abril)", "✗ Zerada — deal marcado devolvido"),
            ("Aparece no relatório de abril", "Sim, em vermelho, com R$ 0,00"),
            ("Conta no indicador 'Devolvidos'", "Sim"),
        ],
    )

    # ═════════════════════════════════════════════════════════════════
    # 9. COMO LER O RELATÓRIO
    # ═════════════════════════════════════════════════════════════════
    pdf.h1("9. Como Ler o Relatório")
    pdf.paragraph("O relatório tem 4 blocos principais:")
    pdf.bullet("CABEÇALHO: vendedor, competência (mês de pagamento), nível.")
    pdf.bullet(
        "BLOCO DE META: meta, total geral da empresa, % atingido, nível resultante."
    )
    pdf.bullet(
        "INDICADORES: quantidade de itens para comissão, quantidade de devolvidos "
        "e total a receber."
    )
    pdf.bullet(
        "LISTA DE VERIFICAÇÃO: uma linha por negócio, com: Tipo (Locação/Venda), "
        "Parcela (1/2, 2/2 ou 1/1), Plano (Semanal/Mensal), Cliente, Placa, "
        "Data Locação, Data Devolução, Valor Base, Parcelas (qtd boletos "
        "considerados na base), Comissão e Status (Ativo/Devolvido)."
    )
    pdf.bullet(
        "TERMO DE CIÊNCIA: espaço para assinatura do vendedor confirmando que "
        "leu e concorda com os valores."
    )

    # ═════════════════════════════════════════════════════════════════
    # 10. PERGUNTAS FREQUENTES
    # ═════════════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.h1("10. Perguntas Frequentes")

    pdf.h2("O que acontece se o cliente pagar atrasado?")
    pdf.paragraph(
        "O valor entra no relatório do MÊS em que foi pago. Se o cliente devia "
        "pagar em março mas pagou em abril, esse valor vai compor a base da 1/2 "
        "paga em abril (que normalmente seria sobre o que foi pago em abril)."
    )

    pdf.h2("E se o deal não aparece no relatório, mesmo o vendedor tendo fechado?")
    pdf.paragraph("Possíveis causas, em ordem de frequência:")
    pdf.bullet("Deal não está com stage WON no Bitrix (ainda está em negociação).")
    pdf.bullet(
        "Campo 'Data de Locação' (UF_CRM_1743092456783) não foi preenchido."
    )
    pdf.bullet('O deal está em pipeline diferente de 48 (Locação) ou 40 (Venda GW12).')
    pdf.bullet("O deal está atribuído a outro vendedor (campo Responsável).")
    pdf.bullet("A data de locação caiu fora da janela de apuração do mês.")

    pdf.h2("Posso alterar a meta depois de gerar o relatório?")
    pdf.paragraph(
        "Sim. A meta é um input no sistema. Basta gerar o relatório novamente "
        "com o novo valor — todos os cálculos recalculam em segundos."
    )

    pdf.h2("Por que o valor base de alguns deals é diferente do valor do contrato?")
    pdf.paragraph(
        "Porque o valor base é o que foi EFETIVAMENTE PAGO no MicroWork no "
        "período, não o que está contratado. Se o cliente pagou parcialmente, "
        "atrasou ou antecipou, a base reflete o que o caixa da empresa recebeu."
    )

    pdf.h2("Como funciona o cálculo do nível se a meta for zero?")
    pdf.paragraph(
        'Nível "Sem Meta" é aplicado e o sistema usa a tabela Bronze como fallback. '
        "Recomenda-se sempre informar uma meta mensal para o cálculo ficar explícito."
    )

    pdf.h2("E se um deal for fechado em duas moedas ou com desconto aplicado?")
    pdf.paragraph(
        "O sistema sempre usa o VALOR TOTAL PAGO no MicroWork, já descontado — "
        "portanto descontos e negociações posteriores ao fechamento já estão "
        "refletidos na base de cálculo."
    )

    # ═════════════════════════════════════════════════════════════════
    # 11. RESUMO OPERACIONAL
    # ═════════════════════════════════════════════════════════════════
    pdf.h1("11. Checklist de Operação Mensal (RH)")
    pdf.bullet("1. Confirmar com a Diretoria a META do mês (quantidade de captações).")
    pdf.bullet(
        "2. Acessar a ferramenta de relatório e selecionar: vendedor, mês de "
        "pagamento e meta."
    )
    pdf.bullet("3. Gerar o relatório e conferir: indicadores, devolvidos, total.")
    pdf.bullet("4. Baixar o PDF e enviar ao vendedor para assinatura.")
    pdf.bullet(
        "5. Arquivar o PDF assinado junto ao contracheque do vendedor."
    )
    pdf.bullet(
        "6. Em caso de divergência apontada pelo vendedor: verificar no Bitrix "
        "o status e os campos do deal em questão (stage WON, data de locação, "
        "pipeline, responsável)."
    )

    pdf.ln(4)
    pdf.nota(
        "Dúvidas técnicas sobre campos do Bitrix ou valores do MicroWork: acionar "
        "o time de BI. Dúvidas sobre regra de comissão ou percentuais: consultar "
        "o documento TM-018."
    )

    pdf.output(str(OUT_PATH))
    print(f"PDF gerado: {OUT_PATH}")


if __name__ == "__main__":
    build()
