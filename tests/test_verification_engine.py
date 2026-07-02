"""Tests for src/verification/engine.py's registry/dispatch.

Uses a throwaway "toy" AssetVerifier (asset_type="toy") registered on a
fresh engine instance — not the shared module-level singleton, and not
FigureAssetVerifier — specifically to prove the engine never special-cases
"figure" anywhere. If these tests only worked with a real figure verifier,
that would mean the engine wasn't actually generic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import pytest

from src.models.correction import CorrectionStatus
from src.models.document import Document
from src.models.metadata import Metadata
from src.models.validation_issue import Severity
from src.models.verification import Finding, RuleSpec
from src.verification.engine import CrossSourceVerificationEngine, UnknownAssetTypeError
from src.verification.matching import MatchedPair, MatchResult, MultiSignalMatcher, WeightedSignal


@dataclass
class ToyItem:
    name: str


def _exact_name(a: ToyItem, b: ToyItem):
    return 1.0 if a.name == b.name else None


class ToyAssetVerifier:
    asset_type = "toy"

    def build_import_matcher(self) -> MultiSignalMatcher:
        return MultiSignalMatcher([WeightedSignal(name="exact", fn=_exact_name, min_confidence=0.9)])

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        return MultiSignalMatcher([WeightedSignal(name="exact", fn=_exact_name, min_confidence=0.9)])

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Any]:
        return [pair.a for pair in match_result.pairs] + list(match_result.unmatched_b)

    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        findings = []
        for item in match_result.unmatched_a:
            findings.append(Finding(asset_type=self.asset_type, kind="toy_missing", object_id=item.name, message=f"missing {item.name}"))
        for pair in match_result.pairs:
            if pair.confidence < 0.99:
                findings.append(Finding(asset_type=self.asset_type, kind="toy_low_confidence", object_id=pair.a.name, confidence=pair.confidence, message="low confidence"))
        return findings

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {
            "toy_missing": RuleSpec(rule_id="TOY_001", reason_code="TOY_MISSING", severity="warning"),
            "toy_low_confidence": RuleSpec(rule_id="TOY_002", reason_code="TOY_LOW_CONF", severity="info"),
        }


@pytest.fixture
def engine() -> CrossSourceVerificationEngine:
    e = CrossSourceVerificationEngine()
    e.register(ToyAssetVerifier())
    return e


def _document() -> Document:
    return Document(source_pdf_path="dummy.pdf", metadata=Metadata(filename="dummy.pdf", page_count=1))


class TestRegistryDispatch:
    def test_unregistered_asset_type_raises(self, engine: CrossSourceVerificationEngine) -> None:
        with pytest.raises(UnknownAssetTypeError):
            engine.run_import("nonexistent", [], [])

    def test_run_import_dispatches_to_registered_verifier(self, engine: CrossSourceVerificationEngine) -> None:
        canonical, findings = engine.run_import("toy", [ToyItem("a")], [ToyItem("a")])
        assert canonical == [ToyItem("a")]
        assert findings == []

    def test_run_import_reports_unmatched_a_as_findings(self, engine: CrossSourceVerificationEngine) -> None:
        canonical, findings = engine.run_import("toy", [ToyItem("a")], [])
        assert canonical == []
        assert len(findings) == 1
        assert findings[0].kind == "toy_missing"

    def test_run_pdf_verification_dispatches(self, engine: CrossSourceVerificationEngine) -> None:
        findings = engine.run_pdf_verification("toy", [ToyItem("a")], [ToyItem("a")])
        assert findings == []


class TestGenericTranslation:
    def test_findings_to_validation_issues_uses_verifiers_rule_table(self, engine: CrossSourceVerificationEngine) -> None:
        document = _document()
        findings = [Finding(asset_type="toy", kind="toy_missing", object_id="a", message="missing a")]

        issues = engine.findings_to_validation_issues(document, findings)

        assert len(issues) == 1
        assert issues[0].rule_id == "TOY_001"
        assert issues[0].severity == Severity.WARNING
        assert issues[0].message == "missing a"

    def test_findings_to_corrections_appends_correction_records(self, engine: CrossSourceVerificationEngine) -> None:
        document = _document()
        assert document.corrections == []
        findings = [Finding(asset_type="toy", kind="toy_missing", object_id="a", evidence="ev", message="missing a")]

        engine.findings_to_corrections(document, findings)

        assert len(document.corrections) == 1
        record = document.corrections[0]
        assert record.object_type == "toy"
        assert record.object_id == "a"
        assert record.reason_code == "TOY_MISSING"
        assert record.status == CorrectionStatus.PROPOSED
        assert record.provider == "mathpix"

    def test_finding_with_unknown_kind_is_skipped_by_both_translations(self, engine: CrossSourceVerificationEngine) -> None:
        document = _document()
        findings = [Finding(asset_type="toy", kind="no_such_kind", message="ignored")]

        issues = engine.findings_to_validation_issues(document, findings)
        engine.findings_to_corrections(document, findings)

        assert issues == []
        assert document.corrections == []

    def test_finding_for_unregistered_asset_type_is_skipped(self, engine: CrossSourceVerificationEngine) -> None:
        document = _document()
        findings = [Finding(asset_type="never_registered", kind="whatever", message="x")]

        assert engine.findings_to_validation_issues(document, findings) == []
        engine.findings_to_corrections(document, findings)
        assert document.corrections == []
