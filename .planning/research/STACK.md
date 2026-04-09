# Technology Stack

**Project:** Mobílli — Relatório de Comissão de Vendedores
**Researched:** 2026-04-09

---

## Recommended Stack

### Core Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.11+ | Runtime | Streamlit Cloud default runtime; 3.10 is minimum for fpdf2 and WeasyPrint, but 3.11 is current stable with better performance |
| Streamlit | 1.45+ (pin to latest stable) | UI framework, filter widgets, download buttons | Already decided in PROJECT.md; `st.download_button` with callable (lazy generation) landed in late-2025 releases — use it for ZIP generation without blocking the UI |

**Confidence:** HIGH — official Streamlit docs and release notes confirm version 1.56.0 current as of March 2026.

---

### HTTP / CRM Integration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| fast-bitrix24 | 1.8.6 | Bitrix24 REST API via webhook | Only actively-maintained Python wrapper that handles Bitrix24's quirky 50-item pagination automatically via `get_all()`. Supports batch calls (`call_batch()`), rate limiting, and both sync/async clients. Zero OAuth — uses webhook URL directly, matching the project's existing setup |

**Do NOT use:**
- `requests` raw calls — you'd rewrite `get_all()` pagination manually (Bitrix24 returns max 50 items per call, total in `total` field).
- `bitrix24-rest` or `pybitrix24` — last releases 2022-2023, unmaintained, no pagination helpers.
- `httpx` directly — same problem as raw `requests` for this API.

**Confidence:** MEDIUM — PyPI confirms version 1.8.6 released July 2025, actively maintained. Library itself is Russian-community maintained; if it goes abandoned, falling back to raw `requests` + manual pagination is straightforward.

---

### PDF Generation

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| fpdf2 | 2.8.7 | Generate styled A4 commission report PDFs | Pure Python, zero system dependencies, works on Streamlit Cloud without `packages.txt` hacks. Supports custom fonts (TTF), images (logo), tables, multi-cell text, and has a template system suitable for a fixed-layout form. Actively maintained under py-pdf org |

**Do NOT use WeasyPrint** — although it produces better CSS-styled output, it requires system libraries (pango, libcairo2, libgdk-pixbuf) that must be listed in `packages.txt` on Streamlit Cloud. This works but is fragile: library versions on Debian Bullseye (the Cloud base) can lag, and the `OSError: cannot load library 'pango-1.0-0'` failure has been reported on Streamlit Community Cloud as recently as April 2024. The workaround (`packages.txt` with `libpango-1.0-0`) resolves it but adds deployment risk for a non-technical RH user sharing a link.

**Do NOT use ReportLab** — the free version (reportlab package) uses a low-level canvas API with steep learning curve for styled tabular reports. The PLATYPUS layout engine works, but fpdf2 achieves the same result with less code for this use case.

**Confidence:** HIGH — fpdf2 2.8.7 confirmed on PyPI (Feb 2026). WeasyPrint Streamlit Cloud deployment issue confirmed in community forum.

---

### Data Manipulation

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pandas | 2.2.x (NOT 3.x yet) | Date filtering, deal grouping, commission calculations | The commission logic (M-1/M-2 parcela rules, churn detection, goal percentage calculation) maps naturally to DataFrame operations. Pandas 3.0 introduced copy-on-write by default (released Jan 2026) — wait for Streamlit Cloud to stabilise on it before adopting. Pin to `pandas>=2.2,<3.0` in requirements.txt |

**Confidence:** MEDIUM — version pinning rationale is based on pandas 3.0 behavioral changes (copy-on-write) being a significant shift. If the team is comfortable with it, `pandas>=2.2` without upper cap is fine.

---

### ZIP Generation

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| zipfile | stdlib | Bundle all-sellers ZIP download | Python standard library, no extra dependency. Use `io.BytesIO` as in-memory buffer and pass the result to `st.download_button(data=callable)` for lazy generation |

**Confidence:** HIGH — stdlib, no version concerns.

---

### Secrets / Configuration

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| st.secrets | Streamlit built-in | Store Bitrix24 webhook URL | Streamlit Community Cloud has a built-in secrets manager (TOML format). Paste webhook URL into app settings → Advanced. Accessed in code as `st.secrets["BITRIX_WEBHOOK"]`. Local dev uses `.streamlit/secrets.toml` (git-ignored) |

**Do NOT use:** `.env` files with `python-dotenv` — they work locally but add complexity for Streamlit Cloud where `st.secrets` is the native solution.

**Confidence:** HIGH — confirmed in official Streamlit documentation.

---

## Complete Stack Summary

```
Python 3.11
Streamlit >=1.45
fast-bitrix24 ==1.8.6
fpdf2 ==2.8.7
pandas >=2.2,<3.0
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| PDF generation | fpdf2 | WeasyPrint | System deps (pango/cairo) fragile on Streamlit Cloud |
| PDF generation | fpdf2 | ReportLab | Low-level canvas API; steeper boilerplate for tabular reports |
| Bitrix24 client | fast-bitrix24 | raw requests | Manual pagination required (50 items/page, `get_all()` equivalent) |
| Bitrix24 client | fast-bitrix24 | pybitrix24 / bitrix24-rest | Unmaintained (last release 2022-2023) |
| Data manipulation | pandas | polars | Streamlit's `st.dataframe` integration is optimised for pandas; no benefit for this scale |
| Secrets | st.secrets | python-dotenv | Not native to Streamlit Cloud; doubles config surface area |
| Data manipulation | pandas 2.2 | pandas 3.0 | Copy-on-write behavior change in 3.0 needs validation with Streamlit Cloud |

---

## Installation

```bash
# requirements.txt (Streamlit Cloud reads this automatically)
streamlit>=1.45
fast-bitrix24==1.8.6
fpdf2==2.8.7
pandas>=2.2,<3.0

# packages.txt — only needed IF WeasyPrint is used instead (NOT recommended)
# libpango-1.0-0
# libgdk-pixbuf2.0-0
# libcairo2
```

Local dev:
```bash
pip install streamlit fast-bitrix24 fpdf2 "pandas>=2.2,<3.0"
```

Secrets setup (local):
```toml
# .streamlit/secrets.toml  — git-ignored
BITRIX_WEBHOOK = "https://your-domain.bitrix24.com/rest/USER_ID/TOKEN/"
```

---

## Deployment Notes

- **Runtime:** Streamlit Community Cloud automatically uses Python 3.11 when no `.python-version` file is present. Add `.python-version` with content `3.11` if you need to pin it explicitly.
- **No `packages.txt` required** with this stack (fpdf2 is pure Python).
- **Cold start:** `fast-bitrix24` makes multiple HTTP calls to Bitrix24 on each filter change. Use `@st.cache_data(ttl=300)` to cache API responses for 5 minutes to keep the app responsive.
- **Free tier limits:** Streamlit Community Cloud free tier may sleep inactive apps after ~7 days without a deploy. RH should expect a ~30s wake-up on first access.

---

## Sources

- Streamlit release notes 2025/2026: https://docs.streamlit.io/develop/quick-reference/release-notes/2025
- Streamlit secrets management: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- Streamlit app dependencies (packages.txt): https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
- fast-bitrix24 PyPI: https://pypi.org/project/fast-bitrix24/
- fast-bitrix24 GitHub: https://github.com/leshchenko1979/fast_bitrix24
- fpdf2 PyPI: https://pypi.org/project/fpdf2/
- fpdf2 HTML support docs: https://py-pdf.github.io/fpdf2/HTML.html
- WeasyPrint PyPI: https://pypi.org/project/weasyprint/
- WeasyPrint on Streamlit Cloud (deployment issue + resolution): https://discuss.streamlit.io/t/installing-weasyprint-for-pdf-generation/66837
- pandas PyPI: https://pypi.org/project/pandas/
- PDF library comparison 2025: https://templated.io/blog/generate-pdfs-in-python-with-libraries/
- WeasyPrint vs ReportLab comparison: https://dev.to/claudeprime/generate-pdfs-in-python-weasyprint-vs-reportlab-ifi
