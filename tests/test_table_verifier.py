"""Tests for src/verification/tables.py::TableVerifier (M-3.2) — the
sixth asset type registered with the cross-source verification engine.
"""

import json

from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.table import Table, TableCell, TableRow
from src.verification.engine import engine
from src.verification.tables import TableVerifier


def _row(cells_text) -> TableRow:
    return TableRow(cells=[TableCell(text=t, row_index=0, col_index=i) for i, t in enumerate(cells_text)])


def _canonical(
    table_id: str = "mathpix-1",
    page: int = 3,
    rows=2,
    cols=2,
    caption=None,
) -> Table:
    """A Mathpix-sourced table — no bbox (MMD has no PDF geometry),
    proportional page_number, matches production shape from
    src/mathpix/ingestor.py::_p2table_to_table()."""
    return Table(
        table_id=table_id,
        page_number=page,
        row_count=rows,
        col_count=cols,
        rows=[_row([f"r{r}c{c}" for c in range(cols)]) for r in range(rows)],
        caption=caption,
        extraction_source="mathpix",
        confidence=0.9,
    )


def _pdf_candidate(
    table_id: str = "table-p3-0",
    page: int = 3,
    rows=2,
    cols=2,
    caption=None,
    confidence: float = 0.85,
) -> Table:
    """An independently PDF-detected table (src/tables/table_extractor.py
    shape) — has bbox and a real page number, unlike the Mathpix side."""
    from src.models.bounding_box import BoundingBox

    return Table(
        table_id=table_id,
        page_number=page,
        row_count=rows,
        col_count=cols,
        rows=[_row([f"r{r}c{c}" for c in range(cols)]) for r in range(rows)],
        caption=caption,
        extraction_source="pymupdf",
        bbox=BoundingBox(x0=10, y0=20, x1=200, y1=300),
        confidence=confidence,
    )


class TestTableVerifierClassify:
    def test_perfect_match_confirms_silently(self):
        canonical = _canonical(rows=3, cols=4, caption="Table 1. Results")
        pdf_table = _pdf_candidate(rows=3, cols=4, caption="Table 1. Results")
        findings = engine.run_pdf_verification("table", [canonical], [pdf_table])
        assert findings == []

    def test_missing_mathpix_table_recovered(self):
        pdf_table = _pdf_candidate(page=9, rows=2, cols=3, caption="Table 5. New data")
        findings = engine.run_pdf_verification("table", [], [pdf_table])
        assert len(findings) == 1
        finding = findings[0]
        assert finding.kind == "missing_from_mathpix"
        assert finding.object_id is None
        recovered = json.loads(finding.proposed_value)
        assert recovered["page_number"] == 9
        assert recovered["row_count"] == 2

    def test_low_confidence_pdf_detection_still_recovered(self):
        """RECOVER never silently drops a low-confidence PDF-only
        candidate — the proposal always surfaces; the reviewer decides."""
        pdf_table = _pdf_candidate(page=4, rows=2, cols=2, confidence=0.2)
        findings = engine.run_pdf_verification("table", [], [pdf_table])
        assert len(findings) == 1
        assert findings[0].kind == "missing_from_mathpix"

    def test_missing_pdf_table_is_unconfirmed_not_removed(self):
        canonical = _canonical(page=5, rows=2, cols=2)
        findings = engine.run_pdf_verification("table", [canonical], [])
        assert len(findings) == 1
        assert findings[0].kind == "missing_from_pdf"
        assert findings[0].object_id == "mathpix-1"

    def test_caption_mismatch_alone(self):
        canonical = _canonical(rows=2, cols=2, caption="Table 1. Old caption")
        pdf_table = _pdf_candidate(rows=2, cols=2, caption="Table 1. Corrected caption")
        findings = engine.run_pdf_verification("table", [canonical], [pdf_table])
        kinds = {f.kind for f in findings}
        assert kinds == {"caption_mismatch"}

    def test_row_count_mismatch_alone(self):
        canonical = _canonical(rows=2, cols=3)
        pdf_table = _pdf_candidate(rows=5, cols=3)
        findings = engine.run_pdf_verification("table", [canonical], [pdf_table])
        kinds = {f.kind for f in findings}
        assert kinds == {"row_count_mismatch"}
        proposed = json.loads(findings[0].proposed_value)
        assert proposed["row_count"] == 5

    def test_column_count_mismatch_alone(self):
        canonical = _canonical(rows=3, cols=2)
        pdf_table = _pdf_candidate(rows=3, cols=6)
        findings = engine.run_pdf_verification("table", [canonical], [pdf_table])
        kinds = {f.kind for f in findings}
        assert kinds == {"column_count_mismatch"}

    def test_structure_mismatch_when_both_dimensions_differ(self):
        canonical = _canonical(rows=2, cols=2)
        pdf_table = _pdf_candidate(rows=6, cols=5)
        findings = engine.run_pdf_verification("table", [canonical], [pdf_table])
        kinds = {f.kind for f in findings}
        assert kinds == {"structure_mismatch"}  # not row+column separately

    def test_ambiguous_match_resolves_one_pair_and_recovers_the_other(self):
        """Two PDF candidates with identical dimensions could equally
        match one Mathpix table — the matcher must still resolve
        deterministically (one KEEP-ish match, one RECOVER), never crash
        or silently drop either."""
        canonical = _canonical(page=3, rows=2, cols=2)
        pdf_a = _pdf_candidate(table_id="table-p3-0", page=3, rows=2, cols=2)
        pdf_b = _pdf_candidate(table_id="table-p3-1", page=3, rows=2, cols=2)
        findings = engine.run_pdf_verification("table", [canonical], [pdf_a, pdf_b])
        kinds = [f.kind for f in findings]
        assert kinds == ["missing_from_mathpix"]  # one consumed the match, one recovered


class TestTableVerifierApply:
    def test_accepting_row_mismatch_updates_table_structure(self):
        verifier = TableVerifier()
        table = _canonical(rows=2, cols=2)
        document = _DocumentDouble(tables=[table])
        pdf_table = _pdf_candidate(rows=5, cols=2)
        correction = CorrectionRecord(
            object_type="table",
            object_id="mathpix-1",
            field="row_count_mismatch",
            original_value=json.dumps(
                {"caption": None, "row_count": 2, "col_count": 2, "rows": [r.model_dump() for r in table.rows], "bbox": None}
            ),
            proposed_value=json.dumps(
                {
                    "caption": None,
                    "row_count": 5,
                    "col_count": 2,
                    "rows": [r.model_dump() for r in pdf_table.rows],
                    "bbox": pdf_table.bbox.model_dump(),
                }
            ),
            status=CorrectionStatus.ACCEPTED,
        )
        verifier.apply(document, correction)
        assert table.row_count == 5
        assert table.bbox is not None

    def test_reverting_row_mismatch_restores_original_structure(self):
        verifier = TableVerifier()
        table = _canonical(rows=2, cols=2)
        document = _DocumentDouble(tables=[table])
        original_payload = json.dumps(
            {"caption": None, "row_count": 2, "col_count": 2, "rows": [r.model_dump() for r in table.rows], "bbox": None}
        )
        proposed_payload = json.dumps(
            {"caption": None, "row_count": 5, "col_count": 2, "rows": [r.model_dump() for r in table.rows], "bbox": None}
        )
        correction = CorrectionRecord(
            object_type="table",
            object_id="mathpix-1",
            field="row_count_mismatch",
            original_value=original_payload,
            proposed_value=proposed_payload,
            status=CorrectionStatus.ACCEPTED,
        )
        verifier.apply(document, correction)
        assert table.row_count == 5

        verifier.revert(document, correction)
        assert table.row_count == 2

    def test_accepting_missing_from_mathpix_recovers_a_new_table(self):
        verifier = TableVerifier()
        document = _DocumentDouble(tables=[])
        pdf_table = _pdf_candidate(table_id="table-p9-0", page=9, rows=2, cols=3)
        correction = CorrectionRecord(
            object_type="table",
            object_id=None,
            field="missing_from_mathpix",
            original_value="",
            proposed_value=pdf_table.model_dump_json(),
            status=CorrectionStatus.ACCEPTED,
        )
        verifier.apply(document, correction)
        assert len(document.tables) == 1
        assert document.tables[0].page_number == 9
        assert document.tables[0].row_count == 2

    def test_low_confidence_apply_is_a_no_op(self):
        verifier = TableVerifier()
        table = _canonical(rows=2, cols=2)
        document = _DocumentDouble(tables=[table])
        correction = CorrectionRecord(
            object_type="table",
            object_id="mathpix-1",
            field="low_confidence",
            original_value="",
            proposed_value="",
            status=CorrectionStatus.ACCEPTED,
        )
        verifier.apply(document, correction)
        assert table.row_count == 2  # untouched


class TestTableRegisteredWithEngine:
    def test_table_is_a_registered_asset_type(self):
        # Importing src.verification.tables registers it at module load
        # time (see _register() at the bottom of that file) — the same
        # pattern every other asset type uses.
        assert "table" in engine._verifiers


class _DocumentDouble:
    """Minimal stand-in for Document — apply()/revert() only touch
    .tables, so a full pydantic Document isn't needed."""

    def __init__(self, tables):
        self.tables = tables
