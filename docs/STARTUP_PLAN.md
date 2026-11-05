# RAWRS startup plan (2026-11-06)

Not legal or financial advice. "Measured" means a run in the Codespace that anyone can reproduce. Everything else is sourced or labelled a hypothesis. Vendor figures come from vendors' own marketing.

## 1. The one-line bet

Governments are about to pay to make their documents accessible. Cheap automation passes the machine checks without making documents readable. RAWRS sells **readable, verified** documents, with the automation rate measured and stated openly, for less than people doing it by hand.

## 2. Market facts

| Fact | Value | Source |
|---|---|---|
| ADA Title II deadline, entities serving 50,000+ people | **26 Apr 2027** (moved from 24 Apr 2026 by the DOJ interim final rule of 20 Apr 2026) | [ADA.gov](https://www.ada.gov/resources/2024-03-08-web-rule/), [Federal Register](https://www.federalregister.gov/documents/2026/04/20/2026-07663/extension-of-compliance-dates-for-nondiscrimination-on-the-basis-of-disability-accessibility-of-web) |
| Smaller entities and special districts | **26 Apr 2028** | same |
| Standard | WCAG 2.1 AA; PDFs are explicitly covered | same |
| Biggest exceptions | PDFs posted **before** the deadline, unless they are "currently being used to apply for, access, or participate in" a service; properly archived content | ADA.gov |
| What that means | The backlog shrinks. The **recurring flow** of new documents (agendas, minutes, budgets, notices, forms) plus service forms is the durable market, which suits subscriptions | inference |
| Rule risk | DOJ plans more rulemaking on the substance, and the NFB sued in May 2026 to restore the original dates | [Duane Morris](https://www.duanemorris.com/alerts/doj_extends_ada_title_ii_digital_accessibility_deadlines_one_year_0426.html), [adatitleiii.com](https://www.adatitleiii.com/2026/04/doj-extends-ada-title-ii-website-accessibility-deadlines-for-governmental-entities-but-litigation-and-compliance-risks-remain/) |
| DOJ's own reason for the delay | It "overestimated" entities' capacity; it cited the limits of generative AI for remediation | [Federal Register](https://www.federalregister.gov/documents/2026/04/20/2026-07663/extension-of-compliance-dates-for-nondiscrimination-on-the-basis-of-disability-accessibility-of-web) |
| Number of US local governments | 90,837 (2022 Census of Governments) | [Census](https://census.gov/newsroom/press-releases/2023/census-of-governments.html) |
| PDFs per county | 10,000–50,000 (**vendor estimate**, no survey exists) | [bmiimaging](https://bmiimaging.com/blog/document-management/ada-title-ii-deadline-pdf-accessibility/) |
| HHS Section 504 rule (health and human services grantees) | First deadline **11 May 2026**, not extended | [Jackson Lewis](https://www.jacksonlewis.com/insights/doj-extends-public-entities-compliance-deadline-ada-related-website-accessibility-hhss-may-2026-deadline-still-looms) |
| EU European Accessibility Act | Enforceable since 28 Jun 2025; fines set nationally and figures vary by source | [Clym](https://www.clym.io/blog/european-accessibility-act-fines-by-country) |

## 3. Competitors and prices (per page)

| Who | Model | Price | Note |
|---|---|---|---|
| CASO Comply, Accessibility On Demand | Automated / automated plus AI checks / plus human review | **$0.30 / $1.80 / from $12** | Guarantee "≥95% compliance score" at $1.80 ([CASO](https://casocomply.com/pricing)) |
| Allyant, Accessible.org | Human services | $5–8; $4–11.50 | vendor comparison and own pages |
| Manual remediation in general | Human | $3–25 | AWS/ASU and Venngage; wide spread |
| ASU + AWS tool | Open source (MIT), Adobe Auto-Tag API + Bedrock | "cents per page" plus Adobe and AWS fees | Free for anyone with AWS and Adobe accounts ([AWS blog](https://aws.amazon.com/blogs/publicsector/from-inaccessible-to-inclusive-how-the-new-pdf-accessibility-remediation-solution-helps-institutions-compliantly-address-accessibility-requirements/)) |
| Adobe Auto-Tag API | API | 500 free transactions a month, then a sales quote | [Adobe](https://developer.adobe.com/document-services/pricing/) |
| OpenDataLoader PDF (Hancom) | Open source (Apache-2.0) auto-tagging; PDF/UA export is paid | free | measured below |
| doclarity (Vienna), Normfluss, PDFix, Equidox, CommonLook, AbleDocs | AI/desktop/EU-hosted | mostly quote-based | EU side is crowded too |

**Read:** fully automated remediation is already a **$0.30/page commodity**. Competing on price there means losing. The opening is the part automation fakes: scans, real alt text, reading order and tables, verified by people.

## 4. Measured evidence (this repo, Codespace, CPU)

| Measurement | Result | Where |
|---|---|---|
| Free stack: OpenDataLoader auto-tag + ~20 lines of `pikepdf` metadata fixes → veraPDF 1.30.3, PDF/UA-1 | **7/10** corpus PDFs pass, 1–37 s each, $0. Before: 0/10 | `scripts/pdfua_baseline.py` |
| …of which scanned books (Bryman, O'Leary) | **pass with 0 characters of text**: a screen reader reads nothing | same |
| Remaining failures | Fonts without Unicode maps or not embedded (2 files); one annotation not tagged | same |
| RAWRS: share of items decided without a human (a) | median 84.6%, pooled 81.5% (10 documents, 546 items) | `docs/AUTOMATION_RATE_2026-11-01.md` |
| RAWRS: OCR on scans (Docling) | 95.4–96.1% word 4-gram recall against human-remediated text | `docs/LICENSING_AUDIT.md` |
| RAWRS: reviewer keeps unchanged (b) | **not measured** (0 reviewed documents) | Task 1 |
| Alt text, best licence-clean model | `qwen2.5vl:7b`: 209 s per figure on CPU, too slow for volume without a GPU or API | `docs/LICENSING_AUDIT.md` |

**What it means:**
1. veraPDF passing is not a moat; anyone gets it free.
2. The moat is **text and structure that are actually right** (OCR, headings, reading order, tables, alt text), checked by people, with the evidence shown.
3. Sell "readable and verified", and show buyers the 0-character "compliant" scan as proof of why.

## 5. Positioning and offer (hypotheses to test with pilots)

| Element | Proposal | Why |
|---|---|---|
| Buyer | ADA coordinator or clerk at cities and counties of 50k+ (deadline 26 Apr 2027); then remediation agencies (white-label) | Closest deadline; agencies already have the customers |
| Wedge | **Free audit report** (Task 4): crawl the site, show the share failing, and the "passes but unreadable" scans | Free, concrete, shows the commodity tools' blind spot |
| Product | Upload or crawl → RAWRS fixes → human review queue → accessible PDF (Task 3) plus HTML/DOCX | Matches what governments must post |
| Price | **$1.50/page** verified-automated (readability guaranteed, scans OCR'd, low-confidence items flagged); **$6/page** human-reviewed; subscription for the recurring flow (e.g. 2,000 pages/month) | Between the $0.30 commodity and $12+ manual tiers; to be validated, not yet costed |
| Proof | Publish measured (a) and, once 5+ documents are reviewed, (b), with n | Honesty differentiates in a market of "100% compliant" claims |
| Workforce | WinVinaya's network of trained persons with disabilities, including screen-reader users, as reviewers | Authentic, and checks what machines can't; the Foundation reports 560–700+ placements (self-reported) |
| Data | Public PDFs only, at first: no PII, which eases procurement | Most backlog documents are already public |

**Can't price yet:** gross margin. That needs review minutes per page from real reviews (Task 1 (b) and review time) and GPU or API cost per figure.

## 6. Go-to-market, first 90 days

| Weeks | Do | Done when |
|---|---|---|
| 1–3 | Task 3: tagged PDF from RAWRS's verified structure; validate with veraPDF plus a text-presence check | Corpus exports pass PDF/UA-1 **and** have real text |
| 2–5 | Task 4: crawler + free audit report; run it on 20 cities of 50k+ | 20 reports ready to send |
| 3–8 | 15–20 conversations with ADA coordinators and clerks (ICMA, NACo, state municipal leagues, LinkedIn); show the report and ask about budget, purchase path, volume | Written notes; price and volume validated or rejected |
| 6–12 | 2–3 paid pilots under each city's small-purchase threshold (varies by state, so check each one) | Signed pilot; (b) and review minutes measured on real documents |
| Parallel | Settle the licences: `qwen2.5vl:3b` → 7b; PyMuPDF decision; LICENSE file | No non-commercial component in the paid path |
| Parallel | Paperwork US buyers ask for: VPAT for RAWRS's own UI, W-9 (a US entity helps), insurance | Ready before the first purchase order |

## 7. Open-source to adopt

| Tool (licence) | Use in RAWRS | Status |
|---|---|---|
| veraPDF (GPL-3+/MPL-2 dual) | Independent PDF/UA-1 check (Task 3) | measured here, 1.30.3 |
| `pikepdf` (MPL-2.0) | Language, title, XMP and PDF/UA identifier fixes | measured here |
| Typst 0.14 (Apache-2.0) | Render a PDF/UA-1 file from RAWRS's verified structure, with real tags and embedded fonts; no hand-written tags | **to test** in Task 3 against LibreOffice |
| OpenDataLoader PDF (Apache-2.0) | Baseline and fallback auto-tagger; also the competitor's free floor | measured here |
| OCRmyPDF (MPL-2.0) + Tesseract (Apache-2.0) | Text layer for scans when only a PDF fix is needed | to test |
| ASU/AWS remediation tool (MIT) | Reference architecture; shows what free looks like | read only |
| MiroFish/MiroShark (AGPL-3.0) | Internal use only: simulate buyer reactions to rehearse objections | **not run**, see §9 |

## 8. Risks

| Risk | Mitigation |
|---|---|
| DOJ weakens or delays the rule again | EU EAA, HHS 504 and higher-ed (Title II also covers public universities); recurring flow, not just backlog |
| Price war at $0.30 | Don't play; sell readability plus review, and show the unreadable "compliant" scans |
| Big players (Adobe, Hancom) improve | Stay the verified-quality layer; can sit on top of their taggers |
| Licences (PyMuPDF AGPL, qwen 3b) | `docs/LICENSING_AUDIT.md` swap order |
| Compute: CPU alt text at 209 s per figure | GPU host or a paid vision API for production; cost it during pilots |
| Overclaiming | Never say "compliant" or "certified"; show the measured numbers with n |

## 9. Not done, and why

- **MiroFish/MiroShark buyer simulation: not run.**
  - It needs an LLM API key. Creating one in your Google AI Studio account was blocked by Claude Code's safety check, and I didn't work around it.
  - To run it: create a key at aistudio.google.com/apikey and write it straight into `/workspaces/miroshark/.env` in the Codespace (not into chat), then tell me.
  - Caution: it is LLM role-play. It can surface objections to rehearse, but it is **not** evidence of demand; the 15–20 real conversations in §6 are.
- No market-size dollar figure: there's no neutral count of documents. The 10k–50k per county figure is a vendor estimate.
- Gross margin: unknown until review minutes are measured.
