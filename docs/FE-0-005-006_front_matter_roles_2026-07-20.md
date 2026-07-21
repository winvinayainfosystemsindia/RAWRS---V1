# FE-0-005 / FE-0-006 — Front-Matter Semantic Classification

> **STATUS: COMPLETE (2026-07-20).** Both remaining gates are closed.
> Full suite: **1645 passed / 0 failed / 7 skipped / 37m46s** — baseline was
> 1617/1/7/42m58s, so +28 passing and the one known failure resolved by P0-1.
> The five required regression cases **are written** — `tests/test_front_matter_roles.py`,
> 21 tests, all passing. See `P0-0_SUITE_PROFILE_2026-07-20.md`.
>
> **The "Recommendation: roll back before merge" below is withdrawn.** It rested
> on the phantom title split. Do not act on it. The §Validation FAILED and
> §Not run sections are retained as historical record only and are both obsolete.

> **CORRECTION 2 (2026-07-20, H-001 — supersedes Correction 1 below).**
> The title split **does not exist in any code version**. It was an artifact of
> stale `__pycache__`. With bytecode cleared, FE-0-005/006 produces the joined
> title with the byline correctly excluded — exactly as designed — reproducibly
> across 5 runs and a backend restart. **This change works.** See
> `H-001_heading_reproducibility_2026-07-20.md`.
>
> Outstanding items are only: full regression suite unrun, and the five
> regression tests unwritten. Neither is a defect in the change.
>
> ~~**CORRECTION 1.** This report's central claim — that FE-0-005 introduced
> the native title split — is WRONG and retracted. The split is pre-existing at
> HEAD.~~ *(Also wrong — the "pre-existing at HEAD" measurement was itself
> contaminated. Struck through and kept visible as record.)*

**Date:** 2026-07-20 · **Status: COMPLETE — suite green; 21 regression tests passing**
Executed under RES v1. ~~Reported at Implementation Complete → **Validation FAILED**.~~ *(Superseded — see status header.)*

---

## Objective

Both ingestion pipelines produce equivalent front-matter semantics: document title → H1, author byline → metadata not heading, classification by role rather than typography.

## Scope

**In:** shared front-matter role classifier; native byline exclusion; Mathpix title promotion.
**Out:** subtitle/abstract/keywords roles (no extractor produces them — YAGNI), content-heading detection quality.

---

## Correction to the brief's premise

The brief stated the title is not promoted to H1. **Evidence contradicts this for the native path**, which already produced an H1 title before any change:

```
NATIVE (pre-change):  H1 'AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?'
                      H2 'Rohit Dhankar'
```

Each pipeline had the opposite half of the problem:

| | title → H1 | byline excluded |
|---|---|---|
| Native | ✅ already correct | ❌ promoted to H2 |
| Mathpix | ❌ missing | ✅ already correct |

FE-0-005 is a **Mathpix-only** gap; FE-0-006 is a **native-only** defect.

---

## Root Cause

`FrontMatter` already carried title/authors/affiliations plus exact source lines, populated *before* `detect_headings()` runs (`phase1_pipeline.py:265` vs `:437`). Heading detection never consumed it — `grep -c front_matter src/headings/heading_detector.py` returned 1, a comment. So the native path re-derived front-matter structure from font-size rank and promoted the byline that front matter had already classified as an author.

**Root Cause Confidence: Confirmed** — `extract_front_matter` returns `authors: ['Rohit Dhankar']`, `author_source_texts: ['Rohit Dhankar']` for the exact line the detector promoted to H2.

---

## Files Modified

| File | Change |
|---|---|
| `src/frontmatter/front_matter_roles.py` | **NEW** — `FrontMatterRole`, `classify_front_matter_line()`, `is_heading_eligible()`, `build_title_heading()` |
| `src/headings/heading_detector.py` | Skip AUTHOR/AFFILIATION lines before the H1-slot test |
| `src/mathpix/ingestor.py` | Title → H1 via shared builder |
| `src/markdown/markdown_builder.py` | Exclude the front-matter title from `content_headings` so it renders once |

---

## Validation Evidence

### Passed

| Criterion | Evidence |
|---|---|
| Byline no longer a heading (native) | `Rohit Dhankar` absent from `GET /headings` |
| Mathpix title → H1 | `H1 p1 'AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?'` |
| HEADING_002 clears | 0 on both paths (was firing on Mathpix) |
| PAGE_001 unchanged | 0 on both — FE-0-004 preserved |
| Markdown byte-identical | Mathpix 14069 B (= FE-0-004 baseline), native 14106 B (= pre-change), title renders **once** on each |
| Errors | 0 on both paths |

### FAILED — native title split

```
NATIVE (pre-change):   H1 'AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?'   (joined)
NATIVE (post-change):  H1 'AIMS OF EDUCATION: DO TEACHERS NEED'
                       H2 'TO BOTHER ABOUT THEM?'                                        (split)
```

The wrapped-title continuation repair (feature_007 `_absorb_continuations`) no longer joins the two source lines. The title is one wrapped line in the PDF; it must be one heading.

**Impact:** native heading structure is wrong — a spurious H2 whose text is a sentence fragment. Markdown output is unaffected (byte-identical) because the front-matter block owns the title's rendering, so this is a *model* defect, not an output defect. It would still reach any consumer reading `document.headings` — the DOCX structure tree, the outline panel, the review queue.

**Root Cause Confidence: Hypothesis — not diagnosed.** Both title source lines classify as `TITLE` and are therefore heading-eligible, so the exclusion path should not affect them. A direct `detect_headings(doc)` call with no page-numbering policy returns **zero** content headings, which does not match the API's two — meaning the pipeline's native heading path differs from the direct call in a way I have not traced. I will not name a mechanism I have not demonstrated.

### Not run

**Full regression suite — NOT RUN for this change.** The run started for FE-0-004 was killed before completion. Neither FE-0-004 nor FE-0-005/006 has a full-suite result.

**Regression tests — NOT WRITTEN.** The five required cases (title promotion, byline exclusion, parity, multi-author, missing-title fallback) are not implemented. Writing tests against known-broken behaviour would encode the defect.

---

## Remaining Risks

| Risk | Severity | Note |
|---|---|---|
| Native title split | **HIGH** | Open regression; blocks completion |
| Full suite unrun on two consecutive changes | **HIGH** | FE-0-004 and this change both lack a baseline comparison |
| No regression tests | Medium | Deferred until behaviour is correct |
| `classify_front_matter_line` is O(lines × source_texts) | Low | Source texts number in single digits |

---

## Rollback Strategy

```
git checkout -- src/headings/heading_detector.py src/mathpix/ingestor.py src/markdown/markdown_builder.py
rm src/frontmatter/front_matter_roles.py
```

Restores the byline-as-heading defect and the missing Mathpix H1; FE-0-004 is untouched by this rollback (`src/headings/page_markers.py` is a separate file). No migration, no persisted state.

**Recommendation: roll back before merge** unless the split is diagnosed first. The native regression is worse than the two defects this change fixes — a fragment H2 corrupts document structure for every native document with a wrapped title, whereas the byline defect adds one wrong heading.

---

## Final Question — remaining front-matter differences

| Property | Native | Mathpix | Match |
|---|---|---|---|
| Title present in front matter | ✅ | ✅ | ✅ |
| Title → H1 in model | ⚠️ split into H1+H2 | ✅ single H1 | ❌ |
| Byline excluded from headings | ✅ | ✅ | ✅ |
| Byline in `front_matter.authors` | ✅ | ✅ | ✅ |
| Affiliations | none in source | none in source | n/a — untested |
| Title rendered once | ✅ | ✅ | ✅ |
| HEADING_002 | 0 | 0 | ✅ |

**Front-matter semantics are NOT yet architecturally consistent.** Byline handling is now consistent and correct on both paths — FE-0-006's objective is met. Title handling is not: Mathpix produces one H1, native produces a split H1+H2.

The difference belongs to **FE-0-005, which stays open**. No new backlog item: this is the same title-promotion work, not a new defect class. Affiliation parity is untested — the sample document has none, so that row is unverified rather than passing.

---

## Next Task

Diagnose the native title split before anything else. Two specific questions: why does the API's native path yield two content headings when a direct `detect_headings()` yields zero, and which of those paths does `_absorb_continuations` run in. Then re-run the full suite for FE-0-004 and this change together.
