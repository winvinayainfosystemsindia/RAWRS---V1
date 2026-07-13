# RAWRS Backend Completion Audit — 2026-07-13

Point-in-time audit, current as of commit `1571747` (Phase M-5.4.1 complete). Compares actual code (`src/`) against `docs/ARCHITECTURE.md`, `docs/ARCHITECTURE_CURRENT.md`, `docs/PHASE_STATUS.md`, `docs/TASKS.md`, `docs/DECISIONS_LOG.md`, `docs/KNOWN_LIMITATIONS.md`, and the M-5.2/M-5.4.1 real-corpus benchmark. No code was changed to produce this audit.

**A note on the docs it's compared against:** both `ARCHITECTURE.md` (pre-Mathpix) and `ARCHITECTURE_CURRENT.md` (dated 2026-07-08, pre-Phase-M-3/M-4/M-5) are themselves stale relative to current code — this audit grounds every claim in direct code inspection (file:line), not in what the docs claim, and flags every place they disagree.

---

## 1. Backend Completion Matrix

| # | Subsystem | Status | Evidence |
|---|---|---|---|
| 1 | Canonical Document | ✅ Production Ready | `src/models/document.py`, `contracts.py`, `semantic_object.py`. `SemanticObject` base (id/bbox/`verification_status`/`confidence`/`lifecycle_status`) unifies 6 registered asset types. Extended additively across every phase M-1→M-5.4.1 with zero breaking changes recorded. |
| 2 | Import Pipeline | ✅ Production Ready | `src/pipeline/phase1_pipeline.py` — dual-path (`mmd_path=None` PDF-native vs Mathpix), both fully wired, deliberate and documented. |
| 3 | Mathpix Integration | 🟡 Needs Hardening | `src/mathpix/{mmd_parser,ingestor,latex_env_parser,math_transformer}.py`. Real, confirmed bug (M-3.1 closeout note): `mmd_parser.py`'s `\footnotetext{N}{body}` regex is single-line-only and misses real multi-line MMD output — 0 footnotes parsed on the Brinkman benchmark sample. Not yet fixed. |
| 4 | OCR | 🟡 Needs Hardening | `src/ocr/{docling_engine,surya_engine,targeted}.py`. Core paths solid; targeted-OCR reliability just closed (M-5.4.1, timeout-bounded, tested). Residual: real per-call inference latency ~100s (CPU-bound, not a bug); Surya's CPU path spawns an external `llama-server` binary (`DECISIONS_LOG.md` Part 4) — a real runtime dependency, fragile across environments. |
| 5 | Evidence Engine | ✅ Production Ready | `src/verification/evidence.py` — `EvidenceSignal`/`EvidenceBundle`, weighted-mean confidence fusion. Used consistently by headings/tables/footnotes verifiers. Well tested. |
| 6 | Evidence Resolution | 🟡 Needs Hardening | `src/verification/text_resolution.py` (`TextResolver`, M-5.3) — solid tiered exact/normalized/containment/fuzzy resolution, real-corpus validated. Only wired into `headings.py` so far; `TableVerifier`/`FootnoteVerifier` still use their own simpler binary matching (M-3.1/M-3.2), not this resolver — adoption breadth is the gap, not the mechanism. |
| 7 | Verification Framework | ✅ Production Ready | `src/verification/{base,engine,matching,merge}.py`. 6 registered asset types (figures, headings, lists, callouts, footnotes, tables); self-registration pattern proven across 3 phases; generic `MultiSignalMatcher`; consistent `MergeAction` (KEEP/REPAIR/RECOVER/REMOVE) decision model. |
| 8 | Recovery Engine | 🟡 Needs Hardening | `merge.py`'s `canonical=None` (RECOVER) branch. Works across headings/footnotes/tables, but proposal-only — never auto-inserts a recovered object into the canonical document, human must apply. Footnote RECOVER findings are currently inflated by item 3's parser bug on at least one real document. |
| 9 | Proposal Engine | ✅ Production Ready | `engine.findings_to_corrections()` — consistent `CorrectionRecord` creation across all 6 asset types. |
| 10 | Correction Pipeline | ✅ Production Ready | `src/api/routes.py::review_correction()` — accept/reject/edit/ignore/undo/needs_review, all wired and tested (M-3/M-4.4). |
| 11 | Versioning | 🟡 Needs Hardening | FEATURE_020 (`src/api/schemas.py:49`) — a single monotonic `document_version` int + per-artifact `*_generated_at_version`, solving exactly one problem (stale-export detection for the frontend). No version history, no diff view, no rollback, no persistence across process restart. |
| 12 | Reviewer Backend APIs | 🟡 Needs Hardening | `src/api/routes.py`. Solid, tested coverage for headings/footnotes/images/tables/reading-order/page-labels/metadata/generic-corrections/validation-issues. Documented, genuine holes (`KNOWN_LIMITATIONS.md`): no paragraph body-text correction API, no cross-document field correction, no "mark validation finding as intentional/acceptable." |
| 13 | Validation Engine | 🟡 Needs Hardening | `src/validation/validator.py` — ~29 rule IDs across document/heading/page/image/OCR/note/table/metadata. Known bug: `PAGE_001` false-positives under `AUTO`/`DISABLED` page-numbering policy (policy isn't threaded into `validate_document()`, `KNOWN_LIMITATIONS.md`, unfixed). Figure-level validation (caption/numbering completeness) has no rule ID. Broken-word OCR detection has no rule ID. |
| 14 | Benchmark Framework | ✅ Production Ready | `src/verification/benchmark_report.py`, `docx_fidelity.py`. Accessibility score, repair rate, confidence distribution, object counts, Mathpix accuracy/recovery rate, DOCX fidelity — all implemented, tested (M-3.3). "Human Minutes Saved" deliberately not implemented (correctly deferred, not a gap) — but M-4.4's telemetry now supplies exactly the data it would need; currently unwired (see ROI ranking, item 2). |
| 15 | DOCX Generator | ✅ Production Ready | `src/docx/docx_generator.py`. Headings, page markers/breaks, image+alt-text, footnote bookmark/hyperlink wiring, CMYK-JPEG fix, sanitization guard. 10/10 benchmark self-comparison DOCX fidelity = 1.0. Footnotes are bookmark/hyperlink, not native Word `w:footnote` OOXML — a documented, deliberate tradeoff, not a defect. |
| 16 | Markdown Generator | ✅ Production Ready | `src/markdown/markdown_builder.py`, `paragraph_grouper.py`. Paragraph reconstruction (bug_001 fixed), heading hierarchy, footnote syntax, alt-text embedding. |
| 17 | Accessibility Metrics | 🟠 Partially Complete | The *score* itself (`compute_accessibility_score`) is solid, but the broader accessibility posture it measures has real open gaps: no PDF-UA-equivalent tagging (explicitly out of scope), figure/caption validation incomplete (item 13), table `<w:tblHeader>` accessibility attribute never audited (flagged in the 2026-06-27 gap audit, never followed up since). |
| 18 | Telemetry | 🟠 Partially Complete | `CorrectionTelemetryEvent` (M-4.4) — collection-only, in-memory (lost on restart, no database per architectural constraint), not exposed via any API/dashboard, not yet aggregated into the Benchmark Framework metric (item 14) it exists to feed. |
| 19 | Performance | 🟠 Needs Investment | No profiling infrastructure found anywhere in `src/`. The one performance bug found this session (M-5.4.1's predictor-rebuild issue) was caught reactively by a benchmark run, not by any standing practice. Real per-document processing time for OCR-heavy documents ran to multiple minutes in this session's benchmarks. |
| 20 | Caching | 🟠 Partially Complete | Exactly one cache exists in the entire backend: `@lru_cache(maxsize=1)` on `build_recognition_predictor()` (`src/ocr/surya_config.py`, this session). No page-render cache, no repeated-PDF-parse cache, no HTTP response caching. Intentionally minimal given "no databases/no cloud," but worth naming as sparse rather than assuming it's covered. |
| 21 | Parallelism | ❌ Missing | No `asyncio`, `ThreadPoolExecutor`, `ProcessPoolExecutor`, or `multiprocessing` anywhere in `src/`, except the single-purpose reliability thread added in M-5.4.1 (not a throughput mechanism). Every document is processed fully sequentially, single-threaded; no evidence of concurrent multi-document processing. |
| 22 | Reading Order | ✅ Production Ready (for its defined scope) | Detection (`PAGE_003`) + FEATURE_016B numbered overlay + drag-reorder + approve workflow; 16 route occurrences confirm real backend wiring. Automatic reordering is explicitly **not planned** (`KNOWN_LIMITATIONS.md`, `DECISIONS_LOG.md` Part 19) — a decision, not a gap. |
| 23 | Semantic Regions | 🟠 Partially Complete / ambiguous term | If this means the `SemanticObject`/asset-type framework (headings/tables/footnotes/figures/lists/callouts) — ✅ Production Ready, 6 types registered. If it means spatial page regions (header/footer/margin/body zones as a first-class model) — ❌ Missing; only heuristic running-header detection exists, embedded inside `HeadingVerifier`, not a standalone region concept. |
| 24 | Cross-page Tables | ❌ Missing | Explicitly documented (`KNOWN_LIMITATIONS.md`) as not implemented. Each page treated independently; manual table creation is the reviewer's only workaround. Known-affected: Brinkman Tables 2 and 5 in the benchmark corpus. |
| 25 | Page Labels | ✅ Production Ready | FEATURE_018, `src/structure/page_label_resolver.py`. Override > reviewer-defined section > detected `printed_label` precedence, wired into Markdown/DOCX regeneration. No TOC/nav/PDF-export (explicitly out of scope for this feature, not a gap in it). |
| 26 | Two-page Spread Detection | ❌ Missing | No trace anywhere in the codebase, and not mentioned in any doc as planned or even deferred — a genuine unscoped blind spot, distinct from the deliberately-deferred items above. |

---

## 2. Remaining Backend Roadmap

Grouped by what's actually blocking vs. deliberately out of scope vs. needs a product decision before any code is written.

**Not blocking production, small/clear fixes (safe to pick up opportunistically):**
- Mathpix multi-line `\footnotetext{}` regex fix (item 3)
- `PAGE_001` false-positive under `AUTO`/`DISABLED` policy (item 13)
- Extend `TextResolver` to `TableVerifier`/`FootnoteVerifier` (item 6)
- Wire `CorrectionTelemetryEvent` into "Human Minutes Saved" (items 14/18)
- Figure-level validation rule + broken-word OCR rule ID (item 13)

**Deliberately deferred by architecture decision — do not start without a scope conversation (per `KNOWN_LIMITATIONS.md`):**
- Equation remediation, multi-column reconstruction, cross-page paragraph stitching
- Cross-page table detection (item 24)
- Span-level text model (blocks bug_005 footnote-marker detection generalization)
- PDF-UA-equivalent accessibility tagging

**Needs a product/infrastructure decision before any code, not a "just build it" item:**
- Parallelism (item 21) — only worth investing if concurrent multi-user throughput is an actual near-term requirement; the tool's current human-in-the-loop, one-document-at-a-time design may not need it
- Persistence / job store beyond in-memory dict (ties into Versioning, item 11, and Telemetry, item 18) — a database would cross the "no databases" architectural constraint and needs explicit sign-off to change
- Two-page spread detection (item 26) — nobody has scoped this; needs a real use case first
- Semantic Regions as spatial zones (item 23) — needs a concrete downstream consumer before it's worth building

---

## 3. Priority Ranking by ROI (highest first)

| Rank | Item | Effort | Manual-remediation reduction | Dependencies |
|---|---|---|---|---|
| 1 | Mathpix multi-line footnotetext fix | Small (regex fix) | High for documents with multi-line MMD footnotes — currently 0 footnotes parsed on affected documents, fully blocking `FootnoteVerifier`'s value on them | None |
| 2 | `PAGE_001` policy threading | Small–Medium (thread `PageNumberingPolicy` into `validate_document()`) | Medium — removes false-positive validation noise reviewers currently have to manually dismiss | None |
| 3 | Wire telemetry → Human Minutes Saved | Medium (aggregation logic; needs real usage data to accumulate first) | High long-term — the single most requested-sounding benchmark metric, and the data collection for it is already live | M-4.4 telemetry (done) |
| 4 | Extend TextResolver to Table/FootnoteVerifier | Medium | Medium — improves cross-source match accuracy the same way it did for headings | `TextResolver` (done) |
| 5 | Figure/OCR validation rule gaps | Small–Medium each | Medium — closes known blind spots in the Validation Engine | None |
| 6 | Reviewer API coverage (paragraph text, "mark intentional") | Medium–Large | Medium — closes the review loop for the last uncovered content types | None |
| 7 | Cross-page table detection | Large (geometry tracking across page boundaries) | Medium — narrow but real (2 known-affected benchmark tables) | Needs architecture sign-off per `KNOWN_LIMITATIONS.md` |
| 8 | Parallelism / performance investment | Large, and possibly unnecessary | Unknown — no evidence yet that this is a real bottleneck for actual usage patterns | Needs a documented real-world throughput requirement first |
| 9 | Two-page spread / spatial semantic regions | Unscoped | Unknown | Needs a concrete use case before any estimate is possible |

---

## 4. Production Readiness Assessment

**RAWRS's backend is production-ready today as a single-reviewer-at-a-time, human-in-the-loop PDF remediation tool** for born-digital and lightly-scanned academic PDFs. The core value loop — Evidence Engine → Verification Framework → Recovery/Proposal Engine → Correction Pipeline → Reviewer APIs — is mature, self-consistent across 6 asset types, and has real-corpus benchmark evidence behind it (M-3 through M-5.4.1). OCR is now reliably bounded (no more indefinite hangs). DOCX/Markdown generation is solid (1.0 fidelity on self-comparison).

**It is not production-ready for:**
- High-concurrency multi-user throughput (no parallelism, in-memory-only job store, no persistence across restart — items 11/18/19/20/21)
- Documents that require cross-page reconstruction: tables, paragraphs, multi-column layouts (item 24, deliberately-deferred list)
- Fully automatic/unsupervised remediation — but this is a **design choice**, not a gap: RAWRS is deliberately human-in-the-loop throughout (Reading Order, Recovery, Corrections all route through reviewer approval by design)

None of the "not ready for" items above are silent or newly discovered — every one is already named in `KNOWN_LIMITATIONS.md` or this audit's matrix, with an explicit reason it wasn't picked up.

---

## 5. Recommendation: Shift back to frontend?

**Yes.** The backend's core value-loop is Production Ready, and its remaining gaps split cleanly into three buckets, none of which block frontend work:

1. **Small, clear fixes** (roadmap section, "not blocking") — cheap enough to interleave with frontend work whenever convenient, don't need dedicated backend-focused time.
2. **Deliberately deferred by architecture decision** — correctly *not* being worked on; starting any of these without a scope conversation would violate this project's own stated process (`KNOWN_LIMITATIONS.md`'s own framing).
3. **Needs a product/infrastructure decision first** (parallelism, persistence, spread detection) — there is nothing to *implement* yet; the next step for these is a decision conversation, not code, so backend engineering time wouldn't be well spent here regardless of what else is happening on the frontend.

Backend development shifting back to frontend completion does not leave real backend risk unaddressed — the small-fix bucket can absorb spare cycles opportunistically, and everything else is either intentionally paused or waiting on a decision, not on engineering capacity.
