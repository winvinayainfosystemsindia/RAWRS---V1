# Projection Architecture — eliminating the canonical output format

**Status:** P1 and P2 shipped (2026-08-03), P3a shipped (2026-08-10); P3b–P5
open. **Date:** 2026-08-02, progress updated 2026-08-10.

| Step | State | Commit |
|---|---|---|
| P1 `ContentStream` + identity | **shipped** | `e3a8386` |
| P2 semantics move into the model | **shipped** | `0419f7f` |
| P3a stream emits `PARAGRAPH` nodes (prose is semantic, not source lines) | **shipped** | pending |
| P3b MarkdownProjection renders from the stream | open | — |
| P4 DocxProjection; text parsing deleted | open | — |
| P5 `Projection` registry | open | — |

**Gate correction.** The byte-identical gates in §7 below were retired on
2026-08-03. P2 proved byte parity defends a renderer defect exactly as hard as
it defends correct behaviour — the pre-P2 renderer discarded 20 detected
headings for months with byte parity green. Projection correctness (PI-1…PI-6,
`ADR_PROJECTION_CORRECTNESS_2026-08-03.md`, ADR-020) is the gate for P3–P5:
`python -m src.benchmark --projection <pdf_dir>`.
**Target:** `Evidence → Findings → Decisions → Semantic Document → Projection Engine → Markdown / DOCX / future`.

## 0. The defect, in one table

`markdown_builder` serialises semantics into text; `docx_generator` deserialises them back. Both then implement the same semantics twice, and the round trip is lossy.

| Encoded by markdown_builder | Decoded by docx_generator | Already in the model as |
|---|---|---|
| `_apply_inline_format` → `**b**` | `_parse_inline_format` | `TextBlock.spans` |
| `_render_pipe_table` | `_add_pipe_table` | `Document.tables` |
| ~~`_footnote_label`~~ → `Footnote.label` (P2) | `_display_number` | `Footnote.number` |
| `_render_front_matter_blocks` | `_front_matter_kinds` (line-shape sniffing) | `Document.front_matter` |
| `![alt](path)` | `_build_image_alignment_map`, `_build_decorative_set` | `Image` |
| `PAGE_BREAK_MARKER` string | marker string match | `Page` |

Evidence it is already breaking: `_add_semantic_table` bypasses the pipe-table text and reads `Document.tables` through a `<!-- table-id -->` anchor, because text could not carry identity. Front matter does the same. The exceptions are the design trying to happen.

## 1. What the Semantic Document contains

| Layer | Holds | Status |
|---|---|---|
| Source facts | `pages`, `blocks` (bbox/font/spans/zone) | exists |
| Semantic objects | `headings`, `footnotes`, `tables`, `images`, `lists`, `callouts`, `front_matter` | exists |
| **Content stream** | ordered, identified sequence of semantic blocks per page | **exists (P1)** — derived, never stored |
| Decisions | `corrections`, `verification_findings` | exists |
| Provenance | `import_provider`, per-object `provenance`, `evidence_items`, `confidence` | exists |
| Identity | `SemanticObject.id` on every renderable object | **complete (P1)** — `TextBlock.block_id` closed the gap |

## 2. Belongs ONLY in the Semantic Document

| Concern | Today lives in | Why it must move |
|---|---|---|
| Reading order of mixed content | still reconstructed by lockstep cursor in the Markdown path; 0 drift measured corpus-wide | **open — P3** |
| Paragraph grouping | **moved (P2)** → `src/structure/paragraph_assembly.py`, Stage 5c | done |
| Suppression | **moved (P2)** → `absorbed_block_ids()`; the 4 text-keyed sets survive only on the OCR line-by-line path | mostly done |
| Inline emphasis | derived at render, re-parsed in DOCX | **open — P4** |
| Footnote numbering/labels | **moved (P2)** → `Footnote.label` | done |
| Object identity | **moved (P1/P2)** → `block_id`, `source_block_id`, `source_block_ids`; `<!-- table-id -->` remains as DOCX transport | **open — P4** |

## 3. Belongs ONLY in a projection

Format mechanics that carry no meaning: `#` vs `w:pStyle="Heading 1"`; `[^1]` vs `w:hyperlink`+`w:bookmark`; pipe syntax vs `w:tbl`; pt sizes, fonts, colours; `w:tblHeader`; image embedding and DPI; file/byte encoding.

Rule: **if removing it changes what the document *means*, it is semantic; if it changes only how it looks in one format, it is projection.**

## 4. Projection interface

```python
class Projection(Protocol):
    format_id: str                     # "markdown" | "docx"
    def render(self, document: Document, *, options: RenderOptions) -> ProjectionResult: ...
    def capabilities(self) -> ProjectionCapabilities: ...
```

| Element | Contract |
|---|---|
| `ProjectionResult` | `content: bytes\|str` **+** `anchors: dict[object_id, SourceRange]` |
| `capabilities()` | what the format can express (e.g. markdown cannot express merged cells) — declared, not discovered by failing |
| **no `parse()`** | projections are one-way; nothing reads a projection back |
| purity | `render(doc)` is deterministic and side-effect free apart from asset files |

`anchors` map a rendered range back to an `object_id`, never to a parse.

**Demoted 2026-08-03** (`WORKSPACE_ARCHITECTURE_2026-08-03.md` §7.4). This line previously read *"anchors is the
whole editing story"*, written when the assumption was that a reviewer edits inside a **rendered** surface. They do
not: editing happens on the semantic surface, built from `ContentNode`s that already carry `object_id`. Anchors buy
one thing — clicking inside a read-only Markdown/DOCX preview to reach the object behind it. **Optional, not
foundational.**

## 5. MarkdownProjection owns

Markdown syntax only: heading `#` depth, emphasis markers, pipe tables, `[^label]` syntax, image link syntax, page-break comment, endnote section heading, escaping. It owns **no** decisions about what is a heading, what is suppressed, what order things come in, or how notes are numbered.

## 6. DocxProjection owns

OOXML only: built-in heading styles, `w:tbl` + `w:tblHeader` + cell merges, footnote part/bookmark/hyperlink wiring, `docPr` alt-text attributes, page breaks, fonts/sizes/colours, image embedding. It **stops parsing text entirely** — `_parse_inline_format`, `_add_pipe_table`, `_build_image_alignment_map`, `_build_decorative_set`, `_front_matter_kinds` and the `PAGE_BREAK_MARKER` protocol all go.

## 7. Incremental path (benchmarks stay green)

The F0 differ profiles the **DOCX**, so DOCX bytes are the thing to hold still. Strangler, one commit per step:

| Step | Change | Gate |
|---|---|---|
| P1 ✅ | `ContentStream` model + builder, additive, no consumer | suite green (shipped `e3a8386`) |
| P2 ✅ | Paragraph grouping, note labelling and prose segmentation move into the model | projection correctness ok=True; KPIs held or improved (shipped `0419f7f`) |
| P3 | MarkdownProjection renders from the stream | **projection correctness ok=True** + KPIs unchanged |
| P4 | DocxProjection renders from the stream; text parsing deleted | projection correctness for DOCX + F0 differ: all 9 KPIs unchanged |
| P5 | `Projection` registry; pipeline loops projections, names no format | suite green |

Each step is revertible; the decision-identity harness (dump artefact, `git stash`, diff) already used for L3.1/L2.2 is the tool.

## 8. Modules/concepts that disappear

| Goes | Reason |
|---|---|
| `docx_generator._parse_inline_format`, `_add_pipe_table`, `_build_image_alignment_map`, `_build_decorative_set`, `_front_matter_kinds` | decoders of a channel that no longer carries semantics |
| `PAGE_BREAK_MARKER` as an inter-module protocol | pages are model objects |
| `<!-- table-id -->` as transport | identity comes from the stream |
| `markdown_builder`'s `raw_text_lines`/`page_blocks` lockstep cursor (P3); ~~`_table_suppressed_blocks`~~ **already gone (P2)**; `_front_matter_source_texts`/`_caption_source_texts` survive on the OCR path only | order and suppression come from the stream |
| "markdown is the source of truth" in `docs/ARCHITECTURE.md` | false, and the premise this replaces |

## 9. New abstractions

| Abstraction | Purpose |
|---|---|
| `ContentBlock` (+ subtypes) | one identified, ordered semantic unit |
| `ContentStream` | the document's ordered content — the single reading-order authority |
| `Projection` protocol + registry | formats become plug-ins; orchestration names none |
| `ProjectionResult(content, anchors)` | output plus id→range map |
| `ProjectionCapabilities` | declared expressiveness limits |

## 10. Editing workflow this enables

| Step | Mechanism |
|---|---|
| Reviewer edits in a surface | anchors map the edit to an `object_id` |
| Edit becomes a decision | `CorrectionRecord`, provider `manual_reviewer` |
| Applied via the rail | `SemanticVerifier.apply()`; undo via `revert()` |
| Semantic Document updates | `document.version` bumps |
| Every projection re-renders | registry loop — Markdown, DOCX and any future format together |
| Validation/benchmarks/history follow | all already read the model, not the output |
| AI assistance | proposes `Finding`s like any other producer; no format knowledge |

Nothing in that chain mentions a format. That is the test of whether the design is right.
