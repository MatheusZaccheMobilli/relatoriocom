# Domain Pitfalls

**Domain:** Streamlit + Bitrix24 CRM + PDF generation (commission reports)
**Researched:** 2026-04-09
**Confidence:** HIGH (verified against official Bitrix24 docs, Streamlit docs, library docs)

---

## Critical Pitfalls

Mistakes that cause rewrites, silent wrong data, or deployment failure.

---

### Pitfall 1: Pagination truncation — silent data loss on crm.deal.list

**What goes wrong:** `crm.deal.list` returns at most 50 records per call. If a salesperson has more than 50 deals in the window being queried, only the first 50 come back. No error is raised. Commission totals are silently wrong.

**Why it happens:** The `start` parameter controls the offset. Without a loop that increments `start` by 50 and checks the `total` field in the response, the first call looks like a complete result.

**Consequences:** A high-performer with many deals gets an understated commission. The RH signs off on a wrong number. Trust in the tool evaporates after the first month.

**Prevention:**
```python
def fetch_all_deals(webhook_url, filter_params):
    results = []
    start = 0
    while True:
        resp = requests.post(webhook_url + "crm.deal.list", json={
            "filter": filter_params,
            "select": [...],
            "start": start
        }).json()
        results.extend(resp["result"])
        if len(resp["result"]) < 50:
            break
        start += 50
    return results
```
For batch efficiency, use Bitrix24's `batch` method (50 sub-requests per call) once total count is known from the first call.

**Detection:** In testing, create a salesperson with >50 deals in a single month and assert `len(deals) > 50`.

**Phase:** Phase 1 (Bitrix24 integration) — build the paginated fetcher before anything else; every downstream calculation depends on it.

---

### Pitfall 2: CLOSEDATE vs. DATE_MODIFY — filtering the wrong date

**What goes wrong:** `CLOSEDATE` is the "expected close date" field the salesperson sets manually, not the actual date the deal moved to a closed stage. `DATE_MODIFY` is the last-modified timestamp. Neither is a reliable "date closed won" without additional logic.

**Why it happens:** The API field name is misleading. In some Bitrix24 configurations, `CLOSEDATE` is updated when the stage changes; in others, it reflects only the manually entered forecast date. The `CLOSED` field (Y/N) only tells you whether a deal is currently closed, not when it became closed.

**Consequences:** Deals close in month M but appear in a different month's commission report, or not at all.

**Prevention:**
- On first integration, call `crm.deal.fields` to inspect all date fields available in the specific Bitrix24 instance.
- Validate against 5–10 known deals: pull the deal, compare `CLOSEDATE`, `DATE_MODIFY`, and `DATE_CREATE` against actual CRM UI values.
- Build an acceptance test: "deal closed on date X must appear in month X's report."
- Consider filtering by `STAGE_ID` (closed stages for pipelines 48 and 40) combined with `DATE_MODIFY` if `CLOSEDATE` is unreliable on this account.

**Detection warning sign:** Running the report for the current month but seeing deals from 2–3 months ago included, or recent deals missing.

**Phase:** Phase 1 — must be validated against real data before commission logic is built on top of it.

---

### Pitfall 3: Float arithmetic produces wrong R$ commission totals

**What goes wrong:** Calculating commission as `deal_value * 0.034` using Python floats produces values like `R$ 1.020000000000001` instead of `R$ 1.02`. When summed across many deals, the error compounds.

**Why it happens:** Binary floating-point cannot represent most decimal fractions exactly. `0.034` in float is `0.033999999999999...`.

**Consequences:** The printed "Total a receber" is off by a few centavos, creating distrust. Worse, if the rounding mode is wrong, the company under/overpays.

**Prevention:**
```python
from decimal import Decimal, ROUND_HALF_UP

rate = Decimal("0.034")          # always from string, never from float
value = Decimal(str(deal_value)) # convert API float via string
commission = value * rate
total = commission.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```
Use `Decimal` throughout the entire calculation pipeline. Never mix `float` and `Decimal` in arithmetic.

**Detection:** Write a unit test: `assert calculate_commission(3000.00, "bronze", "locacao") == Decimal("240.00")`.

**Phase:** Phase 2 (commission logic) — enforce `Decimal` from day one; retrofitting is error-prone.

---

### Pitfall 4: WeasyPrint system dependencies break Streamlit Cloud deploy

**What goes wrong:** WeasyPrint requires Pango, Cairo, and GDK-PixBuf — C libraries that cannot be installed via `pip`. Streamlit Cloud uses Debian/Ubuntu. Without a `packages.txt` file declaring these apt packages, the deploy fails with:
```
OSError: cannot load library 'pango-1.0-0': libpango-1.0-0.so.0: cannot open shared object file
```

**Why it happens:** WeasyPrint is a rendering engine that wraps GTK+ graphical libraries. These are system-level, not Python-level, dependencies.

**Consequences:** The app deploys but crashes on first PDF generation attempt. This is not caught by local development on Windows/macOS (where GTK may already be present via other software).

**Prevention:**
Create `.streamlit/packages.txt` (committed to the repo) with:
```
libpango-1.0-0
libharfbuzz0b
libpangoft2-1.0-0
libgdk-pixbuf2.0-0
libpangocairo-1.0-0
libcairo2
```
Then add `weasyprint` to `requirements.txt` as normal.

Alternatively: use **ReportLab** instead of WeasyPrint. ReportLab is pure Python, has no system dependencies, and works on Streamlit Cloud without `packages.txt`. Trade-off is a more programmatic API vs. HTML/CSS templating.

**Detection:** The first deploy to Streamlit Cloud will fail if `packages.txt` is missing. Test on a Streamlit Cloud staging deploy before building all PDF templates.

**Phase:** Phase 0/1 — decide PDF library before writing any template code. Validate deploy works with a hello-world PDF before building the full layout.

---

### Pitfall 5: Parcela churn logic applied to wrong month boundary

**What goes wrong:** The 3-parcel rule is: deal closed in month X → pay 1/3 in X+1, 2/3 in X+2, 3/3 in X+3. Churn stops payment "in the month subsequent to cancellation." If the churn date is the last day of month M, does the last parcel get paid in M+1 or M+2? Off-by-one errors in month boundary comparisons produce wrong totals.

**Why it happens:** Python's `datetime` month arithmetic has no built-in "add 1 month" operation. Using `timedelta(days=30)` is wrong (February, 31-day months). Developers roll their own and get the edge cases wrong.

**Consequences:** A salesperson is paid for a parcel they shouldn't receive (company loses money), or is denied a parcel they're owed (salesperson grievance, HR problem).

**Prevention:**
```python
from dateutil.relativedelta import relativedelta

def get_installment_months(close_date, churn_date=None):
    """Returns list of months (as date objects) when each installment is due."""
    installments = []
    for i in range(1, 4):
        due_month = close_date + relativedelta(months=i)
        if churn_date is not None:
            # Cease payment from the month *after* churn month
            churn_cutoff = churn_date.replace(day=1) + relativedelta(months=1)
            if due_month.replace(day=1) >= churn_cutoff:
                break
        installments.append(due_month)
    return installments
```
Use `python-dateutil`'s `relativedelta` for all month arithmetic. Define "churn month" as the calendar month of `churn_date.year/churn_date.month`, and the cutoff as the first day of `churn_month + 1`.

**Detection:** Unit tests for every edge case:
- Churn on last day of month M → no payment in M+1
- Churn on first day of month M → no payment in M+1
- No churn → all 3 installments paid

**Phase:** Phase 2 (commission logic) — write tests for all edge cases before implementing the installment display table.

---

## Moderate Pitfalls

### Pitfall 6: Webhook token has no expiry but is account-scoped

**What goes wrong:** Bitrix24 incoming webhooks use a permanent secret key — there is no OAuth token refresh needed. However, the webhook is tied to the account of the user who created it. If that user is deactivated or their permissions change, the webhook stops working silently (returns 401 or empty results).

**Prevention:**
- Create the webhook under an admin account, not a regular employee's account.
- Store the full webhook URL (not just the token) in Streamlit secrets.
- Add a health-check call (`app.info` or similar) at app startup and surface a visible error if the API returns non-200.
- Document which Bitrix24 account owns the webhook in `.env.example`.

**Detection:** The app shows an empty vendor list or zero deals. Always surface API errors to the RH user rather than swallowing them.

**Phase:** Phase 1 — verify credentials and health-check before building any UI.

---

### Pitfall 7: ASSIGNED_BY_ID returns a numeric ID, not a name

**What goes wrong:** `crm.deal.list` returns `ASSIGNED_BY_ID: 42`. The salesperson's display name and CPF require a separate call to `user.get` or `user.list`. If this lookup is done deal-by-deal, it triggers N+1 API calls (one per deal) and hits rate limits.

**Prevention:**
- On app load (or with `@st.cache_data`), fetch the full user list once: `user.list` with all user IDs.
- Build a dict `{user_id: {name, cpf_custom_field}}` and use it as a lookup table.
- Cache this dict for the duration of the session; refresh only when the vendor selector changes.

**Detection warning sign:** App is slow (>5s per load) and Bitrix24 logs show hundreds of `user.get` calls.

**Phase:** Phase 1 — design the data-fetching layer with a single user-list prefetch from the start.

---

### Pitfall 8: ReportLab built-in fonts don't render Portuguese characters

**What goes wrong:** ReportLab's 14 built-in fonts (Helvetica, Times-Roman, etc.) use WinAnsiEncoding or MacRomanEncoding — neither has full support for `ã`, `õ`, `ç`, `á`, `é`, `ê`, etc. These characters render as blank squares or generic blobs in the PDF.

**Why it happens:** The 14 standard PDF fonts have limited glyph sets. Brazilian Portuguese uses characters outside the safe ASCII range constantly.

**Prevention:**
- Register a Unicode-capable TrueType font (e.g., `DejaVuSans.ttf`, `NotoSans-Regular.ttf`, or a Mobílli brand font if one exists).
```python
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
pdfmetrics.registerFont(TTFont("NotoSans", "fonts/NotoSans-Regular.ttf"))
```
- Bundle the `.ttf` file in the repo under a `fonts/` directory.
- Never use `canvas.setFont("Helvetica", 12)` for any user-facing text.

**Detection:** Generate a test PDF with the text "Declaração de comissão — João Ângelo" and visually inspect. If any character is a box or missing, the font is wrong.

**Phase:** Phase 1 (PDF proof-of-concept) — validate font rendering before building the full layout template.

---

### Pitfall 9: st.cache_data on API calls causes stale data for the RH user

**What goes wrong:** If `@st.cache_data` is applied to the Bitrix24 fetch function with the default TTL (indefinite), the first RH user who runs the report "locks in" that API snapshot for all subsequent users and sessions. If a deal was just closed in the CRM, it won't appear.

**Why it happens:** `@st.cache_data` caches by function arguments. If the filter (month, pipeline) hasn't changed, the cache is reused across users.

**Prevention:**
- Set an explicit TTL: `@st.cache_data(ttl=300)` (5 minutes) for vendor lists and deal data.
- For the main report fetch triggered by the "Generate" button, use `st.cache_data(ttl=60)` or bypass cache entirely — the data volume is small (one salesperson, one month).
- Add a "Refresh data" button that calls `st.cache_data.clear()` for power users.

**Detection:** Open the app in two browser tabs. Close a deal in Bitrix24. Reload both tabs. If one shows the deal and the other doesn't, caching is working correctly. If neither shows it after 10 minutes, TTL is too long.

**Phase:** Phase 3 (UI/UX polish) — configure TTLs after the core flows work, but flag during architecture review.

---

### Pitfall 10: ZIP of all salesperson PDFs times out Streamlit Cloud

**What goes wrong:** Generating PDFs for all salespersons at once (the "bulk ZIP" feature) requires N PDF generations sequentially in a single Streamlit script execution. If N=10 salespersons and each PDF takes 2–3 seconds, the total is 20–30 seconds. Streamlit Cloud has no documented hard timeout, but the browser HTTP connection may time out, and the user sees a spinner that never resolves.

**Prevention:**
- Use `st.progress()` to show a progress bar while generating each PDF.
- Generate PDFs lazily: generate them one at a time into a `BytesIO` buffer and add to the ZIP immediately (don't hold all N PDFs in memory simultaneously).
- Use `zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED)` with a `BytesIO` buffer — never write to disk.
- For the MVP (small team, ~5–10 salespersons), sequential generation is acceptable. If N grows, redesign.

**Detection:** Run the bulk generation with 10+ salespersons and measure wall-clock time. If >15s, add a progress indicator.

**Phase:** Phase 4 (bulk export) — design with BytesIO from day one; retrofitting disk-based generation to in-memory is painful.

---

## Minor Pitfalls

### Pitfall 11: secrets.toml accidentally committed to git

**What goes wrong:** Developer creates `.streamlit/secrets.toml` locally with the Bitrix24 webhook URL and commits it. Webhook URL is now public in git history.

**Prevention:**
- Add `.streamlit/secrets.toml` to `.gitignore` immediately when the repo is created.
- Create `.streamlit/secrets.toml.example` with placeholder values as documentation.
- On Streamlit Cloud, enter secrets through the web UI (Settings → Secrets).

**Phase:** Phase 0 (repo setup) — add to `.gitignore` before the first commit.

---

### Pitfall 12: Streamlit session_state key read before initialization

**What goes wrong:** On first load, reading `st.session_state["selected_month"]` raises a `KeyError` if the selectbox hasn't rendered yet. This causes a crash on app startup.

**Prevention:**
```python
if "selected_month" not in st.session_state:
    st.session_state["selected_month"] = default_month()
```
Initialize all session state keys at the top of the script before any widget reads them.

**Phase:** Phase 2 (UI) — defensive initialization pattern from the first widget.

---

### Pitfall 13: Bitrix24 OVERLOAD_LIMIT / QUERY_LIMIT_EXCEEDED on bulk operations

**What goes wrong:** Generating the ZIP for all salespersons triggers many API calls in rapid succession (one `crm.deal.list` per salesperson × 2 pipelines × potential multiple pages = many requests). The Bitrix24 free-tier limit is 2 requests/second with a burst threshold of 50. Exceeding this returns a `503` with `QUERY_LIMIT_EXCEEDED`. The current code has no retry logic and crashes.

**Prevention:**
- Fetch all deals for the month in a single bulk query (all salespersons, both pipelines, date-filtered), then group client-side by `ASSIGNED_BY_ID`. This reduces API calls from N×2 to just 2 paginated fetches.
- If individual fetches are unavoidable, add `time.sleep(0.5)` between calls and retry on 503 with exponential backoff (max 3 retries).

**Detection:** Bitrix24 REST API error response body: `{"error": "QUERY_LIMIT_EXCEEDED"}`.

**Phase:** Phase 1 — design the bulk-fetch strategy before individual-report logic; changing the fetch strategy later requires rewriting the data model.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| Bitrix24 data fetch | Pagination truncation (>50 deals) | Paginated loop from day one |
| Bitrix24 data fetch | Wrong date field for "closed in month" | Validate CLOSEDATE vs DATE_MODIFY against real data |
| PDF library choice | WeasyPrint system deps on Cloud | Decide library before first template |
| PDF rendering | Portuguese characters as boxes | Register TTF font in proof-of-concept |
| Commission calculation | Float rounding on R$ values | Use Decimal("string") everywhere |
| Installment logic | Off-by-one in churn month cutoff | Write unit tests for all edge cases first |
| User lookup | N+1 API calls for ASSIGNED_BY_ID | Prefetch full user list once at session start |
| Secrets | Webhook URL in git history | .gitignore before first commit |
| Bulk PDF/ZIP | Memory spike or timeout | BytesIO + progress bar, single bulk API fetch |
| Caching | Stale deal data across sessions | Set TTL on @st.cache_data |

---

## Sources

- [Bitrix24 REST API Rate Limits](https://apidocs.bitrix24.com/limits.html) — HIGH confidence (official docs)
- [crm.deal.list documentation](https://apidocs.bitrix24.com/api-reference/crm/deals/crm-deal-list.html) — HIGH confidence (official docs)
- [Streamlit Secrets Management](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management) — HIGH confidence (official docs)
- [Streamlit App Dependencies / packages.txt](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies) — HIGH confidence (official docs)
- [WeasyPrint installation on Debian](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html) — HIGH confidence (official docs)
- [WeasyPrint on Streamlit Cloud community thread](https://discuss.streamlit.io/t/installing-weasyprint-for-pdf-generation/66837) — MEDIUM confidence (community verification)
- [ReportLab Fonts chapter](https://docs.reportlab.com/reportlab/userguide/ch3_fonts/) — HIGH confidence (official docs)
- [Python Decimal module](https://docs.python.org/3/library/decimal.html) — HIGH confidence (official docs)
- [Bitrix24 Pagination specifics](https://training.bitrix24.com/rest_help/general/lists.php) — HIGH confidence (official training docs)
