"""Tests for src/verification/artifacts.py (L2.2 artifact suppression).

The contract under test is not "artifacts disappear" — it is "artifacts
disappear *reversibly*, and only when the evidence supports it". So the
three things pinned here are:

1. **Policy.** Which artifact classes are acted on, and which are not.
   DECORATIVE_REPEATED is the one that matters: across the benchmark
   corpus it catches repeated body fragments ('practice.', 'for
   children.'), so acting on it would delete prose.
2. **Reversibility.** Suppression goes through CorrectionRecord, and undo
   restores the line — via the generic SemanticVerifier.revert(), with no
   undo logic of its own.
3. **Reach.** The decision actually changes rendered Markdown, which is
   the whole point: L2 classified artifacts for three commits while
   nothing consumed them.
"""

from pathlib import Path
from typing import List, Optional

import pytest

from src.markdown.markdown_builder import build_markdown
from src.models.bounding_box import BoundingBox
from src.models.contracts import Document, Metadata, Page
from src.models.correction import CorrectionStatus
from src.models.text_block import (
    ArtifactClass,
    ArtifactClassification,
    PhysicalZone,
    TextBlock,
)
from src.ocr.extractor import extract_text
from src.parser.pdf_parser import parse_pdf
from src.pipeline.phase1_pipeline import run_pipeline
from src.structure.structure_detector import detect_structure
from src.verification.artifacts import (
    ASSET_TYPE,
    SUPPRESS_ARTIFACT,
    ArtifactSuppressionVerifier,
    SuppressionPolicy,
    block_id,
    propose_suppressions,
)
from src.verification.engine import engine

BENCHMARK_PDFS = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"


def _block(
    text: str,
    page_number: int = 1,
    order: int = 0,
    artifact_class: Optional[ArtifactClass] = None,
    confidence: float = 0.5,
) -> TextBlock:
    classification = (
        ArtifactClassification(
            artifact_class=artifact_class, confidence=confidence, evidence=["test evidence"]
        )
        if artifact_class is not None
        else None
    )
    return TextBlock(
        page_number=page_number,
        text=text,
        bbox=BoundingBox(x0=0, y0=0, x1=100, y1=10),
        order=order,
        physical_zone=PhysicalZone.HEADER,
        artifact=classification,
    )


class TestPolicy:
    """Which classes are acted on — the evidence-driven part."""

    @pytest.mark.parametrize(
        "artifact_class,expected_policy",
        [
            (ArtifactClass.PAGE_NUMBER, SuppressionPolicy.AUTO),
            (ArtifactClass.RUNNING_HEADER, SuppressionPolicy.AUTO),
            (ArtifactClass.RUNNING_FOOTER, SuppressionPolicy.AUTO),
            (ArtifactClass.RUNNING_TITLE, SuppressionPolicy.PROPOSE),
        ],
    )
    def test_actionable_classes_produce_a_finding_under_their_policy(
        self, artifact_class: ArtifactClass, expected_policy: SuppressionPolicy
    ) -> None:
        grouped = propose_suppressions([_block("Brinkmann", artifact_class=artifact_class)])
        assert len(grouped[expected_policy]) == 1
        other = (
            SuppressionPolicy.PROPOSE
            if expected_policy is SuppressionPolicy.AUTO
            else SuppressionPolicy.AUTO
        )
        assert grouped[other] == []

    def test_decorative_repeated_is_never_acted_on(self) -> None:
        # The corpus-measured reason this class is excluded: it catches
        # repeated body fragments, not decorations. Suppressing (or even
        # proposing) these would delete real prose.
        grouped = propose_suppressions(
            [
                _block("for children.", artifact_class=ArtifactClass.DECORATIVE_REPEATED),
                _block("practice.", order=1, artifact_class=ArtifactClass.DECORATIVE_REPEATED),
            ]
        )
        assert grouped[SuppressionPolicy.AUTO] == []
        assert grouped[SuppressionPolicy.PROPOSE] == []

    def test_unclassified_content_produces_nothing(self) -> None:
        grouped = propose_suppressions([_block("ordinary body prose")])
        assert grouped[SuppressionPolicy.AUTO] == []
        assert grouped[SuppressionPolicy.PROPOSE] == []

    def test_already_suppressed_blocks_are_not_re_proposed(self) -> None:
        block = _block("Brinkmann", artifact_class=ArtifactClass.RUNNING_HEADER)
        block.suppressed = True
        grouped = propose_suppressions([block])
        assert grouped[SuppressionPolicy.AUTO] == []

    def test_finding_carries_the_classification_evidence(self) -> None:
        finding = propose_suppressions(
            [_block("Brinkmann", artifact_class=ArtifactClass.RUNNING_HEADER)]
        )[SuppressionPolicy.AUTO][0]
        assert finding.asset_type == ASSET_TYPE
        assert finding.kind == SUPPRESS_ARTIFACT
        assert finding.object_id == "p1:b0"
        assert "test evidence" in finding.evidence
        assert "Brinkmann" in finding.message

    def test_block_id_distinguishes_repeats_of_identical_text(self) -> None:
        # Artifact text repeats across pages by definition, so identity
        # must not be text-derived or every occurrence would collapse
        # into one correction.
        first = _block("Brinkmann", page_number=3, order=0)
        second = _block("Brinkmann", page_number=4, order=0)
        assert block_id(first) != block_id(second)


class TestReversibility:
    """Suppression is a CorrectionRecord, and undo restores the line."""

    def _document_with(self, blocks: List[TextBlock]) -> Document:
        return Document(
            source_pdf_path="/tmp/x.pdf",
            metadata=Metadata(filename="x.pdf", page_count=1),
            pages=[Page(page_number=1, raw_text="", cleaned_text="")],
            blocks=blocks,
        )

    def test_apply_suppresses_and_revert_restores(self) -> None:
        block = _block("Brinkmann", artifact_class=ArtifactClass.RUNNING_HEADER)
        document = self._document_with([block])
        findings = propose_suppressions(document.blocks)[SuppressionPolicy.AUTO]

        engine.findings_to_corrections(
            document, findings, provider="rawrs_native", status=CorrectionStatus.AUTO_APPLIED
        )
        correction = document.corrections[0]
        assert correction.provider == "rawrs_native"
        assert correction.status is CorrectionStatus.AUTO_APPLIED
        assert correction.reason_code == "RUNNING_ARTIFACT_SUPPRESSED"

        engine.apply_correction(document, correction)
        assert block.suppressed is True

        # Undo uses the generic SemanticVerifier.revert() — this verifier
        # writes no undo logic of its own.
        engine.revert_correction(document, correction)
        assert block.suppressed is False

    def test_apply_is_a_noop_when_the_block_is_gone(self) -> None:
        from src.models.correction import CorrectionRecord

        document = self._document_with([])
        ArtifactSuppressionVerifier().apply(
            document,
            CorrectionRecord(
                object_type=ASSET_TYPE,
                object_id="p9:b9",
                field=SUPPRESS_ARTIFACT,
                original_value="visible",
                proposed_value="suppressed",
            ),
        )  # must not raise — the audit row outlives the block

    def test_auto_applied_status_is_terminal_so_export_is_not_blocked(self) -> None:
        # REVIEW_001 blocks export on non-terminal correction statuses.
        # Emitting ~160 PROPOSED suppressions per document would make every
        # document non-exportable until a human cleared them, which is why
        # AUTO decisions are recorded AUTO_APPLIED.
        from src.accessibility.rules.corrections import CorrectionTerminalRule

        block = _block("Brinkmann", artifact_class=ArtifactClass.RUNNING_HEADER)
        document = self._document_with([block])
        findings = propose_suppressions(document.blocks)[SuppressionPolicy.AUTO]
        engine.findings_to_corrections(
            document, findings, provider="rawrs_native", status=CorrectionStatus.AUTO_APPLIED
        )
        outcomes = CorrectionTerminalRule().evaluate(document)
        assert all(o.outcome.value != "manual_review_required" for o in outcomes)


class TestSuppressionReachesTheOutput:
    """The decision has to change rendered Markdown, or none of it matters."""

    def test_suppressed_block_is_absent_from_markdown(self) -> None:
        page = Page(
            page_number=1,
            raw_text="Brinkmann\nreal body prose here\n",
            cleaned_text="Brinkmann\nreal body prose here\n",
        )
        blocks = [
            _block("Brinkmann", order=0, artifact_class=ArtifactClass.RUNNING_HEADER),
            _block("real body prose here", order=1),
        ]
        document = Document(
            source_pdf_path="/tmp/x.pdf",
            metadata=Metadata(filename="x.pdf", page_count=1),
            pages=[page],
            blocks=blocks,
        )

        before = build_markdown(document)
        assert "Brinkmann" in before

        blocks[0].suppressed = True
        after = build_markdown(document)
        assert "Brinkmann" not in after
        assert "real body prose here" in after


@pytest.mark.skipif(not BENCHMARK_PDFS.is_dir(), reason="benchmark corpus not present")
class TestAgainstTheRealCorpus:
    """A real PDF, end to end — the classes are only trustworthy because
    they were measured on these documents."""

    def test_brinkman_running_header_is_suppressed_and_recorded(self, tmp_path: Path) -> None:
        pdf = next(BENCHMARK_PDFS.glob("7.brinkman*.pdf"), None)
        if pdf is None:
            pytest.skip("Brinkman benchmark PDF not present")

        result = run_pipeline(pdf, output_root=tmp_path, enable_ocr=False)
        assert result.success is True
        document = result.document

        suppression_corrections = [c for c in document.corrections if c.field == SUPPRESS_ARTIFACT]
        assert suppression_corrections, "no artifact suppressions recorded"
        assert all(c.provider == "rawrs_native" for c in suppression_corrections)

        suppressed_blocks = [b for b in document.blocks if b.suppressed]
        assert suppressed_blocks, "no block was actually suppressed"
        # Every suppression that was applied has an audit row behind it.
        applied_ids = {
            c.object_id
            for c in suppression_corrections
            if c.status is CorrectionStatus.AUTO_APPLIED
        }
        assert {block_id(b) for b in suppressed_blocks} <= applied_ids

    def test_no_sentence_like_text_is_auto_suppressed_on_the_corpus(self) -> None:
        # The guard against the DECORATIVE_REPEATED failure mode: running
        # headers/footers/page numbers are labels, not sentences, so
        # nothing ending in sentence punctuation should be auto-suppressed.
        for pdf in sorted(BENCHMARK_PDFS.glob("*.pdf")):
            document = detect_structure(extract_text(parse_pdf(pdf)))
            auto = propose_suppressions(document.blocks)[SuppressionPolicy.AUTO]
            offenders = [
                f.message
                for f in auto
                if f.message.rstrip().rstrip("'\"").endswith((".", "?", "!"))
            ]
            assert not offenders, f"{pdf.name}: sentence-like text auto-suppressed: {offenders[:3]}"
