"""W-2a — a paragraph can be named.

Paragraph was the one detected object of its class with no ``id``. Every
sibling SemanticObject backfills one, and without it a paragraph cannot
be the ``object_id`` of a CorrectionRecord — which is what a reviewer
prose edit needs. Measured before this change: 990 paragraphs across the
benchmark corpus, none addressable.

The identity is derived from *source*, not from position. The sibling
convention is ``{type}-{document_order}``, and that is the one thing this
cannot copy: ``document_order`` is a list counter, so inserting an
earlier paragraph would rename every paragraph after it and a correction
recorded against the old name would land on someone else's prose.
"""

from pathlib import Path

import pytest

from src.models.bounding_box import BoundingBox
from src.models.contracts import Document, Metadata, Page, Paragraph, TextBlock
from src.ocr.extractor import extract_text
from src.parser.pdf_parser import parse_pdf
from src.structure.paragraph_assembly import assemble_paragraphs
from src.structure.structure_detector import detect_structure

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"


def _paragraph(**overrides) -> Paragraph:
    fields = dict(page_number=1, text="Some ordinary prose.", source_block_ids=["p1:b4"])
    fields.update(overrides)
    return Paragraph(**fields)


class TestIdentityIsAssigned:
    def test_a_native_paragraph_is_named_after_its_first_block(self) -> None:
        assert _paragraph(source_block_ids=["p1:b4", "p1:b5"]).id == "paragraph-p1:b4"

    def test_a_mathpix_paragraph_is_named_after_its_source_line(self) -> None:
        # The import path records no TextBlocks, so the .mmd line — a
        # coordinate in the source document, not an index into a list — is
        # the stable basis available there.
        assert _paragraph(source_block_ids=[], source_line=42).id == "paragraph-line-42"

    def test_an_explicit_id_is_never_overwritten(self) -> None:
        assert _paragraph(id="paragraph-supplied").id == "paragraph-supplied"

    def test_a_paragraph_with_no_stable_basis_is_not_given_an_unstable_one(self) -> None:
        # A hand-built fixture, never a pipeline product. Inventing an id
        # from document_order here would be exactly the positional
        # identity this design rejects, so it stays unnamed and honest.
        assert _paragraph(source_block_ids=[], document_order=3).id is None


class TestIdentityIsStable:
    def test_rebuilding_the_same_paragraph_reproduces_the_same_id(self) -> None:
        first = _paragraph(source_block_ids=["p2:b9"])
        second = _paragraph(source_block_ids=["p2:b9"])
        assert first.id == second.id == "paragraph-p2:b9"

    def test_identity_survives_a_persistence_round_trip(self) -> None:
        original = _paragraph(source_block_ids=["p3:b1"])
        restored = Paragraph.model_validate_json(original.model_dump_json())
        assert restored.id == original.id

    def test_identity_does_not_depend_on_list_position(self) -> None:
        # The defect a document_order-based id would have: inserting an
        # earlier paragraph must not rename the ones after it.
        later = _paragraph(source_block_ids=["p1:b7"], document_order=1)
        same_paragraph_shifted = _paragraph(source_block_ids=["p1:b7"], document_order=99)
        assert later.id == same_paragraph_shifted.id

    def test_identical_text_still_yields_distinct_identities(self) -> None:
        first = _paragraph(text="Ibid.", source_block_ids=["p4:b2"])
        second = _paragraph(text="Ibid.", source_block_ids=["p9:b6"])
        assert first.id != second.id


class TestExistingFieldsAreUnchanged:
    def test_every_other_field_keeps_its_value(self) -> None:
        bbox = BoundingBox(x0=1, y0=2, x1=3, y1=4)
        paragraph = _paragraph(
            page_number=7,
            text="Prose.",
            bbox=bbox,
            source_block_ids=["p7:b1", "p7:b2"],
            document_order=5,
            source_line=11,
        )
        assert paragraph.page_number == 7
        assert paragraph.text == "Prose."
        assert paragraph.bbox == bbox
        assert paragraph.source_block_ids == ["p7:b1", "p7:b2"]
        assert paragraph.document_order == 5
        assert paragraph.source_line == 11
        assert paragraph.object_type == "paragraph"


class TestBothConstructionPathsProduceIdentity:
    """The two real paths. Anything else that builds a Paragraph is a
    fixture; the pipeline has exactly these."""

    def test_the_native_assembly_path_names_every_paragraph(self) -> None:
        document = detect_structure(
            extract_text(parse_pdf(SAMPLE_PDF_DIR / "5.Teachingas a profession_Calderhead.pdf"))
        )
        paragraphs = assemble_paragraphs(document)

        assert paragraphs
        assert all(p.id for p in paragraphs)
        assert all(p.id.startswith("paragraph-") for p in paragraphs)

    def test_the_mathpix_path_names_every_paragraph(self) -> None:
        # The ingestor sets source_line and no source_block_ids, so this
        # pins that the second basis actually fires on that path's shape.
        imported = Paragraph(
            page_number=2, text="Imported prose.", document_order=0, source_line=17
        )
        assert imported.id == "paragraph-line-17"


class TestCorpusIdentityIsCollisionFree:
    @pytest.mark.parametrize(
        "filename",
        [
            "1. Nature of Enquiry.pdf",
            "2.FolkPedagogy_Bruner_PsychDimensions_New.pdf",
            "7.brinkman-learner-centred-education-reform-india-missing-beliefs.pdf",
        ],
    )
    def test_no_two_paragraphs_in_a_document_share_an_id(self, filename: str) -> None:
        # These three carry genuinely duplicated prose — Nature has 379
        # paragraphs and 296 distinct texts — so they are the real test of
        # "identical text, distinct identity", not a synthetic one.
        document = detect_structure(extract_text(parse_pdf(SAMPLE_PDF_DIR / filename)))
        paragraphs = assemble_paragraphs(document)

        ids = [p.id for p in paragraphs]
        assert len(ids) == len(set(ids))
        assert len({p.text for p in paragraphs}) < len(paragraphs)  # duplicates really exist
        assert all(ids)


class TestParagraphIsNowAddressable:
    """The regression this milestone exists to prevent: a paragraph must
    be nameable the way its siblings are, so W-2b can make it the
    ``object_id`` of a CorrectionRecord. No correction behaviour is
    implemented here — only the identity it will require."""

    def test_a_paragraph_can_be_found_by_id_like_any_other_semantic_object(self) -> None:
        blocks = [
            TextBlock(
                page_number=1,
                text=f"Line {i}",
                bbox=BoundingBox(x0=72, y0=40 + i * 20, x1=400, y1=56 + i * 20),
                order=i,
            )
            for i in range(3)
        ]
        paragraphs = [
            Paragraph(page_number=1, text=f"Prose {i}.", source_block_ids=[b.block_id])
            for i, b in enumerate(blocks)
        ]
        document = Document(
            source_pdf_path="x.pdf",
            metadata=Metadata(filename="x.pdf", page_count=1),
            pages=[Page(page_number=1, cleaned_text="Prose.")],
            blocks=blocks,
            paragraphs=paragraphs,
        )

        target = paragraphs[1].id
        found = next((p for p in document.paragraphs if p.id == target), None)
        assert found is not None
        assert found.text == "Prose 1."
