"""Tests for src/footnotes/footnote_detector.py (Phase K)."""

from pathlib import Path
from typing import List, Tuple

import fitz
import pytest

from src.footnotes.footnote_detector import _find_span_marker_candidates, detect_footnotes
from src.models.contracts import BoundingBox, Document, Metadata, NoteType, Page, Span, TextBlock
from src.parser.pdf_parser import parse_pdf
from src.structure.structure_detector import detect_structure

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"
SAMPLE_PDFS = sorted(SAMPLE_PDF_DIR.glob("*.pdf"))

# A realistic page of body text (several lines, so the document's
# dominant-body-font-size majority vote isn't skewed by a sparse
# fixture - a 1-2 line synthetic page would let a single small-font
# footnote line outweigh the "body" in character count).
_FILLER_LINES = [
    "This is the first line of ordinary body text on the page.",
    "This is the second line of ordinary body text on the page.",
]


def _build_pdf(
    tmp_path: Path,
    pages_lines: List[List[Tuple[str, float, Tuple[float, float]]]],
    filename: str = "footnotes.pdf",
) -> Path:
    """pages_lines: one list of (text, fontsize, (x, y)) per page."""
    pdf_path = tmp_path / filename
    doc = fitz.open()
    for lines in pages_lines:
        page = doc.new_page()
        for text, fontsize, (x, y) in lines:
            page.insert_text((x, y), text, fontname="helv", fontsize=fontsize)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _footnote_page(filler_extra: str = "", marker_line: str = None) -> List[Tuple[str, float, Tuple[float, float]]]:
    """A standard one-page footnote fixture: 2 filler lines, the marker
    line, optionally more filler, then a footnote body near the bottom
    of the page (y=700, comfortably in the bottom quarter of a default
    792pt-tall page)."""
    lines = [(text, 12.0, (72.0, 72.0 + i * 20)) for i, text in enumerate(_FILLER_LINES)]
    y = 72.0 + len(_FILLER_LINES) * 20
    if marker_line is not None:
        lines.append((marker_line, 12.0, (72.0, y)))
        y += 20
    if filler_extra:
        lines.append((filler_extra, 12.0, (72.0, y)))
    return lines


def _detect(pdf_path: Path) -> Document:
    document = parse_pdf(pdf_path)
    detect_structure(document)
    detect_footnotes(document)
    return document


class TestMarkerAndBodyLinking:
    def test_worked_example_from_phase_k_brief(self, tmp_path: Path) -> None:
        # "The study showed significant improvement¹." / "¹ Improvement
        # measured using standardized test scores." - the exact example
        # given in the Phase K requirements.
        page_lines = _footnote_page(marker_line="The study showed significant improvement¹.")
        page_lines.append(
            ("¹ Improvement measured using standardized test scores.", 8.0, (72.0, 700.0))
        )
        pdf_path = _build_pdf(tmp_path, [page_lines])

        document = _detect(pdf_path)

        assert len(document.footnotes) == 1
        note = document.footnotes[0]
        assert note.note_type == NoteType.FOOTNOTE
        assert note.number == 1
        assert note.marker == "¹"
        assert note.anchor_page_number == 1
        assert note.body_page_number == 1
        assert note.body == "Improvement measured using standardized test scores."
        assert note.anchor_text == "The study showed significant improvement¹."

    def test_marker_without_matching_body_is_not_detected(self, tmp_path: Path) -> None:
        page_lines = _footnote_page(marker_line="A claim with a marker but no note¹.")
        pdf_path = _build_pdf(tmp_path, [page_lines])

        document = _detect(pdf_path)

        assert document.footnotes == []

    def test_body_without_matching_marker_is_not_detected(self, tmp_path: Path) -> None:
        page_lines = _footnote_page()
        page_lines.append(("1. An orphan note with no inline reference.", 8.0, (72.0, 700.0)))
        pdf_path = _build_pdf(tmp_path, [page_lines])

        document = _detect(pdf_path)

        assert document.footnotes == []

    def test_small_font_bottom_text_without_marker_prefix_is_not_a_footnote(
        self, tmp_path: Path
    ) -> None:
        # A page number or running footer at the bottom, in a smaller
        # font, must not be mistaken for a footnote body just because
        # it is small and low on the page - it needs the marker prefix too.
        page_lines = _footnote_page(marker_line="A claim with a marker¹.")
        page_lines.append(("13", 8.0, (72.0, 700.0)))
        pdf_path = _build_pdf(tmp_path, [page_lines])

        document = _detect(pdf_path)

        assert document.footnotes == []

    def test_same_font_size_bottom_text_is_not_a_footnote(self, tmp_path: Path) -> None:
        # Marker-prefixed text at the bottom of the page, but at the
        # SAME font size as the body - no font-size-drop, so not
        # confidently a footnote (could just be a numbered list item).
        page_lines = _footnote_page(marker_line="A claim with a marker¹.")
        page_lines.append(("1. Looks like a note but is body-sized text.", 12.0, (72.0, 700.0)))
        pdf_path = _build_pdf(tmp_path, [page_lines])

        document = _detect(pdf_path)

        assert document.footnotes == []

    def test_marker_prefixed_text_not_at_bottom_of_page_is_not_a_footnote(
        self, tmp_path: Path
    ) -> None:
        # Smaller font + marker prefix, but positioned near the TOP of
        # the page, not the bottom - footnotes are a print-position
        # convention, not just "small marker-prefixed text anywhere".
        page_lines = [
            ("1. Looks like a note but is at the top of the page.", 8.0, (72.0, 72.0)),
            ("A claim with a marker¹.", 12.0, (72.0, 100.0)),
        ]
        pdf_path = _build_pdf(tmp_path, [page_lines])

        document = _detect(pdf_path)

        assert document.footnotes == []

    def test_multiple_footnotes_on_one_page_are_each_linked(self, tmp_path: Path) -> None:
        page_lines = _footnote_page(marker_line="First claim¹.")
        page_lines.append(("Second claim².", 12.0, (72.0, 132.0)))
        page_lines.append(("¹ First note body.", 8.0, (72.0, 700.0)))
        page_lines.append(("² Second note body.", 8.0, (72.0, 715.0)))
        pdf_path = _build_pdf(tmp_path, [page_lines])

        document = _detect(pdf_path)

        assert len(document.footnotes) == 2
        by_number = {note.number: note for note in document.footnotes}
        assert by_number[1].body == "First note body."
        assert by_number[2].body == "Second note body."

    def test_footnote_numbering_resets_per_page(self, tmp_path: Path) -> None:
        page_1 = _footnote_page(marker_line="Page one claim¹.")
        page_1.append(("¹ Page one note.", 8.0, (72.0, 700.0)))
        page_2 = _footnote_page(marker_line="Page two claim¹.")
        page_2.append(("¹ Page two note.", 8.0, (72.0, 700.0)))
        pdf_path = _build_pdf(tmp_path, [page_1, page_2])

        document = _detect(pdf_path)

        assert len(document.footnotes) == 2
        by_page = {note.anchor_page_number: note for note in document.footnotes}
        assert by_page[1].body == "Page one note."
        assert by_page[2].body == "Page two note."
        # neither was cross-linked to the other page's body
        assert by_page[1].body_page_number == 1
        assert by_page[2].body_page_number == 2

    def test_repeated_marker_on_same_page_links_once(self, tmp_path: Path) -> None:
        # The same footnote referenced twice on one page (rare but
        # valid) - only the first occurrence is linked; the second
        # instance of the glyph is left untouched (honest, conservative
        # scope limit - see module docstring).
        page_lines = _footnote_page(marker_line="First mention¹.")
        page_lines.append(("Second mention of the same note¹.", 12.0, (72.0, 132.0)))
        page_lines.append(("¹ The shared note body.", 8.0, (72.0, 700.0)))
        pdf_path = _build_pdf(tmp_path, [page_lines])

        document = _detect(pdf_path)

        assert len(document.footnotes) == 1
        assert document.footnotes[0].anchor_text == "First mention¹."

    def test_no_markers_at_all_yields_no_footnotes(self, tmp_path: Path) -> None:
        pdf_path = _build_pdf(tmp_path, [_footnote_page()])
        document = _detect(pdf_path)
        assert document.footnotes == []


class TestXmlSanitization:
    """XML Sanitization Architecture, Layer 1: proves the
    production-relevant claim that footnote/endnote text is protected -
    not by any code in this module (footnote_detector.py never
    sanitizes), but transitively, because src/structure/structure_detector.py
    (Phase H) now sanitizes TextBlock.text at the one point every block
    is created, and this module's _parse_body_candidate() reads
    block.text verbatim from an already-clean block. See the XML
    Sanitization Architecture Review (docs/DECISIONS_LOG.md)."""

    def test_footnote_body_with_control_character_comes_out_clean(self, tmp_path: Path) -> None:
        page_lines = _footnote_page(marker_line="The study showed significant improvement¹.")
        page_lines.append(
            ("¹ Improvement measured using\x01 standardized test scores.", 8.0, (72.0, 700.0))
        )
        pdf_path = _build_pdf(tmp_path, [page_lines])

        document = _detect(pdf_path)

        assert len(document.footnotes) == 1
        note = document.footnotes[0]
        assert "\x01" not in note.body
        assert note.body == "Improvement measured using standardized test scores."
        assert "\x01" not in note.body_source_text

    def test_sanitization_event_is_recorded_for_the_footnote_body(self, tmp_path: Path) -> None:
        page_lines = _footnote_page(marker_line="The study showed significant improvement¹.")
        page_lines.append(
            ("¹ Improvement measured using\x01 standardized test scores.", 8.0, (72.0, 700.0))
        )
        pdf_path = _build_pdf(tmp_path, [page_lines])

        document = _detect(pdf_path)

        events = [e for e in document.sanitization_events if e.removed_codepoints]
        assert len(events) == 1
        assert events[0].field == "text_block"
        assert events[0].removed_codepoints == ["U+0001"]


class TestEndnoteDetection:
    def test_endnotes_linked_across_pages_with_notes_heading(self, tmp_path: Path) -> None:
        page_1 = _footnote_page(marker_line="First claim¹.")
        page_1.append(("Second claim².", 12.0, (72.0, 132.0)))
        page_2 = [
            ("Notes", 14.0, (72.0, 72.0)),
            ("1. First note body.", 12.0, (72.0, 100.0)),
            ("2. Second note body.", 12.0, (72.0, 120.0)),
        ]
        pdf_path = _build_pdf(tmp_path, [page_1, page_2])

        document = _detect(pdf_path)

        assert len(document.footnotes) == 2
        assert all(note.note_type == NoteType.ENDNOTE for note in document.footnotes)
        by_number = {note.number: note for note in document.footnotes}
        assert by_number[1].body == "First note body."
        assert by_number[1].anchor_page_number == 1
        assert by_number[1].body_page_number == 2
        assert by_number[2].body == "Second note body."

    def test_endnotes_pattern_is_case_insensitive(self, tmp_path: Path) -> None:
        page_1 = _footnote_page(marker_line="A claim¹.")
        page_2 = [
            ("ENDNOTES", 14.0, (72.0, 72.0)),
            ("1. The note body.", 12.0, (72.0, 100.0)),
        ]
        pdf_path = _build_pdf(tmp_path, [page_1, page_2])

        document = _detect(pdf_path)

        assert len(document.footnotes) == 1
        assert document.footnotes[0].note_type == NoteType.ENDNOTE

    def test_endnote_numbering_is_global_not_per_page(self, tmp_path: Path) -> None:
        # Two source pages of markers before the Notes section, sharing
        # one continuously-numbered notes section - confirms endnote
        # matching does not reset per page the way footnote matching does.
        page_1 = _footnote_page(marker_line="Page one claim¹.")
        page_2 = _footnote_page(marker_line="Page two claim².")
        page_3 = [
            ("Notes", 14.0, (72.0, 72.0)),
            ("1. Note for the page one claim.", 12.0, (72.0, 100.0)),
            ("2. Note for the page two claim.", 12.0, (72.0, 120.0)),
        ]
        pdf_path = _build_pdf(tmp_path, [page_1, page_2, page_3])

        document = _detect(pdf_path)

        assert len(document.footnotes) == 2
        by_number = {note.number: note for note in document.footnotes}
        assert by_number[1].anchor_page_number == 1
        assert by_number[2].anchor_page_number == 2
        assert by_number[1].body_page_number == 3
        assert by_number[2].body_page_number == 3

    def test_footnotes_and_endnotes_coexist_in_one_document(self, tmp_path: Path) -> None:
        # A real footnote (body on the same page, bottom, smaller font)
        # plus a separate endnote-section reference, in the same document.
        page_1 = _footnote_page(marker_line="A footnoted claim¹.")
        page_1.append(("¹ A real footnote body.", 8.0, (72.0, 700.0)))
        page_1.append(("An endnoted claim².", 12.0, (72.0, 152.0)))
        page_2 = [
            ("Notes", 14.0, (72.0, 72.0)),
            ("2. A real endnote body.", 12.0, (72.0, 100.0)),
        ]
        pdf_path = _build_pdf(tmp_path, [page_1, page_2])

        document = _detect(pdf_path)

        assert len(document.footnotes) == 2
        by_type = {note.note_type: note for note in document.footnotes}
        assert by_type[NoteType.FOOTNOTE].body == "A real footnote body."
        assert by_type[NoteType.ENDNOTE].body == "A real endnote body."

    def test_notes_heading_alone_with_no_markers_yields_no_endnotes(self, tmp_path: Path) -> None:
        page_1 = _footnote_page()
        page_2 = [
            ("Notes", 14.0, (72.0, 72.0)),
            ("Just a coincidental section with no real notes.", 12.0, (72.0, 100.0)),
        ]
        pdf_path = _build_pdf(tmp_path, [page_1, page_2])

        document = _detect(pdf_path)

        assert document.footnotes == []


class TestPageReferenceProjection:
    def test_footnote_references_populated_on_anchor_page(self, tmp_path: Path) -> None:
        page_lines = _footnote_page(marker_line="A claim¹.")
        page_lines.append(("¹ The note body.", 8.0, (72.0, 700.0)))
        pdf_path = _build_pdf(tmp_path, [page_lines])

        document = _detect(pdf_path)

        assert document.pages[0].footnote_references == ["¹"]
        assert document.pages[0].endnote_references == []

    def test_endnote_references_populated_on_anchor_page_not_body_page(
        self, tmp_path: Path
    ) -> None:
        page_1 = _footnote_page(marker_line="A claim¹.")
        page_2 = [
            ("Notes", 14.0, (72.0, 72.0)),
            ("1. The note body.", 12.0, (72.0, 100.0)),
        ]
        pdf_path = _build_pdf(tmp_path, [page_1, page_2])

        document = _detect(pdf_path)

        assert document.pages[0].endnote_references == ["¹"]
        assert document.pages[0].footnote_references == []
        assert document.pages[1].endnote_references == []

    def test_pages_with_no_notes_have_empty_reference_lists(self, tmp_path: Path) -> None:
        pdf_path = _build_pdf(tmp_path, [_footnote_page()])
        document = _detect(pdf_path)
        assert document.pages[0].footnote_references == []
        assert document.pages[0].endnote_references == []


class TestErrorHandling:
    def test_empty_blocks_is_a_no_op(self, tmp_path: Path) -> None:
        pdf_path = _build_pdf(tmp_path, [_footnote_page(marker_line="A claim¹.")])
        document = parse_pdf(pdf_path)  # detect_structure never run - document.blocks == []

        result = detect_footnotes(document)  # must not raise

        assert result is document
        assert document.footnotes == []

    def test_missing_source_pdf_does_not_raise(self, tmp_path: Path) -> None:
        document = Document(
            source_pdf_path=str(tmp_path / "missing.pdf"),
            metadata=Metadata(filename="missing.pdf"),
            pages=[Page(page_number=1)],
        )
        # Manually populate blocks so detection has something to scan,
        # simulating Phase H having run against a PDF that has since
        # been deleted.
        from src.models.contracts import BoundingBox, TextBlock

        document.blocks = [
            TextBlock(
                page_number=1,
                text="A claim with a marker¹.",
                bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10),
                order=0,
                font_size=12.0,
            )
        ]

        result = detect_footnotes(document)  # must not raise

        assert result is document
        # No page-height signal available (PDF missing) - footnote
        # bodies can never be confirmed without it.
        assert document.footnotes == []

    def test_corrupt_source_pdf_does_not_raise(self, tmp_path: Path) -> None:
        bad_pdf_path = tmp_path / "corrupt.pdf"
        bad_pdf_path.write_text("not a real pdf")
        document = Document(
            source_pdf_path=str(bad_pdf_path),
            metadata=Metadata(filename="corrupt.pdf"),
            pages=[Page(page_number=1)],
        )
        from src.models.contracts import BoundingBox, TextBlock

        document.blocks = [
            TextBlock(
                page_number=1,
                text="A claim with a marker¹.",
                bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10),
                order=0,
                font_size=12.0,
            )
        ]

        result = detect_footnotes(document)  # must not raise
        assert result is document


@pytest.mark.parametrize("sample_pdf_path", SAMPLE_PDFS, ids=[p.name for p in SAMPLE_PDFS])
class TestBenchmarkDocuments:
    def test_detection_does_not_crash_on_real_benchmark_pdfs(self, sample_pdf_path: Path) -> None:
        document = parse_pdf(sample_pdf_path)
        detect_structure(document)
        detect_footnotes(document)  # must not raise

    # The benchmark corpus grew from 4 to 10 PDFs on 2026-06-24 (see
    # DECISIONS_LOG.md "Benchmark Corpus Expansion"). Originally none of
    # the 4 contained a real footnote/endnote, so this guard held for
    # the whole corpus unconditionally. Brinkman - now also in this
    # corpus, not just samples/regressions/ - has 3 real, confirmed,
    # body-linked endnotes (the exact bug_005 fix this signal exists
    # for), so it's excluded here, not because the detector is wrong,
    # but because it would be wrong for this specific PDF to report zero.
    _PDFS_WITH_REAL_LINKED_FOOTNOTES = {
        "7.brinkman-learner-centred-education-reform-india-missing-beliefs.pdf",
    }

    def test_no_real_footnotes_in_current_benchmark_corpus(self, sample_pdf_path: Path) -> None:
        # Confirmed by direct inspection during the Phase K architecture
        # audit: none of the (then 4) benchmark PDFs contain a real
        # footnote or endnote. This pins that finding down as a
        # regression guard - if it ever fails, the benchmark corpus
        # changed, not (necessarily) this module.
        if sample_pdf_path.name in self._PDFS_WITH_REAL_LINKED_FOOTNOTES:
            pytest.skip("known to have real, body-linked footnotes/endnotes - see bug_005")
        document = parse_pdf(sample_pdf_path)
        detect_structure(document)
        detect_footnotes(document)
        assert document.footnotes == []

    # Two further PDFs (added in the same 2026-06-24 corpus expansion)
    # contain real, sequentially-numbered footnote markers - confirmed
    # by direct inspection (e.g. "...discovery of truth (Borg, 1963).1",
    # "...adult?2 Such statements...") - that _find_span_marker_candidates()
    # correctly flags. They never reach Document.footnotes because no
    # matching body text was found to link against (a separate, already-
    # documented limitation - see KNOWN_LIMITATIONS.md), but flagging the
    # marker itself is correct detection, not a false positive.
    _PDFS_WITH_REAL_UNLINKED_MARKERS = {
        "1. Nature of Enquiry.pdf",
        "1.Aims of Education and the teacher_Dhankar_PhilPers (1).pdf",
    }

    def test_bug_005_span_signal_introduces_no_false_positives_on_benchmark_corpus(
        self, sample_pdf_path: Path
    ) -> None:
        # Same guard as above, restated explicitly for bug_005's new
        # span-based detection signal specifically: across every real,
        # independent benchmark PDF confirmed to contain no real
        # footnote/endnote markers at all, the new signal must not turn
        # up a single false-positive marker on its own.
        if (
            sample_pdf_path.name in self._PDFS_WITH_REAL_LINKED_FOOTNOTES
            or sample_pdf_path.name in self._PDFS_WITH_REAL_UNLINKED_MARKERS
        ):
            pytest.skip("known to contain real footnote/endnote markers - see bug_005")
        document = parse_pdf(sample_pdf_path)
        detect_structure(document)
        for block in document.blocks:
            assert _find_span_marker_candidates(block) == []


class TestBug005SpanSuperscriptDetection:
    """bug_005 / feature_005: the span-based marker-detection signal in
    _find_span_marker_candidates()/_span_marker_offset(), tested
    directly against hand-built TextBlock/Span fixtures.

    PyMuPDF's insert_text() cannot synthesize a superscript flag bit
    directly (flags are derived from the font's own properties at
    render time, not a parameter insert_text() exposes) - the same
    constraint tests/test_headings.py's layout-signal tests already
    work around by testing the underlying function directly instead of
    through a rendered PDF (see e.g.
    TestLayoutBasedHeadingDetection::test_majority_bold_span_flags_line_as_bold).
    """

    @staticmethod
    def _span(text: str, size: float, flags: int, x: float = 0.0) -> Span:
        return Span(
            text=text,
            font_name="Test",
            font_size=size,
            font_flags=flags,
            baseline_y=100.0,
            bbox=BoundingBox(x0=x, y0=95.0, x1=x + 10.0, y1=105.0),
        )

    @staticmethod
    def _block(text: str, spans: List[Span]) -> TextBlock:
        return TextBlock(
            page_number=1,
            text=text,
            bbox=BoundingBox(x0=0.0, y0=0.0, x1=100.0, y1=10.0),
            order=0,
            spans=spans,
        )

    def test_glued_superscript_digit_is_detected(self) -> None:
        spans = [self._span("see note", 10.0, 0), self._span("1", 7.0, 1)]
        block = self._block("see note1", spans)

        candidates = _find_span_marker_candidates(block)

        assert len(candidates) == 1
        assert candidates[0].number == 1
        assert candidates[0].marker_text == "1"
        assert candidates[0].anchor_offset == len("see note")

    def test_not_detected_without_superscript_flag(self) -> None:
        spans = [self._span("see note", 10.0, 0), self._span("1", 7.0, 0)]
        assert _find_span_marker_candidates(self._block("see note1", spans)) == []

    def test_not_detected_without_a_visible_size_drop(self) -> None:
        spans = [self._span("see note", 10.0, 0), self._span("1", 10.0, 1)]
        assert _find_span_marker_candidates(self._block("see note1", spans)) == []

    def test_not_detected_when_preceded_by_space(self) -> None:
        # A standalone superscript digit, not glued onto a word, is
        # never a footnote marker - same requirement signal 1 (the
        # literal Unicode glyph path) already enforces.
        spans = [self._span("see note ", 10.0, 0), self._span("1", 7.0, 1)]
        assert _find_span_marker_candidates(self._block("see note 1", spans)) == []

    def test_not_detected_as_the_only_span_on_a_line(self) -> None:
        spans = [self._span("1", 7.0, 1)]
        assert _find_span_marker_candidates(self._block("1", spans)) == []

    def test_not_detected_when_more_than_three_digits(self) -> None:
        # A year-like number with a stray superscript flag must not be
        # mistaken for a footnote marker - bounded to realistic lengths.
        spans = [self._span("circa", 10.0, 0), self._span("2005", 7.0, 1)]
        assert _find_span_marker_candidates(self._block("circa2005", spans)) == []

    def test_block_with_no_span_data_contributes_nothing(self) -> None:
        # A TextBlock built without span data (e.g. predating
        # feature_005, or a non-DIRECT_TEXT/OCR-recovered page) must
        # not error - just contribute zero candidates, additive only.
        block = TextBlock(
            page_number=1,
            text="see note1",
            bbox=BoundingBox(x0=0.0, y0=0.0, x1=1.0, y1=1.0),
            order=0,
        )
        assert _find_span_marker_candidates(block) == []


BUG_005_REGRESSION_PDF = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "regressions"
    / "bug_005_footnote_endnote_information_loss"
    / "source_pdf"
    / "7.brinkman-learner-centred-education-reform-india-missing-beliefs.pdf"
)


class TestBug005RealRegressionPdf:
    """End-to-end regression coverage against the real PDF that
    originally exposed bug_005 - see samples/regressions/
    bug_005_footnote_endnote_information_loss/notes_md/root_cause_audit.md
    for the full root-cause record this pins down.
    """

    def test_all_three_endnotes_detected_and_linked(self) -> None:
        document = _detect(BUG_005_REGRESSION_PDF)

        assert len(document.footnotes) == 3
        by_number = {note.number: note for note in document.footnotes}
        assert set(by_number) == {1, 2, 3}
        for note in document.footnotes:
            assert note.note_type == NoteType.ENDNOTE
            assert note.body_page_number == 16

        assert by_number[1].anchor_page_number == 2
        assert by_number[2].anchor_page_number == 3
        assert by_number[3].anchor_page_number == 7

    def test_marker_three_glued_after_closing_paren_is_detected(self) -> None:
        # "Brinkman Case C": marker 3 is glued directly after a closing
        # parenthesis ("(B4-L)3"), a structurally different context
        # from markers 1/2 (glued after sentence-ending punctuation
        # plus a period, e.g. "13).1") - confirms the "glued onto the
        # preceding span" check generalizes across punctuation shapes,
        # not just the more common one.
        document = _detect(BUG_005_REGRESSION_PDF)
        note = next(n for n in document.footnotes if n.number == 3)
        assert "(B4-L)" in note.anchor_text
        assert note.anchor_offset is not None
        assert note.anchor_text[note.anchor_offset] == "3"
