"""Geração de PDF do relatório de comissão — identidade visual Mobílli."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from fpdf import FPDF

from src.models import RelatorioData

# Paleta Mobílli
LARANJA = (255, 102, 0)         # #FF6600 — cor principal
LARANJA_ESCURO = (204, 82, 0)   # #CC5200 — variante escura
BRANCO = (255, 255, 255)
CINZA_CLARO = (240, 240, 240)
PRETO = (30, 30, 30)

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

LOGO_PATH = Path(__file__).parent.parent.parent / "logo-mobilli.png"
FONTS_DIR = Path(__file__).parent / "fonts"


def _brl(valor: Decimal) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_data(d: date | None) -> str:
    if not d:
        return "-"
    return d.strftime("%d/%m/%Y")


def _mes_ano(d: date) -> str:
    return f"{MESES_PT[d.month]}/{d.year}"


class RelatorioPDF(FPDF):
    def __init__(self, relatorio: RelatorioData):
        super().__init__(orientation="L", format="A4")
        self.rel = relatorio
        self.add_font("DejaVu", "", str(FONTS_DIR / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(FONTS_DIR / "DejaVuSans-Bold.ttf"))
        self.add_font("DejaVu", "I", str(FONTS_DIR / "DejaVuSans-Oblique.ttf"))
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        # Faixa laranja no topo
        self.set_fill_color(*LARANJA_ESCURO)
        self.rect(0, 0, self.w, 28, "F")

        # Logo
        if LOGO_PATH.exists():
            self.image(str(LOGO_PATH), 8, 3, 35)

        # Título
        self.set_font("DejaVu", "B", 16)
        self.set_text_color(*BRANCO)
        self.set_xy(50, 5)
        self.cell(0, 10, "Relatório de Comissão de Vendedores", align="L")

        # Subtítulo
        self.set_font("DejaVu", "", 10)
        self.set_xy(50, 14)
        self.cell(0, 8, f"Pagamento em {_mes_ano(self.rel.competencia)}", align="L")

        # Linha dourada
        self.set_fill_color(*LARANJA_ESCURO)
        self.rect(0, 28, self.w, 2, "F")

        self.set_y(35)

    def footer(self):
        self.set_y(-12)
        self.set_font("DejaVu", "I", 7)
        self.set_text_color(130, 130, 130)
        self.cell(0, 10, f"Mobilli Rentals - Gerado automaticamente - Pagina {self.page_no()}", align="C")


def gerar_pdf(relatorio: RelatorioData) -> bytes:
    """Gera o PDF completo do relatório e retorna os bytes."""
    pdf = RelatorioPDF(relatorio)
    pdf.add_page()

    # ── Dados do Vendedor ─────────────────────────────────
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(*LARANJA_ESCURO)
    pdf.cell(0, 8, "Dados do Vendedor", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("DejaVu", "", 10)
    pdf.set_text_color(*PRETO)
    pdf.cell(60, 6, f"Nome: {relatorio.vendedor.nome}", new_x="RIGHT")
    if relatorio.vendedor.cpf:
        pdf.cell(60, 6, f"CPF: {relatorio.vendedor.cpf}", new_x="RIGHT")
    pdf.ln(8)

    # ── Bloco de Meta ─────────────────────────────────────
    pdf.set_fill_color(*LARANJA)
    pdf.set_text_color(*BRANCO)
    pdf.set_font("DejaVu", "B", 10)

    col_w = 65

    # Cabeçalhos
    pdf.cell(col_w, 8, "Meta", align="C", fill=True)
    pdf.cell(col_w, 8, "Total Geral", align="C", fill=True)
    pdf.cell(col_w, 8, "% Atingido", align="C", fill=True)
    pdf.cell(col_w, 8, "Nível", align="C", fill=True)
    pdf.ln()

    # Valores
    pdf.set_fill_color(*CINZA_CLARO)
    pdf.set_text_color(*PRETO)
    pdf.set_font("DejaVu", "B", 12)

    nivel_label = {
        "Ouro": "OURO",
        "Prata": "PRATA",
        "Bronze": "BRONZE",
        "Sem Meta": "-",
    }

    pdf.cell(col_w, 10, f"{relatorio.nivel.qtd_meta} captações", align="C", fill=True)
    pdf.cell(col_w, 10, f"{relatorio.nivel.qtd_atingida} captações", align="C", fill=True)
    pdf.cell(col_w, 10, f"{relatorio.nivel.percentual_atingido}%", align="C", fill=True)
    pdf.cell(col_w, 10, nivel_label.get(relatorio.nivel.nome, relatorio.nivel.nome), align="C", fill=True)
    pdf.ln(12)

    # ── Indicadores ───────────────────────────────────────
    pdf.set_font("DejaVu", "B", 10)
    pdf.set_text_color(*LARANJA_ESCURO)

    ind_w = 86
    pdf.cell(ind_w, 7, "Itens para Comissão", align="C")
    pdf.cell(ind_w, 7, "Devolvidos", align="C")
    pdf.cell(ind_w, 7, "Total a Receber", align="C")
    pdf.ln()

    pdf.set_font("DejaVu", "B", 14)
    pdf.set_text_color(*PRETO)
    pdf.cell(ind_w, 9, str(relatorio.negocios_fechados), align="C")
    pdf.cell(ind_w, 9, str(relatorio.negocios_encerrados), align="C")

    pdf.set_text_color(*LARANJA_ESCURO)
    pdf.cell(ind_w, 9, _brl(relatorio.total_comissao), align="C")
    pdf.ln(12)

    # ── Tabela de Itens ───────────────────────────────────
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(*LARANJA_ESCURO)
    pdf.cell(0, 8, "Lista de Verificação de Pagamento", new_x="LMARGIN", new_y="NEXT")

    # Cabeçalho da tabela
    cols = [
        ("Tipo", 22),
        ("Parcela", 16),
        ("Nome do Cliente", 72),
        ("Placa", 22),
        ("Data Locação", 26),
        ("Data Devolução", 26),
        ("Valor Base", 30),
        ("Comissão", 28),
        ("Status", 18),
    ]

    pdf.set_fill_color(*LARANJA_ESCURO)
    pdf.set_text_color(*BRANCO)
    pdf.set_font("DejaVu", "B", 7)
    for nome, w in cols:
        pdf.cell(w, 7, nome, align="C", fill=True)
    pdf.ln()

    # Linhas
    pdf.set_font("DejaVu", "", 7)
    for i, item in enumerate(relatorio.itens):
        if item.devolvido:
            pdf.set_fill_color(255, 204, 204)
            pdf.set_text_color(120, 40, 40)
        elif i % 2 == 0:
            pdf.set_fill_color(*BRANCO)
            pdf.set_text_color(*PRETO)
        else:
            pdf.set_fill_color(*CINZA_CLARO)
            pdf.set_text_color(*PRETO)

        vals = [
            item.tipo_operacao,
            item.parcela,
            item.nome_cliente[:40],
            item.placa,
            _fmt_data(item.data_locacao),
            _fmt_data(item.data_devolucao),
            _brl(item.valor_base),
            _brl(item.valor_comissao),
            "DEVOLVIDO" if item.devolvido else "Ativo",
        ]
        for (_, w), val in zip(cols, vals):
            pdf.cell(w, 6, val, align="C", fill=True)
        pdf.ln()

    pdf.ln(5)

    # ── Total ─────────────────────────────────────────────
    pdf.set_fill_color(*LARANJA_ESCURO)
    pdf.set_text_color(*BRANCO)
    pdf.set_font("DejaVu", "B", 12)
    pdf.cell(0, 10, f"Total a Receber: {_brl(relatorio.total_comissao)}", align="R", fill=True)
    pdf.ln(15)

    # ── Termo de Ciência ──────────────────────────────────
    pdf.set_text_color(*PRETO)
    pdf.set_font("DejaVu", "", 9)
    pdf.multi_cell(
        0, 5,
        f"Eu, {relatorio.vendedor.nome}, declaro que li e concordo com os dados "
        f"apresentados acima referentes ao pagamento de {_mes_ano(relatorio.competencia)}.",
    )
    pdf.ln(12)

    # Assinatura e Data
    pdf.set_font("DejaVu", "", 9)
    x_assinatura = 20
    x_data = 160

    pdf.set_x(x_assinatura)
    pdf.cell(100, 0, "_" * 55)
    pdf.set_x(x_data)
    pdf.cell(80, 0, "_" * 30)
    pdf.ln(5)

    pdf.set_x(x_assinatura)
    pdf.cell(100, 5, "Assinatura do Vendedor")
    pdf.set_x(x_data)
    pdf.cell(80, 5, "Data")

    # Retornar bytes
    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
