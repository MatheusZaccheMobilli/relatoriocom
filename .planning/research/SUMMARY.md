# Research Summary: Relatório de Comissão Mobílli

**Synthesized:** 2026-04-09
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

## Executive Summary

Streamlit app connecting to Bitrix24 CRM via webhook to generate monthly sales commission PDFs for HR. The domain is well-understood with no novel technical challenges — only execution risks that are fully documented and preventable. The recommended stack (Python 3.11 + Streamlit + fast-bitrix24 + fpdf2 + pandas) is deployment-safe on Streamlit Cloud without system-level dependencies.

The business logic is the hardest part: TM-018 commission table, 3-parcel installment rule with churn cutoff. Must be isolated pure-function services with full unit test coverage before any UI is built. Custom Bitrix24 field IDs for CPF and vehicle plate are the primary unknowns blocking progress — must be resolved in Phase 1 by querying the live API.

## Recommended Stack

| Component | Library | Version | Confidence |
|-----------|---------|---------|------------|
| Framework | Streamlit | >=1.45 | HIGH |
| Bitrix24 client | fast-bitrix24 | 1.8.6 | MEDIUM-HIGH |
| PDF generation | fpdf2 | 2.8.7 | HIGH |
| Data manipulation | pandas | >=2.2,<3.0 | HIGH |
| ZIP | zipfile (stdlib) | — | HIGH |
| Secrets | st.secrets | — | HIGH |

**Do NOT use:** WeasyPrint (system deps crash Streamlit Cloud), pandas 3.0, unmaintained Bitrix24 wrappers, python-dotenv on Cloud.

## Table Stakes Features

- Filter panel (vendedor/mes/tipo)
- Dados do vendedor (nome/CPF)
- Bloco de meta (Bronze 75%/Prata 100%/Ouro 125%)
- Lista de verificacao de pagamento (parcela/cliente/placa/datas)
- Indicadores (fechados/devolvidos)
- TM-018 commission calculation (B2C only)
- 3-parcel installment rule with churn cessation
- Total a receber (R$)
- PDF individual download styled with Mobilli branding
- Termo de ciencia with signature space

## High-Value Differentiators (include in v1)

- ZIP de todos os vendedores
- `@st.cache_data(ttl=300)` on API calls
- Preview na tela before download
- Meta configuravel via number_input
- Filename with vendedor+mes

## Architecture

Five-layer unidirectional: **UI → Orchestrator → Business Logic → Data Access → Export**

- Centralized `models.py` dataclasses — no raw dicts cross layer boundaries
- Commission engine as pure functions — testable without CRM or Streamlit
- Single `ReportData` dataclass consumed by both preview and PDF
- PDF generated only on explicit button click

## Critical Pitfalls

| Pitfall | Prevention |
|---------|------------|
| Pagination truncation (>50 deals silently lost) | Use fast-bitrix24 `get_all()` |
| Wrong date field for "closed in month" | Validate against known deals in Phase 1 |
| Float arithmetic on R$ totals | Use `Decimal("string")` throughout |
| WeasyPrint crash on Cloud | Use fpdf2 instead |
| Parcela churn off-by-one | Use `dateutil.relativedelta`; unit-test edge cases |
| Bulk API calls rate limit on ZIP | Single bulk fetch, group client-side |
| Secrets in git | Add secrets.toml to .gitignore before first commit |
| Portuguese chars in PDF | Register TTF font (NotoSans/DejaVuSans) before any template |

## Gaps to Resolve in Phase 1

1. CPF custom field ID (query `user.fields`)
2. Vehicle plate custom field ID (query `crm.deal.fields`)
3. Churn/cancellation stage ID in pipeline 48
4. Meta value — global or per-salesperson?
5. Venda 0km vs Usado distinction in pipeline 40
6. Validate `CLOSEDATE` behavior against known deals

## Suggested Phase Order

1. **Foundation + API Validation** — custom field discovery, paginated client, typed models
2. **Business Logic Engine** — commission calc, installments, goal levels (pure functions, unit tested)
3. **PDF Template + Single Report** — fpdf2 with Mobilli branding, Portuguese fonts
4. **Streamlit UI + Preview** — filters, preview, session state (thin layer on stable models)
5. **Bulk ZIP Export + Polish** — bulk fetch, in-memory ZIP, caching, progress bar

---
*Synthesized: 2026-04-09*
