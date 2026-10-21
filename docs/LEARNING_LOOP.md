# Learning loop and OCR cache

Added 2026-10-21. **Neither changes RAWRS output.** The learning loop is read-only and gives advice to a person. The OCR cache returns byte-identical engine results.

## 1. OCR result cache (`src/ocr/cache.py`)

| What | Detail |
|---|---|
| Stores | Raw engine output per page: Docling `text` + `header_items`; Surya `text`. All post-processing (sanitising, heading levels, confidence) still runs on every call |
| Key | PDF sha256 + page + engine package versions + **source bytes of the engine/config modules**. Any change to an engine, its config or its version misses |
| Location | `outputs/cache/ocr/<engine>/<sha[:2]>/<sha>-<fp>-p<N>.json` (atomic write; a corrupt entry is treated as a miss) |
| Off switch | `RAWRS_OCR_CACHE=off`; directory `RAWRS_OCR_CACHE_DIR`. The test suite runs uncached (`tests/conftest.py`) |
| Not cached | Failed pages, so they retry next time |

**Evidence:** a real Docling run on a scanned benchmark page took **98.1 s cold and 0.26 s cached (384×)**, and **0 of 17** page fields differed. 8 tests are in `tests/test_ocr_cache.py`, and the mocked engine suites still pass unchanged (47 passed).

## 2. Learning loop (`src/learning/`, `src/api/learning_routes.py`)

Three signals. All of them were already being recorded (or are recorded now), and nothing read them until this change.

| Signal | Source | What it teaches |
|---|---|---|
| Verdicts on RAWRS proposals | `CorrectionRecord` status + M-4.4 telemetry in every document sidecar | Per rule: acceptance rate with a **95% Wilson interval**, how often the value is rewritten, auto-apply undo rate, median decision time |
| Edits RAWRS never proposed | Records from `manual_reviewer` / `*_BY_REVIEWER` / `*_MANUAL_*` / `*_REVIEWED` | Where the detectors miss, plus the most common `from → to` changes |
| Changes made in Word after export | The remediator uploads the finished DOCX (Export Center → *Finished in Word*) | A structural diff against the DOCX they downloaded, and checklist items fixed or regressed by hand |

### Recommendations (advice only; nothing is applied automatically)

| Recommendation | Rule |
|---|---|
| `collect_more` | Fewer than 30 judgements |
| `candidate_auto_apply` | Accept lower bound ≥ 95% **and** value rewritten ≤ 10% |
| `approaching_auto_apply` | Accept lower bound ≥ 80% (40/40 lands here: its lower bound is 91%) |
| `candidate_retire` | Accept upper bound ≤ 20% |
| `improve_proposed_value` | Value rewritten ≥ 30%: right place, wrong value |
| `revisit_auto_apply` | Auto-applied ≥ 30 times and undo lower bound ≥ 5% |
| `keep_asking` | Anything else |

### DOCX diff (`src/learning/docx_diff.py`)

- **How it works:** python-docx + stdlib `difflib`, reusing the checklist auditor's readers. No dependency was added; the open-source DOCX redliners are AGPL or commercial.
- **Categories:** heading level, promoted or demoted heading, style, text (with word-level changes), alt text written or rewritten, decorative, table header/structure/content, added/removed content/images/tables, metadata.
- **Baseline:** the copy snapshotted at **download time** (`outputs/learning/<job>/exported.docx`, which can be turned off with `RAWRS_LEARNING_SNAPSHOT=off`). In-app edits made after the download are therefore never blamed on Word. If no download was recorded, the current export is used instead.
- **Evidence:** 0.23 s on a real 161-unit export. Style lookup is cached per document and checked equal to python-docx on 10,593 paragraphs. 15 tests.

### API

| Endpoint | Purpose |
|---|---|
| `POST /api/documents/{id}/final-docx` | Upload the finished DOCX (≤ 50 MB, zip-bomb guarded, must contain `word/document.xml`) and get back the diff plus checklist delta |
| `GET` / `DELETE /api/documents/{id}/final-docx` | Read or forget the stored comparison |
| `GET /api/learning/insights` | Everything above, ranked into "what to improve next". The first call reads every sidecar (18.9 s on 1,430); later calls take 0.1 s (mtime index) |
| `GET /api/learning/dataset` | Labelled JSONL (`proposal_decision`, `reviewer_edit`, `post_export_edit`) for offline training |

**UI:** the *Finished in Word* panel in the Export Center, and the `/insights` page linked from the site nav.

**Tests:** backend 51 (`tests/test_learning_*.py`); frontend 5, including axe checks (`frontend/__tests__/FinalDocxPanel.test.tsx`).

### Known limits

- Dev `outputs/documents` contains sidecars written by tests, so insights there mix test data with real reviews.
- Insights are aggregate advice. Turning a recommendation into a pipeline change is a deliberate code change with its own tests, never automatic.
