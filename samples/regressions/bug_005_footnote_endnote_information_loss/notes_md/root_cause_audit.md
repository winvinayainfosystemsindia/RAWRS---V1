# bug_005_footnote_endnote_information_loss — Root Cause Audit & Fix Record

Implements `feature_005_span_level_text_model` exactly as approved in the design review (`docs/DECISIONS_LOG.md` Part 8): an additive `Span` model embedded in `TextBlock` (Option A), populated during Structure Detection, consumed optionally by `footnote_detector.py`. No architecture redesign; every existing consumer of `Document.blocks`/`TextBlock` is unaffected (see Phase 2 verification below).

## Root Cause (confirmed previously, re-verified here against this exact PDF)

`footnote_detector.py`'s only marker-detection signal was a literal Unicode superscript-digit glyph (U+00B9 etc.) glued onto a word. This PDF's 3 footnote/endnote markers are encoded the far more common real-world way: a plain digit at a smaller font size, with PyMuPDF's own `TEXT_FONT_SUPERSCRIPT` flag bit set, on a raised baseline. That signal is extracted correctly by PyMuPDF but was discarded the moment `structure_detector.py` collapsed every span on a line into `TextBlock`'s single `(font_size, is_bold)` scalar pair — span-level information loss, not a defect in the detector's own logic.

Confirmed via direct span dump on this PDF's marker "1" (page 2):
```
text='1'           size=7.04   flags=5 (SUPERSCRIPT|SERIFED)   origin_y=329.39
text='In-service'  size=9.96   flags=4                          origin_y=333.81
```

## Fix

**Phase 1** — `src/models/span.py` (new): `Span(text, font_name, font_size, font_flags, baseline_y, bbox)`, a faithful, undecoded record of one PyMuPDF span. `TextBlock.spans: List[Span] = Field(default_factory=list)` (additive, `src/models/text_block.py`). Populated in `structure_detector.py::_extract_page_blocks()`'s existing per-line loop (`_extract_spans()`) — no new PDF pass, no change to `font_size`/`is_bold`'s existing computation.

**Phase 2** — verified zero behavior change: full fast test suite (567+ tests) and the full suite including real Docling/Surya engine tests (414 tests) both pass unchanged after Phase 1 alone, before any consumer was touched.

**Phase 3/4** — `footnote_detector.py::_find_span_marker_candidates()` (new): a second, additive marker-detection signal. Fires only when ALL of: span text is 1-3 plain digits; the span carries the `TEXT_FONT_SUPERSCRIPT` flag bit; its size is strictly smaller than the largest span on the same line; it is glued onto the immediately preceding span's text with no space between them. Computes and records `anchor_offset` (the marker's exact character position within its line) via `_span_marker_offset()`, with a validating safety check that fails closed (returns no candidate) rather than risk an incorrect position.

**Phase 5** — endnote detection required *no separate code*. `_find_marker_candidates()` is shared by both the footnote and endnote code paths in `detect_footnotes()`; fixing it once fixes both. Confirmed end-to-end against this PDF (all 3 markers route through the endnote path, since this PDF collects its notes under a "Notes" section heading).

## A second, more serious bug found during verification — not anticipated by the design review

Detection alone was not sufficient. `markdown_builder.py`'s marker-substitution logic did a positionally-blind `line.replace(note.marker, f"[^{label}]", 1)` — safe for a rare literal Unicode glyph (vanishingly unlikely to collide with anything else in the text), but actively **corrupting unrelated text** once markers became plain digits: first-pass output showed `"(NCF, 2005: 13).1 In-service"` mis-rendered as `"(NCF, 2005: [^p16-1]3)."` (the replace matched the wrong "1", inside "13", not the actual marker), and `"...Government of India, 2010: 35–37"` mis-rendered as `"...20[^p16-1]0: 35–37"` — the digit '1' from a completely different page's marker corrupting an unrelated year, three paragraphs away.

**Fix:** added `Footnote.anchor_offset: Optional[int]` (additive field, `src/models/footnote.py`), populated by both detection paths in `footnote_detector.py`. Rewrote all three substitution call sites in `markdown_builder.py` into one shared `_substitute_markers()`:
- Groups notes by their own `anchor_text` (a paragraph can combine markers from several joined source lines).
- **Skips a note entirely for a given call if its anchor line isn't present in that text at all** — critical, since `flush_run()` passes the *same* full note list to *every* paragraph produced from one run, and a note belongs to exactly one of them, not all of them.
- Applies `anchor_offset` for exact, position-based replacement when valid.
- Falls back to a blind replace only when bounded to *that one line's own text* (never the whole paragraph) — bounding the residual collision risk to within a single source line rather than across however much text a joined paragraph spans.
- Processes all resolved replacements in descending position order so one replacement's length change never invalidates another still-pending offset.

Verified by direct re-inspection of the regenerated Markdown (`generated_md/`, this folder) after the fix: all 3 markers land exactly on their real source position, and the previously-corrupted unrelated numbers ("2010", "Schweisfurth (2013)", "Alexander, 2008", "23 believe") are untouched.

## Verification against this regression case

| Marker | Page | Real anchor text | Detected? | Correctly placed in Markdown? |
|---|---|---|---|---|
| 1 | 2 | "...interests' (NCF, 2005: 13).1 In-service..." | Yes (span signal) | Yes — `13).[^p16-1] In-service` |
| 2 | 3 | "...teacher education programmes.2 As early as 1978..." | Yes (span signal) | Yes — `programmes.[^p16-2] As early` |
| 3 | 7 | "...Farida (B4-L)3 explains:" | Yes (span signal) | Yes — `(B4-L)[^p16-3] explains` |

All 3 bodies (page 16, under the "Notes" section) correctly linked by number, rendered as a dedicated `## Endnotes` section.

## "Brinkman Case C"

Marker 3 ("Farida (B4-L)3") is structurally distinct from markers 1 and 2: it is glued directly after a closing parenthesis (`)3`) rather than after sentence-ending punctuation plus a period (`.1`, `.2`). Tracked as its own regression case specifically because the "glued onto the immediately preceding span" check needed to be confirmed against more than one punctuation context, not just the more common "end of sentence" shape.

## No-false-positive verification

The same span-based signal was checked against every other superscript-flagged or small-font span in this PDF's structure data (table cell values, page-number running headers, the statistical notation `r = .66, p < .001`) — none satisfy all four required conditions simultaneously (most fail the "glued, no space before" check; table cell digits are not superscript-flagged at all). See `tests/test_footnote_detector.py::TestBug005SpanSuperscriptDetection` for the synthetic no-false-positive test cases this finding is also covered by.
