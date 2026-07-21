# RAWRS — Master Implementation Backlog

Consolidates: Architecture Inventory · Architecture Review · ADR · Implementation Readiness · Engineering Readiness. Supersedes the task lists in all five. `TASKS.md` predates Phase 3.5 and is retired by this document (P0-7).

**Scope honesty (read first):** this backlog is exhaustive for **backend, model, testing, tooling and infrastructure**, all verified in source this session. It is **not exhaustive for UI/UX/reviewer friction** — every frontend claim in this project's documents is code-traced, never click-through verified against a running server. See §Final Question.

---

## Executive Summary

| Metric | Value |
|---|---|
| Verified backlog items | 41 |
| Critical path length | 6 items |
| Blocked on Phase 0 | 38 |
| Suite state | **0 failed / 1727 passed / 7 skipped** (2026-07-22) · runtime 48m58s — measured under concurrent load, see Engineering Standard |
| Fresh-clone reproducible | **No** |
| Architecture | Ratified (ADR), unchanged here |

**Health: amber.** Architecture is sound and settled. Engineering substrate is improving but not yet sufficient: the suite is still slow (37m46s), the benchmark corpus is unavailable to CI, and object identity is actively corrupting review data. The red test is **fixed** (P0-1) and the suite is green.

**Closed since this document was written:** P0-1 (dependency pinning), P0-0 (suite profile), FE-0-004, FE-0-005, FE-0-006, and **FE-0-001 (2026-07-21)** — the last of these closed the top release blocker and, with it, three of the release audit's four Critical risks. `FE-4`'s dependency is now satisfied. Remaining P0s from FE-0: **FE-0-002, FE-0-003**. See `P0-0_SUITE_PROFILE_2026-07-20.md` — it flags that **P0-2's stated dependency order is wrong**: the fast tier cannot reach <2min without P0-3's fixtures, so `P0-2 → P0-3` needs reconciling before P0-2 starts.

---

## Completed Work (verified, not claimed)

| Item | Evidence |
|---|---|
| Footnote/endnote model + detection | `models/footnote.py:50`, `NoteType.ENDNOTE`, `footnote_detector.py:40-51` |
| Accessibility rule registry + evidence + scoring | `accessibility/registry.py:43`, 13 rules |
| Cross-source verification engine | `verification/engine.py:35`, asset-agnostic |
| Correction audit trail + revert | `engine.py:82,107` |
| OCR routing (Docling → Surya fallback) | `ocr/router.py` |
| Page label policy (4 modes) | `structure/page_label_resolver.py` |
| Mathpix import path + object projection | `mathpix/ingestor.py`, `markdown_builder.py:798` |
| `real_docling`/`real_surya` markers | `pytest.ini` — convention exists |
| Stabilization P0-1..P2-11 | `STABILIZATION_REPORT_2026-07-19.md` — **code-traced, live-unverified** |

---

## Master Implementation Backlog

**Legend — Owner:** BE backend · FE frontend · SH shared. **Effort:** S <4h · M 4h-2d · L 2-5d · XL >5d.

### Phase 0 — Engineering Readiness *(blocks everything)*

| ID | Title | Cat | Pri | Eff | Deps | Acceptance | Verify | Owner |
|---|---|---|---|---|---|---|---|---|
| **P0-1** | Pin OCR dependency graph | Infrastructure | P0 | S | — | docling/rapidocr/torch/transformers pinned; `requirements.lock` | Fresh venv reproduces versions; D5 green | BE |
| **P0-0** | Profile suite `--durations=100` | Testing | P0 | S | P0-1 | Ranked cost table; top-N ≥80% runtime named | Committed report | BE |
| **P0-2** | Tier markers (`slow`,`benchmark_pdf`,`golden`) | Testing | P0 | L | P0-0 | Fast <2min; Medium <10min; 0 tests deleted | Time 3 tiers; fast passes with PDFs renamed away | BE |
| **P0-3** | `Document` JSON fixtures + golden runner | Testing | P0 | L | P0-2 | 10 fixtures; md byte-diff + DOCX normalized-XML | Run on clone w/o PDFs; corrupt fixture must fail | BE |
| **P0-4** | Default-invert pytest; xdist; make targets | Developer Experience | P0 | S | P0-2 | bare `pytest` = fast tier | Time bare `pytest` <2min | BE |
| **P0-5** | Orphan-surfacing spike (ADR-002 precondition) | Architecture Dependency | P0 | M | — | Low-confidence re-anchor → visible orphan, never silent | Synthetic low-confidence edit | SH |
| **P0-6** | Document ADR-013 concurrency gate | Documentation | P1 | S | — | `KNOWN_LIMITATIONS.md` states the gate | Present in file | — |
| **P0-7** | Retire `TASKS.md`; point `DOCUMENTATION_MAP.md` here | Documentation | P2 | S | — | No competing task list | grep for stale refs | — |

### ADR-012 → ADR-002 → ADR-010 *(sequential; ADR-012 first — readiness correction)*

| ID | Title | Cat | Pri | Eff | Deps | Acceptance | Verify | Owner |
|---|---|---|---|---|---|---|---|---|
| **A12-1** | SQLite store beside in-memory jobs | Infrastructure | P0 | M | P0-2 | Decision log + corrections durable | Survives restart | BE |
| **A02-1** | Mint UUIDs at detection; legacy ID alias | Architecture Dependency | P0 | M | A12-1 | Every object has stable UUID | All 4 positional sites migrated | BE |
| **A02-2** | Multi-selector re-anchor matcher | Architecture Dependency | P0 | L | A02-1, P0-5 | ≥95% re-anchor; 0 silent mis-anchors | Fixture + synthetic edits | BE |
| **A02-3** | Migrate 4 positional ID sites | Refactoring | P0 | M | A02-1 | `fn-{idx}`, `table-p{p}-{i}`×2, `p{p}-{n}` retired | grep clean | BE |
| **A10-1** | Append-only decision event log | Missing Feature | P0 | M | A12-1, A08-2 | 1 durable event per accept/reject/edit | Synthetic session replay | BE |
| **A10-2** | Surface orphaned corrections in reviewer UI | UX Improvement | P1 | M | A02-2 | Orphans visible + reassignable | Click-through | FE |

### ADR-003 / ADR-004 *(parallel with the identity stream — no contention)*

| ID | Title | Cat | Pri | Eff | Deps | Acceptance | Verify | Owner |
|---|---|---|---|---|---|---|---|---|
| **A03-1** | Document-wide repetition pre-pass | Missing Feature | P0 | L | P0-2 | Repeated text collected before classification | Unit + benchmark | BE |
| **A03-2** | Artifact partition (`pagination`/`layout`/`background`) | Missing Feature | P0 | M | A03-1 | Persisted, queryable, overridable | Benchmark 10/10 | BE |
| **A03-3** | **D1** — suppress first occurrence of running header | Functional Bug | P0 | M | A03-2 | First occurrence no longer a heading | Regression test; heading Δ=0 | BE |
| **A03-4** | **D2** — page-number guard across all 5 tiers | Functional Bug | P0 | S | A03-2 | Guard at entry point, not tier 4 | Regression per tier | BE |
| **A03-5** | Propagate `is_running_header` from Phase 2 | Technical Debt | P1 | S | A03-2 | Stranded Phase-2 flag consumed | `phase2_document.py:48,114` wired | BE |
| **A04-1** | Physical zone field (header/footer/body/margin/gutter) | Missing Feature | P1 | M | A03-1 | Zones populated per page | Benchmark 10/10 | BE |
| **A03-6** | Artifact override UI | UX Improvement | P1 | M | A03-2 | Reviewer can reclassify + see what was suppressed | Click-through | FE |

### ADR-001 / ADR-014 *(three steps; each gated)*

| ID | Title | Cat | Pri | Eff | Deps | Acceptance | Verify | Rollback | Owner |
|---|---|---|---|---|---|---|---|---|---|
| **A01-1** | Complete `SemanticObject` migration (Table/Footnote/TextBlock/Figure) | Technical Debt | P0 | L | P0-3 | 9/9 models migrated | Type check | Per-model | BE |
| **A01-2** | Build shallow tree beside lists (unused) | Architecture Dependency | P0 | XL | A01-1 | Tree built; lists authoritative | Golden gate green | Stop building | BE |
| **A01-3** | Migrate consumers to `walk()` | Refactoring | P0 | XL | A01-2 | All consumers use traversal | Golden gate at each consumer | Revert per consumer | BE |
| **A01-4** | Retire parallel lists | Refactoring | P0 | L | A01-3 | Lists removed | Golden gate green | Restore lists | BE |
| **A14-1** | Retire `_render_page_body_line_by_line` | Refactoring | P0 | L | A01-3 | Single rendering path | Golden gate 10/10 | Native fallback retained | BE |
| **A01-5** | Nested list depth → DOCX `ilvl` | Functional Bug | P1 | M | A01-3 | Nested lists correct in DOCX | DOCX XML assert | — | BE |
| **A01-6** | Table cell → header scope | Accessibility Bug | P1 | M | A01-3 | Header scope emitted | DOCX XML assert | — | BE |

### ADR-005 / 006 / 007

| ID | Title | Cat | Pri | Eff | Deps | Acceptance | Owner |
|---|---|---|---|---|---|---|---|
| **A05-1** | Logical divisions as Section nodes | Missing Feature | P1 | L | A01-3 | front/body/appendix/back bounded | BE |
| **A06-1** | Closed typed edge set (5 kinds) | Missing Feature | P1 | M | A01-3, A02-1 | Each maps 1:1 to DOCX construct | BE |
| **A06-2** | Reference linking in Markdown + DOCX | Missing Feature | P1 | M | A06-1 | xref→target navigable | BE |
| **A07-1** | Reading order stored as tree edits | Refactoring | P2 | M | A01-3 | Corrections persist as tree, not status field | BE |

### ADR-008 / 009 *(parallel — independent of the tree)*

| ID | Title | Cat | Pri | Eff | Deps | Acceptance | Owner |
|---|---|---|---|---|---|---|---|
| **A08-1** | Rule interface + `family` field | Refactoring | P1 | M | P0-2 | One registry shape | BE |
| **A08-2** | `rule_id@version` on every finding | Architecture Dependency | P0 | S | A08-1 | Version on all findings | BE |
| **A08-3** | Port 35 validator rules to registry | Refactoring | P1 | XL | A08-1 | 48 rules, IDs unchanged | BE |
| **A09-1** | Unify `Finding`/`Evidence` output type | Refactoring | P1 | M | A08-1 | One frontend issue type | SH |
| **A08-4** | Split `validator.py` (1290 ln) | Technical Debt | P2 | M | A08-3 | <800 ln per file | BE |
| **A08-5** | Split `routes.py` (1914 ln) | Technical Debt | P2 | L | — | <800 ln per file | BE |

### ADR-011 + Reviewer Surface

| ID | Title | Cat | Pri | Eff | Deps | Acceptance | Owner |
|---|---|---|---|---|---|---|---|
| **A11-1** | Eval harness: replay + per-rule precision/recall | Benchmarking | P1 | L | P0-3, A08-2 | Rule change reports precision delta | BE |
| **A11-2** | Regression gate on merge | Benchmarking | P1 | M | A11-1 | CI blocks on precision drop | BE |
| **FE-1** | Frontend logic test suite | Testing | P1 | L | — | Reviewer workflow covered (7 a11y files today, 0 logic) | FE |
| **FE-2** | Semantic editor as tree view | Missing Feature | P1 | XL | A01-3 | Reviewers edit objects, not markdown | FE |
| **FE-3** | Floating navigator (pages/headings/issues/search) | Missing Feature | P1 | L | A01-3 | IDE-like traversal | FE |
| **FE-4** | Session recovery: last item + last page | UX Improvement | P2 | M | ~~FE-0-001~~ ✅ met 2026-07-21 | P1-7 gap closed | FE |
| **FE-5** | Persist `visitedPages` across reloads | UX Improvement | P2 | S | — | Coverage survives reload | FE |
| **FE-6** | Backend checklist engine | Missing Feature | P2 | M | A08-3 | Replaces `ChecklistPanel.tsx` derivation | SH |

### FE-0 — Live Verification Findings (2026-07-19)

Sourced from `FE0_VERIFICATION_REPORT_2026-07-19.md`. First live click-through in project history. `FE-2` absorbs the read-only-editor finding; `FE-4` now depends on `FE-0-001`.

| ID | Title | Cat | Pri | Eff | Deps | Acceptance | Owner |
|---|---|---|---|---|---|---|---|
| ~~**FE-0-001**~~ | ~~Persist corrections/validation/headings across restart~~ | Data Loss | ~~P0~~ | L | A02 | ✅ **DONE 2026-07-21** — restart preserves review state; see `FE-0-001_document_persistence_2026-07-21.md` | BE |
| ~~**FE-0-002**~~ | ~~Fix all-zero first render after pipeline completion~~ | State Bug | ~~P0~~ | M | — | ✅ **CLOSED 2026-07-21** — not reproducible; 3 live runs, first render identical to post-reload; see `FE-0-002_first_render_investigation_2026-07-21.md` | FE |
| ~~**FE-0-003**~~ | ~~Regenerate endpoint + UI action for stale artifacts~~ | Dead End | ~~P0~~ | M | A14 | ✅ **DONE 2026-07-22** — ticket premise was wrong: downloads always applied corrections, only the *preview* was stale. Fixed by unifying all read paths on a regenerate-and-cache helper; no new endpoint, no UI action, no frontend change. Phase 3 (marker persistence) evaluated and **rejected**. See `FE-0-003_correction_to_output_2026-07-22.md` | BE |
| ~~**FE-0-004**~~ | ~~Emit page-marker `Heading` objects on Mathpix ingest~~ | Correctness | ~~P0~~ | M | A01 | ✅ **DONE 2026-07-20** (commit `2b7a9cf`) — PAGE_001 no longer fires on `###### N` markdown; see `FE-0-004_page_marker_parity_2026-07-19.md` | BE |
| ~~**FE-0-005**~~ | ~~Promote document title to H1 on Mathpix ingest~~ | Semantic | ~~P1~~ | M | A01 | ✅ **DONE 2026-07-20** (commit `2b7a9cf`) — see `FE-0-005-006_front_matter_roles_2026-07-20.md` | BE |
| ~~**FE-0-006**~~ | ~~Classify bylines as front-matter, not headings~~ | Semantic | ~~P1~~ | M | A01 | ✅ **DONE 2026-07-20** (commit `2b7a9cf`) — see `FE-0-005-006_front_matter_roles_2026-07-20.md` | BE |
| **FE-0-007** | Connectivity indicator; derive port from configured base URL | Missing Feedback | P1 | S | — | Backend-down is visible on load; message names the configured port | FE |
| **FE-0-008** | Populate summary counts in `GET /api/documents` | State Bug | P1 | S | A02 | Recent Documents shows real counts | BE |
| **FE-0-010** | Fix correction page-filter spinner range (`max=0, min=1`) | Visual Defect | P2 | S | — | Range derived from page count | FE |
| **FE-0-011** | De-duplicate review queue card in DOM | Visual Defect | P2 | S | — | One Accept control per correction in the a11y tree | FE |
| **FE-0-012** | Reconcile toolbar vs queue counter semantics | Consistency | P2 | S | — | "Corrections N" and queue totals agree or are labelled | FE |
| **FE-0-013** | Stop polling after `status=complete` | Performance | P2 | S | — | No repeat GETs post-completion | FE |

**Not exercised by FE-0** — images, tables, footnotes, lists, callouts (test document had zero of each), Focus Mode, Search, keyboard shortcuts, filter combinations, DOCX Preview interaction. FE-1, FE-3, FE-5, FE-6 remain code-traced claims.

### Phase 4 / Future

| ID | Title | Cat | Pri | Deps |
|---|---|---|---|---|
| **P4-1** | Design system — chrome only (type/spacing/colour) | Design System | P2 | **none — unblocked today** |
| **P4-2** | Design system — object presentation | Design System | P2 | A01-4, A14-1 |
| **F-1** | Optimistic concurrency (ADR-013 gate) | Architecture Dependency | P1 | A12-1 |
| **F-2** | Full job persistence | Infrastructure | P2 | A12-1 |
| **F-3** | Learning model over decision log | Research | P3 | A10-1 + data volume |
| **F-4** | Tagged-PDF / EPUB export | Future Enhancement | P3 | A01-4 — *would reopen ADR-001's full-tree question* |

---

## Dependency Graph & Critical Path

```
P0-1 → P0-0 → P0-2 →┬→ P0-3 → A01-1 → A01-2 → A01-3 → A01-4 → A14-1 → P4-2
                    │                              ├→ A05-1, A06-1, A07-1
                    ├→ A12-1 → A02-1 → A02-2 → A10-1 → A11-1 → A11-2
                    ├→ A03-1 → A03-2 → A03-3/4     (parallel)
                    └→ A08-1 → A08-2/3 → A09-1     (parallel)
P0-5 ──────────────────────────↗ (feeds A02-2)
```

**Critical path (6):** `P0-1 → P0-0 → P0-2 → P0-3 → A01-1 → A01-2/3/4 → A14-1`
**Longest by effort:** the ADR-001 chain (3× XL). Everything else fits beside it.

### Parallel opportunities

| Stream | Items | Contention |
|---|---|---|
| Identity | A12-1 → A02-* → A10-1 | none |
| Artifacts | A03-* / A04-1 | none |
| Rules | A08-* / A09-1 | none |
| Frontend | FE-1, FE-4, FE-5, P4-1 | none |

**Four streams run concurrently after P0-2.** Only the tree chain is strictly serial.

---

## Risk Register

| Risk | Sev | Mitigation |
|---|---|---|
| ADR-001 stalls like `SemanticObject` did (5-of-9) | **Critical** | A01-1 completes the *old* migration first — proves the team can finish one |
| Golden gate too slow to run → skipped | **Critical** | P0-2/P0-4 must land first; gate must be in the fast/medium tier |
| Re-anchor matcher mis-attributes corrections | High | Orphan-on-low-confidence (P0-5); never silent |
| Frontend backlog under-specified | High | **Acknowledged gap — see Final Question** |
| Decision log accrues under a schema that later changes | Medium | Append-only + versioned; never migrate, only add |
| 43-min suite hides new slowness | Medium | P0-0 baseline; track runtime as a metric |

---

## Milestones & Completion Criteria

| Milestone | Criteria |
|---|---|
| **M0 Readiness** | Fast <2min; suite green; fresh clone green; golden runner fails on corruption |
| **M1 Identity** | Corrections survive reprocessing ≥95%; 0 silent mis-anchors; every decision logged durably |
| **M2 Semantics** | D1/D2 fixed; artifacts classified + overridable; heading Δ=0 on 10/10 |
| **M3 Canonical model** | One document model; one rendering path; golden gate green |
| **M4 Rules** | 48 rules, one registry, versioned findings |
| **M5 Reviewer** | Tree editor, navigator, frontend logic tests, eval harness gating merges |
| **Phase 4 DoD** | M0-M5 complete · object presentation stable · design system applied · ADR-013 gate documented or closed |

---

# Final Question

> **"Is there any remaining planning work required before implementation begins?"**

**YES — one artifact, and it is the one this session never produced.**

### Missing artifact: a live product walkthrough

Every frontend, UI, UX, workflow and reviewer-friction claim in all six governing documents is **code-traced, never click-through verified**. This is stated explicitly in each of them:

- Feature Reality Audit — "verified by tracing render chains in code"
- Stabilization Report — "**Live click-through not performed**… browser-driving was out of budget"
- Architecture Inventory — "Frontend rows code-traced, **not** click-through verified"

That was Section 1 of the original Phase 3.5 brief — Upload, OCR, Outline, Review Queue, Editor, PDF, Markdown, DOCX, Accessibility Center, Validation, Export — and it has never been performed.

**Consequence for this backlog:** the backend/model/testing/tooling half is exhaustive and source-verified. The frontend half is a consolidation of *claims*, not findings. FE-1..FE-6 and P4-* are almost certainly incomplete, and I cannot know by how much. Declaring the backlog exhaustive would repeat precisely the error this project has already corrected twice — a report asserting completeness that later inspection disproved.

**The artifact required:** a walkthrough of the running application (`:3000`/`:8001` are up) against the 11 surfaces above, producing verified UI/UX/accessibility defects to merge into the FE-* section.

**Estimated effort:** 1 day. **Blocking:** frontend items only. **Not blocking:** the entire critical path.

### Recommended sequencing

Do not serialize behind the walkthrough. **Start P0-1 immediately** — it is source-verified, zero-risk, on the critical path, and independent of anything the walkthrough could discover. Run the walkthrough in parallel and merge its findings into FE-* before the frontend stream begins.

Planning is complete for backend, model, testing, benchmarking and infrastructure. It is **not** complete for the reviewer-facing surface, and that gap is one day of work — not another document.

---

## Governing process

Every item in this backlog executes under **`RAWRS_ENGINEERING_STANDARD.md` (RES v1)** — lifecycle, evidence standard, validation standard, reporting template, Definition of Done, review checklist. Task reports reference RES rather than restating it.

---

## UPDATE — FE-0 executed 2026-07-19

The walkthrough above was performed. See `FE0_VERIFICATION_REPORT_2026-07-19.md` and the FE-0 backlog section.

**Status 2026-07-22: every FE-0 P0 is closed.** FE-0-001, FE-0-002, FE-0-003, FE-0-004, FE-0-005 and FE-0-006 are done. Remaining FE-0 items are P1/P2 (FE-0-007, -008, -010..013).

- **FE-0-002** closed by live re-verification, not a code change — already fixed; see `FE-0-002_first_render_investigation_2026-07-21.md`.
- **FE-0-003** closed at half the estimated scope: two of the three surfaces named in the ticket were already correct. See `FE-0-003_correction_to_output_2026-07-22.md`.

**Evaluated-but-rejected optimization — FE-0-003 Phase 3 (export marker persistence).** Persisting `markdown/docx_generated_at_version` through the job checkpoint was implemented and unit-tested (7/7), then rejected on production verification: `_write_checkpoint` fires only on job-lifecycle events, while markers advance during a GET, so nothing flushed them and the marker did not survive a live restart. Making it work requires a GET request to write a checkpoint. Benefit is one rebuild per artifact per restart (~110 ms Markdown / ~880 ms DOCX, once) — not worth turning every read path into a disk writer. Reverted; `src/api/jobs.py` untouched. **Do not re-propose without new evidence that the rebuild cost matters.**

Settled architecture: GET performs regeneration and cache updates only; checkpoint writes stay tied to job lifecycle events; one regeneration per artifact after restart is accepted.

**Outcome:** 13 defects found, 4 at P0. Three of them — FE-0-001, FE-0-002, FE-0-004 — cause the product to display a document as clean when it is not. None had been predicted by any of the six prior planning documents, and none was discoverable by code tracing: each required watching the running application.

**Corrections to the claims above:**
- The primary input is a **Mathpix package**, not a PDF. "Upload → OCR processing" describes a path that is no longer the product's front door. Phase-3.5 Section 1's 11 surfaces were framed around the superseded pipeline.
- The information architecture is **sound**; no screen requires redesign. The defects are data-binding, persistence and semantic-classification bugs.
- The critical path is **unchanged**. FE-0 confirmed it.

**Residual gap:** images, tables, footnotes, lists, callouts, Focus Mode, Search, keyboard shortcuts and DOCX Preview were not exercised — the test document contained none of the first five. A second walkthrough on a figure- and table-rich document is required before the frontend stream is fully evidenced. It blocks no P0 item.
