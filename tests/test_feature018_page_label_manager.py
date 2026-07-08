"""Tests for FEATURE_018: Page Label Manager.

Covers:
  - Page/Document model: new page-label fields, PageLabelSection
  - src/structure/page_label_resolver.py: roman conversion, section
    precedence, manual-override precedence, prefix/suffix
  - structure_detector._detect_printed_label: confidence/conflict tuple
  - validator._check_page_labels: PAGE_004-008
  - GET/PATCH/PUT page-label API endpoints
  - Correction-history round-trip via the existing generic Corrections API
  - Markdown/DOCX download regen-on-demand for page label corrections
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.jobs import Job, JobStatus, _jobs
from src.api.main import app
from src.models.contracts import (
    Document,
    Heading,
    HeadingLevel,
    Metadata,
    Page,
    PageLabelSection,
    PageLabelStatus,
    PageLabelStyle,
    Severity,
)
from src.pipeline.phase1_pipeline import PipelineResult
from src.structure.page_label_resolver import format_number, resolve_page_labels
from src.structure.structure_detector import _detect_printed_label
from src.validation.validator import _check_page_labels


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_jobs():
    _jobs.clear()
    yield
    _jobs.clear()


@pytest.fixture()
def client():
    return TestClient(app)


def _make_doc(pages: list[Page] | None = None) -> Document:
    doc = Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=len(pages) if pages else 1),
    )
    doc.pages = pages or [Page(page_number=1)]
    return doc


def _inject_job(doc: Document, job_id: str = "test-job-018") -> str:
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


def _line(text: str, y0: float, y1: float) -> dict:
    return {"spans": [{"text": text}], "bbox": (0, y0, 10, y1)}


def _page_dict(*lines: dict) -> dict:
    return {"blocks": [{"lines": list(lines)}]}


# ===========================================================================
# Model: new Page/Document fields, PageLabelSection
# ===========================================================================


class TestPageLabelModel:
    def test_page_defaults_are_backward_compatible(self):
        page = Page(page_number=1)
        assert page.label_confidence is None
        assert page.label_conflict is False
        assert page.page_label is None
        assert page.page_label_status == PageLabelStatus.DETECTED

    def test_document_page_label_sections_defaults_empty(self):
        doc = _make_doc()
        assert doc.page_label_sections == []

    def test_page_label_section_construction(self):
        section = PageLabelSection(
            start_page=1, end_page=5, style=PageLabelStyle.ROMAN_LOWER, start_number=1
        )
        assert section.prefix == ""
        assert section.suffix == ""


# ===========================================================================
# Resolver
# ===========================================================================


class TestFormatNumber:
    def test_arabic_passthrough(self):
        assert format_number(42, PageLabelStyle.ARABIC) == "42"

    def test_roman_lower_round_trips(self):
        assert format_number(1, PageLabelStyle.ROMAN_LOWER) == "i"
        assert format_number(4, PageLabelStyle.ROMAN_LOWER) == "iv"
        assert format_number(9, PageLabelStyle.ROMAN_LOWER) == "ix"
        assert format_number(40, PageLabelStyle.ROMAN_LOWER) == "xl"

    def test_roman_upper(self):
        assert format_number(9, PageLabelStyle.ROMAN_UPPER) == "IX"

    def test_none_style_returns_none(self):
        assert format_number(5, PageLabelStyle.NONE) is None


class TestResolvePageLabels:
    def test_no_sections_falls_back_to_printed_label(self):
        doc = _make_doc([Page(page_number=1, printed_label="7")])
        resolve_page_labels(doc)
        assert doc.pages[0].page_label == "7"
        assert doc.pages[0].page_label_status == PageLabelStatus.DETECTED

    def test_no_sections_no_printed_label_stays_none(self):
        doc = _make_doc([Page(page_number=1)])
        resolve_page_labels(doc)
        assert doc.pages[0].page_label is None

    def test_section_overrides_detected_fallback(self):
        doc = _make_doc([Page(page_number=1, printed_label="99")])
        doc.page_label_sections = [
            PageLabelSection(start_page=1, end_page=1, style=PageLabelStyle.ARABIC, start_number=5)
        ]
        resolve_page_labels(doc)
        assert doc.pages[0].page_label == "5"
        assert doc.pages[0].page_label_status == PageLabelStatus.APPROVED

    def test_manual_override_wins_over_section(self):
        doc = _make_doc([Page(page_number=1)])
        doc.pages[0].page_label = "custom"
        doc.pages[0].page_label_status = PageLabelStatus.OVERRIDDEN
        doc.page_label_sections = [
            PageLabelSection(start_page=1, end_page=1, style=PageLabelStyle.ARABIC, start_number=1)
        ]
        resolve_page_labels(doc)
        assert doc.pages[0].page_label == "custom"
        assert doc.pages[0].page_label_status == PageLabelStatus.OVERRIDDEN

    def test_prefix_and_suffix(self):
        doc = _make_doc([Page(page_number=1)])
        doc.page_label_sections = [
            PageLabelSection(
                start_page=1, end_page=1, style=PageLabelStyle.ARABIC,
                start_number=3, prefix="A-", suffix="-final",
            )
        ]
        resolve_page_labels(doc)
        assert doc.pages[0].page_label == "A-3-final"

    def test_offset_shifts_whole_section(self):
        doc = _make_doc([Page(page_number=1), Page(page_number=2)])
        doc.page_label_sections = [
            PageLabelSection(start_page=1, end_page=2, style=PageLabelStyle.ARABIC, start_number=100)
        ]
        resolve_page_labels(doc)
        assert [p.page_label for p in doc.pages] == ["100", "101"]

    def test_restart_mid_document(self):
        pages = [Page(page_number=n) for n in range(1, 5)]
        doc = _make_doc(pages)
        doc.page_label_sections = [
            PageLabelSection(start_page=1, end_page=2, style=PageLabelStyle.ROMAN_LOWER, start_number=1),
            PageLabelSection(start_page=3, end_page=4, style=PageLabelStyle.ARABIC, start_number=1),
        ]
        resolve_page_labels(doc)
        assert [p.page_label for p in doc.pages] == ["i", "ii", "1", "2"]

    def test_returns_changed_page_numbers_only(self):
        doc = _make_doc([Page(page_number=1, printed_label="1"), Page(page_number=2, printed_label="2")])
        resolve_page_labels(doc)  # first resolve: both change from None -> value
        changed = resolve_page_labels(doc)  # second resolve: nothing changes
        assert changed == []


# ===========================================================================
# Detection confidence
# ===========================================================================


class TestDetectPrintedLabelConfidence:
    def test_zero_candidates(self):
        label, confidence, conflict = _detect_printed_label(_page_dict(), page_height=1000)
        assert (label, confidence, conflict) == (None, None, False)

    def test_one_candidate_high_confidence(self):
        page_dict = _page_dict(_line("42", 0, 10))  # within top margin of 1000pt page
        label, confidence, conflict = _detect_printed_label(page_dict, page_height=1000)
        assert label == "42"
        assert confidence == 1.0
        assert conflict is False

    def test_two_candidates_conflict(self):
        page_dict = _page_dict(_line("3", 0, 10), _line("5", 0, 10))
        label, confidence, conflict = _detect_printed_label(page_dict, page_height=1000)
        assert label is None
        assert confidence is None
        assert conflict is True


# ===========================================================================
# Validation rules PAGE_004-008
# ===========================================================================


class TestPageLabelValidation:
    def test_page_004_duplicate_labels(self):
        doc = _make_doc([Page(page_number=1, page_label="1"), Page(page_number=2, page_label="1")])
        issues = _check_page_labels(doc)
        assert any(i.rule_id == "PAGE_004" and i.severity == Severity.ERROR for i in issues)

    def test_page_005_missing_label_in_section(self):
        doc = _make_doc([Page(page_number=1)])  # no page_label set
        doc.page_label_sections = [
            PageLabelSection(start_page=1, end_page=1, style=PageLabelStyle.ARABIC)
        ]
        issues = _check_page_labels(doc)
        assert any(i.rule_id == "PAGE_005" and i.severity == Severity.ERROR for i in issues)

    def test_page_005_not_flagged_when_style_none(self):
        doc = _make_doc([Page(page_number=1)])
        doc.page_label_sections = [
            PageLabelSection(start_page=1, end_page=1, style=PageLabelStyle.NONE)
        ]
        issues = _check_page_labels(doc)
        assert not any(i.rule_id == "PAGE_005" for i in issues)

    def test_page_006_overlapping_sections(self):
        doc = _make_doc([Page(page_number=1), Page(page_number=2)])
        doc.page_label_sections = [
            PageLabelSection(start_page=1, end_page=2, style=PageLabelStyle.ARABIC),
            PageLabelSection(start_page=2, end_page=3, style=PageLabelStyle.ARABIC),
        ]
        issues = _check_page_labels(doc)
        assert any(i.rule_id == "PAGE_006" and i.severity == Severity.ERROR for i in issues)

    def test_page_007_conflict_flagged(self):
        doc = _make_doc([Page(page_number=1, label_conflict=True)])
        issues = _check_page_labels(doc)
        assert any(i.rule_id == "PAGE_007" and i.severity == Severity.WARNING for i in issues)

    def test_page_008_unreviewed_conflict_flagged(self):
        page = Page(page_number=1, label_conflict=True)
        page.page_label_status = PageLabelStatus.DETECTED
        doc = _make_doc([page])
        issues = _check_page_labels(doc)
        assert any(i.rule_id == "PAGE_008" and i.severity == Severity.WARNING for i in issues)

    def test_page_008_not_flagged_once_reviewed(self):
        page = Page(page_number=1, label_conflict=True)
        page.page_label_status = PageLabelStatus.OVERRIDDEN
        doc = _make_doc([page])
        issues = _check_page_labels(doc)
        assert not any(i.rule_id == "PAGE_008" for i in issues)
        # PAGE_007 (conflict existed) still fires regardless of review status.
        assert any(i.rule_id == "PAGE_007" for i in issues)

    def test_no_issues_for_clean_document(self):
        doc = _make_doc([Page(page_number=1, page_label="1"), Page(page_number=2, page_label="2")])
        assert _check_page_labels(doc) == []


# ===========================================================================
# API
# ===========================================================================


class TestGetPageLabelsApi:
    def test_returns_pages_sorted_with_sections(self):
        doc = _make_doc([Page(page_number=2, page_label="2"), Page(page_number=1, page_label="1")])
        doc.page_label_sections = [PageLabelSection(start_page=1, end_page=2, style=PageLabelStyle.ARABIC)]
        job_id = _inject_job(doc, "pl-get")
        resp = TestClient(app).get(f"/api/documents/{job_id}/page-labels")
        assert resp.status_code == 200
        body = resp.json()
        assert [p["page_number"] for p in body["pages"]] == [1, 2]
        assert len(body["sections"]) == 1

    def test_unknown_job_404s(self):
        resp = TestClient(app).get("/api/documents/does-not-exist/page-labels")
        assert resp.status_code == 404


class TestPatchPageLabelApi:
    def test_override_sets_status_and_appends_correction(self, client):
        doc = _make_doc([Page(page_number=1, page_label="1", printed_label="1")])
        job_id = _inject_job(doc, "pl-override")

        resp = client.patch(
            f"/api/documents/{job_id}/page-labels/1",
            json={"action": "override", "label": "xii"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["page_label"] == "xii"
        assert body["page_label_status"] == "overridden"

        corrections = client.get(f"/api/documents/{job_id}/corrections?object_type=page_label")
        entries = corrections.json()["corrections"]
        assert len(entries) == 1
        assert entries[0]["current_value"] == "1"
        assert entries[0]["suggested_value"] == "xii"

    def test_override_requires_label(self, client):
        doc = _make_doc([Page(page_number=1)])
        job_id = _inject_job(doc, "pl-override-missing")
        resp = client.patch(
            f"/api/documents/{job_id}/page-labels/1", json={"action": "override", "label": ""}
        )
        assert resp.status_code == 422

    def test_reset_reverts_to_detected(self, client):
        doc = _make_doc([Page(page_number=1, printed_label="9")])
        job_id = _inject_job(doc, "pl-reset")

        client.patch(f"/api/documents/{job_id}/page-labels/1", json={"action": "override", "label": "zz"})
        resp = client.patch(f"/api/documents/{job_id}/page-labels/1", json={"action": "reset"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["page_label"] == "9"
        assert body["page_label_status"] == "detected"

    def test_unknown_page_404(self, client):
        doc = _make_doc([Page(page_number=1)])
        job_id = _inject_job(doc, "pl-404")
        resp = client.patch(
            f"/api/documents/{job_id}/page-labels/99", json={"action": "override", "label": "x"}
        )
        assert resp.status_code == 404


class TestSectionsApi:
    def test_apply_section_updates_labels_and_appends_corrections(self, client):
        doc = _make_doc([Page(page_number=1), Page(page_number=2)])
        job_id = _inject_job(doc, "pl-sections")

        resp = client.put(
            f"/api/documents/{job_id}/page-label-sections",
            json={"sections": [
                {"start_page": 1, "end_page": 2, "style": "roman_lower", "start_number": 1, "prefix": "", "suffix": ""}
            ]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert [p["page_label"] for p in body["pages"]] == ["i", "ii"]

        corrections = client.get(f"/api/documents/{job_id}/corrections?object_type=page_label")
        assert len(corrections.json()["corrections"]) == 2

    def test_invalid_style_returns_422(self, client):
        doc = _make_doc([Page(page_number=1)])
        job_id = _inject_job(doc, "pl-bad-style")
        resp = client.put(
            f"/api/documents/{job_id}/page-label-sections",
            json={"sections": [{"start_page": 1, "end_page": 1, "style": "not_a_style", "start_number": 1, "prefix": "", "suffix": ""}]},
        )
        assert resp.status_code == 422

    def test_manual_override_untouched_by_section(self, client):
        doc = _make_doc([Page(page_number=1)])
        job_id = _inject_job(doc, "pl-override-preserved")
        client.patch(f"/api/documents/{job_id}/page-labels/1", json={"action": "override", "label": "kept"})

        resp = client.put(
            f"/api/documents/{job_id}/page-label-sections",
            json={"sections": [{"start_page": 1, "end_page": 1, "style": "arabic", "start_number": 500, "prefix": "", "suffix": ""}]},
        )
        assert resp.status_code == 200
        page = next(p for p in resp.json()["pages"] if p["page_number"] == 1)
        assert page["page_label"] == "kept"
        assert page["page_label_status"] == "overridden"


# ===========================================================================
# Markdown/DOCX regen + H6 marker sync
# ===========================================================================


class TestExportRegenerationOnPageLabelChange:
    def _doc_with_marker(self) -> Document:
        doc = _make_doc([Page(page_number=1, printed_label="1")])
        doc.headings = [
            Heading(level=HeadingLevel.H6, text="1", page_number=1, document_order=0, is_page_marker=True)
        ]
        return doc

    def test_override_updates_existing_h6_heading_text(self, client):
        doc = self._doc_with_marker()
        job_id = _inject_job(doc, "pl-marker-sync")

        client.patch(f"/api/documents/{job_id}/page-labels/1", json={"action": "override", "label": "xlv"})

        marker = next(h for h in doc.headings if h.is_page_marker and h.page_number == 1)
        assert marker.text == "xlv"

    def test_markdown_download_regenerates_after_override(self, client):
        doc = self._doc_with_marker()
        doc.pages[0].raw_text = "Body text."
        doc.pages[0].cleaned_text = "Body text."
        job_id = _inject_job(doc, "pl-md-regen")

        client.patch(f"/api/documents/{job_id}/page-labels/1", json={"action": "override", "label": "xlv"})

        resp = client.get(f"/api/documents/{job_id}/download/markdown")
        assert resp.status_code == 200
        assert "xlv" in resp.text
