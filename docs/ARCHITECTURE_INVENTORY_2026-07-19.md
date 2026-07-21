# Architecture Inventory — Phase 3.5A

Due-diligence review. Every row traced in the repo; no claim carried over from prior reports.
Legend: ✅ Exists · 🟡 Partial · 🔴 Missing

**Headline:** RAWRS has **two incompatible canonical document representations**. Almost every Phase 3.5 request is Category C for that one reason.

---

## Central Finding

`markdown_builder.py` has two rendering paths:

| Path | Mechanism | Evidence |
|---|---|---|
| RAWRS-native | Reconstructs output by scanning `page.cleaned_text` line-by-line and re-matching objects by **exact string** | `_render_page_body_line_by_line()` :709-762 |
| Mathpix | Projects `Document`'s real objects sorted by `source_line` — a true object sequence | `_render_page_semantic()` :798-842 |

The Mathpix docstring states the native mechanism "structurally cannot work" for object projection (:809-812). So on the native path the canonical document is **page text + side-lists rejoined by string match**, not an ordered object graph. Regions, a semantic editor, document-wide reasoning and export-wide suppression all require the object graph on *both* paths.

---

# Existing Subsystems

| Subsystem | Purpose | Capability | Key limitation | Extension point |
|---|---|---|---|---|
| Document model | Root aggregate | 12 parallel typed lists + `version` | Flat lists, no ordering/containment/region | `models/document.py:75-121` |
| Page model | Physical page | OCR route, labels, printed_label, reading-order status | No region map, no header/footer zones | `models/page.py:172-205` |
| Object model | Shared base | `SemanticObject` (id/page/bbox/provenance/confidence/lifecycle) | **Migration incomplete** — Table, Footnote, TextBlock, Figure still bare `BaseModel` | `models/semantic_object.py:46` |
| OCR pipeline | Text recovery | Router → Docling → Surya fallback; targeted re-OCR w/ timeout | Page-level confidence only | `ocr/router.py:139` |
| Import pipeline | Mathpix ingest | `ImportProvider` protocol, mmd_parser, CorrectionRecord | Only provider is Mathpix | `mathpix/ingestor.py` |
| Heading detection | H1–H6 | 5-tier cascade; layout-rank primary; H6 page markers by policy | **Single-pass** — see gap table | `headings/heading_detector.py:529-594` |
| Validation | Rule checks | 35 rule IDs (DOC/HEADING/IMAGE/META/NOTE/OCR/PAGE/TABLE) | Hardcoded procedural, not a registry | `validation/validator.py` (1290 ln) |
| Accessibility engine | A11y scoring | Registry + evidence bundles + scoring/debt/provenance | 13 rules only; **parallel to validator** | `accessibility/registry.py:43` |
| Verification | Cross-source | Asset-agnostic engine; headings/figures/tables/lists/footnotes/callouts | Findings are per-object, no doc-wide pass | `verification/engine.py:35` |
| Correction engine | Audit trail | `apply/revert_correction`, `RuleSpec` table, version bump | Revert is per-rule bespoke | `verification/engine.py:82,107` |
| Markdown gen | .md output | Two paths (above) | Native path is string-match | `markdown/markdown_builder.py` |
| DOCX gen | .docx output | Heading styles, footnote/endnote wiring (Phase K) | Consumes markdown assumptions | `docx/docx_generator.py` (1182 ln) |
| Export | Download | md/docx/report + `_needs_export_regen` vs `version` | — | `api/routes.py:1599-1703` |
| State mgmt (FE) | Reviewer state | 6 React contexts + 4 hooks | No document-scoped persistence | `frontend/lib/store/` |
| Navigation | Nav tree/chips | `SemanticNavTree`, `NavChips` | Tree over flat lists; no floating navigator | `components/workspace/` |
| Review engine (FE) | Queue/actions | `useReviewAction`, `ReviewQueueContext` | — | `lib/hooks/useReviewAction.ts` |

---

# Missing Foundational Subsystems

| Capability | Status | Evidence |
|---|---|---|
| Semantic document regions | 🔴 | Zero hits: `grep "class .*Region\|DocumentRegion"` on `src/models/*.py` |
| Semantic editor model | 🔴 | `MarkdownEditor.tsx` is CodeMirror over **markdown text**; no object editor exists |
| Footnote model | ✅ | `models/footnote.py:50` — marker, anchor_offset, continuation lines |
| Endnote model | ✅ | `NoteType.ENDNOTE`; Notes-section detection `footnote_detector.py:40-51,102` |
| Cross-reference model | 🔴 | No xref model (only PDF image `xref` ints) |
| Document knowledge graph | 🔴 | No graph structure anywhere |
| Running header detection | 🟡 | Verification-layer only: `verification/headings.py:280-297,499` |
| Running footer detection | 🟡 | Same signal, not separately modelled |
| Repeated heading detection | 🟡 | `emitted_heading_texts` guard, tier 4 only |
| Global heading reasoning | 🔴 | Detection is strictly single-pass, forward-only |
| Document-wide reasoning | 🔴 | No pre-pass stage in pipeline |
| Page metadata model | ✅ | `Page` carries labels/route/status/width |
| Reading-order graph | 🔴 | Status enum only (`ReadingOrderStatus`); no graph |
| Semantic relationships | 🟡 | Footnote↔anchor only; nothing generalised |
| Checklist engine | 🔴 | Frontend-only derivation, `ChecklistPanel.tsx:29` — no backend |
| Rule engine | 🟡 | Two: a11y registry (pluggable) + validator (hardcoded) |
| Reviewer knowledge model | 🔴 | No learning/feedback persistence |
| Accessibility reasoning engine | 🟡 | Scores + evidence; no cross-rule inference |

---

## Confirmed Defects (verified this phase)

| # | Defect | Evidence |
|---|---|---|
| D1 | First occurrence of a running header still becomes a heading | `heading_detector.py:550-554` states it in the docstring |
| D2 | Page-number guard applies to tier 4 only; tiers 1/2/3/5 unguarded | `heading_detector.py:579-581` |
| D3 | `SemanticObject` migration abandoned mid-way | Table/Footnote/TextBlock/Figure bare `BaseModel` |
| D4 | Two rule engines, divergent | 35 validator IDs vs 13 registry IDs, no shared vocabulary |
| D5 | Test suite not clean; full run >5 min | 1 failure at ~13% of run; **identity unconfirmed — run interrupted** |

---

# Requested Enhancements Classification

| Request | Class | Justification |
|---|---|---|
| Running header removal | **A → C** | Symptom is a bug; root cause needs a doc-wide pre-pass that does not exist |
| Repeated heading suppression | **A → C** | Same pre-pass; single-pass detector cannot see repeats ahead |
| Page-number hierarchy | **A** | Relocate existing guard to entry point — real bug fix, no new subsystem |
| Footnote rendering | **B** | Model + detector exist; rendering path needs work |
| Endnote rendering | **B** | Same |
| Heading intelligence | **B** | 5-tier cascade exists; enhance after pre-pass lands |
| Semantic regions | **C** | Nothing exists |
| Document-wide reasoning | **C** | No pipeline stage for it |
| Semantic editor | **C** | Editor is text-based; needs object graph first |
| Reference linking | **C** | No cross-reference model |
| Reading-order improvements | **C** | Status enum ≠ graph |
| Floating navigator | **B** | Nav components exist; this is a UI addition |

**Six of twelve are Category C.** Three more are Category A that decay into C once root-caused.

---

# Proposed Architecture Designs

### C-1 · Object Sequence Unification *(prerequisite for everything else)*
| | |
|---|---|
| Purpose | One canonical ordered object graph on both native and Mathpix paths |
| Responsibilities | Assign `source_line`/order to native-path objects; retire string-match reinsertion |
| Interface | `Document.sequence() -> List[SemanticObject]` in document order |
| Migration | Complete `SemanticObject` for Table/Footnote/TextBlock/Figure; keep `cleaned_text` populated in parallel during transition |
| Compatibility | Native renderer stays as fallback until sequence coverage proven per-document |
| Risk | **High** — touches markdown, docx, validation, verification |
| Test | Byte-identical markdown on all 10 benchmark PDFs before switchover |

### C-2 · Document-Wide Pre-Pass
| | |
|---|---|
| Purpose | Global reasoning before classification |
| Responsibilities | Collect repeated text across pages; emit repetition/position statistics |
| Interface | `analyze_document(pages) -> DocumentProfile` consumed by heading detector |
| Integration | New pipeline stage between `detect_structure` and `detect_headings` |
| Migration | Additive; detector accepts optional profile, falls back to current behaviour |
| Risk | **Low** — additive, no existing contract changes |
| Test | D1/D2 regressions; benchmark heading counts must not regress |

### C-3 · Region Model
| | |
|---|---|
| Purpose | Front matter / main / running header / footer / sidebar / note regions |
| Data | `DocumentRegion` enum + `region: Optional[DocumentRegion]` on `SemanticObject` |
| Integration | Populated by C-2's profile; consumed by heading detection, validation, exports |
| Migration | Optional field defaulting `None` = "unclassified", never "no region" |
| Risk | **Low** once C-2 exists; **high** if attempted before |

### C-4 · Relationship / Cross-Reference Graph
| | |
|---|---|
| Purpose | Generalise the footnote↔anchor link to all object pairs |
| Data | `Relationship(source_id, target_id, kind)` list on `Document` |
| Prerequisite | C-1 (stable object IDs on every type) |
| Risk | Medium |

### C-5 · Semantic Editor Model
| | |
|---|---|
| Purpose | Reviewers edit objects, not markdown |
| Prerequisite | C-1 + C-4 |
| Risk | High — largest frontend change in the project |

### C-6 · Unified Rule Engine
| | |
|---|---|
| Purpose | Collapse validator's 35 hardcoded rules into the a11y registry |
| Migration | Port rule-by-rule, keeping IDs stable so the frontend is unaffected |
| Risk | Medium — mechanical but wide |

---

# Dependency Graph

```
C-2 Pre-Pass ──┬──> C-3 Regions ──┐
   (low risk)  │                  ├──> Heading Intelligence (B)
               └──> D1/D2 fixes ──┘

C-1 Object Sequence ──┬──> C-4 Relationships ──> C-5 Semantic Editor
   (high risk)        │
                      └──> Reading-Order Graph

C-6 Rule Engine ── independent (can run in parallel)
Floating Navigator (B) ── independent
```

| Subsystem | Prereq | Blocks | Risk |
|---|---|---|---|
| C-2 Pre-pass | none | C-3, D1, D2 | Low |
| C-3 Regions | C-2 | heading intelligence, exports | Low |
| C-1 Object sequence | none (but wide) | C-4, C-5, reading order | **High** |
| C-4 Relationships | C-1 | C-5 | Medium |
| C-5 Semantic editor | C-1, C-4 | — | High |
| C-6 Rule engine | none | — | Medium |

**C-2 is the cheapest high-value entry point. C-1 is the expensive one everything glamorous depends on.**

---

# Recommended Implementation Order

| Phase | Contents | Rationale |
|---|---|---|
| **3.5B** | Fix D5 (green suite) → C-2 pre-pass → D1, D2 → C-3 regions | Low risk, additive, closes the loudest correctness gaps |
| **3.6** | C-1 object sequence unification | Highest risk; needs a clean suite (3.5B) as its safety net |
| **3.7** | C-4 relationships + reading-order graph + C-6 rule engine | All unblocked by C-1 |
| **3.8** | C-5 semantic editor + floating navigator + Section 1 walkthrough | Frontend phase, once the model it must present is real |
| **4** | Design system overhaul | Last — restyling a surface whose data model is mid-migration is wasted work |

---

# Risks

| Risk | Severity | Mitigation |
|---|---|---|
| C-1 breaks markdown/docx output silently | **High** | Byte-diff all 10 benchmark PDFs before switchover |
| Test suite unknown-failing | **High** | Resolve D5 before any refactor |
| Building regions before the pre-pass | High | Enforce C-2 → C-3 order |
| Two rule engines drift further | Medium | Freeze new rules to the registry only |
| >5 min test runs discourage running them | Medium | Mark slow tests; fast default subset |

---

# Technical Debt

| Item | Evidence |
|---|---|
| Abandoned `SemanticObject` migration | 5 of 9 models migrated |
| Duplicate rule engines | validator 35 vs registry 13 |
| Dual rendering paths | `markdown_builder.py` :709 / :798 |
| `routes.py` 1914 lines, `validator.py` 1290 | Both exceed the 800-line project limit |
| String-match coupling | Renderer depends on exact text equality with detector output |
| Session-scoped `visitedPages` | Prior report, `PdfViewportContext` |

---

# Final Recommendation

**Do not implement Phase 3.5 as written.** Six of its twelve asks are Category C, and three of the "bug fixes" decay into Category C once root-caused. Forcing them into the current architecture produces exactly the pattern this project already has: a feature that exists, renders, and doesn't work.

**Proceed with Phase 3.5B: green test suite → C-2 pre-pass → D1/D2 → C-3 regions.** All additive, all low-risk, and it makes Sections 3, 4 and 6 of the original brief genuinely true.

**Answer to "is RAWRS semantically mature enough to learn from expert remediators?" — No.** Learning from remediators requires a stable object identity to attach feedback to (C-1), a relationship model to express corrections (C-4), and a reviewer knowledge model (absent entirely). That question belongs after Phase 3.7, not now.

---

## Verification status of this document

| Claim type | Method |
|---|---|
| All 🔴 Missing rows | grep-verified absent across `src/` |
| All file:line citations | Read directly this session |
| D1, D2 | Source docstrings state the limitation explicitly |
| D5 | **Partially verified** — failure observed, identity unconfirmed (run interrupted) |
| Frontend rows | Code-traced, **not** click-through verified against a live server |
