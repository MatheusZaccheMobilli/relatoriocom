# Architecture Patterns

**Domain:** Streamlit commission report app (Bitrix24 CRM + PDF export)
**Researched:** 2026-04-09
**Overall confidence:** HIGH (Streamlit patterns, Bitrix24 API), MEDIUM (PDF library choice for Cloud)

---

## Recommended Architecture

Five distinct layers with unidirectional data flow. Each layer depends only on the layer below it — UI calls services, services call the API client, nothing calls upward.

```
┌─────────────────────────────────────────────────┐
│  UI Layer (Streamlit)                           │
│  app.py  +  components/                        │
│  Filter widgets → triggers report render        │
└────────────────┬────────────────────────────────┘
                 │ calls
┌────────────────▼────────────────────────────────┐
│  Report Orchestrator                            │
│  services/report_builder.py                    │
│  Coordinates: fetch → transform → calculate    │
│               → assemble report data model     │
└────────────────┬────────────────────────────────┘
                 │ calls
┌────────────────▼────────────────────────────────┐
│  Business Logic Layer                           │
│  services/commission.py                        │
│  services/installments.py                      │
│  Pure functions: no I/O, no Streamlit           │
└────────────────┬────────────────────────────────┘
                 │ calls
┌────────────────▼────────────────────────────────┐
│  Data Access Layer                              │
│  bitrix/client.py  +  bitrix/transformers.py   │
│  HTTP calls to webhook, pagination, mapping     │
└────────────────┬────────────────────────────────┘
                 │ calls
┌────────────────▼────────────────────────────────┐
│  Export Layer                                   │
│  pdf/generator.py  +  pdf/templates/            │
│  Accepts report data model → returns bytes      │
└─────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | File(s) | Responsibility | Communicates With |
|-----------|---------|---------------|-------------------|
| UI Layer | `app.py`, `components/filters.py`, `components/report_preview.py` | Render widgets, handle filter state, trigger downloads | Report Orchestrator |
| Report Orchestrator | `services/report_builder.py` | Coordinate fetch + transform + calculate into a `ReportData` dataclass | All service + data layers |
| Commission Engine | `services/commission.py` | Apply TM-018 rules: level detection (Bronze/Prata/Ouro), rate lookup, total calculation | Called by Report Orchestrator |
| Installment Engine | `services/installments.py` | Determine which deals belong to M-1/M-2 windows, flag churned contracts | Called by Report Orchestrator |
| Bitrix24 Client | `bitrix/client.py` | Execute HTTP calls against webhook, handle pagination (50-record pages), rate limit retries | External Bitrix24 API |
| Bitrix24 Transformers | `bitrix/transformers.py` | Map raw API dicts to typed Python dataclasses (Deal, Seller, Customer) | Bitrix24 Client |
| PDF Generator | `pdf/generator.py` | Accept `ReportData`, render HTML template, return PDF bytes | Jinja2 templates |
| PDF Templates | `pdf/templates/*.html` | HTML/CSS layout in Mobillli brand style | PDF Generator |
| Config | `config.py` | Load secrets, commission table constants, goal defaults | All layers |
| Data Models | `models.py` | Dataclasses: `Deal`, `Seller`, `ReportData`, `InstallmentRow` | Shared across all layers |

---

## Recommended File/Module Structure

```
relatorio/
├── app.py                          # Streamlit entry point — only UI code
├── config.py                       # st.secrets + constants (commission rates, goal defaults)
├── models.py                       # Dataclasses: Deal, Seller, Customer, ReportData, InstallmentRow
├── requirements.txt
├── packages.txt                    # apt packages if WeasyPrint used (libpango, etc.)
│
├── bitrix/
│   ├── __init__.py
│   ├── client.py                   # HTTP calls, pagination loop, retry logic
│   └── transformers.py             # Raw dict → typed dataclasses
│
├── services/
│   ├── __init__.py
│   ├── report_builder.py           # Orchestrator: fetch + transform + calculate
│   ├── commission.py               # TM-018 logic: level detection, rate lookup, total
│   └── installments.py             # M-1/M-2 windowing, churn detection
│
├── pdf/
│   ├── __init__.py
│   ├── generator.py                # ReportData → PDF bytes (via Jinja2 + library)
│   └── templates/
│       ├── report.html             # Single-seller report layout
│       └── style.css               # Mobillli brand styles
│
└── components/
    ├── __init__.py
    ├── filters.py                  # Sidebar: seller selector, month picker, operation type
    └── report_display.py           # Render report preview in Streamlit UI
```

**Rule:** `app.py` must never import from `bitrix/` or `pdf/` directly. It only calls `services/report_builder.py`. This keeps the Streamlit rerun lifecycle from tangling with I/O.

---

## Data Flow

```
User changes filter (seller / month / operation type)
    │
    ▼
app.py reads st.session_state → calls report_builder.build(seller_id, month, op_type)
    │
    ▼
report_builder.py:
    1. bitrix/client.get_deals(category_id, date_range)     → list[dict]
    2. bitrix/transformers.to_deals(raw)                    → list[Deal]
    3. bitrix/client.get_seller(seller_id)                  → dict
    4. bitrix/transformers.to_seller(raw)                   → Seller
    5. services/installments.compute(deals, month)          → list[InstallmentRow]
    6. services/commission.calculate(installments, seller)  → CommissionResult
    7. Assemble → ReportData dataclass
    │
    ▼
app.py renders ReportData via components/report_display.py (preview)
    │
    ▼  [on "Gerar PDF" click]
pdf/generator.render(report_data)  → bytes
    │
    ▼
st.download_button(data=pdf_bytes, file_name="comissao_vendedor_mes.pdf")
```

For the "ZIP de todos os vendedores" flow:

```
report_builder iterates all sellers → list[ReportData]
pdf/generator.render() called per seller → list[bytes]
zipfile.ZipFile assembled in memory → st.download_button
```

---

## Key Architecture Decisions

### 1. Centralized `models.py` with dataclasses

All data shapes live in one file. Every layer imports from `models.py` and returns typed objects — no raw dicts travel beyond `transformers.py`. This eliminates the "what keys does this dict have?" problem across layers.

### 2. `@st.cache_data` on Bitrix24 calls

Decorate `client.get_deals()` and `client.get_seller()` with `@st.cache_data(ttl=300)`. Streamlit reruns on every widget interaction — without caching, every filter change triggers a full API roundtrip. A 5-minute TTL is appropriate since CRM data changes slowly.

```python
@st.cache_data(ttl=300)
def get_deals(category_id: int, year: int, month: int) -> list[dict]:
    ...
```

**Important:** cache is keyed by function arguments, so different (seller, month) combinations get their own cache entry automatically.

### 3. PDF library: ReportLab over WeasyPrint for Cloud

WeasyPrint requires system-level `pango` and `cairo` libraries. While installable via `packages.txt` on Streamlit Community Cloud, it has documented instability (OSError: cannot load library 'pango-1.0-0'). ReportLab is pure Python, installs without system dependencies, and is production-stable on Streamlit Cloud. Use `reportlab` with `platypus` for the table/layout structure.

If brand-accurate HTML rendering is mandatory, WeasyPrint + `packages.txt` (libpango-1.0-0, libcairo2, libgdk-pixbuf2.0-0) is viable but adds deployment risk.

**Recommended:** ReportLab for v1 due to Cloud reliability. Can migrate to WeasyPrint if layout requirements demand HTML/CSS fidelity.

### 4. Bitrix24 pagination handled entirely in `client.py`

The API returns 50 records per page with a `next` offset. `client.py` runs the pagination loop internally — callers receive a complete list. This keeps business logic free of API pagination details.

```python
def get_deals(category_id, date_from, date_to):
    all_deals = []
    start = 0
    while True:
        response = _call("crm.deal.list", filter={...}, start=start)
        all_deals.extend(response["result"])
        if "next" not in response:
            break
        start = response["next"]
    return all_deals
```

### 5. Commission engine as pure functions

`services/commission.py` takes only dataclasses as input and returns dataclasses. No Streamlit, no HTTP, no file I/O. This makes it trivially unit-testable and safe to reuse for future B2B rules.

---

## Patterns to Follow

### Pattern: Report Data Model as Single Source of Truth

Assemble one `ReportData` dataclass in `report_builder.py`. Both the Streamlit preview and the PDF generator consume the same object. This eliminates divergence between what the UI shows and what the PDF contains.

```python
@dataclass
class ReportData:
    seller: Seller
    month: int
    year: int
    operation_type: str
    goal_value: float
    level: str                        # "Bronze" | "Prata" | "Ouro"
    deals_closed: int
    deals_churned: int
    installment_rows: list[InstallmentRow]
    total_commission: float
```

### Pattern: Secrets via `st.secrets`, constants via `config.py`

Webhook URL lives in `.streamlit/secrets.toml` (maps to `st.secrets["BITRIX_WEBHOOK"]`). Commission rate table and goal defaults are constants in `config.py` — readable and editable by non-developers.

---

## Anti-Patterns to Avoid

### Anti-Pattern: Bitrix24 calls inside `app.py`

Mixing API calls with Streamlit widget rendering causes the HTTP call to execute on every rerun (every filter change, every button click). Isolate all I/O in `services/` and let `@st.cache_data` govern reuse.

### Anti-Pattern: Building the PDF inside `app.py`

PDF generation is CPU-bound and slow. It should only run when the user explicitly clicks "Gerar PDF", not on every filter change. Use `st.button` to gate `pdf/generator.render()`.

### Anti-Pattern: Raw dicts passed between layers

Passing `deal["ASSIGNED_BY_ID"]` through multiple files makes refactoring fragile. All data crossing a layer boundary must be a typed dataclass from `models.py`.

### Anti-Pattern: Commission rules hardcoded in UI layer

The TM-018 table (Bronze 8%, Prata 9%, Ouro 10% for Locação, etc.) changes over time. Keep it in `config.py` as a constant dict, not embedded in rendering code.

---

## Build Order (Phase Dependencies)

The architecture has a strict dependency order:

```
Phase 1: Foundation
  models.py + config.py + bitrix/client.py
  Reason: Everything else depends on data models and API access.
  Nothing else can be built without these.

Phase 2: Data Access Completeness
  bitrix/transformers.py
  Reason: Typed objects needed before business logic can be written.

Phase 3: Business Logic
  services/installments.py → services/commission.py → services/report_builder.py
  Reason: Installments feed commission; commission feeds report builder.
  Build and unit-test in isolation (no Streamlit needed).

Phase 4: PDF Export
  pdf/templates/ → pdf/generator.py
  Reason: Needs complete ReportData model from Phase 1+3.
  Can be developed in parallel with Phase 3 once models.py is stable.

Phase 5: Streamlit UI
  components/ → app.py
  Reason: UI is the thinnest layer; builds on top of everything.
  Should be assembled last to avoid rewiring widgets as data models evolve.

Phase 6: ZIP Export
  Thin addition on top of Phase 4+5 — loop + zipfile.
```

Phases 3 and 4 can be parallelized once `models.py` is locked.

---

## Scalability Considerations

| Concern | Current Scale (v1) | Future Scale |
|---------|--------------------|--------------|
| API calls | Cache with `@st.cache_data(ttl=300)` | Add background refresh if TTL too aggressive |
| PDF generation | Synchronous, fine for single report | Use `st.spinner` for UX; ZIP generation may need progress bar |
| Seller list | Fetched from Bitrix24 on load | Cache aggressively — seller list changes rarely |
| Commission rules | Constants in `config.py` | Move to database/config file if rules change frequently |
| Multi-user contention | Streamlit Cloud handles concurrency natively | No action needed for HR team scale |

---

## Sources

- [Streamlit Architecture Docs](https://docs.streamlit.io/develop/concepts/architecture) — HIGH confidence
- [st.cache_data Documentation](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data) — HIGH confidence
- [crm.deal.list API Reference](https://apidocs.bitrix24.com/api-reference/crm/deals/crm-deal-list.html) — HIGH confidence
- [WeasyPrint on Streamlit Cloud thread](https://discuss.streamlit.io/t/installing-weasyprint-for-pdf-generation/66837) — MEDIUM confidence (community report of pango OSError)
- [Streamlit Community Cloud app dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies) — HIGH confidence
- [Project structure discussion (2025)](https://discuss.streamlit.io/t/project-structure-for-medium-and-large-apps-full-example-ui-and-logic-splitted/59967) — MEDIUM confidence (community pattern, not official)
- [fast-bitrix24 PyPI](https://pypi.org/project/fast-bitrix24/) — MEDIUM confidence (library availability verified)
