"""Automation-rate metrics: how much RAWRS decides on its own.

Method and caveats: docs/AUTOMATION_RATE_2026-11-01.md.

Every reviewable item lands in exactly one bucket of BUCKETS. Two numbers
come out of the buckets, and they are never combined:

(a) decided_without_human = auto_decided / all items, read from the snapshot
    taken when the pipeline finished, before any human touched the document.
(b) reviewer_kept_unchanged = accepted_unchanged / (accepted_unchanged +
    edited + rejected), read from the live Document. It reads "not measured
    yet" until MIN_REVIEWED_DOCS documents carry at least one human decision.

Checks are RAWRS's own 40-item checklist audit run on RAWRS's own DOCX
(self-graded; veraPDF in Task 3 is the independent check). warn and manual
both count as needing a human.

Rates are floored and durations ceiled to one decimal, so rounding never
flatters RAWRS. The Wilson bound is item-level and overconfident, because
items within one document are correlated; the per-document median is the
headline.
"""

from __future__ import annotations

import json
import math
import os
import statistics
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger

from src.learning.decisions import is_human_edit, outcome, wilson_interval
from src.models.correction import CorrectionRecord, CorrectionStatus
from src.models.equation import EquationStatus
from src.models.figure import AltTextStatus
from src.models.footnote import FootnoteReviewStatus
from src.models.heading import HeadingReviewStatus
from src.models.page import PageType, ReadingOrderStatus
from src.models.table import TableStatus
from src.models.validation_issue import ValidationIssueStatus

SCHEMA = "rawrs.automation-metrics/v1"
SIDECAR_SUFFIX = ".metrics.json"
CATEGORIES = ("headings", "images", "tables", "reading_order", "footnotes", "corrections", "equations")
BUCKETS = ("auto_decided", "pending_human", "accepted_unchanged", "edited", "rejected")
HUMAN_BUCKETS = ("accepted_unchanged", "edited", "rejected")
MIN_REVIEWED_DOCS = 5
MAX_REVIEW_DELTA_SECONDS = 300
CHECK_NEEDS_HUMAN = ("manual", "warn")
NOT_MEASURED = "not measured yet"
WILSON_NOTE = "item-level; overconfident because items within a document are correlated"
ESTIMATE_LABEL = "estimate: similarity to a human-remediated version"
DEFINITIONS = {
    "decided_without_human": "auto_decided / all items, at pipeline end, before any human review",
    "reviewer_kept_unchanged": "accepted_unchanged / (accepted_unchanged + edited + rejected), human-reviewed documents only",
    "checks": "RAWRS's own checklist audit of its own DOCX (self-graded); warn and manual count as needs-human",
}

_PENDING_IMAGE = (AltTextStatus.PENDING_REVIEW, AltTextStatus.SKIPPED)
_KEPT_IMAGE = (AltTextStatus.APPROVED, AltTextStatus.HUMAN_REVIEWED)
_CORRECTION_BUCKET = {
    "auto_kept": "auto_decided", "pending": "pending_human", "accepted": "accepted_unchanged",
    "edited": "edited", "rejected": "rejected", "ignored": "rejected",
    "undone": "rejected", "auto_undone": "rejected",
}
_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# per-item buckets
# --------------------------------------------------------------------------- #

def _human_index(document: Any) -> Dict[tuple, List[CorrectionRecord]]:
    """Live (not undone) reviewer records, keyed by (object_type, object_id)."""
    index: Dict[tuple, List[CorrectionRecord]] = defaultdict(list)
    for record in document.corrections:
        if record.status is not CorrectionStatus.REVERTED and is_human_edit(record):
            index[(record.object_type, str(record.object_id))].append(record)
    return index


def _codes(human: Dict[tuple, List[CorrectionRecord]], object_type: str, object_id: Any) -> set:
    return {r.reason_code for r in human.get((object_type, str(object_id)), [])}


def _heading_bucket(heading: Any, codes: set) -> str:
    if heading.review_status is HeadingReviewStatus.REJECTED or "HEADING_REJECTED_BY_REVIEWER" in codes:
        return "rejected"
    if codes or heading.review_status is HeadingReviewStatus.LEVEL_CHANGED:
        return "edited"
    if heading.review_status is HeadingReviewStatus.APPROVED:
        return "accepted_unchanged"
    return "auto_decided"


def _image_bucket(image: Any, records: List[CorrectionRecord]) -> str:
    figure = image.figure
    status = figure.alt_text_status if figure is not None and figure.alt_text_status else AltTextStatus.PENDING_REVIEW
    if not records:
        # ponytail: COMPLEX without a reviewer record never happens today
        # (only the review route sets it); counted as asking a human.
        return "pending_human" if status in _PENDING_IMAGE + (AltTextStatus.COMPLEX,) else "auto_decided"
    if status is AltTextStatus.SKIPPED:
        return "pending_human"
    if status is AltTextStatus.REJECTED:
        return "rejected"
    before = json.loads(min(records, key=lambda r: r.created_at).original_value)
    same_text = (before.get("alt_text") or "") == ((figure.alt_text if figure else "") or "")
    if same_text and (status in _KEPT_IMAGE or before.get("alt_text_status") == status.value):
        return "accepted_unchanged"
    return "edited"


def _table_bucket(table: Any, codes: set) -> str:
    # A table the reviewer had to create is one RAWRS missed: counted as edited.
    if table.status is TableStatus.MANUALLY_CREATED or codes:
        return "edited"
    if table.status is TableStatus.REVIEWED:
        return "accepted_unchanged"
    return "auto_decided"


def _reading_order_bucket(page: Any, codes: set, flagged: set) -> str:
    if page.reading_order_status is ReadingOrderStatus.CORRECTED or codes:
        return "edited"
    if page.reading_order_status is ReadingOrderStatus.APPROVED:
        return "accepted_unchanged"
    return "pending_human" if page.page_number in flagged else "auto_decided"


def _footnote_bucket(note: Any, codes: set) -> str:
    if note.review_status is FootnoteReviewStatus.REJECTED:
        return "rejected"
    if note.review_status is FootnoteReviewStatus.EDITED or codes:
        return "edited"
    if note.review_status is FootnoteReviewStatus.APPROVED:
        return "accepted_unchanged"
    return "auto_decided"


def _equation_bucket(equation: Any, codes: set) -> str:
    if codes:
        return "edited"
    return "pending_human" if equation.status is EquationStatus.FLAGGED else "auto_decided"


def _removed(human: Dict[tuple, List[CorrectionRecord]], object_type: str, present: set, code: str) -> int:
    """Objects a reviewer removed (rejected heading, deleted table): no longer in
    the document, so only their records remain. Reviewer-created ones excluded."""
    count = 0
    for (kind, object_id), records in human.items():
        codes = {r.reason_code for r in records}
        if kind == object_type and object_id not in present and code in codes and not any("CREATED" in c for c in codes):
            count += 1
    return count


def item_buckets(document: Any) -> Dict[str, Dict[str, int]]:
    """Count every reviewable item of ``document`` into exactly one bucket.

    Each item is one decision: "this is a heading at this level", "this alt
    text", "this page's order", "this proposed correction". Reviewer
    CorrectionRecords are attributed to the object they changed, never to
    "corrections", so nothing is counted twice.
    """
    counts = {category: {bucket: 0 for bucket in BUCKETS} for category in CATEGORIES}
    human = _human_index(document)
    flagged = {
        issue.page_number for issue in document.validation_issues
        if issue.rule_id == "PAGE_003" and issue.status is ValidationIssueStatus.OPEN
    }
    headings = [h for h in document.headings if not h.is_page_marker]
    for h in headings:
        counts["headings"][_heading_bucket(h, _codes(human, "heading", h.id))] += 1
    counts["headings"]["rejected"] += _removed(
        human, "heading", {str(h.id) for h in headings}, "HEADING_REJECTED_BY_REVIEWER")
    for image in document.images:
        counts["images"][_image_bucket(image, human.get(("figure", image.image_id), []))] += 1
    for table in document.tables:
        counts["tables"][_table_bucket(table, _codes(human, "table", table.table_id))] += 1
    counts["tables"]["rejected"] += _removed(
        human, "table", {t.table_id for t in document.tables}, "TABLE_DELETED_BY_REVIEWER")
    for page in document.pages:
        codes = _codes(human, "reading_order", page.page_number)
        counts["reading_order"][_reading_order_bucket(page, codes, flagged)] += 1
    for note in document.footnotes:
        counts["footnotes"][_footnote_bucket(note, _codes(human, "footnote", note.footnote_id))] += 1
    for equation in document.equations:
        counts["equations"][_equation_bucket(equation, _codes(human, "equation", equation.id))] += 1
    for record in document.corrections:
        if not is_human_edit(record):
            counts["corrections"][_CORRECTION_BUCKET[outcome(record)]] += 1
    return counts


# --------------------------------------------------------------------------- #
# rounding and rates
# --------------------------------------------------------------------------- #

def floor_pct(fraction: float) -> float:
    """Percentage floored to one decimal: never rounds in RAWRS's favour."""
    return math.floor(fraction * 1000 + 1e-9) / 10


def ceil_seconds(seconds: float) -> float:
    return math.ceil(seconds * 10 - 1e-9) / 10


def _totals(buckets: Dict[str, Dict[str, int]]) -> Dict[str, int]:
    return {b: sum(buckets[c][b] for c in CATEGORIES) for b in BUCKETS}


def _rate(numerators: List[int], denominators: List[int]) -> Dict[str, Any]:
    """Pooled rate, per-document median, item-level Wilson lower bound."""
    pairs = [(n, d) for n, d in zip(numerators, denominators) if d > 0]
    items, hits = sum(d for _, d in pairs), sum(n for n, _ in pairs)
    if not items:
        return {"documents": 0, "items": 0, "status": NOT_MEASURED}
    low, _ = wilson_interval(hits, items)
    return {
        "documents": len(pairs),
        "items": items,
        "median_document_pct": floor_pct(statistics.median(n / d for n, d in pairs)),
        "pooled_pct": floor_pct(hits / items),
        "wilson_low_pct": floor_pct(low),
        "wilson_note": WILSON_NOTE,
        "status": "measured",
    }


def document_rates(snapshot: Dict[str, Dict[str, int]], live: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    """(a) and (b) for one document."""
    before, after = _totals(snapshot), _totals(live)
    total, decided = sum(before.values()), sum(after[b] for b in HUMAN_BUCKETS)
    return {
        "decided_without_human": _rate([before["auto_decided"]], [total]),
        "reviewer_kept_unchanged": _rate([after["accepted_unchanged"]], [decided]),
        "human_decisions": decided,
    }


# --------------------------------------------------------------------------- #
# sidecar
# --------------------------------------------------------------------------- #

def sidecar_path(output_root: Path, stem: str) -> Path:
    return Path(output_root) / "reports" / f"{stem}{SIDECAR_SUFFIX}"


def _read(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("schema") == SCHEMA else None


def _write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def write_pipeline_metrics(
    document: Any, path: Path, stage_seconds: Dict[str, float], total_seconds: float,
    checks: Optional[Dict[str, int]],
) -> bool:
    """Write the pre-review snapshot. Never raises: metrics must not fail a job.
    Review time already on disk (a re-run of the same job) is kept."""
    try:
        with _lock:
            previous = _read(path) or {}
            _write(path, {
                "schema": SCHEMA,
                "written_at": datetime.now(timezone.utc).isoformat(),
                "total_seconds": total_seconds,
                "stage_seconds": dict(stage_seconds),
                "pages": {
                    "total": len(document.pages),
                    "ocr": sum(1 for p in document.pages if p.page_type is PageType.OCR_REQUIRED),
                },
                "checks": dict(checks) if checks else None,
                "snapshot": item_buckets(document),
                "review_seconds_strict": previous.get("review_seconds_strict", 0),
                "review_seconds_loose": previous.get("review_seconds_loose", 0),
                "estimate": previous.get("estimate"),
            })
        return True
    except Exception as exc:
        logger.error("Automation metrics not written to {}: {}", path, exc)
        return False


def add_review_time(path: Path, strict_seconds: float, loose_seconds: float) -> Optional[Dict[str, float]]:
    """Add one capped delta of active review time; None when the job has no sidecar."""
    def capped(value: float) -> float:
        return min(max(float(value), 0.0), MAX_REVIEW_DELTA_SECONDS)

    with _lock:
        data = _read(path)
        if data is None:
            return None
        data["review_seconds_strict"] = data.get("review_seconds_strict", 0) + capped(strict_seconds)
        data["review_seconds_loose"] = data.get("review_seconds_loose", 0) + capped(loose_seconds)
        _write(path, data)
    return {"review_seconds_strict": data["review_seconds_strict"], "review_seconds_loose": data["review_seconds_loose"]}


def _set(path: Path, key: str, value: Any) -> bool:
    with _lock:
        data = _read(path)
        if data is None:
            return False
        data[key] = value
        _write(path, data)
    return True


def set_estimate(path: Path, estimate: Dict[str, Any]) -> bool:
    return _set(path, "estimate", {"label": ESTIMATE_LABEL, **estimate})


def set_independent_validation(path: Path, summary: Optional[Dict[str, Any]]) -> bool:
    """veraPDF + text check of the exported PDF (src/docx/pdf_export.summary_of)."""
    return _set(path, "independent", summary)


# --------------------------------------------------------------------------- #
# job and corpus views
# --------------------------------------------------------------------------- #

def _live_document(output_root: Path, stem: str) -> Any:
    from src.models.document import Document

    path = Path(output_root) / "documents" / f"{stem}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Document.model_validate(raw["document"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def job_metrics(output_root: Path, stem: str) -> Optional[Dict[str, Any]]:
    """Sidecar plus review buckets computed from the live Document (the source
    of truth, so they cannot go stale). None when the job has no sidecar."""
    data = _read(sidecar_path(output_root, stem))
    if data is None:
        return None
    document = _live_document(output_root, stem)
    live = item_buckets(document) if document is not None else data["snapshot"]
    return {**data, "job_id": stem, "live": live, "rates": document_rates(data["snapshot"], live),
            "definitions": DEFINITIONS}


def _checks_view(sidecars: List[Dict[str, Any]]) -> Dict[str, Any]:
    with_checks = [s["checks"] for s in sidecars if s.get("checks")]
    totals = defaultdict(int)
    for checks in with_checks:
        for status, n in checks.items():
            totals[status] += n
    needs_human = sum(totals[s] for s in CHECK_NEEDS_HUMAN)
    applicable = [c.get("pass", 0) + c.get("fail", 0) + sum(c.get(s, 0) for s in CHECK_NEEDS_HUMAN) for c in with_checks]
    return {
        "pass": totals["pass"], "fail": totals["fail"], "needs_human": needs_human,
        "not_applicable": totals["not_applicable"],
        "pass_rate": _rate([c.get("pass", 0) for c in with_checks], applicable),
        "note": DEFINITIONS["checks"],
    }


def _timing_view(sidecars: List[Dict[str, Any]]) -> Dict[str, Any]:
    stages = sorted({name for s in sidecars for name in s.get("stage_seconds", {})})
    totals = [s["total_seconds"] for s in sidecars]
    return {
        "documents": len(sidecars),
        "median_total_seconds": ceil_seconds(statistics.median(totals)) if totals else None,
        "max_total_seconds": ceil_seconds(max(totals)) if totals else None,
        "median_stage_seconds": {
            name: ceil_seconds(statistics.median(
                s["stage_seconds"][name] for s in sidecars if name in s.get("stage_seconds", {})))
            for name in stages
        },
    }


def _review_time_view(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    timed = [j for j in jobs if j.get("review_seconds_loose", 0) > 0]
    if not timed:
        return {"documents": 0, "status": NOT_MEASURED}
    return {
        "documents": len(timed),
        "median_loose_seconds": ceil_seconds(statistics.median(j["review_seconds_loose"] for j in timed)),
        "median_strict_seconds": ceil_seconds(statistics.median(j["review_seconds_strict"] for j in timed)),
        "note": "in-tab active time; loose = input within 300 s, strict = within 60 s",
        "status": "measured",
    }


def _estimate_view(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    estimates = [j["estimate"] for j in jobs if j.get("estimate")]
    keys = sorted({k for e in estimates for k, v in e.items() if isinstance(v, (int, float))})
    return {
        "label": ESTIMATE_LABEL,
        "documents": len(estimates),
        "mean": {k: round(statistics.mean(e[k] for e in estimates if k in e), 4) for k in keys},
    }


def _independent_view(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    checked = [j["independent"] for j in jobs if j.get("independent")]
    validated = [c for c in checked if c.get("pdfua1_compliant") is not None]
    return {
        "label": checked[0]["label"] if checked else "independent check of the exported PDF",
        "documents_exported": len(checked),
        "documents_validated": len(validated),
        "pdfua1_compliant": sum(1 for c in validated if c["pdfua1_compliant"]),
        "documents_with_no_text": sum(1 for c in checked if c.get("characters") == 0),
        "status": "measured" if checked else NOT_MEASURED,
    }


def aggregate(output_root: Path) -> Dict[str, Any]:
    """Every job with a sidecar under ``output_root/reports``. Measured (a),
    (b), checks, timing and review time stay apart from the estimate."""
    reports = Path(output_root) / "reports"
    stems = sorted(p.name[: -len(SIDECAR_SUFFIX)] for p in reports.glob(f"*{SIDECAR_SUFFIX}")) if reports.is_dir() else []
    jobs = [j for j in (job_metrics(output_root, stem) for stem in stems) if j is not None]
    snapshot = [_totals(j["snapshot"]) for j in jobs]
    live = [_totals(j["live"]) for j in jobs]
    reviewed = [t for t in live if sum(t[b] for b in HUMAN_BUCKETS) > 0]
    kept = _rate([t["accepted_unchanged"] for t in reviewed], [sum(t[b] for b in HUMAN_BUCKETS) for t in reviewed])
    if len(reviewed) < MIN_REVIEWED_DOCS:
        kept = {"status": NOT_MEASURED, "documents": len(reviewed), "items": kept.get("items", 0)}
    return {
        "schema": "rawrs.automation-aggregate/v1",
        "documents": len(jobs),
        "unreadable_sidecars": len(stems) - len(jobs),
        "definitions": DEFINITIONS,
        "measured": {
            "decided_without_human": _rate([t["auto_decided"] for t in snapshot], [sum(t.values()) for t in snapshot]),
            "reviewer_kept_unchanged": {**kept, "human_reviewed_documents": len(reviewed),
                                        "min_reviewed_documents": MIN_REVIEWED_DOCS},
            "checks": _checks_view(jobs),
            "timing": _timing_view(jobs),
            "review_time": _review_time_view(jobs),
            "independent": _independent_view(jobs),
            "snapshot_by_category": _sum_categories(j["snapshot"] for j in jobs),
            "live_by_category": _sum_categories(j["live"] for j in jobs),
        },
        "estimate": _estimate_view(jobs),
    }


def _sum_categories(per_job: Iterable[Dict[str, Dict[str, int]]]) -> Dict[str, Dict[str, int]]:
    out = {category: {bucket: 0 for bucket in BUCKETS} for category in CATEGORIES}
    for buckets in per_job:
        for category in CATEGORIES:
            for bucket in BUCKETS:
                out[category][bucket] += buckets.get(category, {}).get(bucket, 0)
    return out
