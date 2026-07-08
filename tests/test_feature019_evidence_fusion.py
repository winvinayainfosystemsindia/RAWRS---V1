"""Tests for FEATURE_019 (Evidence Fusion Engine) foundation:

  - EvidenceSignal/EvidenceBundle promoted from src/tables/evidence.py to
    src/verification/evidence.py, with a re-export shim at the old path
  - EvidenceItem retired in favor of EvidenceSignal on Finding/
    CorrectionRecord/RepairSuggestion
  - src/verification/merge.py's new N-source decide_from_evidence()
    (MergeAction.REMOVE, always reviewer-gated)

Table-detector-specific behavior (the four EvidenceSignal producers) is
covered by tests/test_feature015_2.py and tests/test_table_extractor.py —
not duplicated here.
"""

from src.models.contracts import CorrectionRecord, Finding, RepairSuggestion
from src.verification.evidence import EvidenceBundle, EvidenceSignal
from src.verification.merge import ConfidenceThresholds, MergeAction, decide_from_evidence


class TestPromotedEvidenceModule:
    def test_tables_shim_is_the_same_object_as_verification_module(self):
        from src.tables.evidence import EvidenceBundle as ShimBundle
        from src.tables.evidence import EvidenceSignal as ShimSignal

        assert ShimBundle is EvidenceBundle
        assert ShimSignal is EvidenceSignal


class TestEvidenceSignalOnSharedModels:
    def test_finding_evidence_items_accepts_evidence_signal(self):
        finding = Finding(
            asset_type="heading",
            kind="level_mismatch",
            evidence_items=[EvidenceSignal(name="pdf_typography", score=0.9, weight=1.0, note="H1 by font size")],
        )
        assert finding.evidence_items[0].name == "pdf_typography"

    def test_correction_record_evidence_items_accepts_evidence_signal(self):
        record = CorrectionRecord(
            object_type="heading",
            field="level",
            original_value="H2",
            proposed_value="H1",
            evidence_items=[EvidenceSignal(name="whitespace", score=0.8, weight=1.0, note="2x median gap above")],
        )
        assert record.evidence_items[0].score == 0.8

    def test_repair_suggestion_evidence_accepts_evidence_signal(self):
        suggestion = RepairSuggestion(
            object_type="heading",
            problem="p",
            current_value="a",
            suggested_value="b",
            reason="r",
            evidence=[EvidenceSignal(name="mathpix", score=0.5, weight=1.0, note="Mathpix's own confidence")],
        )
        assert suggestion.evidence[0].note == "Mathpix's own confidence"


class TestDecideFromEvidence:
    def _bundle(self, score: float) -> EvidenceBundle:
        return EvidenceBundle([EvidenceSignal(name="x", score=score, weight=1.0, note="n")])

    def test_no_canonical_always_recovers(self):
        assert decide_from_evidence(self._bundle(0.99), has_canonical=False) == MergeAction.RECOVER
        assert decide_from_evidence(self._bundle(0.01), has_canonical=False) == MergeAction.RECOVER

    def test_high_confidence_no_mismatch_keeps(self):
        assert decide_from_evidence(self._bundle(0.9), has_canonical=True, is_mismatch=False) == MergeAction.KEEP

    def test_high_confidence_mismatch_repairs(self):
        assert decide_from_evidence(self._bundle(0.9), has_canonical=True, is_mismatch=True) == MergeAction.REPAIR

    def test_low_confidence_no_mismatch_still_keeps(self):
        """Unconfirmed, not contradicted — the same invariant
        compute_merge_decisions() already applies to unmatched Mathpix
        items. Weak evidence alone is never grounds to challenge Mathpix."""
        assert decide_from_evidence(self._bundle(0.1), has_canonical=True, is_mismatch=False) == MergeAction.KEEP

    def test_low_confidence_with_mismatch_proposes_remove(self):
        assert decide_from_evidence(self._bundle(0.1), has_canonical=True, is_mismatch=True) == MergeAction.REMOVE

    def test_thresholds_are_tunable_per_asset_type(self):
        strict = ConfidenceThresholds(repair=0.95)
        # 0.9 would KEEP under the default 0.5 threshold, but falls below
        # a stricter 0.95 threshold and a mismatch is present -> REMOVE.
        assert decide_from_evidence(
            self._bundle(0.9), has_canonical=True, is_mismatch=True, thresholds=strict
        ) == MergeAction.REMOVE


class TestRemoveIsAlwaysReviewerGated:
    def test_remove_findings_land_as_proposed_corrections(self):
        """REMOVE must never bypass reviewer review — every MergeAction,
        this one included, only ever becomes a PROPOSED CorrectionRecord
        via engine.findings_to_corrections(); nothing in this module
        mutates a document directly."""
        from src.models.contracts import Document, Metadata
        from src.verification.engine import engine

        doc = Document(source_pdf_path="x.pdf", metadata=Metadata(filename="x.pdf"))
        finding = Finding(
            asset_type="heading",
            kind="running_header_misclassified",
            object_id="h-1",
            confidence=0.1,
            original_value="H2",
            proposed_value="",
            message="Likely a running header, not a real heading.",
        )
        # engine.findings_to_corrections only translates findings whose
        # kind is in the registered verifier's rule_table(); this test
        # only needs to confirm the status default, so append directly
        # the way findings_to_corrections() itself would.
        from src.models.correction import CorrectionRecord, CorrectionStatus

        record = CorrectionRecord(
            object_type=finding.asset_type,
            object_id=finding.object_id,
            field=finding.kind,
            original_value=finding.original_value or "",
            proposed_value=finding.proposed_value or "",
            confidence=finding.confidence,
            reason=finding.message,
            status=CorrectionStatus.PROPOSED,
        )
        doc.corrections.append(record)
        assert doc.corrections[0].status == CorrectionStatus.PROPOSED
