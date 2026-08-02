"""The correction rail is one pipeline, not two (path-agnostic entry).

Before this, seven pipeline call sites each hand-rolled the same
"record these findings" sequence — extend verification_findings, then
findings_to_corrections — six of them inside an ``if _mathpix_path``
branch, and the seventh (artifact suppression) had already drifted into a
different shape. The rail's semantics therefore lived in the pipeline, and
which asset types could produce corrections was decided by a branch.

Two things fix that, and they are what these tests pin:

* ``engine.record_findings`` is the single entry point, so the rail's
  rules (autonomy per finding; only unresolved findings reach the
  reviewer queue) are defined once.
* ``SemanticVerifier.inspect`` is the single-source producer hook and
  ``engine.run_inspection`` calls it for every registered verifier, so a
  type joins the rail by implementing a method rather than by a pipeline
  edit.
"""

from typing import Any, Dict, List, Optional

import pytest

from src.models.contracts import Document, Metadata
from src.models.correction import NON_TERMINAL_STATUSES, CorrectionRecord, CorrectionStatus
from src.models.verification import Finding, RuleSpec
from src.verification.base import SemanticVerifier
from src.verification.engine import CrossSourceVerificationEngine
from src.verification.matching import MatchResult, MultiSignalMatcher


class _RecordingVerifier(SemanticVerifier):
    """Minimal single-source verifier: reports what it was told to."""

    asset_type = "widget"

    def __init__(self, findings: Optional[List[Finding]] = None) -> None:
        self._findings = findings or []
        self.applied: List[str] = []

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        return MultiSignalMatcher([])

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Any]:
        return []

    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        return []

    def inspect(self, document: Any) -> List[Finding]:
        return list(self._findings)

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {"defect": RuleSpec(rule_id="WIDGET_001", reason_code="WIDGET_DEFECT")}

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        self.applied.append(correction.proposed_value)


def _finding(auto_apply: bool = False, proposed: str = "fixed") -> Finding:
    return Finding(
        asset_type="widget",
        kind="defect",
        object_id="w-1",
        original_value="broken",
        proposed_value=proposed,
        auto_apply=auto_apply,
    )


@pytest.fixture
def document() -> Document:
    return Document(source_pdf_path="x.pdf", metadata=Metadata(filename="x.pdf", page_count=1))


@pytest.fixture
def engine() -> CrossSourceVerificationEngine:
    # A fresh engine, not the module singleton — registering a fake asset
    # type on the shared one would leak into every other test.
    return CrossSourceVerificationEngine()


class TestSingleEntryPoint:
    def test_reviewable_finding_is_recorded_and_queued(self, engine, document) -> None:
        engine.register(_RecordingVerifier())
        engine.record_findings(document, [_finding()], provider="rawrs_native")

        assert len(document.corrections) == 1
        assert document.corrections[0].status is CorrectionStatus.PROPOSED
        assert document.corrections[0].provider == "rawrs_native"
        # PROPOSED is unresolved, so it belongs in the reviewer's queue.
        assert len(document.verification_findings) == 1

    def test_auto_apply_finding_is_applied_and_not_queued(self, engine, document) -> None:
        verifier = _RecordingVerifier()
        engine.register(verifier)
        engine.record_findings(document, [_finding(auto_apply=True)], provider="rawrs_native")

        assert document.corrections[0].status is CorrectionStatus.AUTO_APPLIED
        assert verifier.applied == ["fixed"], "the engine must apply an auto_apply finding"
        # Already decided — it is an audit row, not a review item. Queuing it
        # would bury the findings that genuinely need a human.
        assert document.verification_findings == []

    def test_mixed_batch_is_split_correctly(self, engine, document) -> None:
        verifier = _RecordingVerifier()
        engine.register(verifier)
        engine.record_findings(
            document,
            [_finding(auto_apply=True, proposed="a"), _finding(proposed="b")],
            provider="rawrs_native",
        )

        statuses = {c.proposed_value: c.status for c in document.corrections}
        assert statuses == {
            "a": CorrectionStatus.AUTO_APPLIED,
            "b": CorrectionStatus.PROPOSED,
        }
        assert verifier.applied == ["a"]
        assert [f.proposed_value for f in document.verification_findings] == ["b"]

    def test_terminal_status_never_reaches_the_review_queue(self, engine, document) -> None:
        # The rule is stated against the shared partition, not a literal
        # list, so the queue and REVIEW_001's export gate cannot disagree.
        engine.register(_RecordingVerifier())
        engine.record_findings(
            document, [_finding()], provider="manual_reviewer", status=CorrectionStatus.EDITED
        )
        assert CorrectionStatus.EDITED not in NON_TERMINAL_STATUSES
        assert len(document.corrections) == 1
        assert document.verification_findings == []

    def test_defaults_match_the_previous_hardcoded_values(self, engine, document) -> None:
        # Every pre-existing cross-source call site passed neither argument.
        engine.register(_RecordingVerifier())
        engine.record_findings(document, [_finding()])
        assert document.corrections[0].provider == "mathpix"
        assert document.corrections[0].status is CorrectionStatus.PROPOSED


class TestPathAgnosticProducers:
    def test_inspection_collects_from_every_registered_verifier(self, engine, document) -> None:
        engine.register(_RecordingVerifier([_finding(), _finding(proposed="second")]))
        assert len(engine.run_inspection(document)) == 2

    def test_verifier_without_inspect_contributes_nothing(self, engine, document) -> None:
        # The base default is empty, which is why adding the hook changed
        # no existing verifier's behaviour.
        class _CrossSourceOnly(_RecordingVerifier):
            asset_type = "legacy"

            def inspect(self, document: Any) -> List[Finding]:
                return SemanticVerifier.inspect(self, document)

        engine.register(_CrossSourceOnly())
        assert engine.run_inspection(document) == []

    def test_a_failing_verifier_does_not_break_the_pass(self, engine, document) -> None:
        class _Broken(_RecordingVerifier):
            asset_type = "broken"

            def inspect(self, document: Any) -> List[Finding]:
                raise RuntimeError("detector blew up")

        engine.register(_Broken())
        engine.register(_RecordingVerifier([_finding()]))
        # One misbehaving asset type must not cost the document every
        # other type's findings.
        assert len(engine.run_inspection(document)) == 1

    def test_no_registered_verifiers_yields_nothing(self, engine, document) -> None:
        assert engine.run_inspection(document) == []


class TestArtifactSuppressionJoinsViaTheHook:
    """The real producer, proving the hook is used rather than decorative."""

    def test_artifact_verifier_reports_through_inspect(self) -> None:
        from src.models.bounding_box import BoundingBox
        from src.models.text_block import (
            ArtifactClass,
            ArtifactClassification,
            PhysicalZone,
            TextBlock,
        )
        from src.verification.artifacts import ArtifactSuppressionVerifier

        block = TextBlock(
            page_number=1,
            text="Brinkmann",
            bbox=BoundingBox(x0=0, y0=0, x1=10, y1=5),
            order=0,
            physical_zone=PhysicalZone.HEADER,
            artifact=ArtifactClassification(
                artifact_class=ArtifactClass.RUNNING_HEADER, confidence=0.5, evidence=["repeats"]
            ),
        )
        document = Document(
            source_pdf_path="x.pdf",
            metadata=Metadata(filename="x.pdf", page_count=1),
            blocks=[block],
        )

        findings = ArtifactSuppressionVerifier().inspect(document)
        assert len(findings) == 1
        # Autonomy rides on the finding, so the engine — not the pipeline —
        # decides to apply it.
        assert findings[0].auto_apply is True
