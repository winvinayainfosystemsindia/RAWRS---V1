"""Tests for src/markdown/markdown_builder.py."""

from pathlib import Path
from typing import List, Optional, Tuple

from src.footnotes.footnote_detector import detect_footnotes
from src.headings.heading_detector import detect_headings
from src.markdown.markdown_builder import build_markdown
from src.models.contracts import (
    BoundingBox,
    Document,
    Figure,
    Footnote,
    Heading,
    HeadingLevel,
    Image,
    Metadata,
    NoteType,
    Page,
    TextBlock,
)
from src.ocr.extractor import extract_text
from src.parser.pdf_parser import parse_pdf
from src.structure.structure_detector import detect_structure


def _build_document(pages_text: List[str]) -> Document:
    """Build a Document with text pre-populated and headings detected.

    Mirrors the real pipeline: parser creates pages, OCR (stubbed here
    via direct cleaned_text assignment) fills in text, heading_detector
    populates document.headings before markdown_builder ever runs.
    """
    pages = [Page(page_number=i + 1, cleaned_text=text) for i, text in enumerate(pages_text)]
    document = Document(
        source_pdf_path="dummy.pdf",
        metadata=Metadata(filename="dummy.pdf"),
        pages=pages,
    )
    return detect_headings(document)


def _add_image(
    document: Document,
    page_number: int,
    *,
    file_path: str = "outputs/images/dummy/page1_img1.png",
    label: Optional[str] = None,
    caption: Optional[str] = None,
    alt_text: Optional[str] = None,
    extraction_failed: bool = False,
) -> Image:
    figure = (
        Figure(label=label, caption=caption, alt_text=alt_text)
        if (label or caption or alt_text)
        else None
    )
    image = Image(
        image_id=f"img-{len(document.images) + 1}",
        page_number=page_number,
        file_path=file_path,
        width=100,
        height=100,
        figure=figure,
        extraction_failed=extraction_failed,
    )
    document.images.append(image)
    return image


class TestHeadingGeneration:
    def test_h1_through_h5_render_with_correct_atx_depth(self) -> None:
        document = _build_document(
            ["Doc Title\nIntroduction\n3.1 Overview\n3.1.1 Objectives\n3.1.1.1 Detail"]
        )
        markdown = build_markdown(document)

        assert "# Doc Title" in markdown
        assert "## Introduction" in markdown
        assert "### 3.1 Overview" in markdown
        assert "#### 3.1.1 Objectives" in markdown
        assert "##### 3.1.1.1 Detail" in markdown

    def test_heading_levels_use_correct_hash_count_not_just_substrings(self) -> None:
        document = _build_document(["Doc Title\nIntroduction"])
        markdown = build_markdown(document)

        lines = markdown.splitlines()
        assert "# Doc Title" in lines
        assert "## Introduction" in lines
        # the H1 line must not itself be a longer heading in disguise
        assert "## Doc Title" not in lines


class TestPageMarkerGeneration:
    def test_h6_page_marker_uses_required_format(self) -> None:
        document = _build_document(["some text"])
        markdown = build_markdown(document)
        assert "###### 1" in markdown.splitlines()

    def test_exactly_one_marker_per_page(self) -> None:
        document = _build_document(["page one", "page two", "page three"])
        markdown = build_markdown(document)

        lines = markdown.splitlines()
        assert lines.count("###### 1") == 1
        assert lines.count("###### 2") == 1
        assert lines.count("###### 3") == 1

    def test_marker_is_synthesized_when_headings_not_pre_populated(self) -> None:
        # build_markdown must still produce valid output even if
        # heading_detector was never run (document.headings == []).
        page = Page(page_number=1, cleaned_text="some text")
        document = Document(
            source_pdf_path="dummy.pdf", metadata=Metadata(filename="dummy.pdf"), pages=[page]
        )
        markdown = build_markdown(document)
        assert "###### 1" in markdown.splitlines()


class TestReadingOrderPreservation:
    def test_headings_and_body_text_stay_in_source_order(self) -> None:
        document = _build_document(
            ["Doc Title\nsome intro text\nIntroduction\nmore body text\n3.1 Overview\nfinal text"]
        )
        markdown = build_markdown(document)

        positions = [
            markdown.index("# Doc Title"),
            markdown.index("some intro text"),
            markdown.index("## Introduction"),
            markdown.index("more body text"),
            markdown.index("### 3.1 Overview"),
            markdown.index("final text"),
        ]
        assert positions == sorted(positions)

    def test_multi_page_content_stays_in_page_order(self) -> None:
        document = _build_document(["Doc Title\nIntroduction", "3.1 Overview\nbody"])
        markdown = build_markdown(document)

        positions = [
            markdown.index("###### 1"),
            markdown.index("# Doc Title"),
            markdown.index("## Introduction"),
            markdown.index("###### 2"),
            markdown.index("### 3.1 Overview"),
        ]
        assert positions == sorted(positions)

    def test_pages_out_of_input_order_are_still_rendered_in_page_number_order(self) -> None:
        page_2 = Page(page_number=2, cleaned_text="second")
        page_1 = Page(page_number=1, cleaned_text="first")
        document = Document(
            source_pdf_path="dummy.pdf",
            metadata=Metadata(filename="dummy.pdf"),
            pages=[page_2, page_1],  # deliberately out of order
        )
        markdown = build_markdown(document)

        assert markdown.index("###### 1") < markdown.index("###### 2")


class TestImageReferenceGeneration:
    def test_image_with_figure_label_and_caption(self) -> None:
        document = _build_document(["Doc Title"])
        _add_image(
            document,
            page_number=1,
            file_path="outputs/images/dummy/page1_img1.png",
            label="Figure 1",
            caption="A diagram of the process.",
            alt_text="Figure 1: A diagram of the process.: description pending human review",
        )
        markdown = build_markdown(document)

        assert (
            "![Figure 1: A diagram of the process.: description pending human review]"
            "(outputs/images/dummy/page1_img1.png)" in markdown
        )
        assert "*A diagram of the process.*" in markdown

    def test_alt_text_comes_from_figure_alt_text_not_label(self) -> None:
        # Phase F.4: markdown's alt slot must read Figure.alt_text, not
        # Figure.label - a figure can have a label with no alt_text set
        # (e.g. a Figure constructed before Phase F.3 ran) and that must
        # render an empty alt attribute, never silently fall back to the
        # label.
        document = _build_document(["Doc Title"])
        _add_image(
            document,
            page_number=1,
            file_path="outputs/images/dummy/page1_img1.png",
            label="Figure 1",
        )
        markdown = build_markdown(document)

        assert "![](outputs/images/dummy/page1_img1.png)" in markdown
        assert "![Figure 1]" not in markdown

    def test_image_without_figure_uses_empty_alt_text(self) -> None:
        document = _build_document(["Doc Title"])
        _add_image(document, page_number=1, file_path="outputs/images/dummy/page1_img1.jpg")
        markdown = build_markdown(document)

        assert "![](outputs/images/dummy/page1_img1.jpg)" in markdown

    def test_failed_extraction_is_not_referenced(self) -> None:
        document = _build_document(["Doc Title"])
        _add_image(
            document,
            page_number=1,
            file_path="outputs/images/dummy/broken.png",
            extraction_failed=True,
        )
        markdown = build_markdown(document)

        assert "broken.png" not in markdown

    def test_images_are_grouped_under_their_own_page(self) -> None:
        document = _build_document(["page one text", "page two text"])
        _add_image(document, page_number=2, file_path="outputs/images/dummy/p2.png")
        markdown = build_markdown(document)

        page_1_section, page_2_section = markdown.split("###### 2")
        assert "p2.png" not in page_1_section
        assert "p2.png" in page_2_section


class TestMultiPageDocuments:
    def test_three_pages_produce_three_page_breaks(self) -> None:
        document = _build_document(["one", "two", "three"])
        markdown = build_markdown(document)
        assert markdown.count("<!-- pagebreak -->") == 3

    def test_page_breaks_follow_each_pages_content(self) -> None:
        document = _build_document(["Doc Title", "3.1 Overview"])
        markdown = build_markdown(document)

        first_break = markdown.index("<!-- pagebreak -->")
        assert markdown.index("# Doc Title") < first_break
        assert first_break < markdown.index("### 3.1 Overview")


class TestEmptyDocuments:
    def test_document_with_no_pages_returns_empty_string(self) -> None:
        document = Document(source_pdf_path="dummy.pdf", metadata=Metadata(filename="dummy.pdf"))
        assert build_markdown(document) == ""

    def test_page_with_no_text_and_no_images_still_renders_marker_and_break(self) -> None:
        document = _build_document([""])
        markdown = build_markdown(document)

        assert markdown.startswith("###### 1")
        assert "<!-- pagebreak -->" in markdown

    def test_output_has_no_excessive_blank_lines(self) -> None:
        document = _build_document(["Doc Title\nIntroduction", ""])
        markdown = build_markdown(document)
        assert "\n\n\n" not in markdown


def _footnote(
    *,
    note_type: NoteType = NoteType.FOOTNOTE,
    number: int = 1,
    marker: str = "¹",
    anchor_page_number: int = 1,
    anchor_text: str,
    anchor_offset: Optional[int] = None,
    body: str = "A note body.",
    body_page_number: Optional[int] = None,
    body_source_text: Optional[str] = None,
) -> Footnote:
    return Footnote(
        note_type=note_type,
        number=number,
        marker=marker,
        anchor_page_number=anchor_page_number,
        anchor_text=anchor_text,
        anchor_offset=anchor_offset,
        body=body,
        body_page_number=body_page_number if body_page_number is not None else anchor_page_number,
        body_source_text=body_source_text or f"{marker} {body}",
    )


class TestFootnoteRendering:
    # Every fixture below opens with a "Doc Title" line before the
    # footnoted text, so the footnoted line is ordinary body text, not
    # accidentally promoted to H1 by heading_detector's positional-H1-
    # slot rule (the first non-blank line of the whole document) - a
    # footnote marker inside a document's own title is not a realistic
    # scenario this phase needs to handle.

    def test_inline_marker_is_substituted_with_footnote_syntax(self) -> None:
        document = _build_document(["Doc Title\nA claim with a marker¹."])
        document.footnotes = [_footnote(anchor_text="A claim with a marker¹.")]

        markdown = build_markdown(document)

        assert "A claim with a marker[^p1-1]." in markdown
        assert "¹" not in markdown

    def test_footnote_definition_uses_markdown_footnote_syntax(self) -> None:
        document = _build_document(["Doc Title\nA claim with a marker¹."])
        document.footnotes = [
            _footnote(anchor_text="A claim with a marker¹.", body="Improvement measured using standardized test scores.")
        ]

        markdown = build_markdown(document)

        assert "[^p1-1]: Improvement measured using standardized test scores." in markdown

    def test_footnote_definition_appears_after_anchor_page_body(self) -> None:
        document = _build_document(["Doc Title\nA claim with a marker¹.\nMore body text after."])
        document.footnotes = [_footnote(anchor_text="A claim with a marker¹.")]

        markdown = build_markdown(document)

        assert markdown.index("More body text after.") < markdown.index("[^p1-1]:")

    def test_raw_body_source_line_is_not_duplicated(self) -> None:
        # The original page-bottom line ("¹ A note body.") must not
        # ALSO appear verbatim as a plain body paragraph once a proper
        # footnote definition has replaced it.
        document = _build_document(
            ["Doc Title\nA claim with a marker¹.\n¹ A note body."]
        )
        document.footnotes = [_footnote(anchor_text="A claim with a marker¹.", body="A note body.")]

        markdown = build_markdown(document)

        assert markdown.count("A note body.") == 1

    def test_multiple_footnotes_on_one_page_all_render(self) -> None:
        document = _build_document(["Doc Title\nFirst claim¹.\nSecond claim²."])
        document.footnotes = [
            _footnote(number=1, marker="¹", anchor_text="First claim¹.", body="First note."),
            _footnote(number=2, marker="²", anchor_text="Second claim².", body="Second note."),
        ]

        markdown = build_markdown(document)

        assert "First claim[^p1-1]." in markdown
        assert "Second claim[^p1-2]." in markdown

    # bug_005 / feature_005: a plain-digit marker (the span-based
    # detection signal) is a common substring that can collide with an
    # unrelated number elsewhere in the text - unlike a literal Unicode
    # superscript glyph. anchor_offset exists specifically to keep the
    # correct occurrence from being replaced wrongly, confirmed by a
    # real regression: see samples/regressions/
    # bug_005_footnote_endnote_information_loss/notes_md/root_cause_audit.md.

    def test_plain_digit_marker_with_offset_replaces_correct_occurrence(self) -> None:
        # "1" appears twice in this line: once inside "2005" (must be
        # left alone) and once as the real, glued marker at the end.
        line = "Reported in 2005: see note 1"
        offset = line.index(" 1", len("Reported in 2005: see note")) + 1
        document = _build_document([f"Doc Title\n{line}"])
        document.footnotes = [
            _footnote(marker="1", anchor_text=line, anchor_offset=offset, body="A note.")
        ]

        markdown = build_markdown(document)

        assert "Reported in 2005: see note [^p1-1]" in markdown
        assert "2005[^p1-1]" not in markdown  # the wrong "1" (inside "2005") must be untouched

    def test_plain_digit_marker_does_not_corrupt_an_unrelated_paragraph(self) -> None:
        # The real bug found during bug_005's implementation: a second,
        # unrelated paragraph containing the same digit must never be
        # touched by a marker belonging to a different paragraph.
        anchor_line = "A claim glued to a marker1 right here."
        other_line = "An unrelated sentence mentioning the year 1999 in passing."
        document = _build_document([f"Doc Title\n{anchor_line}\n{other_line}"])
        offset = anchor_line.index("marker1") + len("marker")
        document.footnotes = [
            _footnote(marker="1", anchor_text=anchor_line, anchor_offset=offset, body="A note.")
        ]

        markdown = build_markdown(document)

        assert "marker[^p1-1] right here" in markdown
        assert "1999" in markdown  # untouched - not the marker's paragraph
        assert "[^p1-1]999" not in markdown
        assert "19[^p1-1]99" not in markdown
        assert "[^p1-1]: A note." in markdown

    def test_no_footnotes_leaves_output_unchanged(self) -> None:
        document = _build_document(["Doc Title\nSome ordinary text."])
        document_with_empty_notes = _build_document(["Doc Title\nSome ordinary text."])
        document_with_empty_notes.footnotes = []

        assert build_markdown(document) == build_markdown(document_with_empty_notes)


class TestEndnoteRendering:
    # Same rationale as TestFootnoteRendering above: a "Doc Title" line
    # precedes the footnoted text so it isn't mistaken for the document's H1.

    def test_endnotes_collected_into_dedicated_section(self) -> None:
        document = _build_document(["Doc Title\nA claim with a marker¹.", "Notes"])
        document.footnotes = [
            _footnote(
                note_type=NoteType.ENDNOTE,
                anchor_text="A claim with a marker¹.",
                anchor_page_number=1,
                body_page_number=2,
                body="An endnote body.",
                body_source_text="1. An endnote body.",
            )
        ]

        markdown = build_markdown(document)

        assert "## Endnotes" in markdown
        assert "[^p2-1]: An endnote body." in markdown
        assert "A claim with a marker[^p2-1]." in markdown

    def test_endnotes_section_is_last_in_document(self) -> None:
        document = _build_document(["Doc Title\nA claim with a marker¹.", "Notes"])
        document.footnotes = [
            _footnote(
                note_type=NoteType.ENDNOTE,
                anchor_text="A claim with a marker¹.",
                body_page_number=2,
                body_source_text="1. An endnote body.",
            )
        ]

        markdown = build_markdown(document)

        assert markdown.rstrip().endswith("[^p2-1]: A note body.")

    def test_notes_heading_line_is_suppressed_when_endnotes_exist(self) -> None:
        document = _build_document(["Doc Title\nA claim with a marker¹.", "Notes"])
        document.footnotes = [
            _footnote(
                note_type=NoteType.ENDNOTE,
                anchor_text="A claim with a marker¹.",
                body_page_number=2,
                body_source_text="1. A note body.",
            )
        ]

        markdown = build_markdown(document)

        lines = [line for line in markdown.splitlines() if line.strip()]
        assert "Notes" not in lines

    def test_endnote_body_source_line_is_not_duplicated(self) -> None:
        document = _build_document(["Doc Title\nA claim¹.", "Notes\n1. The endnote body."])
        document.footnotes = [
            _footnote(
                note_type=NoteType.ENDNOTE,
                anchor_text="A claim¹.",
                body_page_number=2,
                body="The endnote body.",
                body_source_text="1. The endnote body.",
            )
        ]

        markdown = build_markdown(document)

        assert markdown.count("The endnote body.") == 1

    def test_no_endnotes_section_when_no_endnotes_detected(self) -> None:
        document = _build_document(["Doc Title\nSome ordinary text."])
        markdown = build_markdown(document)
        assert "Endnotes" not in markdown


def _build_document_with_blocks(
    page_lines: List[Tuple[str, float, float, Optional[int]]],
) -> Document:
    """Build a one-page Document whose Page.cleaned_text and
    Document.blocks are directly, consistently constructed - the same
    contract src/pipeline/phase1_pipeline.py's real stages produce
    (extract_text populates cleaned_text, detect_structure populates
    blocks from the same underlying lines), without going through a
    real synthetic PDF. PyMuPDF's own block-clustering for a tiny
    `fitz`-`insert_text`-built PDF turned out to be too unpredictable
    to calibrate reliably as a test fixture (gap size alone shifts its
    internal block boundaries in ways a hand-built single-line-per-call
    PDF doesn't represent real authored documents well) - constructing
    both sides of the contract directly instead exercises the real
    _render_page_body_with_paragraphs code path with full control over
    the exact geometry/source_block_index signals it reads.

    page_lines: list of (text, y0, y1, source_block_index) for page 1,
    in order. x0/x1 are fixed dummy values - paragraph_grouper's
    gap/block-index signals only need realistic y/height here, not
    real horizontal layout.
    """
    cleaned_text = "\n".join(text for text, *_ in page_lines)
    blocks = [
        TextBlock(
            page_number=1,
            text=text,
            bbox=BoundingBox(x0=50.0, y0=y0, x1=250.0, y1=y1),
            order=order,
            source_block_index=source_block_index,
        )
        for order, (text, y0, y1, source_block_index) in enumerate(page_lines)
    ]
    document = Document(
        source_pdf_path="dummy.pdf",
        metadata=Metadata(filename="dummy.pdf"),
        pages=[Page(page_number=1, cleaned_text=cleaned_text)],
        blocks=blocks,
    )
    return detect_headings(document)


class TestParagraphReconstruction:
    """Option B - see samples/regressions/bug_001_brinkman_word_splitting/
    notes_md/ for the audit and design review this implements. Unlike
    every test above (which builds a synthetic Document with no
    document.blocks, exercising the unchanged line-by-line fallback
    path), these populate document.blocks directly so the new
    geometry-grounded path actually runs.
    """

    # A 12pt-text line's bbox height is roughly font-size-sized; gaps
    # below are chosen well clear of the 1.5x-median-height paragraph-
    # break threshold (small) or well past it (large), so these tests
    # aren't sensitive to the exact ratio - only the to-scale relationship.
    _LINE_HEIGHT = 12.0
    _SINGLE_SPACED_GAP = 2.0  # ordinary line-wrap continuation
    _PARAGRAPH_BREAK_GAP = 40.0  # unambiguous new-paragraph gap

    def test_wrapped_lines_join_into_one_paragraph(self) -> None:
        # "Doc Title" first, exactly like TestFootnoteRendering above -
        # heading_detector's positional H1 rule promotes the first
        # non-blank line in the whole document regardless of layout.
        y = 100.0
        lines = [("Doc Title", y, y + self._LINE_HEIGHT, 0)]
        y += self._LINE_HEIGHT + self._PARAGRAPH_BREAK_GAP
        for text in ("This sentence wraps across", "several lines that all belong", "to one single paragraph."):
            lines.append((text, y, y + self._LINE_HEIGHT, 1))
            y += self._LINE_HEIGHT + self._SINGLE_SPACED_GAP

        document = _build_document_with_blocks(lines)
        markdown = build_markdown(document)

        assert (
            "This sentence wraps across several lines that all belong to one single paragraph."
            in markdown
        )
        # must render as ONE markdown block, not three separate ones
        assert "across\n\nseveral" not in markdown
        assert "belong\n\nto" not in markdown

    def test_large_vertical_gap_keeps_paragraphs_separate(self) -> None:
        y = 100.0
        lines = [("Doc Title", y, y + self._LINE_HEIGHT, 0)]
        y += self._LINE_HEIGHT + self._PARAGRAPH_BREAK_GAP
        lines.append(("First paragraph stands alone.", y, y + self._LINE_HEIGHT, 1))
        y += self._LINE_HEIGHT + self._PARAGRAPH_BREAK_GAP
        # same source_block_index as the line above on purpose - the
        # vertical-gap fallback alone must still force the break.
        lines.append(("Second paragraph is distinct.", y, y + self._LINE_HEIGHT, 1))

        document = _build_document_with_blocks(lines)
        markdown = build_markdown(document)

        lines_out = [line for line in markdown.splitlines() if line.strip()]
        assert "First paragraph stands alone." in lines_out
        assert "Second paragraph is distinct." in lines_out

    def test_heading_interrupts_paragraph_join(self) -> None:
        # "Introduction" is a fixed H2 keyword (docs/HEADING_RULES.md) -
        # deterministic regardless of font/layout, so this isolates the
        # heading-interruption behavior from layout-signal tuning.
        y = 100.0
        lines = [("Doc Title", y, y + self._LINE_HEIGHT, 0)]
        y += self._LINE_HEIGHT + self._PARAGRAPH_BREAK_GAP
        lines.append(("Text before the heading wraps", y, y + self._LINE_HEIGHT, 1))
        y += self._LINE_HEIGHT + self._SINGLE_SPACED_GAP
        lines.append(("onto a second line here.", y, y + self._LINE_HEIGHT, 1))
        y += self._LINE_HEIGHT + self._PARAGRAPH_BREAK_GAP
        lines.append(("Introduction", y, y + self._LINE_HEIGHT, 2))
        y += self._LINE_HEIGHT + self._PARAGRAPH_BREAK_GAP
        lines.append(("Text after the heading also wraps", y, y + self._LINE_HEIGHT, 3))
        y += self._LINE_HEIGHT + self._SINGLE_SPACED_GAP
        lines.append(("onto its own second line.", y, y + self._LINE_HEIGHT, 3))

        document = _build_document_with_blocks(lines)
        markdown = build_markdown(document)

        assert "Text before the heading wraps onto a second line here." in markdown
        assert "## Introduction" in markdown
        assert "Text after the heading also wraps onto its own second line." in markdown
        # the two body paragraphs must not have been fused across the heading
        assert "here. Introduction" not in markdown
        assert "Introduction Text after" not in markdown

    def test_footnote_marker_substitutes_correctly_inside_joined_paragraph(self) -> None:
        y = 100.0
        lines = [("Doc Title", y, y + self._LINE_HEIGHT, 0)]
        y += self._LINE_HEIGHT + self._PARAGRAPH_BREAK_GAP
        lines.append(("A claim with a marker¹ that", y, y + self._LINE_HEIGHT, 1))
        y += self._LINE_HEIGHT + self._SINGLE_SPACED_GAP
        lines.append(("wraps onto a second line.", y, y + self._LINE_HEIGHT, 1))

        document = _build_document_with_blocks(lines)
        # Matches anchor_text against the exact TextBlock text
        # src/structure/structure_detector.py would have extracted -
        # the same exact-line-matching convention markdown_builder.py
        # already documents relying on (src/footnotes/footnote_detector.py
        # builds real Footnotes the same way; this attaches one
        # directly to isolate markdown_builder's substitution behavior).
        anchor_block = next(b for b in document.blocks if "marker" in b.text)
        document.footnotes = [
            Footnote(
                note_type=NoteType.FOOTNOTE,
                number=1,
                marker="¹",
                anchor_page_number=1,
                anchor_text=anchor_block.text,
                body="A note body.",
                body_page_number=1,
                body_source_text="not present on this page",
            )
        ]

        markdown = build_markdown(document)

        assert "A claim with a marker[^p1-1] that wraps onto a second line." in markdown
        assert "¹" not in markdown

    def test_pages_without_blocks_still_use_line_by_line_fallback(self) -> None:
        # No document.blocks at all - this must behave exactly like
        # every synthetic _build_document test above: one block per
        # raw cleaned_text line, unchanged.
        document = _build_document(["Doc Title\nFirst line.\nSecond line."])
        assert document.blocks == []

        markdown = build_markdown(document)

        lines_out = [line for line in markdown.splitlines() if line.strip()]
        assert "First line." in lines_out
        assert "Second line." in lines_out
        assert "First line. Second line." not in markdown


class TestBrinkmanRegressionEndToEnd:
    """A live, full-pipeline smoke test against the actual regression
    case (samples/regressions/bug_001_brinkman_word_splitting/) this
    feature was built to fix - see notes_md/root_cause_audit.md.
    Permanent regression coverage for the originally-reported defect,
    independent of the synthetic-fixture tests above.
    """

    _PDF_PATH = (
        Path(__file__).resolve().parents[1]
        / "samples"
        / "regressions"
        / "bug_001_brinkman_word_splitting"
        / "source_pdf"
        / "7.brinkman-learner-centred-education-reform-india-missing-beliefs.pdf"
    )

    def test_previously_word_fragmented_sentence_now_joins_correctly(self) -> None:
        document = parse_pdf(self._PDF_PATH)
        document = extract_text(document)
        document = detect_structure(document)
        document = detect_footnotes(document)
        document = detect_headings(document)
        markdown = build_markdown(document)

        assert (
            "beliefs of 60 elementary teachers in three Indian states are explored through "
            "written questionnaires, semi-structured interviews, and open-ended "
            "life-narratives, while their pedagogy is analysed through classroom observations."
        ) in markdown
        # the original symptom: any of these fragments alone on its own line
        for fragment in ("questionnaires,", "semi-structured", "open-ended", "life-narratives,"):
            assert f"\n\n{fragment}\n\n" not in markdown
