"""V-1a — a reconciliation finding needs a second source that could speak.

``import_provider`` says whether there is something to reconcile *against*.
These tests pin the other half: whether there was anything to reconcile
*with*. A detector that ran and found nothing still has an opinion; a
detector with no text layer to read has none, and that difference is the
whole milestone.
"""

from typing import Any, List

import pytest

from src.models.contracts import BoundingBox, Document, Metadata, Page, TextBlock
from src.verification.base import SemanticVerifier, text_evidence_available
from src.verification.callouts import CalloutVerifier
from src.verification.figures import FigureVerifier
from src.verification.footnotes import FootnoteVerifier
from src.verification.headings import HeadingVerifier
from src.verification.lists import ListVerifier
from src.verification.tables import TableVerifier

GATED = (HeadingVerifier, ListVerifier, TableVerifier, FootnoteVerifier)


def _block() -> TextBlock:
    return TextBlock(
        page_number=1,
        text="a line the PDF's text layer actually carried",
        bbox=BoundingBox(x0=0, y0=0, x1=100, y1=10),
        order=0,
    )


def _document(*, blocks: bool, provider: str = "mathpix") -> Any:
    document = Document(
        source_pdf_path="synthetic.pdf",
        metadata=Metadata(filename="synthetic.pdf", page_count=1),
        pages=[Page(page_number=1)],
    )
    document.import_provider = provider
    document.blocks = [_block()] if blocks else []
    return document


class TestTheCapability:
    def test_the_default_is_true_so_an_unknown_verifier_keeps_speaking(self) -> None:
        """A verifier that never heard of this capability must keep producing
        findings — the default is the fail-closed property."""

        class Unaware(SemanticVerifier):
            asset_type = "unaware"

            def build_pdf_matcher(self):  # pragma: no cover - never called
                raise NotImplementedError

            def classify(self, match_result, **context):  # pragma: no cover
                raise NotImplementedError

            def to_canonical(self, match_result, **context):  # pragma: no cover
                raise NotImplementedError

            def rule_table(self):  # pragma: no cover
                return {}

            def apply(self, document, correction):  # pragma: no cover
                raise NotImplementedError

        assert Unaware().second_source_available(_document(blocks=False)) is True

    def test_text_evidence_is_read_from_the_document_not_a_provider(self) -> None:
        assert text_evidence_available(_document(blocks=True)) is True
        assert text_evidence_available(_document(blocks=False)) is False
        assert text_evidence_available(object()) is False

    @pytest.mark.parametrize("verifier", [cls() for cls in GATED])
    def test_the_four_reconciling_verifiers_require_text_evidence(
        self, verifier: SemanticVerifier
    ) -> None:
        assert verifier.second_source_available(_document(blocks=True)) is True
        assert verifier.second_source_available(_document(blocks=False)) is False

    @pytest.mark.parametrize("verifier", [FigureVerifier(), CalloutVerifier()])
    def test_figures_and_callouts_are_not_gated_by_text_evidence(
        self, verifier: SemanticVerifier
    ) -> None:
        """A scan's image objects are real evidence, and a callout has no
        PDF-side source that could be absent — neither may be suppressed."""
        assert verifier.second_source_available(_document(blocks=False)) is True


class TestSuppressionHappensBeforeDetection:
    """The guard sits in front of the expensive second source: on a scanned
    document those detectors are exactly what we refuse to pay for."""

    @pytest.mark.parametrize(
        "verifier, module, detector",
        [
            (HeadingVerifier(), "src.headings.heading_detector", "detect_headings_from_pdf"),
            (ListVerifier(), "src.lists.list_detector", "detect_lists_from_pdf"),
            (TableVerifier(), "src.tables.table_extractor", "extract_tables"),
            (
                FootnoteVerifier(),
                "src.footnotes.footnote_detector",
                "detect_footnote_pdf_candidates",
            ),
        ],
    )
    def test_no_text_evidence_means_the_detector_is_never_called(
        self, verifier, module, detector, monkeypatch
    ) -> None:
        import importlib

        called: List[str] = []
        monkeypatch.setattr(
            importlib.import_module(module),
            detector,
            lambda *a, **k: called.append(detector) or [],
        )

        findings = verifier.inspect(_document(blocks=False), output_root="unused")

        assert called == []
        assert [f for f in findings if "unconfirmed" in f.kind] == []

    @pytest.mark.parametrize(
        "verifier, module, detector",
        [
            (HeadingVerifier(), "src.headings.heading_detector", "detect_headings_from_pdf"),
            (ListVerifier(), "src.lists.list_detector", "detect_lists_from_pdf"),
            (TableVerifier(), "src.tables.table_extractor", "extract_tables"),
        ],
    )
    def test_text_evidence_present_means_the_detector_still_runs(
        self, verifier, module, detector, monkeypatch
    ) -> None:
        """Source available and zero objects found is a real answer, and the
        comparison must still happen."""
        import importlib

        called: List[str] = []
        monkeypatch.setattr(
            importlib.import_module(module),
            detector,
            lambda *a, **k: called.append(detector) or [],
        )

        verifier.inspect(_document(blocks=True), output_root="unused")

        assert called == [detector]

    def test_a_detector_that_raises_is_not_treated_as_absence(self, monkeypatch) -> None:
        """Parser failure is not proof that the source was silent, so the
        failure surfaces (the engine logs it) rather than quietly becoming a
        suppression."""
        import importlib

        def _boom(*_a, **_k):
            raise RuntimeError("pdf unreadable")

        monkeypatch.setattr(
            importlib.import_module("src.lists.list_detector"),
            "detect_lists_from_pdf",
            _boom,
        )

        with pytest.raises(RuntimeError):
            ListVerifier().inspect(_document(blocks=True))


class TestWhatMustSurvive:
    def test_the_footnote_single_source_half_still_speaks_without_text_evidence(
        self, monkeypatch
    ) -> None:
        """FOOTNOTE_VERIFY_004 is RAWRS's own reading, not a comparison."""
        sentinel = object()
        monkeypatch.setattr(
            FootnoteVerifier,
            "_unlinked_body_findings",
            staticmethod(lambda doc: [sentinel]),
        )

        assert FootnoteVerifier().inspect(_document(blocks=False)) == [sentinel]

    def test_the_native_path_is_unchanged(self) -> None:
        """No provider, no reconciliation — before and after V-1a."""
        native = _document(blocks=True, provider="")

        assert HeadingVerifier().inspect(native) == []
        assert ListVerifier().inspect(native) == []
        assert TableVerifier().inspect(native) == []


class TestTheRuleTablesAreUntouched:
    """V-1a changes when a verifier speaks, never what it says."""

    def test_gated_verifiers_keep_their_rule_ids(self) -> None:
        rules = {
            spec.rule_id for cls in GATED for spec in cls().rule_table().values()
        }

        assert {"HEADING_VERIFY_001", "LIST_VERIFY_001", "TABLE_VERIFY_002"} <= rules
        assert "FOOTNOTE_VERIFY_004" in rules
