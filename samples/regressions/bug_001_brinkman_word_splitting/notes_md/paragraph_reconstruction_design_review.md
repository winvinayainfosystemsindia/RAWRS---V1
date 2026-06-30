# Paragraph Reconstruction — Design Review

Design only. No code written, no source files modified. Builds on `notes_md/root_cause_audit.md`.

## Shared constraint across all three options

`markdown_builder.py::_render_page_body()` currently matches headings and footnotes against `page.cleaned_text.splitlines()` by **exact line-text equality**. Any paragraph-joining design must either (a) run that matching *before* joining and only join the surviving "plain body" runs between heading/footnote events, or (b) re-point matching at a coarser unit while preserving line-level provenance. All three options below choose (a) — it's a strictly smaller change to existing, working heading/footnote logic than redefining what they match against.

Also true for all three options: since Bug 2 is pervasive (every benchmark PDF's body text is currently one-line-per-paragraph), fixing it **will** change every benchmark PDF's `generated_md`, by design — that's the point, not a regression by itself. The real risk surface is whether the new paragraph boundaries are *correct*, not whether output changes at all.

---

## Option A — Lexical line-joining inside `markdown_builder.py`

**Design:** A small helper, local to `markdown_builder.py`, that buffers consecutive plain-body lines and decides "join vs. break" using only the text itself — no bbox, no new model fields. Heuristic: keep buffering unless the previous line ends in terminal sentence punctuation (`.?!:;` optionally followed by a closing quote); repair line-end hyphens (`word-\nword` → `wordword`) at join points; flush the buffer to one paragraph block whenever a heading/footnote/suppressed line interrupts the run, or the punctuation rule fires.

**Pros**
- Smallest diff — one file, one new function, zero new model fields, zero new data sources.
- Zero dependency on `Document.blocks`/bbox data, so no risk of disturbing anything Phase H/K already relies on.
- Already happens to "fix" the literal Brinkman sentence, because none of Bug 1's word-fragments (`questionnaires,` / `semi-structured` / `interviews,` / `while` / `their`) end in terminal punctuation, so the default "keep joining" behavior glues them back together by coincidence.

**Cons**
- That fix is **coincidental, not structural** — Bug 1 (PyMuPDF mis-segmenting a justified line) can just as easily fragment a line at a position that *does* end in a comma+capitalized-next-word, or split a quoted sentence, and the lexical heuristic would then do the wrong thing. This is exactly the "naive global line joining" Requirement 5 warns against — it's narrower than joining *everything*, but it's still a guess made with no positional grounding.
- False positives are a real risk on other benchmark PDFs: abbreviations (`Dr.`, `U.S.`, `Fig. 3`), numbered list items ending in a colon, or any line that legitimately ends a sentence at a normal line-wrap point will be silently merged or split wrong, and there's no signal available to catch it (string heuristics can't distinguish "end of paragraph" from "end of sentence that just happens to be at a line-wrap").
- Builds nothing reusable for Requirement 3 — multi-column detection, callout/table/equation detection all fundamentally need geometry, which this option deliberately avoids touching.

**Regression risk:** Medium-high, *despite* being the smallest diff — the risk is concentrated in correctness (silently wrong paragraph boundaries on other PDFs), not breakage (it won't crash, it'll just sometimes misjoin).

**Future compatibility:** Poor. Provides no foothold for any Requirement 3 item.

**Estimated complexity:** Low — roughly a day, one file touched.

---

## Option B — Geometry-grounded paragraph grouping on top of `Document.blocks`

**Design:** `TextBlock` is deliberately line-granularity by existing design intent (its own docstring: "deliberately matching the granularity... later phases need... per-line, not per-paragraph"), so this option does not redefine it — it adds one new field and one new pure function that *consumes* it, leaving `TextBlock`/Phase H exactly as-is for every existing caller (Phase K footnote detection keeps working unmodified).

1. **One additive field on `TextBlock`:** `source_block_index: int` — the index of the PyMuPDF `page.get_text("dict")["blocks"]` entry a line came from. This is already iterated over in `structure_detector.py::_extract_page_blocks()` (`for block in page_dict.get("blocks", [])`) and simply isn't retained today — free to capture, zero new extraction cost.
2. **One new pure function** (e.g. `src/structure/paragraph_grouper.py::group_into_paragraphs(blocks: List[TextBlock]) -> List[Paragraph]`), where `Paragraph` is a small new model (`page_number`, `text`, `bbox`, `order`, back-reference to the contributing `TextBlock.order` values for provenance). It:
   - **Fixes Bug 1** first: merges same-page lines sharing (near-)identical `bbox.y0/y1` into one logical line, walking left-to-right, gated by an x-continuity check (next fragment's `x0` must be ≥ previous fragment's `x1`, no overlap) and a maximum-gap bound — guards against merging two genuinely different columns that happen to share a y-coordinate, which is the multi-column false-merge risk flagged in the audit.
   - **Fixes Bug 2** second: joins consecutive same-`source_block_index` lines into one paragraph (real space at the join, hyphen repair at line-wraps); a large vertical gap between consecutive lines *within* the same PyMuPDF block (reusing `validator.py`'s already-tested, self-calibrating `1.5× median line height` convention — `_READING_ORDER_JUMP_RATIO`) still forces a paragraph break, as a safety net for the cases where PyMuPDF's own block segmentation lumps two real paragraphs together.
3. **`markdown_builder.py::_render_page_body()`** keeps its existing per-line scan to identify heading lines and footnote substitutions (unchanged), but instead of appending each surviving body line as its own block immediately, it now resolves the corresponding `Paragraph`(s) for each run of consecutive plain-body lines and appends the joined paragraph text instead.

**Pros**
- Fixes both confirmed bugs with one mechanism, grounded in already-extracted, already-tested data (`Document.blocks`, Phase H is "VERIFIED COMPLETE" per `PHASE_STATUS.md`) rather than guessing from punctuation.
- Directly extensible toward every Requirement-3 item without another foundational change: `source_block_index` + bbox is exactly the prerequisite signal column-clustering, callout-block detection (a stylistically distinct PyMuPDF block), table detection (regular bbox-grid alignment), and equation detection (unusual font/spacing runs) would all need anyway — this captures it once instead of each future feature re-deriving it.
- `AltTextStatus`'s existing "nearby TextBlocks" mechanism (`phase1_pipeline.py::_nearby_block_texts`) is untouched and could trivially be upgraded to "nearby paragraphs" later with strictly better context, supporting the already-agreed AI alt-text direction.
- Independently unit-testable as a pure function against bbox fixtures, matching this codebase's existing testing style.
- Reuses an established, already-validated threshold convention (`1.5×` median line height) instead of inventing a new heuristic from scratch.

**Cons**
- More surface area than Option A: one new field, one new function/module, and a change to how `markdown_builder.py` consumes body lines (3 files instead of 1).
- `source_block_index` is a new signal not yet validated against the full benchmark corpus — PyMuPDF's own block segmentation won't always equal "one real paragraph" (sometimes splits one paragraph into two blocks, occasionally merges two); the vertical-gap fallback narrows this but doesn't eliminate it, so this still carries *some* heuristic risk — just narrower and positionally-grounded rather than purely lexical.
- Requires reconciling heading/footnote exact-line matching against a coarser output, which is a real (if contained) change to `_render_page_body()`'s control flow.

**Regression risk:** Medium. Same "every benchmark PDF's markdown changes" blast radius as any Bug-2 fix, but the geometric signal is materially more trustworthy than lexical heuristics, lowering the odds of new *silent* mis-joins. Needs validation against all 4 benchmark PDFs plus this regression case before trusting it, same as any of these options.

**Future compatibility:** Strong. This is genuinely the first real building block toward column/callout/table/equation work, without committing to building any of them now.

**Estimated complexity:** Medium — a few hundred lines across 2-3 files, new unit tests for the grouping function, one additive model field, no new external dependencies.

---

## Option C — Dedicated Layout Analysis stage with a `LayoutZone` model

**Design:** Promotes "what kind of content occupies this region, and how its lines group" into its own pipeline stage, rather than a function bolted onto `structure_detector.py` or `markdown_builder.py`.

1. New stage ("Phase L — Layout Analysis") in `phase1_pipeline.py`, between Detect Structure and Detect Headings, consuming `Document.blocks` unchanged (so Phase K footnote detection, which already reads `Document.blocks`, needs zero changes).
2. New `Document.layout_zones: List[LayoutZone]` model: `zone_type` (enum — `BODY_TEXT`, `HEADING`, `CALLOUT`, `TABLE`, `EQUATION`, `CAPTION`, `UNKNOWN`; only `BODY_TEXT`/`UNKNOWN` actually populated in Phase 1, the rest reserved-but-unset — mirroring this codebase's own existing pattern of naming a future slot before building it, e.g. `AltTextStatus.HUMAN_REVIEWED`, `OCR_003`), `page_number`, `bbox`, `column_index` (defaults to 0; a real, if minimal, first step on multi-column), `reconstructed_text` (same Bug-1/Bug-2 fix as Option B, just performed here), and back-references to source `TextBlock.order` values for provenance.
3. `markdown_builder.py` renders from `layout_zones` (in order) instead of raw lines; same heading/footnote reconciliation approach as Option B, formalized as a documented contract of the new model.
4. Column/callout/table/equation work becomes "write a new classifier that sets `zone_type`/`column_index` on existing zones" in a later phase — not another rewrite of text rendering.

**Pros**
- Cleanest separation of concerns; every Requirement-3 item gets an explicit, named, reserved home in the model now, not just "the data happens to be reusable."
- Matches this project's own established habit of modeling a future slot ahead of populating it.
- Fully isolated and auditable (`tests/test_layout_zones.py` alongside the new stage), independently reviewable.
- `Document.blocks` stays completely untouched — strongest backward-compatibility story of the three.

**Cons**
- Largest scope by far: new model, new pipeline stage, updates to `phase1_pipeline.py`'s stage list/docstring, and (per this project's own documentation discipline observed throughout this engagement) doc updates to `ARCHITECTURE.md`/`ARCHITECTURE_CURRENT.md`/`PHASE_STATUS.md`.
- `RAWRS_PROJECT_CONTEXT.md` lists "Do not redesign architecture" as a standing development rule. A new pipeline stage is additive/non-breaking, not a redesign of anything existing, but it's the option that sits closest to that line — a stakeholder-expectations risk as much as a technical one.
- Largest amount of new, unvalidated code before the benchmark corpus can confirm it's trustworthy.
- Solves Requirement 3 by reserving space for features that aren't scheduled yet — real value if/when they land, dead weight (four unused enum members, an unused `column_index` field) until then.

**Regression risk:** Medium-high in the short term (more new surface area = more to get wrong before re-validation), but the lowest *compounding* risk of the three — future column/callout/table/equation work plugs in here without triggering another markdown-rendering rewrite each time.

**Future compatibility:** Strongest of the three, by design.

**Estimated complexity:** High — new model(s), new pipeline stage, the same markdown-consumption change as Option B plus the zone abstraction around it, full benchmark re-validation, and a documentation pass.

---

## Recommended choice: Option B

It fixes both confirmed bugs with one geometry-grounded mechanism built on data this project has already extracted and already tested (Phase H), which directly addresses Requirement 5 (avoids the lexical-guessing problem Option A has) without committing to a new pipeline stage / model family that Requirement 3's features aren't actually scheduled to need yet (Option C). `source_block_index` + bbox is the same prerequisite signal a future Option-C-style layout stage would need anyway — choosing B now doesn't foreclose growing into something like C later if/when column, callout, table, or equation work actually gets scheduled; it just doesn't pay that cost speculatively today. Recommend re-evaluating toward Option C only once at least one of the Requirement-3 future capabilities has a concrete commitment, not on spec.
