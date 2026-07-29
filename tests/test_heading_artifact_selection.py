"""L3 — Heading Detector: Artifact-aware Candidate Selection.

The heading detector now consumes the canonical L2 ArtifactClassification
(src/structure/layout_signals.py::classify_artifacts, attached to
document.blocks) and rejects any line an artifact-classified block occupies
from heading candidacy *before* it is scored - so running headers/footers,
page numbers, and decorative repeated lines never become content headings,
and a rejected artifact preceding the title does not consume the H1 slot.

These tests pin the mechanism (the index), the behaviour (rejection +
H1-slot preservation) via the deterministic dummy-PDF path, and the full
detect_structure -> detect_headings wiring on a real PDF.
"""

import fitz

from src.headings.heading_detector import _index_artifact_texts, detect_headings
from src.models.bounding_box import BoundingBox
from src.models.contracts import Document, Metadata, Page, TextBlock
from src.models.text_block import ArtifactClass, ArtifactClassification
from src.ocr.extractor import extract_text
from src.parser.pdf_parser import parse_pdf
from src.structure.structure_detector import detect_structure


def _artifact(cls: ArtifactClass) -> ArtifactClassification:
    return ArtifactClassification(artifact_class=cls, confidence=0.9, evidence=["zone", "repeats"])


def _blk(text: str, page: int, order: int, artifact_class=None) -> TextBlock:
    block = TextBlock(
        page_number=page,
        text=text,
        bbox=BoundingBox(x0=72, y0=40, x1=300, y1=52),
        order=order,
    )
    if artifact_class is not None:
        block.artifact = _artifact(artifact_class)
    return block


def _content_texts(document: Document) -> list:
    return [h.text for h in document.headings if not h.is_page_marker]


class TestIndexArtifactTexts:
    def test_only_classified_blocks_indexed_by_page(self):
        blocks = [
            _blk("Journal of X", 1, 0, ArtifactClass.RUNNING_HEADER),
            _blk("iv", 1, 1, ArtifactClass.PAGE_NUMBER),
            _blk("Real body sentence.", 1, 2),  # not an artifact
            _blk("Journal of X", 2, 0, ArtifactClass.RUNNING_HEADER),
        ]
        index = _index_artifact_texts(blocks)
        assert index[1] == {"Journal of X", "iv"}
        assert index[2] == {"Journal of X"}
        assert "Real body sentence." not in index[1]

    def test_empty_blocks_yield_empty_index(self):
        assert _index_artifact_texts([]) == {}


class TestArtifactRejection:
    def _document_run(self, with_artifact: bool) -> Document:
        # "Running Masthead" is the document's first productive line, so
        # absent L3 it claims the H1 slot; "Actual Content Heading" follows.
        page = Page(page_number=1, cleaned_text="Running Masthead\nActual Content Heading\nsome body.")
        masthead = _blk(
            "Running Masthead", 1, 0, ArtifactClass.RUNNING_HEADER if with_artifact else None
        )
        content = _blk("Actual Content Heading", 1, 1)
        document = Document(
            source_pdf_path="dummy.pdf",
            metadata=Metadata(filename="dummy.pdf"),
            pages=[page],
            blocks=[masthead, content],
        )
        detect_headings(document)
        return document

    def test_artifact_line_is_rejected_as_heading(self):
        assert "Running Masthead" not in _content_texts(self._document_run(with_artifact=True))

    def test_control_without_artifact_keeps_the_line(self):
        # The very difference L3 makes: identical input, no classification.
        assert "Running Masthead" in _content_texts(self._document_run(with_artifact=False))

    def test_h1_slot_passes_to_next_line_when_artifact_rejected(self):
        # The rejected masthead must not spend the H1 slot; the real title
        # after it should still be detected (as the now-first line).
        assert "Actual Content Heading" in _content_texts(self._document_run(with_artifact=True))


class TestStructureToHeadingsWiring:
    def _three_page_pdf(self, tmp_path):
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page(width=612, height=792)
            # Bold running masthead in the top (HEADER) band, identical on
            # every page -> classify_artifacts -> RUNNING_HEADER.
            page.insert_text((72, 40), "Running Masthead", fontname="hebo", fontsize=12)
            # A unique, non-bold body line so the masthead is bold-relative.
            page.insert_text((72, 400), f"Distinct body line {i}", fontname="helv", fontsize=10)
        path = tmp_path / "masthead.pdf"
        doc.save(str(path))
        doc.close()
        return extract_text(parse_pdf(str(path)))

    def test_running_header_excluded_end_to_end(self, tmp_path):
        document = detect_structure(self._three_page_pdf(tmp_path))

        # Precondition: the Layout Intelligence layer classified it.
        masthead_blocks = [b for b in document.blocks if b.text.strip() == "Running Masthead"]
        assert masthead_blocks
        assert all(b.artifact is not None for b in masthead_blocks)
        assert masthead_blocks[0].artifact.artifact_class == ArtifactClass.RUNNING_HEADER

        # L3 active (blocks present): the masthead is never a heading.
        detect_headings(document)
        assert "Running Masthead" not in _content_texts(document)

        # Control: with the evidence removed, the bold masthead IS emitted
        # as a heading (first occurrence) - isolating L3 as the cause.
        document.blocks = []
        detect_headings(document)
        assert "Running Masthead" in _content_texts(document)
