"""Helpers de UI compartilhados entre páginas (CSS, formatters, labels)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import streamlit as st
from dateutil.relativedelta import relativedelta


MESES_PT: dict[int, str] = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

# Primeiro mês com a regra nova vigente (limita opções no relatório)
PRIMEIRO_MES_VIGENTE = date(2026, 5, 1)
# Primeiro mês visível no dashboard de captações = M-1 do primeiro pagamento
PRIMEIRO_MES_CAPTACAO = date(2026, 4, 1)

NIVEL_BADGES: dict[str, str] = {
    "Ouro": "🥇 Ouro",
    "Prata": "🥈 Prata",
    "Bronze": "🥉 Bronze",
    "Sem Meta": "-",
}

CSS_MOBILLI = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
    /* ---------- Tipografia base (BI-grade) ---------- */
    html, body, [class*="css"], .stMarkdown, .stApp, table, button, input, select {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
        -webkit-font-smoothing: antialiased;
        font-feature-settings: 'tnum', 'cv11';
    }
    .stApp { background-color: #fafbfc; }

    /* ---------- Reset visual do Streamlit ---------- */
    .stDeployButton, #MainMenu { display: none !important; }
    header[data-testid="stHeader"] {
        background-color: #1a1a1a;
        position: relative;
    }
    /* Banner "EM CONSTRUÇÃO" no header preto */
    header[data-testid="stHeader"]::before {
        content: "🚧  DASHBOARD EM CONSTRUÇÃO  🚧";
        position: absolute;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        color: #FFC107;
        font-weight: 800;
        font-size: 13px;
        letter-spacing: 2px;
        white-space: nowrap;
        pointer-events: none;
        text-shadow: 0 0 8px rgba(255, 193, 7, 0.25);
    }
    section[data-testid="stSidebar"] { background-color: #1a1a1a; border-right: 1px solid #2a2a2a; }
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stNumberInput label,
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label { color: #f5f5f5 !important; }
    section[data-testid="stSidebar"] [data-baseweb="select"] > div {
        background-color: #2a2a2a;
        border-color: #3a3a3a;
        color: #f5f5f5;
    }
    /* Texto selecionado no select fica legível */
    section[data-testid="stSidebar"] [data-baseweb="select"] [class*="ValueContainer"],
    section[data-testid="stSidebar"] [data-baseweb="select"] input,
    section[data-testid="stSidebar"] [data-baseweb="select"] span { color: #f5f5f5 !important; }
    /* Input numérico */
    section[data-testid="stSidebar"] [data-testid="stNumberInputContainer"] input { color: #1a1a1a !important; }
    /* Botão "Atualizar dados" no sidebar — secundário, fundo escuro */
    section[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) {
        background-color: #2a2a2a !important;
        border-color: #3a3a3a !important;
        color: #f5f5f5 !important;
    }
    section[data-testid="stSidebar"] .stButton > button:not([kind="primary"]):hover {
        background-color: #3a3a3a !important;
        border-color: #FF6600 !important;
    }

    /* ---------- Botões ---------- */
    .stButton > button {
        font-weight: 600 !important;
        border-radius: 6px !important;
    }
    .stButton > button[kind="primary"] {
        background-color: #FF6600 !important;
        border-color: #FF6600 !important;
        color: #ffffff !important;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #e55a00 !important;
        border-color: #e55a00 !important;
    }
    .stDownloadButton > button {
        background-color: #FF6600 !important;
        border-color: #FF6600 !important;
        color: #ffffff !important;
    }

    /* Streamlit metric — usado em algumas telas */
    [data-testid="stMetricValue"] { color: #1a1a1a !important; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: #6b7280 !important; }

    /* ---------- HEADER (banda discreta com underline laranja) ---------- */
    .mob-hero {
        background: #ffffff;
        padding: 22px 28px 20px;
        border-radius: 8px;
        border: 1px solid #e5e7eb;
        border-top: 3px solid #FF6600;
        margin-bottom: 20px;
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
    }
    .mob-hero h1 {
        margin: 0;
        font-size: 22px;
        color: #1a1a1a !important;
        font-weight: 700;
        letter-spacing: -0.3px;
    }
    .mob-hero .mob-hero-sub {
        margin-top: 4px;
        font-size: 13px;
        color: #6b7280;
        font-weight: 400;
    }
    .mob-hero .mob-hero-meta {
        text-align: right;
        font-size: 11px;
        color: #6b7280;
        line-height: 1.5;
        text-transform: uppercase;
        letter-spacing: 0.4px;
    }
    .mob-hero .mob-hero-meta b {
        color: #1a1a1a;
        font-size: 13px;
        text-transform: none;
        letter-spacing: 0;
    }

    /* ---------- KPI CARDS ---------- */
    .mob-kpi {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        padding: 18px 20px;
        border-radius: 8px;
        height: 100%;
    }
    .mob-kpi-label {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        color: #6b7280;
        font-weight: 600;
        margin-bottom: 8px;
    }
    .mob-kpi-value {
        font-size: 30px;
        font-weight: 700;
        color: #1a1a1a;
        line-height: 1;
        font-variant-numeric: tabular-nums;
    }
    .mob-kpi-help {
        font-size: 11px;
        color: #6b7280;
        margin-top: 6px;
    }
    .mob-kpi.accent-dark { border-top: 2px solid #1a1a1a; }

    /* ---------- HIGHLIGHTS do header (3 destaques) ---------- */
    .mob-hl-row {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 12px;
        margin-bottom: 24px;
    }
    .mob-hl {
        background: #ffffff;
        border-radius: 8px;
        padding: 20px 22px;
        border: 1px solid #e5e7eb;
        position: relative;
    }
    .mob-hl-lbl {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        color: #6b7280;
        font-weight: 600;
    }
    .mob-hl-val {
        font-size: 34px;
        font-weight: 700;
        color: #1a1a1a;
        line-height: 1.1;
        margin-top: 8px;
        font-variant-numeric: tabular-nums;
    }
    .mob-hl-sub {
        font-size: 11px;
        color: #6b7280;
        margin-top: 4px;
    }
    /* Atual recebe leve realce em laranja na borda */
    .mob-hl.parcial { border-left: 3px solid #FF6600; }
    .mob-hl.proj { border-left: 3px solid #1a1a1a; }

    /* ---------- META + NÍVEL (faixa de progresso) ---------- */
    .mob-meta-wrap {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 18px 22px;
        margin-bottom: 24px;
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 18px;
        align-items: center;
    }
    .mob-meta-info {
        display: flex;
        flex-direction: column;
        gap: 8px;
    }
    .mob-meta-head {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
    }
    .mob-meta-title {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        color: #6b7280;
        font-weight: 700;
    }
    .mob-meta-num {
        font-variant-numeric: tabular-nums;
        font-size: 13px;
        color: #1a1a1a;
        font-weight: 600;
    }
    .mob-meta-num b { font-size: 18px; }
    .mob-meta-bar {
        height: 12px;
        background: #f3f4f6;
        border-radius: 6px;
        overflow: hidden;
        position: relative;
    }
    .mob-meta-fill {
        height: 100%;
        border-radius: 6px;
        transition: width 0.3s ease;
    }
    .mob-meta-fill.bronze { background: linear-gradient(90deg, #d4a373 0%, #c08552 100%); }
    .mob-meta-fill.prata  { background: linear-gradient(90deg, #d1d5db 0%, #9ca3af 100%); }
    .mob-meta-fill.ouro   { background: linear-gradient(90deg, #fbbf24 0%, #f59e0b 100%); }
    /* Marca de 100% e 125% */
    .mob-meta-bar::after {
        content: "";
        position: absolute;
        top: 0; bottom: 0;
        width: 1px;
        background: #1a1a1a;
        opacity: 0.35;
        left: var(--meta-pct, 100%);
    }
    .mob-meta-marks {
        display: flex;
        justify-content: space-between;
        font-size: 10px;
        color: #9ca3af;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
        margin-top: 2px;
    }
    .mob-nivel-badge {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 12px 22px;
        border-radius: 8px;
        min-width: 130px;
        text-align: center;
    }
    .mob-nivel-badge.bronze { background: #fef3e7; border: 1px solid #f0c79c; }
    .mob-nivel-badge.prata  { background: #f3f4f6; border: 1px solid #d1d5db; }
    .mob-nivel-badge.ouro   { background: #fef3c7; border: 1px solid #fcd34d; }
    .mob-nivel-emoji { font-size: 26px; line-height: 1; }
    .mob-nivel-name {
        font-size: 13px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-top: 4px;
    }
    .mob-nivel-badge.bronze .mob-nivel-name { color: #92400e; }
    .mob-nivel-badge.prata  .mob-nivel-name { color: #4b5563; }
    .mob-nivel-badge.ouro   .mob-nivel-name { color: #92400e; }
    .mob-nivel-pct {
        font-size: 11px;
        color: #6b7280;
        margin-top: 2px;
        font-variant-numeric: tabular-nums;
    }

    /* ---------- VENDEDOR CARD ---------- */
    .mob-vend {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 18px;
        height: 100%;
        display: flex;
        flex-direction: column;
        gap: 12px;
    }
    .mob-vend-head {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .mob-avatar {
        width: 40px; height: 40px;
        border-radius: 6px;
        background: #fff3eb;
        color: #FF6600;
        font-weight: 700;
        font-size: 14px;
        display: flex; align-items: center; justify-content: center;
        flex-shrink: 0;
        border: 1px solid #ffe1cc;
    }
    .mob-avatar.lider {
        background: #1a1a1a;
        color: #ffffff;
        border-color: #1a1a1a;
    }
    .mob-vend-name {
        font-weight: 600;
        font-size: 14px;
        color: #1a1a1a;
        line-height: 1.2;
    }
    .mob-vend-role {
        font-size: 10px;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 2px;
    }
    .mob-vend-stats {
        display: flex;
        gap: 16px;
        padding-top: 8px;
        border-top: 1px solid #f3f4f6;
    }
    .mob-vend-stat { flex: 1; }
    .mob-vend-stat-num {
        font-size: 22px;
        font-weight: 700;
        color: #1a1a1a;
        line-height: 1;
        font-variant-numeric: tabular-nums;
    }
    .mob-vend-stat-lbl {
        font-size: 10px;
        color: #6b7280;
        text-transform: uppercase;
        margin-top: 4px;
        letter-spacing: 0.4px;
        font-weight: 600;
    }

    /* ---------- Section titles ---------- */
    .mob-section-title {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #6b7280;
        margin: 16px 0 12px 0;
        padding-bottom: 8px;
        border-bottom: 1px solid #e5e7eb;
    }

    /* ---------- BADGES Δ% (up/dn/ne) ---------- */
    .mob-delta {
        display: inline-flex;
        align-items: center;
        gap: 3px;
        font-size: 11px;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 4px;
        margin-left: 6px;
        vertical-align: middle;
        font-variant-numeric: tabular-nums;
    }
    .mob-delta.up { background: #ecfdf5; color: #047857; border: 1px solid #d1fae5; }
    .mob-delta.dn { background: #fef2f2; color: #b91c1c; border: 1px solid #fee2e2; }
    .mob-delta.ne { background: #f9fafb; color: #4b5563; border: 1px solid #e5e7eb; }
    .mob-delta::before {
        font-size: 9px;
        font-weight: 700;
    }
    .mob-delta.up::before { content: "▲"; }
    .mob-delta.dn::before { content: "▼"; }
    .mob-delta.ne::before { content: "■"; }

    /* ---------- COMPARATIVO (barras) ---------- */
    .mob-cmp-row { margin-bottom: 18px; }
    .mob-cmp-head {
        display: flex;
        justify-content: space-between;
        margin-bottom: 8px;
    }
    .mob-cmp-head .mob-cmp-label {
        font-weight: 700;
        font-size: 12px;
        color: #1a1a1a;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .mob-cmp-bar {
        height: 6px;
        background: #f3f4f6;
        border-radius: 3px;
        overflow: hidden;
        margin-bottom: 4px;
    }
    .mob-cmp-fill {
        height: 100%;
        border-radius: 3px;
    }
    .mob-cmp-fill.prev { background: #6b7280; }
    .mob-cmp-fill.curr { background: #FF6600; }
    .mob-cmp-fill.proj {
        background: #FF6600;
        background-image: linear-gradient(45deg, rgba(255,255,255,0.55) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.55) 50%, rgba(255,255,255,0.55) 75%, transparent 75%);
        background-size: 8px 8px;
        opacity: 0.85;
    }
    .mob-cmp-mini {
        display: flex;
        justify-content: space-between;
        font-size: 11px;
        color: #4b5563;
        font-variant-numeric: tabular-nums;
    }
    .mob-cmp-mini b { color: #1a1a1a; font-weight: 600; }

    /* ---------- TABELA ---------- */
    .mob-tab {
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
        background: #ffffff;
        border-radius: 8px;
        overflow: hidden;
        border: 1px solid #e5e7eb;
    }
    .mob-tab th {
        text-align: left;
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        color: #6b7280;
        padding: 10px 14px;
        border-bottom: 1px solid #e5e7eb;
        background: #f9fafb;
        font-weight: 700;
    }
    .mob-tab td {
        padding: 10px 14px;
        border-bottom: 1px solid #f3f4f6;
        color: #1a1a1a;
    }
    .mob-tab tr:last-child td { border-bottom: none; }
    .mob-tab tr:hover td { background: #fafbfc; }
    .mob-tab tr.total td {
        font-weight: 700;
        background: #1a1a1a;
        color: #ffffff;
        border-top: none;
    }
    .mob-tab tr.total:hover td { background: #1a1a1a; }
    .mob-tab td.num {
        text-align: right;
        font-variant-numeric: tabular-nums;
    }

    /* ---------- TABELA DE ITENS DO RELATÓRIO ---------- */
    .mob-tab-itens { font-size: 12px; }
    .mob-tab-itens th, .mob-tab-itens td {
        padding: 8px 10px;
        white-space: nowrap;
    }
    .mob-tab-itens td:nth-child(4) {  /* Cliente — pode quebrar */
        white-space: normal;
        max-width: 220px;
    }
    .mob-tab-itens tr.row-devolvido td {
        background: #fef2f2;
        color: #7f1d1d;
    }
    .mob-tab-itens tr.row-devolvido:hover td { background: #fee2e2; }
    .mob-tab-itens tfoot tr.total td {
        font-weight: 700;
        background: #1a1a1a;
        color: #ffffff;
        font-size: 14px;
        padding: 12px 14px;
    }
    .mob-tab-itens tfoot tr.total td.num { font-size: 16px; }

    /* ---------- TERMO DE CIÊNCIA + ASSINATURA ---------- */
    .mob-termo {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 24px 28px;
        margin: 28px 0 20px;
        border-left: 3px solid #FF6600;
    }
    .mob-termo-titulo {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #6b7280;
        font-weight: 800;
        margin-bottom: 12px;
    }
    .mob-termo-corpo {
        font-size: 14px;
        color: #1a1a1a;
        line-height: 1.6;
        margin-bottom: 32px;
    }
    .mob-assinatura {
        max-width: 420px;
        margin-top: 28px;
    }
    .mob-assinatura-linha {
        height: 1px;
        background: #1a1a1a;
        margin-bottom: 6px;
    }
    .mob-assinatura-label {
        font-size: 11px;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 600;
        text-align: center;
    }

    /* ---------- Tabs nativas Streamlit ---------- */
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 4px;
        border-bottom: 1px solid #e5e7eb;
    }
    button[data-baseweb="tab"] {
        font-weight: 600 !important;
        font-size: 13px !important;
        text-transform: uppercase;
        letter-spacing: 0.4px;
        color: #6b7280 !important;
        padding: 10px 16px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] { color: #1a1a1a !important; }
    [data-baseweb="tab-highlight"] { background-color: #FF6600 !important; height: 2px !important; }

    /* ---------- Misc ---------- */
    hr { border-color: #e5e7eb !important; }
    .stMarkdown h2, .stMarkdown h3 { color: #1a1a1a !important; font-weight: 700; }
</style>
"""


def aplicar_css() -> None:
    st.markdown(CSS_MOBILLI, unsafe_allow_html=True)


def formatar_brl(valor: Decimal) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_data(d: date | None) -> str:
    if not d:
        return "-"
    return d.strftime("%d/%m/%Y")


def mes_ano_label(d: date) -> str:
    return f"{MESES_PT[d.month]}/{d.year}"


def opcoes_de_mes(
    ate_mes_seguinte: bool = True,
    desde: date | None = None,
) -> list[date]:
    """Lista meses do `desde` (default: PRIMEIRO_MES_VIGENTE) até o mês atual
    (ou seguinte), ordenados do mais recente pro mais antigo."""
    floor = desde or PRIMEIRO_MES_VIGENTE
    hoje = date.today()
    inicio = hoje.replace(day=1)
    if ate_mes_seguinte:
        inicio = inicio + relativedelta(months=1)

    meses: list[date] = []
    m = inicio
    while m >= floor:
        meses.append(m)
        m = m - relativedelta(months=1)
    return meses


def variacao_pct(atual: int | float, anterior: int | float) -> float:
    """Variação percentual: (atual - anterior) / anterior * 100.

    Retorna 0.0 se `anterior` é zero (evita divisão por zero / inf).
    """
    if not anterior:
        return 0.0
    return (float(atual) - float(anterior)) / float(anterior) * 100.0


def classe_delta(pct: float) -> str:
    """Classe CSS por sinal: up (≥ +1%), dn (≤ -1%), ne (entre)."""
    if pct >= 1.0:
        return "up"
    if pct <= -1.0:
        return "dn"
    return "ne"


def formatar_pct(pct: float) -> str:
    """+5% / -17% / 0%"""
    sinal = "+" if pct > 0 else ""
    return f"{sinal}{pct:.0f}%"


MES_PT_CURTO: dict[int, str] = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}


def mes_curto(d: date) -> str:
    return MES_PT_CURTO[d.month]
