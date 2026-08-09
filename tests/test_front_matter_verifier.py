"""L5'b-2 — the review rail for front matter RAWRS cannot classify.

Not a missing-front-matter detector: L5'b-1 fixed the one demonstrated
detection defect, and a page with no extractable text stays silent
(DOC_001 owns that). What this covers is the honest remainder — a line
the evidence places inside the front matter that no supported role fits,
surfaced as a question rather than answered with a guess.
"""

from pathlib import Path
from typing import List

import pytest

import src.verification.frontmatter  # noqa: F401 - registers the verifier
from src.frontmatter.front_matter_extractor import (
    extract_front_matter,
    unresolved_front_matter_lines,
)
from src.models.bounding_box import BoundingBox
from src.models.contracts import Document, Metadata, Page, TextBlock
from src.models.correction import CorrectionStatus
from src.models.front_matter import FrontMatter, FrontMatterItem, FrontMatterRole
from src.models.text_block import ArtifactClass, ArtifactClassification
from src.ocr.extractor import extract_text
from src.parser.pdf_parser import parse_pdf
from src.structure.structure_detector import detect_structure
from src.verification.engine import engine
from src.verification.frontmatter import UNRESOLVED_LINE, FrontMatterVerifier

SAMPLE_PDF_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"


def _block(text: str, size: float, order: int) -> TextBlock:
    return TextBlock(
        page_number=1,
        text=text,
        bbox=BoundingBox(x0=72, y0=40 + order * 20, x1=400, y1=56 + order * 20),
        order=order,
        font_size=size,
    )


def _titled_document(extra: List[TextBlock], body_size: float = 10.0) -> Document:
    """A document whose title is detected, plus whatever follows it."""
    title = _block("A Detected Title", 24.0, 0)
    body = [
        _block(f"ordinary body line number {i} on the page", body_size, 100 + i) for i in range(8)
    ]
    blocks = [title, *extra, *body]
    front_matter = FrontMatter(
        title="A Detected Title",
        title_source_texts=[title.text],
        items=[
            FrontMatterItem(
                role=FrontMatterRole.TITLE,
                text=title.text,
                source_block_id=title.block_id,
                document_order=0,
                page_number=1,
            )
        ],
    )
    return Document(
        source_pdf_path="fm.pdf",
        metadata=Metadata(filename="fm.pdf", page_count=1),
        pages=[Page(page_number=1, cleaned_text="\n".join(b.text for b in blocks))],
        blocks=blocks,
        front_matter=front_matter,
    )


def _corpus_document(filename: str) -> Document:
    return extract_front_matter(
        detect_structure(extract_text(parse_pdf(SAMPLE_PDF_DIR / filename)))
    )


class TestWhatBecomesAFinding:
    def test_nature_reports_its_unclassifiable_subtitle(self) -> None:
        document = _corpus_document("1. Nature of Enquiry.pdf")
        findings = FrontMatterVerifier().inspect(document)

        assert len(findings) == 1
        finding = findings[0]
        assert finding.kind == UNRESOLVED_LINE
        assert finding.object_id == "p1:b94"  # 'Setting the field'
        assert "Setting the field" in finding.message
        assert "font_size=18.0" in finding.evidence
        assert "body_font_size=9.5" in finding.evidence
        assert "title_font_size=24.0" in finding.evidence

    def test_the_finding_names_no_role(self) -> None:
        # The whole point: RAWRS states the unresolved fact and stops.
        # Saying "author" or "subtitle" here would be the human's call
        # made by the machine.
        finding = FrontMatterVerifier().inspect(_corpus_document("1. Nature of Enquiry.pdf"))[0]

        assert finding.proposed_value == ""
        assert finding.original_value == ""
        assert finding.confidence is None
        lowered = finding.message.lower()
        assert "author" not in lowered
        assert "subtitle" not in lowered

    def test_folk_pedagogy_reports_its_publisher_imprint(self) -> None:
        # Nature is not the only candidate. feature_008's affiliation
        # guard rejects this line *as an affiliation* — correctly, and
        # without saying what it is instead.
        findings = FrontMatterVerifier().inspect(
            _corpus_document("2.FolkPedagogy_Bruner_PsychDimensions_New.pdf")
        )

        assert [f.object_id for f in findings] == ["p1:b2"]
        assert "HARVARD UNIVERSITY PRESS" in findings[0].message

    @pytest.mark.parametrize(
        "filename",
        [
            "1.Aims of Education and the teacher_Dhankar_PhilPers (1).pdf",
            "3. sockett_profession.pdf",
            "5.Teachingas a profession_Calderhead.pdf",
            "6. Fullan&Hargreaves_teacherasaperson.pdf",
            "7.brinkman-learner-centred-education-reform-india-missing-beliefs.pdf",
        ],
    )
    def test_documents_whose_front_matter_resolves_are_silent(self, filename: str) -> None:
        assert FrontMatterVerifier().inspect(_corpus_document(filename)) == []

    @pytest.mark.parametrize(
        "filename",
        [
            "2. Social research strategies Bryman.pdf",
            "4. O Leary_Developing the research questions.pdf",
            "4.Teaching as a professional discipline-Chapter 1.pdf",
        ],
    )
    def test_no_extractable_evidence_means_no_finding(self, filename: str) -> None:
        # No page-1 text layer. There is nothing to have an opinion about,
        # and DOC_001 already reports the absence.
        assert FrontMatterVerifier().inspect(_corpus_document(filename)) == []


class TestWhatDoesNotBecomeAFinding:
    def test_ordinary_body_text_does_not(self) -> None:
        document = _titled_document([])
        assert FrontMatterVerifier().inspect(document) == []

    def test_a_claimed_line_does_not(self) -> None:
        # An author the extractor already claimed is resolved by
        # definition, so it is not an open question.
        author = _block("Jane Doe", 14.0, 1)
        document = _titled_document([author])
        document.front_matter.items.append(
            FrontMatterItem(
                role=FrontMatterRole.AUTHOR,
                text=author.text,
                source_block_id=author.block_id,
                document_order=1,
                page_number=1,
            )
        )
        assert FrontMatterVerifier().inspect(document) == []

    def test_a_running_title_does_not(self) -> None:
        # Unlike title discovery — where excluding artifacts would delete
        # three real corpus titles — a running head inside the byline band
        # is an artifact, not unresolved semantics.
        masthead = _block("A Repeated Running Head", 14.0, 1)
        masthead.artifact = ArtifactClassification(
            artifact_class=ArtifactClass.RUNNING_TITLE, confidence=0.9, evidence=["repeats"]
        )
        assert FrontMatterVerifier().inspect(_titled_document([masthead])) == []

    def test_ocr_noise_does_not(self) -> None:
        noise = [
            _block("~Uu1;L L/~<73J", 18.5, 1),
            _block(". $L", 17.0, 2),
            _block("NuN 14k", 16.0, 3),
        ]
        assert FrontMatterVerifier().inspect(_titled_document(noise)) == []

    def test_a_bare_chapter_kicker_does_not(self) -> None:
        # "CHAPTER 1" sits beside Nature's subtitle in the same band and
        # is one word plus a number — the same word test that keeps it out
        # of titles keeps it out of the reviewer's queue.
        assert FrontMatterVerifier().inspect(_titled_document([_block("CHAPTER 1", 18.0, 1)])) == []

    def test_a_line_below_the_body_size_does_not(self) -> None:
        assert (
            FrontMatterVerifier().inspect(
                _titled_document([_block("a small print line of text", 8.0, 1)])
            )
            == []
        )


class TestCorrectionRail:
    """The reviewer's answer is the proposal — recorded, applied and
    undone through the rail every other asset type uses."""

    def _document_with_finding(self):
        line = _block("Setting the field", 18.0, 1)
        document = _titled_document([line])
        findings = FrontMatterVerifier().inspect(document)
        assert len(findings) == 1
        engine.record_findings(document, findings, provider="rawrs_native")
        return document, document.corrections[-1], line

    def test_a_finding_reaches_the_queue_unresolved(self) -> None:
        document, correction, _ = self._document_with_finding()

        assert correction.object_type == "front_matter"
        assert correction.status is CorrectionStatus.PROPOSED
        assert correction.reason_code == "FRONT_MATTER_ROLE_UNRESOLVED"
        assert correction.proposed_value == ""
        # Proposing changed nothing about the document.
        assert len(document.front_matter.items) == 1

    def test_the_reviewers_role_choice_creates_the_item(self) -> None:
        document, correction, line = self._document_with_finding()
        correction.proposed_value = "author"  # the reviewer's Edit

        engine.apply_correction(document, correction)

        created = [i for i in document.front_matter.items if i.source_block_id == line.block_id]
        assert len(created) == 1
        assert created[0].role is FrontMatterRole.AUTHOR
        assert created[0].text == "Setting the field"  # text from the block, never invented

    def test_undo_removes_what_the_decision_created(self) -> None:
        document, correction, line = self._document_with_finding()
        correction.proposed_value = "author"
        engine.apply_correction(document, correction)

        engine.revert_correction(document, correction)

        assert [i.source_block_id for i in document.front_matter.items] != [line.block_id]
        assert len(document.front_matter.items) == 1  # just the title again

    def test_applying_twice_does_not_duplicate(self) -> None:
        document, correction, line = self._document_with_finding()
        correction.proposed_value = "affiliation"
        engine.apply_correction(document, correction)
        engine.apply_correction(document, correction)

        created = [i for i in document.front_matter.items if i.source_block_id == line.block_id]
        assert len(created) == 1

    def test_rejecting_mutates_nothing(self) -> None:
        # Reject and Ignore are terminal decisions that never call apply();
        # this pins that an unresolved proposal on its own changes nothing.
        document, correction, _ = self._document_with_finding()
        correction.status = CorrectionStatus.REJECTED

        assert len(document.front_matter.items) == 1

    def test_an_unrecognised_role_creates_nothing(self) -> None:
        document, correction, _ = self._document_with_finding()
        correction.proposed_value = "subtitle"  # not a supported role

        engine.apply_correction(document, correction)

        assert len(document.front_matter.items) == 1

    def test_the_engine_dispatches_by_asset_type(self) -> None:
        assert engine._verifiers["front_matter"].__class__ is FrontMatterVerifier  # noqa: SLF001

    def test_the_rule_is_registered_as_informational(self) -> None:
        spec = FrontMatterVerifier().rule_table()[UNRESOLVED_LINE]
        assert spec.rule_id == "FRONT_MATTER_001"
        assert spec.reason_code == "FRONT_MATTER_ROLE_UNRESOLVED"
        assert spec.severity == "info"


class TestResolvedItemReachesTheDocument:
    def test_an_accepted_role_enters_the_traversal(self) -> None:
        # The decision has to reach the output, not stop at the audit row.
        from src.models.content_stream import ContentKind
        from src.structure.content_stream import build_content_stream

        line = _block("Setting the field", 18.0, 1)
        document = _titled_document([line])
        engine.record_findings(
            document, FrontMatterVerifier().inspect(document), provider="rawrs_native"
        )
        correction = document.corrections[-1]
        correction.proposed_value = "author"
        engine.apply_correction(document, correction)

        nodes = [
            n for n in build_content_stream(document).nodes if n.kind is ContentKind.FRONT_MATTER
        ]
        assert len(nodes) == 2  # the title, and the line the reviewer classified


class TestUnresolvedLineQuery:
    def test_it_reports_the_measured_evidence(self) -> None:
        line = _block("Setting the field", 18.0, 1)
        [unresolved] = unresolved_front_matter_lines(_titled_document([line]))

        assert unresolved.block_id == line.block_id
        assert unresolved.text == "Setting the field"
        assert unresolved.font_size == 18.0
        assert unresolved.title_font_size == 24.0
        assert unresolved.body_font_size == 10.0

    def test_a_document_with_no_front_matter_reports_nothing(self) -> None:
        document = Document(
            source_pdf_path="empty.pdf", metadata=Metadata(filename="empty.pdf"), pages=[]
        )
        assert unresolved_front_matter_lines(document) == []
