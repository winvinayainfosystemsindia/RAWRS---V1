# FE-0-004 — Eliminate False PAGE_001 Errors for Mathpix Documents

**Date:** 2026-07-19 · **Scope:** canonical model correctness · **Status:** Implementation Complete → Validation (targeted passed; full suite outstanding)
Executed under RES v1.

---

## Objective

Make the canonical document model complete regardless of ingestion source, so PAGE_001 stops reporting false errors on Mathpix documents. Fix the model, not the validator.

## Scope

**In:** page-marker construction in the Mathpix ingestion path; extraction of the shared builder; regression tests.
**Out:** heading classification quality (FE-0-005/006), the render-time fallback in `markdown_builder.py` (left as a safety net), PAGE_003 reading-order warnings, readiness scoring formula.

---

## Root Cause

`Document.headings` is the canonical model. Page markers were built independently in each path:

| Path | Built markers? | Site |
|---|---|---|
| Native PDF | Yes, inline | `heading_detector.py:289-307` |
| Mathpix | **No** | `ingestor.py` — only `_p2heading_to_heading()`, hardcoded `is_page_marker=False` (`:260`) |
| Markdown renderer | Yes, at render time | `markdown_builder.py:626-648` |

The third hid the second. When the model had no marker, `_page_marker_for()` synthesized a replacement so `###### 1..4` appeared in the output. The markdown looked correct while `Document.headings` contained none, so `_check_missing_page_markers()` (`validator.py:481`, which reads `document.headings`) reported every page as missing its marker.

Those 4 phantom ERRORs were the document's **entire** error count and drove `ready:false`.

**Root Cause Confidence: Confirmed.** Evidence: markdown contained `###### 1/2/3/4` while `GET /headings` returned 1 heading with `is_page_marker:false`; `error_count` was exactly the page count; the fix removed all 4 errors with markdown byte-identical.

---

## Design Decision

| Option | Verdict |
|---|---|
| Special-case PAGE_001 for Mathpix | **Rejected** — silences the symptom, leaves the model incomplete for every other consumer |
| Copy the marker loop into the ingestor | **Rejected** — a third copy of the same rule; the defect *is* duplicated logic |
| **Extract a shared builder, call from both paths** | **Chosen** — one source of truth; divergence requires editing one function |
| Make the renderer persist its synthesized markers | Rejected — rendering must not mutate the canonical model |

Markers are appended **after** content headings in the Mathpix path rather than interleaved. The Mathpix renderer projects content by `source_line` and resolves markers by `page_number`, so relative order does not affect output — and existing index-based assertions (`doc.headings[0]`) keep working.

---

## Files Modified

| File | Change |
|---|---|
| `src/headings/page_markers.py` | **NEW** — `build_page_marker()`, single source of truth (69 ln) |
| `src/headings/heading_detector.py` | Inline construction (19 ln) → call to shared helper (4 ln); +1 import |
| `src/mathpix/ingestor.py` | **The fix** — new step 2b builds one marker per page; +1 import |
| `tests/test_mathpix_ingestor.py` | 3 assertions corrected; +6 parity regression tests |

No schema change. No new dependency.

---

## Acceptance Criteria

| Criterion | Met | Evidence |
|---|---|---|
| PAGE_001 no false positives | ✅ | `PAGE_001 count: 0`; `error_count` 4 → 0 |
| Native PDF behaviour unchanged | ✅ | Native re-run: `PAGE_001 count: 0`, 4 markers, 2 content headings |
| Markdown output unchanged | ✅ | **Byte-identical** — 14069 bytes before and after, `diff` clean |
| Heading counts correct | ✅ | `GET /headings` still returns 1 (filters markers); `heading_count` 1 → 5 = 1 content + 4 markers, matching native's 6 = 2 + 4 |
| Readiness improves only from phantom removal | ⚠️ **See below** | PAGE errors 4 → 0; **overall_score unchanged at 0.3333** |
| Heading tests still pass | ✅ | 426 passed / 0 failed |

### The readiness criterion, precisely

The score did **not** improve. `overall_score` was 0.3333 before and after.

```
before: PAGE err 4 warn 4 ready False | HEADING err 0 warn 4 ready False | META ready True
after:  PAGE err 0 warn 4 ready False | HEADING err 0 warn 4 ready False | META ready True
```

The score is the fraction of *ready* categories. PAGE remains not-ready because 4 real PAGE_003 reading-order warnings survive, so removing the errors moved `error_count` without moving the score. The criterion as written anticipated an improvement; the honest result is that error count improved and the composite score did not. Reported rather than reframed.

---

## Validation Performed

| Type | Result |
|---|---|
| Functional | Mathpix re-run: errors 4 → 0, PAGE_001 absent |
| Regression (targeted) | `426 passed, 0 failed` (heading/validation/markdown/page-number, 10m30s) |
| Regression (file) | `tests/test_mathpix_ingestor.py`: `58 passed` |
| Parity | Native re-run: 4 markers, PAGE_001 = 0, unchanged |
| Output stability | Markdown byte-identical (14069 B) |
| Side-channel | `grep -c "synthesizing one"` = **0** — renderer fallback no longer fires |

**Full-suite regression: NOT YET RUN for this change.** A 46m10s full suite completed during this task, but it used pre-FE-0-004 code — provably, since it reported only the known docling failure rather than the 3 `test_mathpix_ingestor` failures the intermediate state produced. It validates P0-1, not this change. Stated per RES §4 rule 2 rather than implied.

---

## Regression Tests Added

`TestFE0004PageMarkerParity` — 6 tests:

1. one marker per page, correct page numbers
2. markers are H6
3. exactly one marker per page (asserts PAGE_001's invariant directly)
4. `_check_missing_page_markers()` returns `[]` for a Mathpix document
5. label precedence `page_label` → `printed_label` → physical number matches native
6. **both modules resolve `build_page_marker` to the same function object** — fails if either path grows its own copy

Test 6 is the one that prevents recurrence: it fails on divergence itself, not just on symptoms.

---

## Remaining Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Full suite not yet run against this change | **Medium** | Run before merge; 426 targeted tests pass |
| `heading_count` rises for Mathpix docs (1 → 5) | Low | Intended parity; `GET /headings` unchanged. Any UI reading `heading_count` as "content headings" was already wrong for native docs |
| Renderer fallback still exists | Low | Deliberate safety net for legacy callers; now proven dormant (0 warnings) |
| `document_order` groups markers after content in Mathpix, interleaved in native | Low | No consumer depends on cross-group ordering; see Final Question |

---

## Rollback Strategy

```
git checkout -- src/headings/heading_detector.py src/mathpix/ingestor.py tests/test_mathpix_ingestor.py
rm src/headings/page_markers.py
```

No migration, no persisted state, no schema change. Documents processed under the fix carry extra Heading objects in memory only; reprocessing regenerates them. Reverting restores the phantom errors — it does not corrupt anything.

---

## Next Dependent Task

**FE-0-005 / FE-0-006** — front-matter role classification (title → H1, byline ≠ heading). Same ingestion path, same file, and the Final Question below shows content-heading divergence is now the *only* remaining semantic gap.

---

## Final Question — canonical document comparison

Same source document through both pipelines:

| Property | Native PDF | Mathpix | Match |
|---|---|---|---|
| Pages | 4 | 4 | ✅ |
| **Page markers** | **4** | **4** | ✅ |
| Marker labels | 1,2,3,4 | 1,2,3,4 | ✅ |
| PAGE_001 errors | 0 | 0 | ✅ |
| Page labels | 4 | 4 | ✅ |
| Reading-order pages | 4 | 4 | ✅ |
| **Content headings** | **2** | **1** | ❌ |

**Page-marker handling is now architecturally consistent across both ingestion pipelines.**

One semantic difference remains, and it is **not** page-marker related: native detects 2 content headings, Mathpix 1. Native's extra heading is the author byline "Rohit Dhankar", promoted by font-size rank. Mathpix omits it because the MMD has no `\section` for it.

That difference is **already tracked** — it is precisely FE-0-006 (byline should not be a heading) and FE-0-005 (title should be H1, which *neither* path currently produces). No new backlog item is warranted; creating one would duplicate existing entries and violate the MIB's uniqueness rule.

Recommendation: no new item. FE-0-005/006 already cover it, and this comparison is evidence for their priority.
