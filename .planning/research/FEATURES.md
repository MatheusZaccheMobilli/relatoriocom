# Feature Landscape

**Domain:** Sales Commission Report PDF Generator (HR internal tool, CRM-connected)
**Project:** Mobílli — Relatório de Comissão de Vendedores
**Researched:** 2026-04-09

---

## Table Stakes

Features users expect. Missing = the tool is not usable or RH reverts to manual spreadsheets.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Filter: vendedor, mês/ano, tipo de operação | Without filters the report is meaningless — RH needs to select which vendedor/month to print | Low | Three `st.selectbox` widgets; all three affect the same data fetch |
| Dados do vendedor (nome, CPF) | The report is a formal document the vendedor signs — name and CPF are legally required for identification | Low | CPF field location in Bitrix24 must be confirmed (custom field) |
| Bloco de meta: competência, valor da meta, nível atingido | Core business logic — vendedor and RH both need to see the performance tier that drives percentage | Medium | Three-tier rule (Bronze 75% / Prata 100% / Ouro 125%) is exact; meta value is configurable per run |
| Lista de verificação de pagamento (parcela, cliente, placa, datas) | This is the auditable line-item list the vendedor reviews and signs against — it IS the report body | Medium | Depends on parcela logic (3 months, ceases on churn); placa is a custom field in Bitrix24 |
| Indicadores: negócios fechados, negócios encerrados (devolvidos) | Transparency — vendedor must see what was counted and what was discounted | Medium | "Devolvidos" requires checking M-1/M-2 deals that have a cancellation status in current month |
| Total a receber (R$) | The whole point of the document — must show the final commission figure | Medium | Depends on calculation table TM-018 (B2C rates per tipo/nivel) |
| Cálculo de comissão TM-018 | Engine behind the total — percentage varies by tipo (Locação/Venda 0km/Venda Usado) and nível (Bronze/Prata/Ouro) | Medium | Rates are: Venda 0km 1.00/1.20/1.30%, Venda Usado 3.40/4.00/4.80%, Locação 8/9/10% sobre primeira mensalidade |
| Regra de parcelas (3 meses, cessa no churn) | Locação commission is split over 3 months — without this, totals are wrong | High | Most complex business logic; requires cross-month deal lookups (M-1 and M-2) |
| Geração de PDF individual download | RH prints and collects physical signature — PDF is the delivery artifact | Medium | HTML→PDF via WeasyPrint or Jinja2+WeasyPrint; `st.download_button` delivers the file |
| Termo de ciência + espaço para assinatura | Legal requirement — document is meaningless without the acknowledgment clause and signature line | Low | Static text block in the PDF template |
| Identidade visual Mobílli no PDF | HR will not use a plain PDF; branding signals this is an official document | Low | Logo, colors from mobillirentals.com.br; CSS in HTML template |
| Error message when CRM API fails | Webhook can be unavailable or return errors — user needs feedback, not a blank screen or stack trace | Low | `try/except` with `st.error()` user-friendly message |
| Loading indicator during data fetch | Bitrix24 REST calls can take 2–5 seconds; without feedback users click repeatedly and trigger duplicate calls | Low | `st.spinner()` wrapping API calls |

---

## Differentiators

Features that go beyond the minimum and create real value. Not expected, but significantly improve the tool.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Geração de ZIP com PDFs de todos os vendedores | RH can print the whole team's reports in one action instead of repeating the workflow N times per month | Medium | Loop over vendedores, generate each PDF in-memory, pack with `zipfile` stdlib, `st.download_button(data=zip_bytes, file_name="comissoes_MMYYYY.zip")` — confirmed feasible via Streamlit community |
| Cache de dados do Bitrix24 (st.cache_data com TTL) | Prevents re-fetching the same CRM data on every widget interaction; critical when listing all vendedores or all deals for a month | Low | `@st.cache_data(ttl=300)` on API fetch functions; cache keyed by (pipeline, month, vendedor_id) |
| Preview do relatório na tela antes do download | RH can verify data is correct before printing; catches field mapping errors early without wasting paper | Low | Render the same HTML template into `st.html()` or `st.markdown()` before PDF export |
| Meta mensal configurável na interface | Business changes the meta monthly — embedding it in code causes a new deploy each time | Low | `st.number_input` for "Valor da meta mensal"; stored in session_state, injected into calculation |
| Indicação visual do nível (ícone/cor Bronze/Prata/Ouro) | Makes the screen preview immediately readable; quick visual confirmation for RH | Low | CSS class on the nível badge in both preview and PDF template |
| Mensagem clara quando não há dados no período | Empty state guidance prevents confusion when a vendedor had zero deals in a month | Low | `st.info()` with "Nenhum negócio encontrado para [vendedor] em [mês/ano]" |
| Nome de arquivo do PDF com vendedor + mês | Prevents confusion when RH has multiple PDFs open | Low | `f"{vendedor_nome}_{mes_ref}.pdf"` as `file_name` parameter |

---

## Anti-Features

Features to explicitly NOT build in v1. Including them would delay delivery without proportional value.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Assinatura digital (DocuSign, Clicksign) | Adds external service dependency, OAuth integration, and ongoing cost; physical signature process already exists and works | Print the PDF; collect physical signature as-is |
| App mobile / responsive layout | Streamlit on mobile is poor DX; RH uses desktop; adds CSS complexity with no benefit | Access via desktop browser only |
| Edição manual de valores no relatório | Undermines trust in the CRM data and creates audit risk; RH should not override calculated figures | If data is wrong, fix it in Bitrix24; re-generate |
| Histórico de relatórios gerados / audit log | Adds database, storage, and authentication complexity; no stated requirement | RH saves the PDF file; that IS the audit trail |
| Autenticação / login de usuário | Streamlit Cloud on a private-share link is sufficient access control for an internal HR tool | Use Streamlit Cloud's built-in link sharing or secrets-based password if needed later |
| Cálculo de comissões B2B (>=5 motos) | Explicitly out of scope for v1; different rate structure, different pipeline logic | Stated in PROJECT.md as "after v1" |
| Consórcio | Not in current Bitrix24 pipelines; no data source exists | Add when pipeline is created |
| Notificações por e-mail / WhatsApp | No stated requirement; adds integration surface area | Out of scope |
| Dashboard / gráficos de performance | This is a print-ready document tool, not a BI dashboard; charts add complexity without serving the signing workflow | Power BI already covers analytics |
| Exportação para Excel / CSV | The deliverable is a printable PDF for signature; tabular export is a different use case | Out of scope |
| Cálculo de passivos de regras anteriores (item 3.4 TM-018) | Explicitly excluded from v1 in PROJECT.md; requires historical rule versioning | Stated out of scope |

---

## Feature Dependencies

```
Filtros (vendedor, mês, tipo)
  → Conexão Bitrix24 API (pipeline 48 / 40)
    → Dados do vendedor (nome, CPF)
    → Lista de deals do mês (fechamento, status, valor)
      → Regra de parcelas (M-1, M-2, churn check)
        → Lista de verificação de pagamento
        → Indicadores (fechados, devolvidos)
        → Cálculo TM-018 (tipo + nível → percentual)
          → Bloco de meta (meta configurável → % atingido → nível)
            → Total a receber (R$)
              → Template HTML/CSS (identidade visual Mobílli)
                → Geração de PDF individual (st.download_button)
                  → Geração de ZIP todos vendedores (batch loop)

Cache (st.cache_data) wraps: Conexão Bitrix24 API
Preview na tela wraps: Template HTML/CSS (same template, no PDF conversion)
```

---

## MVP Recommendation

Prioritize (ship in this order — each builds on the previous):

1. **Conexão Bitrix24 + filtros** — Without CRM data, nothing works. Validate that the webhook returns the fields needed (placa, CPF) before building logic on top.
2. **Regra de parcelas + cálculo TM-018** — Core business logic. Implement with hardcoded test data first (decoupled from API), then wire up.
3. **Template PDF + identidade visual** — Once logic is correct, wrap in HTML/CSS template. `st.download_button` delivers the file.
4. **Batch ZIP** — Low effort after single-PDF works; high value for RH monthly workflow.
5. **Cache + error handling** — Polish; prevents bad UX on slow/failed API calls.

Defer to post-v1:
- Meta configurável via UI (hardcode a reasonable default first, make it an input once base works)
- Preview on-screen (add after PDF template is stable; same template, just rendered inline)

---

## Open Questions (Must Resolve Before Coding Logic)

| Question | Impact | How to Resolve |
|----------|--------|----------------|
| Campo de CPF do vendedor no Bitrix24 | Cannot populate dados do vendedor without it | Query `crm.contact.fields` or `crm.deal.fields` via webhook; inspect custom field IDs |
| Campo de placa do veículo no Bitrix24 | Cannot populate lista de verificação | Same: inspect custom fields on deal or associated entity |
| Como identificar "devolução/churn" no pipeline | Determines which deals are "negócios encerrados" | Identify stage ID that represents cancellation in pipeline 48; confirm with RH |
| Valor base da meta mensal — fixo ou por vendedor? | Affects whether meta input is a single field or per-vendedor config | Confirm with RH/gestão |
| Venda 0km vs Venda Usado — como distinguir no Bitrix24? | Two different commission rates in the same pipeline 40 | Identify if there is a deal field, category, or stage that marks 0km vs usado |

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Table stakes features | HIGH | Directly specified in PROJECT.md + CLAUDE.md; no ambiguity |
| Differentiators | HIGH | Batch ZIP and caching are confirmed feasible in Streamlit (official docs + community examples) |
| Anti-features | HIGH | Explicitly out-of-scope items from PROJECT.md; general HR tool over-engineering patterns |
| Feature dependencies | MEDIUM | Dependency chain is logical but custom Bitrix24 field mapping is unverified until API is queried |
| Complexity estimates | MEDIUM | Based on Streamlit patterns research; actual complexity depends on Bitrix24 data shape |

---

## Sources

- Streamlit official docs — caching: https://docs.streamlit.io/develop/concepts/architecture/caching
- Streamlit official docs — download button: https://docs.streamlit.io/knowledge-base/using-streamlit/how-download-file-streamlit
- Streamlit community — batch ZIP download: https://discuss.streamlit.io/t/using-streamlit-how-to-fetch-several-data-files-and-zip-them-so-the-user-can-download-multiple-files-at-once/79159
- Streamlit example app — PDF report: https://github.com/streamlit/example-app-pdf-report
- Bitrix24 REST API — error codes: https://apidocs.bitrix24.com/error-codes.html
- Qobra — commission statement template required fields: https://www.qobra.co/blog/commission-statement-template
- Python PDF libraries comparison 2025: https://www.nutrient.io/blog/top-10-ways-to-generate-pdfs-in-python/
- PROJECT.md (authoritative source of record for this project)
