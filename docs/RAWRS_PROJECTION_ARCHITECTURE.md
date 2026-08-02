# Projection Architecture — eliminating the canonical output format

**Status:** design, pre-implementation. **Date:** 2026-08-02.
**Target:** `Evidence → Findings → Decisions → Semantic Document → Projection Engine → Markdown / DOCX / future`.

## 0. The defect, in one table

`markdown_builder` serialises semantics into text; `docx_generator` deserialises them back. Both then implement the same semantics twice, and the round trip is lossy.

| Encoded by markdown_builder | Decoded by docx_generator | Already in the model as |
|---|---|---|
| `_apply_inline_format` → `**b**` | `_parse_inline_format` | `TextBlock.spans` |
| `_render_pipe_table` | `_add_pipe_table` | `Document.tables` |
| `_footnote_label` | `_display_number` | `Footnote.number` |
| `_render_front_matter_blocks` | `_front_matter_kinds` (line-shape sniffing) | `Document.front_matter` |
| `![alt](path)` | `_build_image_alignment_map`, `_build_decorative_set` | `Image` |
| `PAGE_BREAK_MARKER` string | marker string match | `Page` |

Evidence it is already breaking: `_add_semantic_table` bypasses the pipe-table text and reads `Document.tables` through a `<!-- table-id -->` anchor, because text could not carry identity. Front matter does the same. The exceptions are the design trying to happen.

## 1. What the Semantic Document contains

| Layer | Holds | Status |
|---|---|---|
| Source facts | `pages`, `blocks` (bbox/font/spans/zone) | exists |
| Semantic objects | `headings`, `footnotes`, `tables`, `images`, `lists`, `callouts`, `front_matter` | exists |
| **Content stream** | ordered, identified sequence of semantic blocks per page | **missing — the gap** |
| Decisions | `corrections`, `verification_findings` | exists |
| Provenance | `import_provider`, per-object `provenance`, `evidence_items`, `confidence` | exists |
| Identity | `SemanticObject.id` on every renderable object | partial (`TextBlock` has none) |

## 2. Belongs ONLY in the Semantic Document

| Concern | Today lives in | Why it must move |
|---|---|---|
| Reading order of mixed content | reconstructed twice, by lockstep text-cursor matching | it is a semantic decision, currently made inside a projection |
| Paragraph grouping | `group_into_paragraphs` called at render time | ditto — a detector running inside a renderer |
| Suppression | `TextBlock.suppressed` ✔ plus 4 text-keyed sets in the renderer | text keys collide on duplicate lines |
| Inline emphasis | derived at render, re-parsed in DOCX | round-trips through `**` |
| Footnote numbering/labels | computed independently in both | two numbering authorities |
| Object identity | `<!-- table-id -->` only | anchors are a transport hack |

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

`anchors` is the whole editing story: an edit in a surface maps to an `object_id`, never to a parse.

## 5. MarkdownProjection owns

Markdown syntax only: heading `#` depth, emphasis markers, pipe tables, `[^label]` syntax, image link syntax, page-break comment, endnote section heading, escaping. It owns **no** decisions about what is a heading, what is suppressed, what order things come in, or how notes are numbered.

## 6. DocxProjection owns

OOXML only: built-in heading styles, `w:tbl` + `w:tblHeader` + cell merges, footnote part/bookmark/hyperlink wiring, `docPr` alt-text attributes, page breaks, fonts/sizes/colours, image embedding. It **stops parsing text entirely** — `_parse_inline_format`, `_add_pipe_table`, `_build_image_alignment_map`, `_build_decorative_set`, `_front_matter_kinds` and the `PAGE_BREAK_MARKER` protocol all go.

## 7. Incremental path (benchmarks stay green)

The F0 differ profiles the **DOCX**, so DOCX bytes are the thing to hold still. Strangler, one commit per step:

| Step | Change | Gate |
|---|---|---|
| P1 | `ContentStream` model + builder, additive, no consumer | suite green; output byte-identical (no consumer) |
| P2 | Paragraph grouping + note numbering move to pipeline, write into the stream | markdown byte-identical (dump/diff harness) |
| P3 | MarkdownProjection renders from the stream | markdown byte-identical corpus-wide |
| P4 | DocxProjection renders from the stream; text parsing deleted | F0 differ: all 9 KPIs unchanged |
| P5 | `Projection` registry; pipeline loops projections, names no format | suite green |

Each step is revertible; the decision-identity harness (dump artefact, `git stash`, diff) already used for L3.1/L2.2 is the tool.

## 8. Modules/concepts that disappear

| Goes | Reason |
|---|---|
| `docx_generator._parse_inline_format`, `_add_pipe_table`, `_build_image_alignment_map`, `_build_decorative_set`, `_front_matter_kinds` | decoders of a channel that no longer carries semantics |
| `PAGE_BREAK_MARKER` as an inter-module protocol | pages are model objects |
| `<!-- table-id -->` as transport | identity comes from the stream |
| `markdown_builder`'s `raw_text_lines`/`page_blocks` lockstep cursor, `_table_suppressed_blocks`, `_front_matter_source_texts`, `_caption_source_texts` | order and suppression come from the stream |
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
