# RAWRS product track: progress

Read this file and `git log` first after any context reset, then carry on from **Next**.

**Product:** crawl an organisation's public documents, score each one, fix the easy majority automatically, queue the rest for a human, and output accessible files, priced per document. The buyers are US state and local governments (ADA Title II, 2027-04-26, WCAG 2.1 AA), remediation agencies, and EU organisations (EAA). Billing, accounts and multi-organisation support wait until after the first pilot.

## Status

| Task | State | Commit |
|---|---|---|
| 1 Automation rate | done | `e525188` |
| 2 Licence audit | done | see `git log` (docs: licence audit) |
| 3 Accessible PDF export | not started | — |
| 4 Crawler + free audit report | not started | — |

**Startup plan (2026-11-06):** `docs/STARTUP_PLAN.md` covers the market, competitors, measured free-stack baseline, offer, 90-day go-to-market and risks. Key measurement: OpenDataLoader + pikepdf passes veraPDF PDF/UA-1 on 7/10 corpus PDFs for free, but the 2 scanned books pass with 0 characters of text. Task 3 should test Typst PDF/UA-1 against LibreOffice, and add a text-presence check next to veraPDF. MiroShark ran 2026-11-06 (§9): weak, with role swaps in ≥5/19 agents and no price signal. It is a list of objections to rehearse, not demand evidence.

**Next:** wait for the user's go on Task 3. Task 2's results are in `docs/LICENSING_AUDIT.md`.
- Recommended first swap: `qwen2.5vl:7b`. Then Surya → Docling/Tesseract + GLM-OCR regions. PyMuPDF needs a business decision.
- Open: `qwen3-vl:4b` with `think: false` is not tested; `qwen2.5vl:7b` (5.7 GB loaded) is not tried on the 8 GB reference machine.
- Codespace: the gold DOCX copies and every bench JSON were deleted on 2026-11-05 (`CLEANED`), and the Codespace was stopped.
- **Keeping the Codespace awake:** it has a 30 min idle timeout, and the 240 min default only applies to new Codespaces. Background polls from the laptop get stopped for low memory. Foreground `gh codespace ssh -- 'sleep 480; tail …'` calls worked. Make long runs resumable: `licence_bench.py alt` saves after every figure and skips figures already done.

## Task 1: automation rate (agreed changes, 2026-11-01)

1. **Two numbers, never combined:**
   - **(a) "Decided without asking a human"** = auto_decided ÷ all items. Measured on the corpus now.
   - **(b) "Reviewer kept unchanged"** = accepted_unchanged ÷ (accepted_unchanged + edited + rejected). Needs real reviews.
   - Both definitions go in the report, the docstrings and the panel.
2. **Statistics:**
   - Items within a document are not independent. Report the median across documents, and state n as both documents and items.
   - The Wilson bound is labelled "item-level; overconfident".
   - Floor rounding, never up.
3. **Review timer:**
   - `active_strict` uses a 60 s idle window; `active_loose` uses a 300 s idle window. Quote loose, with strict beside it.
   - Each delta is capped at 300 s.
   - The endpoint takes `{strict_seconds, loose_seconds}`; the sidecar stores `review_seconds_strict` and `review_seconds_loose`.
4. **Self-grading:** the 40 checks are RAWRS's own audit of its own output. Say so in the report and in KNOWN_LIMITATIONS. Task 3's veraPDF results are the independent check.
5. **Proxy:** similarity of RAWRS's DOCX to the 10 human-remediated DOCX files, from the existing benchmark differ.
   - Labelled "estimate: similarity to a human-remediated version". Never "what a reviewer would keep", and never (a) or (b).
   - Kept separate in the CLI, the API and the panel.
   - Every reviewer metric is shown next to its count of human-reviewed documents.
   - Reviewer metrics read "not measured yet" until `MIN_REVIEWED_DOCS = 5` reviewed documents exist; this is tested at 4 and at 5.
   - WinVinaya's daily use fills these in; no special review session is needed.
6. **Corpus files are gitignored** (`samples/benchmark/pdfs/`, `remediated_docx/`).
   - Copy them to the Codespace with `gh codespace cp -r -e`.
   - Fail clearly unless 10 PDFs and 10 DOCX files are present.
   - They are copyrighted: delete them from the Codespace after the run and never commit them.

## Roadmap (stop and report after each task; wait for the go-ahead)

Each report covers what changed, real numbers, what wasn't tested, open questions, and the recommended next step.

- **Task 2: licence audit (report only).**
  - For every restrictive dependency or model weight (known: PyMuPDF AGPL, the Surya weights, `qwen2.5vl:3b`; check transitive dependencies too), give: the exact licence with a source link; what it blocks for commercial or networked use; 1–2 permissive replacements or the cost of a paid licence; the effort to swap it.
  - Run the top OCR and alt-text replacements on a benchmark subset in the Codespace and compare quality, using Task 1 metrics where they apply.
  - Done when `docs/LICENSING_AUDIT.md` has the comparison numbers and a recommended swap order.
- **Task 3: accessible PDF export.**
  - DOCX → tagged PDF, preferably with LibreOffice's tagged-PDF export. No hand-written PDF tags.
  - Validate with veraPDF against PDF/UA-1.
  - Add the results to the checklist audit and to the Task 1 metrics, labelled as independent validation.
  - Done when the benchmark documents export, and the report gives pass/fail by check (table headers, alt text, reading order, language, title, equations) with the reason for each failure. If LibreOffice can't get close, recommend the next option with evidence.
- **Task 4: crawler + free audit report (the sales tool).**
  - `python -m src.audit <url>`: sitemap.xml, falling back to a shallow same-domain crawl. Respect robots.txt, rate-limit requests, cap counts, and use an honest User-Agent. Download into an isolated folder.
  - Score each PDF with veraPDF plus RAWRS's input checks: tagged or not, title, language, text layer or scanned, images without alt text, table structure.
  - One HTML and PDF report with:
    - totals and the share failing, broken down by issue type;
    - the 20 worst documents, each with its URL and plain-English problems;
    - hours by hand vs with RAWRS, based only on measured Task 1 figures, with n shown, labelled an estimate;
    - a note that this is an automated check, not a certification.
  - It must read clearly for a non-technical official.
  - Done when it has run end to end on one real city or county site and the report has been shown to the user.

## Working rules

- Every new dependency gets a one-line justification in DECISIONS_LOG, saying why the installed tools aren't enough.
- Heavy runs (corpus, OCR, model comparisons) go in the Codespace, one process at a time.
- The backend suite stays green against the known baseline. New logic gets tests that would fail if it broke. Write general solutions, not code shaped to pass specific tests.
- Commit after each task with a clear message. **Do not push**, and do not open PRs.
- If a request is a bad idea or impossible, say so and propose the better path.
- Work through each task fully up to its checkpoint. This file preserves the state, so context length is not a reason to stop early.

## Log

| Date | Step | Result |
|---|---|---|
| 2026-11-01 | Task 1 plan approved | this file created |
| 2026-11-01 | `src/metrics/automation.py` written (uncommitted) | buckets, rates, sidecar, aggregate |
| 2026-11-01 | Codespace worktree `/tmp/rm` = origin/main + copied changes | new tests 14/14 pass; full fast suite started, log in `/tmp/suite.log` |

### Task 1 resume checklist (plan: `~/.claude/plans/pasted-content-id-e404-before-you-start-tranquil-newt.md`)
- [x] `src/metrics/automation.py`: `item_buckets`, `document_rates`, `write_pipeline_metrics`, `add_review_time`, `set_estimate`, `job_metrics`, `aggregate`
- [x] `src/metrics/__init__.py` + `__main__.py` CLI (`python -m src.metrics [outputs] [--json]`)
- [x] `phase1_pipeline.py`: `_stage_done(name)` replacing the 8 `if on_stage_complete:` lines; `PipelineResult.stage_seconds`; `_write_checklist_report` returns `report.summary`; call `write_pipeline_metrics` after stage 8, before the final return
- [x] `learning_routes.py`: `GET /api/documents/{id}/metrics`, `POST /api/documents/{id}/review-time {strict_seconds, loose_seconds}` (404 with no sidecar)
- [x] `tests/test_automation_metrics.py` 14/14
- [x] frontend (tsc clean; jest 64/64 in Codespace): `useReviewTimer.ts`, `AutomationPanel.tsx`, `api.getDocumentMetrics`/`postReviewTime`, tests
- [x] `scripts/run_corpus_metrics.py` (10 PDF / 10 DOCX guard, `RAWRS_OCR_CACHE=off`, `run_corpus` → `set_estimate`)
- [x] Codespace: copied the corpus, ran the suite and the corpus, deleted the copies
- [x] DECISIONS_LOG Part 27, KNOWN_LIMITATIONS, LEARNING_LOOP cross-reference
- [x] report `docs/AUTOMATION_RATE_2026-11-01.md`; committed (no push)
| 2026-11-01 | Backend fast suite (Codespace) | 2907 passed / 2 failed / 19 skipped; the 2 (`TestStructureDetectionDoesNotChangeExistingOutputs`) were caused by Ollama being started mid-run, and pass 10/10 when re-run with it off |
| 2026-11-01 | Corpus note | `samples/benchmark/pdfs/` is TRACKED (for CI); only `remediated_docx/` is gitignored. Copied to the Codespace at `/tmp/rm/samples/benchmark/remediated_docx` (delete after the run) |
| 2026-11-01 | Corpus run (10 docs, 546 items) | (a) median 84.6% / pooled 81.5% (Wilson low 78.0%); sensitivity 73.2%; (b) not measured yet (0 reviewed); checks pass median 79.1% / pooled 78.7% (self-graded); median 17.2 s, max 722.0 s; estimate heading F1 0.682 |
| 2026-11-01 | Open questions | (1) Should (a) be published at all? 3 documents score 100% while one has heading F1 0.35. (2) Surya needs `llama-server` in the Codespace. (3) The panel has not been checked in a live app |
| 2026-11-03 | `bench4.sh` | Codespace idled out after `qwen2.5vl:3b` (10/10) |
| 2026-11-05 | `bench5.sh` OCR + `bench6.sh` alt text (resumable, 900 s production limit) | OCR: Docling 95.4/96.4% and 96.1/97.5%, Tesseract 92.5/89.2% and 91.6/90.9%. Alt overlap recall/precision: 3b 37.6/48.6, 7b 48.1/55.3, qwen3-vl:4b 47.6/44.3 (9/10), granite 33.1/24.7 (8/10). `CLEANED`, JSON deleted, Codespace stopped |
| 2026-11-05 | Task 2 done | `docs/LICENSING_AUDIT.md` measured comparison + swap order; no new RAWRS dependency, so no DECISIONS_LOG entry (Tesseract was benchmark-only, installed in the Codespace) |
| 2026-11-06 | MiroShark run (`scripts/miroshark_run.py`, Gemini free tier, Ollama `nomic-embed-text` embeddings) | Run 1: 4 agents, no buyers. Run 2 (fictional cast seed): 19 agents, 10 rounds, 39 posts; reports failed on HTTP 429. Codespace disk was 100%: HF cache + `.ollama` moved to `/tmp` (separate 118 GB disk, may be wiped on restart) and symlinked back; pip cache deleted. Gemini key `rawrs-miroshark` is still active (revoke in AI Studio if not needed) |
| 2026-11-06 | Startup research + `scripts/pdfua_baseline.py` (Codespace: Java 17, veraPDF 1.30.3, opendataloader-pdf 2.5.19, pikepdf 10.17) | 0/10 → 7/10 pass PDF/UA-1; scans pass with 0 text chars; Granite model removed from the Codespace (disk 90%→84%) |
| 2026-11-06 | Task 3 code (uncommitted) | `src/docx/pdf_export.py` (LibreOffice 25.2 tagged PDF/UA-1 export, veraPDF, pypdfium2 text count, `MIN_PAGE_CHARACTERS=20`, `report_path`, `stored_verdict`), pipeline step after metrics, `GET /download/pdf`, `pdf_available`, `/checklist` gains `independent`, sidecar `independent` + aggregate view, frontend download links, `tests/test_pdf_export.py` (7), `scripts/pdfua_report.py` (veraPDF rule → checklist check table) |
| 2026-11-06 | Task 3 Codespace run 1 (invalid) | `/tmp/hf` (HF cache symlink) wiped on restart → Docling OCR failed on every O'Leary page; pipeline still "succeeded" with 17 characters, PDF/UA-1 PASS, checklist 24 pass. 9/9 PASS otherwise. Bryman was a 133-byte LFS pointer (no git-lfs in Codespace; copied real file, sha 6d192939…) |
| 2026-11-06 | Task 3 Codespace run 2 | started in `/workspaces/rw` (= HEAD `ad147b4` + Task 3 files), `RAWRS_PDF_EXPORT=on RAWRS_VERAPDF=/workspaces/verapdf/verapdf python scripts/run_corpus_metrics.py --out outputs/corpus_pdfua`, log `/workspaces/t3.log`; Ollama qwen2.5vl:3b + glm-ocr:q8_0 up |

| 2026-11-06 | Task 3 run 2 + report | 10/10 PASS veraPDF PDF/UA-1, all with text (O'Leary 30777 chars); Task 1 numbers unchanged ((a) median 84.6%); demo PDF PASS after the ScreenTip fill-in; `docs/PDF_EXPORT_2026-11-06.md`, DECISIONS_LOG Part 28, KNOWN_LIMITATIONS |

### Task 3 resume checklist
- [x] tests 21/21 in Codespace (incl. end-to-end LibreOffice → veraPDF) — before the threshold/stored_verdict edits
- [x] edits written locally: threshold, `stored_verdict` + test, `ChecklistReport.independent`, `IndependentLine` in `ChecklistAuditPanel.tsx`
- [x] copy them to `/workspaces/rw`; pytest test_pdf_export; tsc + jest in Codespace
- [x] when run 2 ends: `python scripts/pdfua_report.py outputs/corpus_pdfua` (re-run text check with new threshold if needed) + `python -m src.metrics outputs/corpus_pdfua`
- [x] demo `frontend/public/demo/download/document.pdf` (convert demo DOCX in the Codespace) — index.json already says `pdf_available: true`
- [x] report `docs/PDF_EXPORT_2026-11-06.md`; DECISIONS_LOG (LibreOffice + veraPDF are external binaries, no pip dependency; pypdfium2 comes with docling); KNOWN_LIMITATIONS line "Checks are self-graded" → now independent; findings: OCR total failure is a silent success (checklist + veraPDF both pass)
- [x] backend fast suite in Codespace, Ollama OFF: 2916 passed / 2 failed / 19 skipped. The 2 are `TestStructureDetectionDoesNotChangeExistingOutputs` (an extra FRONT_MATTER_001 in one run), the same 2 as the Task 1 baseline; they pass 10/10 in isolation, so it is order-dependent pollution, not Ollama (the Task 1 explanation looks wrong; not investigated). Committed (no push); Codespace copies deleted, Codespace stopped
- Note: `docs/CURRENT_STATE.md` shows as deleted in the working tree — not by Task 3; leave it out of the commit and ask the user
