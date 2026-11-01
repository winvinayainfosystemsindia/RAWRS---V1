# Automation rate: method and first corpus run (2026-11-01)

Code: `src/metrics/automation.py`. CLI: `python -m src.metrics [outputs_dir] [--json]`. Corpus runner: `scripts/run_corpus_metrics.py`.

## Read this first

| Number | What it is | Quotable now? |
|---|---|---|
| (a) Decided without asking a human | Share of reviewable items RAWRS settled itself at pipeline end | **No, not alone.** It measures how often RAWRS asks, not whether it was right (see the per-document table) |
| (b) Reviewer kept unchanged | accepted_unchanged ÷ (accepted_unchanged + edited + rejected) | **Not measured yet**: 0 human-reviewed documents; it needs at least 5 |
| Checklist pass rate | RAWRS's own 40-item audit of its own DOCX | Only as "self-graded"; veraPDF in Task 3 is the independent check |
| Similarity to human remediation | `src/benchmark` differ, RAWRS DOCX against the 10 human DOCX files | Only labelled as an **estimate**; it is not reviewer behaviour |

## Method

| Item | Rule |
|---|---|
| Corpus | 10 PDFs in `samples/benchmark/pdfs/` (2 fully scanned, 1 partly scanned), 161 pages |
| Run | `python scripts/run_corpus_metrics.py`, Codespace with 4 vCPU (AMD EPYC 7763) and 16 GB, OCR on, OCR cache off (cold), Ollama `qwen2.5vl:3b` and `glm-ocr:q8_0`, branch `origin/main` `46510a6` plus this change |
| Items | headings (excluding page markers), images, tables, reading order (one per page), footnotes, pipeline corrections, equations; each item in exactly one bucket |
| "Asked a human" | image with no alt text or skipped; equation `flagged`; page with an open `PAGE_003`; correction still proposed or pending |
| Rounding | rates floored and durations ceiled, to one decimal place |
| Statistics | median across documents is the headline; the pooled figure and an item-level Wilson 95% lower bound are also given; that bound is overconfident because items within one document are correlated |
| Checks | `warn` and `manual` count as needs-human; `not_applicable` is left out |

## Measured (n = 10 documents, 546 items, 329 applicable checks)

| Metric | Median per document | Pooled | Item-level Wilson low |
|---|---|---|---|
| (a) Decided without asking a human | 84.6% | 81.5% (445/546) | 78.0% |
| (b) Reviewer kept unchanged | not measured yet | — | — |
| Checklist pass (self-graded) | 79.1% | 78.7% (259/329) | 73.9% |

Checks: 259 pass, 14 fail, 56 need a human (`warn` + `manual`; at least 4 per document), 71 not applicable.

| Category | Decided by RAWRS | Asked a human |
|---|---|---|
| headings | 143 | 0 |
| images | 12 | 0 |
| tables | 3 | 0 |
| reading order (pages) | 102 | 59 |
| footnotes | 7 | 0 |
| corrections | 178 | 42 |
| equations | 0 | 0 |

**Timing:** median 17.2 s per document; maximum 722.0 s (Bryman, 26 scanned pages). The scanned documents took 722.0 s and 700.9 s. The median per stage is under 6 s for every stage. Review time is not measured yet.

## Per document

| Document | Pages (OCR) | Items | (a) | Checks pass | Seconds | Estimate: heading F1 |
|---|---|---|---|---|---|---|
| 1. Nature of Enquiry | 28 (0) | 122 | 77.0% | 77.7% | 17.9 | 0.55 |
| 1. Aims of Education | 4 (0) | 8 | 50.0% | 86.6% | 1.0 | 0.80 |
| 2. Bryman (scanned) | 26 (26) | 74 | 100.0% | 73.6% | 722.0 | 0.93 |
| 2. Bruner | 26 (0) | 109 | 65.1% | 66.6% | 16.6 | 0.76 |
| 3. Sockett | 9 (0) | 23 | 60.8% | 66.6% | 9.4 | 0.43 |
| 4. O'Leary (scanned) | 13 (13) | 58 | 100.0% | 84.8% | 700.9 | 0.67 |
| 4. Teaching, Ch. 1 | 27 (2) | 37 | 100.0% | 78.7% | 127.0 | 0.35 |
| 5. Calderhead | 4 (0) | 13 | 92.3% | 86.6% | 1.3 | 0.67 |
| 6. Fullan & Hargreaves | 6 (0) | 20 | 95.0% | 86.6% | 2.1 | 0.82 |
| 7. Brinkman | 18 (0) | 82 | 75.6% | 79.4% | 246.3 | 0.83 |

**Why (a) cannot be quoted alone:** three documents score 100% because the scan path and `4.Teaching` raise no review flags, not because they are right. `4.Teaching` matches only 35% of the human headings (F1). A high (a) shows that RAWRS asked no one, not that the output is right.

## Sensitivity (hand calculation, not in the CLI)

If AI alt text is counted as needing review (12 items), and each of the other 33 open warnings (TABLE, HEADING, PAGE_007/008, DOC_004) turns one decided item into an asked one, then (a) = (445 − 12 − 33) / 546 = **73.2%** pooled.

## Estimate: similarity to a human-remediated version (n = 10)

Heading precision 0.648, recall 0.770, F1 0.682; footnote placement 0.60; figure count fidelity 0.85; table count fidelity 0.785; front-page similarity 0.575. These figures measure how close RAWRS's output is to an independent human remediation. They do not show what a reviewer would keep.

## Not measured, or not tested

| Gap | Effect |
|---|---|
| No human reviews | (b) and review time are empty. WinVinaya's daily use fills them; both switch to measured on their own once 5 documents are reviewed |
| Surya fallback failed on 1 page (`4.Teaching` p27): `llama-server binary not found` in the Codespace | That page has Docling-only text; production may differ |
| Ollama cold start falls inside the first document that uses it | Its timing is inflated |
| The review timer was tested only with Jest fake timers | No live browser session was measured |
| The panel was not checked in a running app | Covered only by Jest and axe |
