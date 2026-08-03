"""The architectural guardrail — ADR-016 … ADR-020, mechanically.

Two halves. The static half asserts the codebase still has the shape the ADRs
describe. The runtime half asserts the properties a projection must hold that
no import graph can express: identity stability and determinism.

As with the projection checker, every invariant gets a test that makes it
FIRE, not only one that makes it pass.
"""

from collections import Counter
from types import SimpleNamespace

import pytest

from src.architecture.contract import GeneratedObject, Limitation, ProjectionContract
from src.architecture.invariants import (
    EXCEPTIONS,
    check_all,
    check_correction_rail,
    check_layering,
    check_projection_contracts,
    check_reading_order_not_stored,
)
from src.benchmark.projection import ProjectionReport, _check_set, check_projection
from src.models.bounding_box import BoundingBox
from src.models.heading import Heading, HeadingLevel
from src.models.text_block import TextBlock


# --------------------------------------------------------------------------- #
# static: the architecture still has the shape the ADRs describe
# --------------------------------------------------------------------------- #

class TestArchitectureHolds:
    def test_no_violations(self) -> None:
        violations = check_all()
        assert violations == [], "\n".join(str(v) for v in violations)

    @pytest.mark.parametrize(
        "check",
        [
            check_layering,
            check_reading_order_not_stored,
            check_correction_rail,
            check_projection_contracts,
        ],
        ids=lambda c: c.__name__,
    )
    def test_each_check_individually(self, check) -> None:
        assert check() == []


class TestDeclaredExceptions:
    """An exception is a debt entry, not a shrug. Each must say why it exists
    and what removes it, or it is indistinguishable from an oversight."""

    def test_every_exception_is_explained_and_has_an_exit(self) -> None:
        for exc in EXCEPTIONS:
            assert exc.reason.strip(), exc
            assert exc.retired_by.strip(), exc
            assert exc.invariant.startswith("AI-"), exc

    def test_the_list_is_short(self) -> None:
        """A guardrail with a long exception list is one nobody reads. If this
        trips, the question is whether the architecture moved — not whether to
        raise the number."""
        assert len(EXCEPTIONS) <= 5, [e.subject for e in EXCEPTIONS]


# --------------------------------------------------------------------------- #
# PI-1 read strictly: materialized, or diagnosed. There is no third state.
# --------------------------------------------------------------------------- #

def _contract(*codes: str) -> ProjectionContract:
    return ProjectionContract(
        format_id="test",
        generates=(GeneratedObject(kind="heading", identity="Generated", reason="test"),),
        limitations=tuple(Limitation(code=c, kind="heading", reason="test") for c in codes),
    )


class TestDiagnosedAbsence:
    def test_absence_under_a_declared_limitation_is_diagnosed_not_lost(self) -> None:
        report = ProjectionReport(document="t")
        _check_set(
            report,
            "heading",
            Counter({"A Title": 1}),
            Counter(),
            authorized_absent={"A Title": "rendered_elsewhere"},
            contract=_contract("rendered_elsewhere"),
        )
        assert report.ok
        assert [f.kind for f in report.findings] == ["diagnosed_absence"]

    def test_absence_under_an_undeclared_limitation_is_a_violation(self) -> None:
        """The checker will not invent an excuse the projection did not make."""
        report = ProjectionReport(document="t")
        _check_set(
            report,
            "heading",
            Counter({"A Title": 1}),
            Counter(),
            authorized_absent={"A Title": "invented_reason"},
            contract=_contract("some_other_code"),
        )
        assert [v.kind for v in report.violations] == ["undeclared_limitation"]

    def test_absence_with_no_reason_at_all_is_a_lost_object(self) -> None:
        report = ProjectionReport(document="t")
        _check_set(report, "heading", Counter({"A Title": 1}), Counter(), contract=_contract())
        assert [v.kind for v in report.violations] == ["lost_object"]

    def test_undeclared_generated_object_is_a_violation(self) -> None:
        report = ProjectionReport(document="t")
        _check_set(report, "heading", Counter(), Counter({"Surprise": 1}), contract=_contract())
        assert [v.kind for v in report.violations] == ["invented_object"]

    def test_declared_generated_object_is_a_finding(self) -> None:
        report = ProjectionReport(document="t")
        _check_set(report, "heading", Counter(), Counter({"Generated": 1}), contract=_contract())
        assert report.ok
        assert [f.kind for f in report.findings] == ["renderer_generated_object"]


class TestMarkdownContractIsHonoured:
    def test_the_real_contract_declares_the_absences_the_checker_produces(self) -> None:
        """Guards the coupling that matters: if someone adds a new authorized
        absence to the checker without declaring it on the projection, this
        fails rather than silently widening what may vanish."""
        from src.benchmark.projection import _authorized_absent_headings
        from src.markdown.markdown_builder import PROJECTION_CONTRACT
        from src.models.front_matter import FrontMatter

        doc = SimpleNamespace(
            blocks=[],
            tables=[],
            headings=[],
            footnotes=[],
            images=[],
            front_matter=FrontMatter(title="T", title_source_texts=["T"]),
        )
        for code in _authorized_absent_headings(doc).values():
            assert code in PROJECTION_CONTRACT.limitation_codes(), code


# --------------------------------------------------------------------------- #
# runtime: identity stability
# --------------------------------------------------------------------------- #

def _block(text: str, order: int, y: float = 100.0) -> TextBlock:
    return TextBlock(
        page_number=1,
        text=text,
        bbox=BoundingBox(x0=50.0, y0=y, x1=250.0, y1=y + 10.0),
        order=order,
        source_block_index=0,
    )


class TestIdentityStability:
    """ADR-018 rule 1: identity lives on the objects, not on positions. Two
    renderings of one document must realize the same identities, or an anchor
    from one render is meaningless in the next — and anchors are the whole
    editing story."""

    def _doc(self):
        return SimpleNamespace(
            blocks=[_block("Section One", 0), _block("Body prose.", 1, 112.0)],
            tables=[],
            footnotes=[],
            images=[],
            lists=[],
            pages=[],
            front_matter=None,
            headings=[
                Heading(
                    level=HeadingLevel.H2,
                    text="Section One",
                    page_number=1,
                    document_order=0,
                    is_page_marker=False,
                    source_block_id="p1:b0",
                )
            ],
            source_pdf_path="fixture.pdf",
        )

    def test_block_identity_is_derived_not_minted(self) -> None:
        """block_id must be a function of the block, so two Documents built
        from the same page agree without coordination."""
        assert _block("x", 3).block_id == _block("different text", 3).block_id == "p1:b3"

    def test_repeated_checks_realize_the_same_identities(self) -> None:
        doc, md = self._doc(), "## Section One\n\nBody prose.\n"
        first, second = check_projection(doc, md), check_projection(doc, md)
        assert first.counts == second.counts
        assert first.ok and second.ok

    def test_traversal_identities_match_the_objects_they_point_at(self) -> None:
        """ContentStream nodes must reference model ids, never mint their own —
        otherwise a second traversal produces nodes nobody can correlate."""
        from src.structure.content_stream import build_content_stream

        doc = self._doc()
        stream = build_content_stream(doc)
        model_ids = {b.block_id for b in doc.blocks} | {str(h.id) for h in doc.headings}
        assert stream.nodes, "expected a non-empty traversal"
        for node in stream.nodes:
            assert node.object_id in model_ids, node

    def test_two_traversals_of_one_document_agree(self) -> None:
        from src.structure.content_stream import build_content_stream

        doc = self._doc()
        a = [n.object_id for n in build_content_stream(doc).nodes]
        b = [n.object_id for n in build_content_stream(doc).nodes]
        assert a == b
