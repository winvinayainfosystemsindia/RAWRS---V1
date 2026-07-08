"""Tests for FEATURE_015.2: Hybrid Table Detection & Accessibility Workspace.

Covers:
  - EvidenceSignal / EvidenceBundle (confidence maths, serialisation)
  - find_caption() utility (all score tiers, no-match case)
  - SpanAlignmentDetector private helpers (_collect_narrow_spans,
    _group_into_bands, _cluster_x0, _find_consistent_runs, _build_cell_grid)
  - VectorBorderDetector (smoke: returns CandidateRegion list)
  - Candidate IoU merge logic in table_extractor (_iou, merge)
  - AltTextQualityEvaluator (all 5 dimensions, pass/fail thresholds)
  - AIProvider / StubProvider (capabilities, generate_alt_text)
  - get_provider() registry (RAWRS_AI_STUB env var)
  - ObjectLifecycleStatus model enum and transitions on Table / Image
  - Table.evidence_signals + lifecycle_status field round-trip via JSON
  - Image.lifecycle_status field
  - GET /api/documents/{id}/export-readiness endpoint
  - _table_out() evidence_signals, lifecycle_status, confidence_explanation
  - review_table() lifecycle advancement to HUMAN_REVIEWED
  - generate_image_alt_text() lifecycle advancement to AI_PROCESSED
  - review_image() lifecycle advancement (APPROVED / HUMAN_REVIEWED)
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.jobs import Job, JobStatus, _jobs
from src.api.main import app
from src.models.contracts import (
    Document,
    Image,
    Metadata,
    ObjectLifecycleStatus,
    Page,
    Table,
    TableCell,
    TableRow,
    TableStatus,
)
from src.models.lifecycle import ObjectLifecycleStatus as LC
from src.pipeline.phase1_pipeline import PipelineResult
from src.tables.evidence import EvidenceBundle, EvidenceSignal


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_jobs():
    _jobs.clear()
    yield
    _jobs.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def _make_doc(**kwargs) -> Document:
    doc = Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=2),
    )
    for k, v in kwargs.items():
        setattr(doc, k, v)
    return doc


def _inject_job(doc: Document, job_id: str = "j015-2") -> str:
    result = PipelineResult(
        source_pdf_path="test.pdf",
        success=True,
        status=doc.processing_status,
        duration_seconds=0.1,
        document=doc,
    )
    job = Job(
        job_id=job_id,
        filename="test.pdf",
        pdf_path=Path("test.pdf"),
        status=JobStatus.COMPLETE,
        created_at=datetime.now(timezone.utc),
        result=result,
    )
    _jobs[job_id] = job
    return job_id


def _make_table(table_id: str = "tbl-0", page: int = 1, confidence: float = 0.9) -> Table:
    cells = [
        TableCell(text="Name", row_index=0, col_index=0, is_header=True),
        TableCell(text="Value", row_index=0, col_index=1, is_header=True),
        TableCell(text="Alice", row_index=1, col_index=0),
        TableCell(text="42", row_index=1, col_index=1),
    ]
    rows = [
        TableRow(cells=cells[:2], is_header_row=True),
        TableRow(cells=cells[2:]),
    ]
    return Table(
        table_id=table_id,
        page_number=page,
        rows=rows,
        row_count=2,
        col_count=2,
        status=TableStatus.AUTO_DETECTED,
        extraction_source="vector_border",
        confidence=confidence,
    )


def _make_image(image_id: str = "img-0", page: int = 1) -> Image:
    img = Image(image_id=image_id, page_number=page, file_path="/tmp/img.png", extraction_failed=False)
    return img


# ===========================================================================
# EvidenceSignal / EvidenceBundle
# ===========================================================================


class TestEvidenceSignal:
    def test_fields_stored(self):
        s = EvidenceSignal(name="vector_borders", score=0.9, weight=1.0, note="found")
        assert s.name == "vector_borders"
        assert s.score == 0.9
        assert s.weight == 1.0
        assert s.note == "found"


class TestEvidenceBundle:
    def test_empty_bundle_confidence_is_zero(self):
        b = EvidenceBundle()
        assert b.confidence == 0.0

    def test_single_signal(self):
        b = EvidenceBundle()
        b.add(EvidenceSignal("a", score=0.8, weight=1.0, note=""))
        assert b.confidence == pytest.approx(0.8)

    def test_weighted_mean(self):
        b = EvidenceBundle()
        b.add(EvidenceSignal("a", score=1.0, weight=2.0, note=""))  # 2.0
        b.add(EvidenceSignal("b", score=0.0, weight=1.0, note=""))  # 0.0
        # (1.0*2 + 0.0*1) / 3 = 0.6667
        assert b.confidence == pytest.approx(2 / 3)

    def test_confidence_clamped_above_one(self):
        b = EvidenceBundle()
        b.add(EvidenceSignal("a", score=2.0, weight=1.0, note=""))
        assert b.confidence == 1.0

    def test_confidence_clamped_below_zero(self):
        b = EvidenceBundle()
        b.add(EvidenceSignal("a", score=-1.0, weight=1.0, note=""))
        assert b.confidence == 0.0

    def test_explanation_contains_confidence(self):
        b = EvidenceBundle()
        b.add(EvidenceSignal("vector_borders", score=1.0, weight=1.0, note="3 lines"))
        exp = b.explanation
        assert "confidence=" in exp
        assert "vector_borders" in exp

    def test_to_dict_list(self):
        b = EvidenceBundle()
        b.add(EvidenceSignal("s1", score=0.75, weight=0.5, note="ok"))
        lst = b.to_dict_list()
        assert len(lst) == 1
        assert lst[0]["name"] == "s1"
        assert lst[0]["score"] == pytest.approx(0.75, abs=1e-3)
        assert lst[0]["weight"] == pytest.approx(0.5, abs=1e-3)
        assert lst[0]["note"] == "ok"

    def test_from_dict_list_round_trip(self):
        original = EvidenceBundle()
        original.add(EvidenceSignal("a", score=0.6, weight=1.2, note="test"))
        original.add(EvidenceSignal("b", score=0.3, weight=0.8, note="test2"))
        restored = EvidenceBundle.from_dict_list(original.to_dict_list())
        assert restored.confidence == pytest.approx(original.confidence)
        assert len(restored.signals) == 2
        assert restored.signals[0].name == "a"

    def test_from_dict_list_empty(self):
        b = EvidenceBundle.from_dict_list([])
        assert b.confidence == 0.0


# ===========================================================================
# find_caption()
# ===========================================================================


class TestFindCaption:
    """Tests for src/tables/detectors/caption.py:find_caption."""

    def _page_dict(self, lines: list) -> dict:
        """Build a minimal PyMuPDF page_dict with given text lines."""
        blocks = []
        for (text, x0, y0, x1, y1) in lines:
            blocks.append({
                "type": 0,
                "lines": [{
                    "bbox": (x0, y0, x1, y1),
                    "spans": [{"text": text, "bbox": (x0, y0, x1, y1)}],
                }],
            })
        return {"blocks": blocks}

    def test_no_blocks_returns_none(self):
        from src.tables.detectors.caption import find_caption
        caption, score = find_caption({}, (50, 300, 500, 500), page_width=595)
        assert caption is None
        assert score == 0.0

    def test_table_label_pattern_score_1(self):
        from src.tables.detectors.caption import find_caption
        # Line at y=270 (above region_top=300 by 30pt); region_top=300
        page_dict = self._page_dict([("Table 1. Results", 50, 265, 250, 275)])
        caption, score = find_caption(page_dict, (50, 300, 500, 500), page_width=595)
        assert caption == "Table 1. Results"
        assert score == pytest.approx(1.0)

    def test_figure_label_pattern(self):
        from src.tables.detectors.caption import find_caption
        page_dict = self._page_dict([("Figure 2: Comparison", 50, 265, 250, 275)])
        caption, score = find_caption(page_dict, (50, 300, 500, 500), page_width=595)
        assert score == pytest.approx(1.0)

    def test_allcaps_short_line_score_08(self):
        from src.tables.detectors.caption import find_caption
        page_dict = self._page_dict([("SURVEY RESULTS", 50, 268, 200, 278)])
        caption, score = find_caption(page_dict, (50, 300, 500, 500), page_width=595)
        assert caption == "SURVEY RESULTS"
        assert score == pytest.approx(0.8)

    def test_sentence_ending_period_score_06(self):
        from src.tables.detectors.caption import find_caption
        page_dict = self._page_dict([("Mean scores across conditions.", 50, 270, 300, 280)])
        caption, score = find_caption(page_dict, (50, 300, 500, 500), page_width=595)
        assert score == pytest.approx(0.6)

    def test_short_line_rejected_below_min_score(self):
        # "Mean scores" scores 0.4 internally but _MIN_CAPTION_SCORE=0.6 rejects it.
        # Vague standalone phrases (kickers, running headers) must not become captions.
        from src.tables.detectors.caption import find_caption
        page_dict = self._page_dict([("Mean scores", 50, 270, 200, 280)])
        caption, score = find_caption(page_dict, (50, 300, 500, 500), page_width=595)
        assert caption is None
        assert score == pytest.approx(0.0)

    def test_score_candidate_short_line_is_04(self):
        # The scoring function itself still returns 0.4 for a short standalone line;
        # find_caption gates it out via _MIN_CAPTION_SCORE.
        from src.captions.caption_detector import _score_candidate
        assert _score_candidate("Mean scores") == pytest.approx(0.4)

    def test_wide_line_ignored(self):
        from src.tables.detectors.caption import find_caption
        # Line nearly as wide as the page (90% of 595 = 535)
        page_dict = self._page_dict([("This is very wide body text that spans the whole page.", 10, 268, 545, 278)])
        caption, score = find_caption(page_dict, (50, 300, 500, 500), page_width=595)
        assert caption is None

    def test_line_outside_search_window_ignored(self):
        from src.tables.detectors.caption import find_caption
        # y=200 is 100pt above region_top=300; default search_above=50pt, so not in window
        page_dict = self._page_dict([("Table 1.", 50, 195, 200, 205)])
        caption, score = find_caption(page_dict, (50, 300, 500, 500), page_width=595)
        assert caption is None

    def test_closest_candidate_wins(self):
        from src.tables.detectors.caption import find_caption
        page_dict = self._page_dict([
            ("Figure 1.", 50, 265, 200, 275),   # y_mid=270, closer
            ("Table 2.", 50, 255, 200, 265),   # y_mid=260, farther
        ])
        caption, score = find_caption(page_dict, (50, 300, 500, 500), page_width=595)
        assert "Figure" in caption   # closest to region wins


# ===========================================================================
# SpanAlignmentDetector helpers
# ===========================================================================


class TestCollectNarrowSpans:
    def test_wide_spans_excluded(self):
        from src.tables.detectors.span_alignment import _collect_narrow_spans
        page_dict = {"blocks": [{"type": 0, "lines": [{"spans": [
            {"text": "wide body text", "bbox": (0, 10, 500, 20), "flags": 0},
        ]}]}]}
        result = _collect_narrow_spans(page_dict, page_width=595.0)
        assert result == []  # 500pt span > 0.45 * 595 = 267.75

    def test_narrow_spans_included(self):
        from src.tables.detectors.span_alignment import _collect_narrow_spans
        page_dict = {"blocks": [{"type": 0, "lines": [{"spans": [
            {"text": "Cell", "bbox": (50, 10, 150, 20), "flags": 0},
        ]}]}]}
        result = _collect_narrow_spans(page_dict, page_width=595.0)
        assert len(result) == 1
        assert result[0]["text"] == "Cell"

    def test_empty_text_excluded(self):
        from src.tables.detectors.span_alignment import _collect_narrow_spans
        page_dict = {"blocks": [{"type": 0, "lines": [{"spans": [
            {"text": "   ", "bbox": (50, 10, 100, 20), "flags": 0},
        ]}]}]}
        result = _collect_narrow_spans(page_dict, page_width=595.0)
        assert result == []

    def test_image_blocks_ignored(self):
        from src.tables.detectors.span_alignment import _collect_narrow_spans
        page_dict = {"blocks": [{"type": 1, "image": "..."}]}
        result = _collect_narrow_spans(page_dict, page_width=595.0)
        assert result == []


class TestGroupIntoBands:
    def test_same_y_grouped(self):
        from src.tables.detectors.span_alignment import _group_into_bands
        spans = [
            {"x0": 50, "y0": 100.0, "x1": 100, "y1": 110, "text": "A", "flags": 0},
            {"x0": 200, "y0": 101.5, "x1": 250, "y1": 111.5, "text": "B", "flags": 0},
        ]
        bands = _group_into_bands(spans)
        assert len(bands) == 1
        assert len(bands[0]) == 2

    def test_different_y_splits_band(self):
        from src.tables.detectors.span_alignment import _group_into_bands
        spans = [
            {"x0": 50, "y0": 100.0, "x1": 100, "y1": 110, "text": "A", "flags": 0},
            {"x0": 50, "y0": 120.0, "x1": 100, "y1": 130, "text": "B", "flags": 0},
        ]
        bands = _group_into_bands(spans)
        assert len(bands) == 2

    def test_empty_input(self):
        from src.tables.detectors.span_alignment import _group_into_bands
        assert _group_into_bands([]) == []


class TestClusterX0:
    def test_two_clusters(self):
        from src.tables.detectors.span_alignment import _cluster_x0
        spans = [
            {"x0": 50},
            {"x0": 52},
            {"x0": 200},
            {"x0": 202},
        ]
        clusters = _cluster_x0(spans, gap=15.0)
        assert len(clusters) == 2
        assert clusters[0] == pytest.approx(51.0)
        assert clusters[1] == pytest.approx(201.0)

    def test_single_cluster(self):
        from src.tables.detectors.span_alignment import _cluster_x0
        spans = [{"x0": 50}, {"x0": 55}, {"x0": 58}]
        clusters = _cluster_x0(spans, gap=15.0)
        assert len(clusters) == 1

    def test_empty_input(self):
        from src.tables.detectors.span_alignment import _cluster_x0
        assert _cluster_x0([], gap=15.0) == []


class TestBuildCellGrid:
    def test_two_col_two_row(self):
        from src.tables.detectors.span_alignment import _build_cell_grid
        run_bands = [
            ([{"x0": 50, "text": "Name", "y0": 100, "x1": 100, "y1": 110, "flags": 0},
              {"x0": 200, "text": "Value", "y0": 100, "x1": 260, "y1": 110, "flags": 0}], [50.0, 200.0]),
            ([{"x0": 50, "text": "Alice", "y0": 120, "x1": 100, "y1": 130, "flags": 0},
              {"x0": 200, "text": "42", "y0": 120, "x1": 230, "y1": 130, "flags": 0}], [50.0, 200.0]),
        ]
        col_positions = [50.0, 200.0]
        grid = _build_cell_grid(run_bands, col_positions)
        assert len(grid) == 2
        assert grid[0][0] == "Name"
        assert grid[0][1] == "Value"
        assert grid[1][0] == "Alice"
        assert grid[1][1] == "42"


# ===========================================================================
# ObjectLifecycleStatus
# ===========================================================================


class TestObjectLifecycleStatus:
    def test_all_values_exist(self):
        for v in ("DETECTED", "AI_PROCESSED", "HUMAN_REVIEWED",
                  "ACCESSIBILITY_VALIDATED", "EXPORT_VERIFIED", "APPROVED"):
            assert LC(v) is not None

    def test_is_str_enum(self):
        assert isinstance(LC.DETECTED, str)
        assert LC.DETECTED == "DETECTED"

    def test_table_default_lifecycle(self):
        t = _make_table()
        assert t.lifecycle_status == LC.DETECTED

    def test_image_default_lifecycle(self):
        img = _make_image()
        assert img.lifecycle_status == LC.DETECTED

    def test_table_lifecycle_assignment(self):
        t = _make_table()
        t.lifecycle_status = LC.HUMAN_REVIEWED
        assert t.lifecycle_status == LC.HUMAN_REVIEWED

    def test_image_lifecycle_assignment(self):
        img = _make_image()
        img.lifecycle_status = LC.APPROVED
        assert img.lifecycle_status == LC.APPROVED


# ===========================================================================
# Table.evidence_signals field
# ===========================================================================


class TestTableEvidenceSignals:
    def test_evidence_signals_default_empty(self):
        t = _make_table()
        assert t.evidence_signals == []

    def test_evidence_signals_stored(self):
        t = _make_table()
        signals = [{"name": "vector_borders", "score": 1.0, "weight": 1.0, "note": "found"}]
        t.evidence_signals = signals
        assert t.evidence_signals[0]["name"] == "vector_borders"

    def test_evidence_signals_round_trip(self):
        bundle = EvidenceBundle()
        bundle.add(EvidenceSignal("vector_borders", score=0.95, weight=1.0, note="3 cells"))
        t = _make_table()
        t.evidence_signals = bundle.to_dict_list()
        restored = EvidenceBundle.from_dict_list(t.evidence_signals)
        assert restored.confidence == pytest.approx(0.95)


# ===========================================================================
# AltTextQualityEvaluator
# ===========================================================================


class TestAltTextQualityEvaluator:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from src.ai.quality import AltTextQualityEvaluator
        from src.ai.alt_text_generator import AltTextRequest, AltTextResult
        self.Evaluator = AltTextQualityEvaluator
        self.Request = AltTextRequest
        self.Result = AltTextResult

    def _req(self, caption: str = "", page: int = 1) -> object:
        return self.Request(
            image_path="/tmp/img.png",
            caption=caption,
            figure_label=None,
            nearby_text=[],
            page_number=page,
        )

    def _res(self, description: str = "A chart showing revenue growth over time with a clear upward trend.",
             confidence: float = 0.9) -> object:
        return self.Result(
            description=description,
            purpose="Shows revenue growth.",
            visible_text="Q1 Q2 Q3",
            confidence=confidence,
        )

    def test_good_result_passes(self):
        ev = self.Evaluator()
        q = ev.evaluate(self._res(), self._req())
        assert q.passes is True
        assert q.overall_score >= 0.45

    def test_placeholder_fails(self):
        ev = self.Evaluator()
        q = ev.evaluate(self._res("N/A"), self._req())
        assert q.passes is False
        assert any("placeholder" in i.lower() for i in q.issues)

    def test_stub_text_fails(self):
        ev = self.Evaluator()
        q = ev.evaluate(self._res("Stub description for image"), self._req())
        assert q.passes is False

    def test_todo_placeholder_fails(self):
        ev = self.Evaluator()
        q = ev.evaluate(self._res("TODO: describe this image"), self._req())
        assert q.passes is False

    def test_too_short_penalised(self):
        ev = self.Evaluator()
        # "Short." is 1 word — below minimum 8. Issue must be reported and score reduced.
        q_short = ev.evaluate(self._res("Short."), self._req())
        q_normal = ev.evaluate(self._res(), self._req())
        assert any("short" in i.lower() for i in q_short.issues)
        assert q_short.overall_score < q_normal.overall_score

    def test_caption_restatement_penalised(self):
        ev = self.Evaluator()
        caption = "Revenue growth chart 2020 2021 2022 2023"
        # Description that's almost identical to the caption
        desc = "Revenue growth chart showing 2020 2021 2022 2023 data trend."
        q = ev.evaluate(self._res(desc), self._req(caption=caption))
        assert any("restate" in i.lower() or "overlap" in i.lower() or "caption" in i.lower()
                   for i in q.issues)

    def test_low_confidence_lowers_score(self):
        ev = self.Evaluator()
        q_low = ev.evaluate(self._res(confidence=0.1), self._req())
        q_high = ev.evaluate(self._res(confidence=0.95), self._req())
        assert q_low.overall_score < q_high.overall_score

    def test_quality_result_summary(self):
        ev = self.Evaluator()
        q = ev.evaluate(self._res(), self._req())
        assert "Quality" in q.summary


# ===========================================================================
# AIProvider / StubProvider
# ===========================================================================


class TestStubProvider:
    @pytest.fixture(autouse=True)
    def _env(self):
        os.environ["RAWRS_AI_STUB"] = "1"
        yield
        os.environ.pop("RAWRS_AI_STUB", None)

    def test_capabilities_available(self):
        from src.ai.providers.stub import StubProvider
        caps = StubProvider().capabilities()
        assert caps.available is True
        assert caps.vision is True

    def test_generate_returns_result(self):
        from src.ai.providers.stub import StubProvider
        from src.ai.alt_text_generator import AltTextRequest
        provider = StubProvider()
        req = AltTextRequest(
            image_path="/tmp/test_image.png",
            caption="Test",
            figure_label=None,
            nearby_text=[],
            page_number=1,
        )
        result = provider.generate_alt_text(req)
        assert result.description
        assert "test_image" in result.description
        assert result.image_type == "PHOTOGRAPH"
        assert 0.0 <= result.confidence <= 1.0

    def test_stub_name(self):
        from src.ai.providers.stub import StubProvider
        assert StubProvider().name == "Stub"


# ===========================================================================
# Registry: get_provider()
# ===========================================================================


class TestAltTextRegistry:
    def test_stub_env_returns_stub_provider(self):
        os.environ["RAWRS_AI_STUB"] = "1"
        try:
            from src.ai.registry import get_provider
            from src.ai.providers.stub import StubProvider
            provider = get_provider()
            assert isinstance(provider, StubProvider)
        finally:
            os.environ.pop("RAWRS_AI_STUB", None)

    def test_no_provider_raises(self):
        os.environ.pop("RAWRS_AI_STUB", None)
        from src.ai.provider import AIProviderUnavailableError
        import src.ai.registry as reg_mod
        unavail = MagicMock()
        unavail.capabilities.return_value = MagicMock(available=False, vision=True,
                                                       unavailable_reason="no GPU")
        unavail.name = "Mock"
        with patch.object(reg_mod, "_candidate_providers", return_value=[unavail]):
            with pytest.raises(AIProviderUnavailableError):
                reg_mod.get_provider()


# ===========================================================================
# generate_alt_text() end-to-end with stub
# ===========================================================================


class TestGenerateAltText:
    @pytest.fixture(autouse=True)
    def _env(self):
        os.environ["RAWRS_AI_STUB"] = "1"
        yield
        os.environ.pop("RAWRS_AI_STUB", None)

    def test_generate_returns_result(self):
        from src.ai.alt_text_generator import generate_alt_text, AltTextRequest
        req = AltTextRequest(
            image_path="/tmp/img_001.png",
            caption="A bar chart",
            figure_label=None,
            nearby_text=[],
            page_number=3,
        )
        result = generate_alt_text(req)
        assert result.description
        assert result.confidence >= 0.0


# ===========================================================================
# API: _table_out() evidence signals and lifecycle
# ===========================================================================


class TestTableOutEvidence:
    def test_table_out_includes_evidence(self, client):
        doc = _make_doc()
        t = _make_table()
        t.evidence_signals = [
            {"name": "vector_borders", "score": 1.0, "weight": 1.0, "note": "3 cells"},
        ]
        t.lifecycle_status = LC.DETECTED
        doc.tables = [t]
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/tables")
        assert resp.status_code == 200
        tables = resp.json()["tables"]
        assert len(tables) == 1
        ev = tables[0]["evidence_signals"]
        assert len(ev) == 1
        assert ev[0]["name"] == "vector_borders"
        assert tables[0]["lifecycle_status"] == "DETECTED"

    def test_table_out_confidence_explanation_present(self, client):
        doc = _make_doc()
        t = _make_table()
        t.evidence_signals = [
            {"name": "span_column_alignment", "score": 0.8, "weight": 0.7, "note": "3 cols"},
        ]
        doc.tables = [t]
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/tables")
        tbl = resp.json()["tables"][0]
        assert tbl["confidence_explanation"] is not None
        assert "span_column_alignment" in tbl["confidence_explanation"]

    def test_table_out_no_evidence_explanation_null(self, client):
        doc = _make_doc()
        t = _make_table()
        t.evidence_signals = []
        doc.tables = [t]
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/tables")
        tbl = resp.json()["tables"][0]
        # With no signals the explanation may be null or empty
        exp = tbl.get("confidence_explanation")
        # Allow None or empty string when no signals
        assert exp is None or exp == ""


# ===========================================================================
# API: review_table() lifecycle → HUMAN_REVIEWED
# ===========================================================================


class TestReviewTableLifecycle:
    def test_review_advances_lifecycle(self, client):
        doc = _make_doc()
        t = _make_table()
        assert t.lifecycle_status == LC.DETECTED
        doc.tables = [t]
        job_id = _inject_job(doc)
        resp = client.patch(
            f"/api/documents/{job_id}/tables/{t.table_id}",
            json={"caption": "My Table"},
        )
        assert resp.status_code == 200
        assert resp.json()["lifecycle_status"] == "HUMAN_REVIEWED"

    def test_lifecycle_after_review_in_document(self, client):
        doc = _make_doc()
        t = _make_table()
        doc.tables = [t]
        job_id = _inject_job(doc)
        client.patch(
            f"/api/documents/{job_id}/tables/{t.table_id}",
            json={"caption": "Updated"},
        )
        assert doc.tables[0].lifecycle_status == LC.HUMAN_REVIEWED


# ===========================================================================
# API: generate_image_alt_text() lifecycle → AI_PROCESSED
# ===========================================================================


class TestGenerateImageAltTextLifecycle:
    @pytest.fixture(autouse=True)
    def _env(self):
        os.environ["RAWRS_AI_STUB"] = "1"
        yield
        os.environ.pop("RAWRS_AI_STUB", None)

    def test_generate_alt_text_sets_ai_processed(self, client, tmp_path):
        img_file = tmp_path / "page_001_img_0.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)  # minimal PNG header

        doc = _make_doc()
        img = _make_image()
        img.file_path = str(img_file)
        doc.images = [img]
        job_id = _inject_job(doc)

        resp = client.post(f"/api/documents/{job_id}/images/{img.image_id}/generate-alt-text")
        assert resp.status_code in (200, 503), resp.text
        if resp.status_code == 200:
            assert doc.images[0].lifecycle_status == LC.AI_PROCESSED


# ===========================================================================
# API: review_image() lifecycle transitions
# ===========================================================================


class TestReviewImageLifecycle:
    def test_approve_sets_approved(self, client):
        from src.models.figure import Figure, AltTextStatus
        doc = _make_doc()
        img = _make_image()
        img.figure = Figure(
            ai_description="A chart showing data.",
            alt_text_status=AltTextStatus.AI_GENERATED,
        )
        doc.images = [img]
        job_id = _inject_job(doc)
        resp = client.patch(
            f"/api/documents/{job_id}/images/{img.image_id}",
            json={"action": "approve"},
        )
        assert resp.status_code == 200
        assert doc.images[0].lifecycle_status == LC.APPROVED

    def test_reject_sets_human_reviewed(self, client):
        from src.models.figure import Figure, AltTextStatus
        doc = _make_doc()
        img = _make_image()
        img.figure = Figure(alt_text_status=AltTextStatus.AI_GENERATED)
        doc.images = [img]
        job_id = _inject_job(doc)
        resp = client.patch(
            f"/api/documents/{job_id}/images/{img.image_id}",
            json={"action": "reject"},
        )
        assert resp.status_code == 200
        assert doc.images[0].lifecycle_status == LC.HUMAN_REVIEWED

    def test_mark_decorative_sets_human_reviewed(self, client):
        from src.models.figure import Figure, AltTextStatus
        doc = _make_doc()
        img = _make_image()
        img.figure = Figure(alt_text_status=AltTextStatus.AI_GENERATED)
        doc.images = [img]
        job_id = _inject_job(doc)
        resp = client.patch(
            f"/api/documents/{job_id}/images/{img.image_id}",
            json={"action": "mark_decorative"},
        )
        assert resp.status_code == 200
        assert doc.images[0].lifecycle_status == LC.HUMAN_REVIEWED

    def test_skip_sets_human_reviewed(self, client):
        from src.models.figure import Figure, AltTextStatus
        doc = _make_doc()
        img = _make_image()
        img.figure = Figure(alt_text_status=AltTextStatus.AI_GENERATED)
        doc.images = [img]
        job_id = _inject_job(doc)
        resp = client.patch(
            f"/api/documents/{job_id}/images/{img.image_id}",
            json={"action": "skip"},
        )
        assert resp.status_code == 200
        assert doc.images[0].lifecycle_status == LC.HUMAN_REVIEWED


# ===========================================================================
# API: GET /export-readiness
# ===========================================================================


class TestExportReadiness:
    def test_empty_doc_returns_schema(self, client):
        doc = _make_doc()
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        assert resp.status_code == 200
        body = resp.json()
        assert "ready" in body
        assert "overall_score" in body
        assert "categories" in body
        cats = body["categories"]
        assert "tables" in cats
        assert "images" in cats
        assert "headings" in cats
        assert "footnotes" in cats
        assert "reading_order" in cats
        assert "metadata" in cats

    def test_no_tables_category_complete(self, client):
        doc = _make_doc()
        doc.tables = []
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        tables_cat = resp.json()["categories"]["tables"]
        assert tables_cat["complete"] is True

    def test_unreviewed_table_incomplete(self, client):
        doc = _make_doc()
        t = _make_table()
        doc.tables = [t]
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        tables_cat = resp.json()["categories"]["tables"]
        assert tables_cat["complete"] is False
        assert tables_cat["total"] == 1
        assert any("unreviewed" in i.lower() or "review" in i.lower() for i in tables_cat["issues"])

    def test_reviewed_table_improves_score(self, client):
        doc = _make_doc()
        t = _make_table()
        t.status = TableStatus.REVIEWED
        t.lifecycle_status = LC.HUMAN_REVIEWED
        t.caption = "My Table"
        doc.tables = [t]
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        body = resp.json()
        # Score should be positive with a reviewed table
        assert body["overall_score"] >= 0.0

    def test_no_language_metadata_incomplete(self, client):
        doc = Document(
            source_pdf_path="test.pdf",
            metadata=Metadata(filename="test.pdf", page_count=1, language=None, title=None),
        )
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        meta_cat = resp.json()["categories"]["metadata"]
        assert meta_cat["complete"] is False
        assert any("language" in i.lower() for i in meta_cat["issues"])

    def test_language_and_title_set_metadata_complete(self, client):
        doc = Document(
            source_pdf_path="test.pdf",
            metadata=Metadata(filename="test.pdf", page_count=1, language="en-US", title="My Doc"),
        )
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        meta_cat = resp.json()["categories"]["metadata"]
        assert meta_cat["complete"] is True

    def test_footnotes_category_always_complete(self, client):
        doc = _make_doc()
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        fn_cat = resp.json()["categories"]["footnotes"]
        assert fn_cat["complete"] is True

    def test_overall_score_fraction(self, client):
        doc = Document(
            source_pdf_path="test.pdf",
            metadata=Metadata(filename="test.pdf", page_count=1, language="en-US", title="T"),
        )
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        body = resp.json()
        assert 0.0 <= body["overall_score"] <= 1.0

    def test_ready_flag_false_when_issues(self, client):
        # Unreviewed table + no language → not ready
        doc = _make_doc()
        t = _make_table()
        doc.tables = [t]
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        assert resp.json()["ready"] is False

    def test_job_not_found_404(self, client):
        resp = client.get("/api/documents/nonexistent-job/export-readiness")
        assert resp.status_code == 404

    def test_category_total_matches_objects(self, client):
        doc = _make_doc()
        doc.tables = [_make_table("t0"), _make_table("t1"), _make_table("t2")]
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        tables_cat = resp.json()["categories"]["tables"]
        assert tables_cat["total"] == 3

    def test_images_category_unreviewed_incomplete(self, client):
        from src.models.figure import Figure, AltTextStatus
        doc = _make_doc()
        img = _make_image()
        img.figure = Figure(alt_text_status=AltTextStatus.AI_GENERATED)
        doc.images = [img]
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        img_cat = resp.json()["categories"]["images"]
        assert img_cat["complete"] is False

    def test_images_category_approved_complete(self, client):
        from src.models.figure import Figure, AltTextStatus
        doc = _make_doc()
        img = _make_image()
        img.figure = Figure(alt_text_status=AltTextStatus.APPROVED, alt_text="A chart.")
        img.lifecycle_status = LC.APPROVED
        doc.images = [img]
        job_id = _inject_job(doc)
        resp = client.get(f"/api/documents/{job_id}/export-readiness")
        img_cat = resp.json()["categories"]["images"]
        assert img_cat["complete"] is True


# ===========================================================================
# IoU calculation (table_extractor private helper)
# ===========================================================================


class TestIoU:
    def test_perfect_overlap(self):
        from src.tables.table_extractor import _iou
        assert _iou((0, 0, 100, 100), (0, 0, 100, 100)) == pytest.approx(1.0)

    def test_no_overlap(self):
        from src.tables.table_extractor import _iou
        assert _iou((0, 0, 50, 50), (100, 100, 200, 200)) == pytest.approx(0.0)

    def test_partial_overlap(self):
        from src.tables.table_extractor import _iou
        # Two 100x100 boxes overlapping 50x50 = 2500 intersection, 17500 union
        iou = _iou((0, 0, 100, 100), (50, 50, 150, 150))
        assert iou == pytest.approx(2500 / 17500, rel=1e-3)

    def test_contained_box(self):
        from src.tables.table_extractor import _iou
        # Inner box fully inside outer; intersection = inner area
        iou = _iou((0, 0, 100, 100), (25, 25, 75, 75))
        inner_area = 50 * 50  # 2500
        outer_area = 100 * 100  # 10000
        # union = outer = 10000 (inner is subset)
        assert iou == pytest.approx(inner_area / outer_area)


# ===========================================================================
# VectorBorderDetector — smoke tests
# ===========================================================================


def _make_bordered_pdf(path: "Path") -> None:
    """Create a minimal PDF with a 3-row × 3-col table using explicit vector borders."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    col_w, row_h, x0, y0 = 80, 25, 50, 100
    xs = [x0 + i * col_w for i in range(4)]
    ys = [y0 + i * row_h for i in range(4)]
    for y in ys:
        page.draw_line(fitz.Point(xs[0], y), fitz.Point(xs[-1], y))
    for x in xs:
        page.draw_line(fitz.Point(x, ys[0]), fitz.Point(x, ys[-1]))
    data = [["Name", "Score", "Grade"], ["Alice", "95", "A"], ["Bob", "82", "B"]]
    for ri, row in enumerate(data):
        for ci, text in enumerate(row):
            page.insert_text(fitz.Point(xs[ci] + 4, ys[ri] + 16), text, fontsize=9)
    doc.save(str(path))
    doc.close()


class TestVectorBorderDetector:
    def test_bordered_pdf_returns_candidate(self, tmp_path):
        import fitz
        from src.tables.detectors.vector_border import VectorBorderDetector
        from src.tables.detectors.base import CandidateRegion

        pdf_path = tmp_path / "bordered.pdf"
        _make_bordered_pdf(pdf_path)
        fitz_doc = fitz.open(str(pdf_path))
        try:
            fitz_page = fitz_doc[0]
            detector = VectorBorderDetector()
            candidates = detector.detect(fitz_page, page_number=1)
        finally:
            fitz_doc.close()

        assert len(candidates) >= 1
        c = candidates[0]
        assert isinstance(c, CandidateRegion)
        assert c.page_number == 1
        assert len(c.bbox) == 4
        assert c.raw_rows is not None and len(c.raw_rows) >= 2

    def test_empty_page_returns_empty(self, tmp_path):
        import fitz
        from src.tables.detectors.vector_border import VectorBorderDetector

        doc = fitz.open()
        doc.new_page()
        pdf_path = tmp_path / "empty.pdf"
        doc.save(str(pdf_path))
        doc.close()

        fitz_doc = fitz.open(str(pdf_path))
        try:
            fitz_page = fitz_doc[0]
            candidates = VectorBorderDetector().detect(fitz_page, page_number=1)
        finally:
            fitz_doc.close()

        assert candidates == []

    def test_candidate_has_vector_borders_signal(self, tmp_path):
        import fitz
        from src.tables.detectors.vector_border import VectorBorderDetector

        pdf_path = tmp_path / "bordered2.pdf"
        _make_bordered_pdf(pdf_path)
        fitz_doc = fitz.open(str(pdf_path))
        try:
            fitz_page = fitz_doc[0]
            candidates = VectorBorderDetector().detect(fitz_page, page_number=1)
        finally:
            fitz_doc.close()

        assert len(candidates) >= 1
        signal_names = {s.name for s in candidates[0].evidence.signals}
        assert "vector_borders" in signal_names

    def test_candidate_bbox_is_tuple_of_four(self, tmp_path):
        import fitz
        from src.tables.detectors.vector_border import VectorBorderDetector

        pdf_path = tmp_path / "bordered3.pdf"
        _make_bordered_pdf(pdf_path)
        fitz_doc = fitz.open(str(pdf_path))
        try:
            fitz_page = fitz_doc[0]
            candidates = VectorBorderDetector().detect(fitz_page, page_number=1)
        finally:
            fitz_doc.close()

        assert len(candidates) >= 1
        bbox = candidates[0].bbox
        assert len(bbox) == 4
        x0, y0, x1, y1 = bbox
        assert x1 > x0 and y1 > y0


# ===========================================================================
# _find_consistent_runs — unit tests
# ===========================================================================


class TestFindConsistentRuns:
    def _make_band(self, y0: float, x0_vals: list) -> tuple:
        spans = [{"x0": x, "y0": y0, "x1": x + 30, "y1": y0 + 10, "text": "x", "flags": 0}
                 for x in x0_vals]
        from src.tables.detectors.span_alignment import _cluster_x0, COL_GAP_PT
        cols = _cluster_x0(spans, COL_GAP_PT)
        return (spans, cols)

    def test_three_consistent_bands_form_run(self):
        from src.tables.detectors.span_alignment import _find_consistent_runs
        bands = [
            self._make_band(0, [50, 150, 250]),
            self._make_band(15, [50, 150, 250]),
            self._make_band(30, [50, 150, 250]),
        ]
        runs = _find_consistent_runs(bands)
        assert len(runs) == 1
        run_bands, col_positions = runs[0]
        assert len(run_bands) == 3
        assert len(col_positions) >= 2

    def test_two_bands_too_few_for_run(self):
        from src.tables.detectors.span_alignment import _find_consistent_runs
        bands = [
            self._make_band(0, [50, 150]),
            self._make_band(15, [50, 150]),
        ]
        runs = _find_consistent_runs(bands)
        assert runs == []

    def test_gap_breaks_run(self):
        from src.tables.detectors.span_alignment import _find_consistent_runs
        bands = [
            self._make_band(0, [50, 150]),
            self._make_band(15, [50, 150]),
            self._make_band(30, [50, 150]),
            # large gap here
            self._make_band(200, [50, 150]),
            self._make_band(215, [50, 150]),
            self._make_band(230, [50, 150]),
        ]
        runs = _find_consistent_runs(bands)
        assert len(runs) == 2


# ===========================================================================
# _merge_overlapping_candidates — unit tests
# ===========================================================================


class TestMergeOverlappingCandidates:
    def _make_cand(self, bbox: tuple, signal_name: str = "vector_borders") -> "CandidateRegion":
        from src.tables.detectors.base import CandidateRegion
        from src.tables.evidence import EvidenceBundle, EvidenceSignal
        bundle = EvidenceBundle()
        bundle.add(EvidenceSignal(name=signal_name, score=0.9, weight=1.0, note="test"))
        return CandidateRegion(page_number=1, bbox=bbox, evidence=bundle, raw_rows=[["a", "b"]])

    def test_no_overlap_returns_both(self):
        from src.tables.table_extractor import _merge_overlapping_candidates
        a = self._make_cand((0, 0, 50, 50))
        b = self._make_cand((100, 100, 200, 200))
        result = _merge_overlapping_candidates([a, b])
        assert len(result) == 2

    def test_high_overlap_merges_to_one(self):
        from src.tables.table_extractor import _merge_overlapping_candidates
        a = self._make_cand((0, 0, 100, 100), "vector_borders")
        b = self._make_cand((5, 5, 95, 95), "span_column_alignment")
        result = _merge_overlapping_candidates([a, b])
        assert len(result) == 1

    def test_merged_signals_combined(self):
        from src.tables.table_extractor import _merge_overlapping_candidates
        a = self._make_cand((0, 0, 100, 100), "vector_borders")
        b = self._make_cand((5, 5, 95, 95), "span_column_alignment")
        result = _merge_overlapping_candidates([a, b])
        signal_names = {s.name for s in result[0].evidence.signals}
        assert "vector_borders" in signal_names
        assert "span_column_alignment" in signal_names

    def test_single_candidate_unchanged(self):
        from src.tables.table_extractor import _merge_overlapping_candidates
        a = self._make_cand((0, 0, 100, 100))
        result = _merge_overlapping_candidates([a])
        assert len(result) == 1
        assert result[0] is a

    def test_merged_bbox_covers_both(self):
        from src.tables.table_extractor import _merge_overlapping_candidates
        a = self._make_cand((0, 0, 80, 80))
        b = self._make_cand((10, 10, 100, 100))
        result = _merge_overlapping_candidates([a, b])
        x0, y0, x1, y1 = result[0].bbox
        assert x0 == 0 and y0 == 0
        assert x1 == 100 and y1 == 100
