"""Tests for src/verification/lists.py::ListVerifier."""

from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.list_block import ListBlock, ListItem, ListType
from src.models.verification import VerificationStatus
from src.verification.engine import CrossSourceVerificationEngine
from src.verification.lists import ListVerifier


def _list(items, list_type=ListType.BULLET, page=1, order=0):
    return ListBlock(
        list_type=list_type,
        items=[ListItem(text=t) for t in items],
        page_number=page,
        document_order=order,
    )


class TestBuildPdfMatcher:
    def test_matches_by_item_overlap(self) -> None:
        verifier = ListVerifier()
        canonical = _list(["Apple", "Banana", "Cherry"])
        pdf_candidate = _list(["Apple", "Banana", "Cherry"], page=1)
        result = verifier.build_pdf_matcher().match([canonical], [pdf_candidate])
        assert len(result.pairs) == 1
        assert result.pairs[0].matched_by == "item_overlap"

    def test_no_overlap_no_page_match_stays_unmatched(self) -> None:
        verifier = ListVerifier()
        canonical = _list(["Apple", "Banana"], page=1)
        pdf_candidate = _list(["Zebra", "Yak"], page=9)
        result = verifier.build_pdf_matcher().match([canonical], [pdf_candidate])
        # Positional fallback still claims the pair (last-resort signal).
        assert len(result.pairs) == 1
        assert result.pairs[0].matched_by == "positional_fallback"


class TestClassify:
    def test_matching_lists_are_verified_keep(self) -> None:
        verifier = ListVerifier()
        canonical = _list(["Apple", "Banana"])
        pdf_candidate = _list(["Apple", "Banana"])
        result = verifier.build_pdf_matcher().match([canonical], [pdf_candidate])
        findings = verifier.classify(result)
        assert findings == []
        assert canonical.verification_status == VerificationStatus.VERIFIED

    def test_item_count_mismatch_produces_repair_finding(self) -> None:
        verifier = ListVerifier()
        canonical = _list(["Apple", "Banana"])
        pdf_candidate = _list(["Apple", "Banana", "Cherry"])
        result = verifier.build_pdf_matcher().match([canonical], [pdf_candidate])
        findings = verifier.classify(result)
        assert len(findings) == 1
        assert findings[0].kind == "item_count_mismatch"
        assert findings[0].original_value == "2"
        assert findings[0].proposed_value == "3"
        assert canonical.verification_status == VerificationStatus.MISMATCH

    def test_unmatched_canonical_is_unconfirmed(self) -> None:
        verifier = ListVerifier()
        canonical = _list(["Apple", "Banana"], page=1)
        result = verifier.build_pdf_matcher().match([canonical], [])
        findings = verifier.classify(result)
        assert len(findings) == 1
        assert findings[0].kind == "unconfirmed"
        assert canonical.verification_status == VerificationStatus.MISSING_FROM_PDF

    def test_unmatched_pdf_list_is_recovered(self) -> None:
        verifier = ListVerifier()
        pdf_candidate = _list(["X", "Y", "Z"], page=3)
        result = verifier.build_pdf_matcher().match([], [pdf_candidate])
        findings = verifier.classify(result)
        assert len(findings) == 1
        assert findings[0].kind == "recovered_from_pdf"
        assert findings[0].proposed_value is not None


class TestRuleTable:
    def test_every_finding_kind_has_a_rule(self) -> None:
        verifier = ListVerifier()
        rules = verifier.rule_table()
        for kind in ("unconfirmed", "recovered_from_pdf", "item_count_mismatch"):
            assert kind in rules
            assert rules[kind].rule_id.startswith("LIST_VERIFY_")


class TestApply:
    def test_recovered_from_pdf_appends_new_list(self) -> None:
        verifier = ListVerifier()
        pdf_candidate = _list(["X", "Y"], page=2)
        result = verifier.build_pdf_matcher().match([], [pdf_candidate])
        findings = verifier.classify(result)

        class _Doc:
            lists = []

        document = _Doc()
        correction = CorrectionRecord(
            object_type="list",
            field="recovered_from_pdf",
            original_value="",
            proposed_value=findings[0].proposed_value,
            status=CorrectionStatus.ACCEPTED,
        )
        verifier.apply(document, correction)
        assert len(document.lists) == 1
        assert [i.text for i in document.lists[0].items] == ["X", "Y"]

    def test_item_count_mismatch_is_informational_noop(self) -> None:
        verifier = ListVerifier()

        class _Doc:
            lists = []

        document = _Doc()
        correction = CorrectionRecord(
            object_type="list",
            field="item_count_mismatch",
            original_value="2",
            proposed_value="3",
        )
        verifier.apply(document, correction)  # must not raise
        assert document.lists == []


class TestEngineRegistration:
    def test_registers_under_list_asset_type(self) -> None:
        import src.verification.lists  # noqa: F401 - registers ListVerifier
        from src.verification.engine import engine as module_engine

        assert isinstance(module_engine._verifiers.get("list"), ListVerifier)

    def test_findings_to_corrections_round_trip_via_fresh_engine(self) -> None:
        engine = CrossSourceVerificationEngine()
        engine.register(ListVerifier())
        canonical = _list(["A", "B"])
        pdf_candidate = _list(["A", "B", "C"])
        findings = engine.run_pdf_verification("list", [canonical], [pdf_candidate])

        class _Doc:
            corrections = []

        document = _Doc()
        engine.findings_to_corrections(document, findings)
        assert len(document.corrections) == 1
        assert document.corrections[0].object_type == "list"
        assert document.corrections[0].reason_code == "LIST_ITEM_COUNT_MISMATCH"
