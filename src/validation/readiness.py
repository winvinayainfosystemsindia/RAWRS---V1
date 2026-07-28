"""Accessibility Readiness — LEGACY DIAGNOSTICS ONLY (no longer a readiness gate).

**Not part of the production export-readiness path.** The canonical readiness
authority is `AccessibilityReport.export_ready` (src/accessibility/, GET
/accessibility-report), which evaluates live document/review state. This module
computes a summary over the *frozen, pipeline-time* `Document.validation_issues`
snapshot, so it can never reflect reviewer actions and must not gate export.
The `/readiness` and `/export-readiness` HTTP endpoints that once exposed this
were retired in the readiness convergence; `compute_readiness` is kept only as
an isolated diagnostic (unit-tested in tests/test_readiness.py) and is imported
by nothing in the production request path.

Groups Document.validation_issues by rule_id prefix (HEADING_001,
LIST_VERIFY_002, IMAGE_VERIFY_004, TABLE_005, ...) — a purely mechanical
rollup, no hand-maintained rule map.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from src.models.document import Document
from src.models.validation_issue import Severity

# Small, static prefix -> human label map. Not a rule_id registry — new
# rule prefixes that aren't listed here still work, just with their raw
# prefix as the label (see ReadinessCategory.label fallback below).
_CATEGORY_LABELS: Dict[str, str] = {
    "DOC": "Document",
    "HEADING": "Headings",
    "PAGE": "Page Structure",
    "IMAGE": "Images",
    "OCR": "OCR Quality",
    "TABLE": "Tables",
    "NOTE": "Footnotes & Endnotes",
    "META": "Metadata",
    "LIST": "Lists",
}


@dataclass
class ReadinessCategory:
    category: str
    label: str
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0

    @property
    def ready(self) -> bool:
        return self.error_count == 0 and self.warning_count == 0


@dataclass
class ReadinessReport:
    categories: List[ReadinessCategory] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(c.ready for c in self.categories)

    @property
    def overall_score(self) -> float:
        if not self.categories:
            return 1.0
        return sum(1 for c in self.categories if c.ready) / len(self.categories)


def _category_prefix(rule_id: str) -> str:
    return rule_id.split("_")[0] if rule_id else "OTHER"


def compute_readiness(document: Document) -> ReadinessReport:
    by_category: Dict[str, ReadinessCategory] = {}

    for issue in document.validation_issues:
        prefix = _category_prefix(issue.rule_id)
        category = by_category.setdefault(
            prefix, ReadinessCategory(category=prefix, label=_CATEGORY_LABELS.get(prefix, prefix.title()))
        )
        if issue.severity == Severity.ERROR:
            category.error_count += 1
        elif issue.severity == Severity.WARNING:
            category.warning_count += 1
        else:
            category.info_count += 1

    ordered = sorted(by_category.values(), key=lambda c: c.category)
    return ReadinessReport(categories=ordered)
