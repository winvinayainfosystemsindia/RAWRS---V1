"""Tables: the sixth asset type registered with the cross-source
verification engine.

Mathpix-sourced Table objects (src/mathpix/ingestor.py::_p2table_to_table())
never carry a bbox — MMD has no PDF geometry — and use a proportional
page_number estimate, the same imprecision class FootnoteVerifier's
anchor_page_number placeholder had before src/verification/footnotes.py.
Identity matching therefore leans on dimensions (row/col count) + caption
similarity + page proximity rather than bbox overlap, mirroring
headings.py's signal-priority pattern rather than figures.py's bbox-based
one. The PDF-side candidate source is src/tables/table_extractor.py's
existing extract_tables() — already a pure function (the pipeline itself
assigns its result to document.tables), already evidence-scored via the
same EvidenceBundle/EvidenceSignal primitive this module reuses. Zero new
table-detection logic; this file only adds the cross-source comparison
layer on top.

Built on merge.compute_merge_decisions() (the simpler binary
canonical-vs-PDF pattern — see FootnoteVerifier/figures.py) rather than
headings.py's multi-signal EvidenceBundle fusion for the identity
decision itself; table identity is "same dimensions + caption + page",
not several independent typography-style signals to fuse. Once matched,
classify() below still reports each independent structural disagreement
(caption/row/column/overall structure) as its own Finding, exactly the
granularity headings.py's classify() already demonstrates for
level_mismatch vs. text_correction.
"""

from __future__ import annotations

import difflib
import json
from typing import Any, Dict, List, Optional

from src.models.bounding_box import BoundingBox
from src.models.correction import CorrectionRecord
from src.models.table import Table, TableRow
from src.models.verification import Finding, RuleSpec
from src.verification.base import SemanticVerifier
from src.verification.matching import MatchResult, MultiSignalMatcher, WeightedSignal
from src.verification.merge import MergeAction

# Two tables whose normalized captions are at least this similar are
# considered "the same caption" for matching purposes even when not
# identical (e.g. an OCR/recognition difference).
_CAPTION_SIMILARITY_MATCH_MIN = 0.6

# Same boundary FigureVerifier/HeadingVerifier use — an identity match
# below this confidence is too weak to safely propose a REPAIR from.
_LOW_CONFIDENCE_THRESHOLD = 0.5


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _caption_differs(a: Optional[str], b: Optional[str]) -> bool:
    if not a and not b:
        return False
    if not a or not b:
        return True
    return _normalize(a) != _normalize(b)


def _dimensions_signal(a: Table, b: Table) -> Optional[float]:
    return 0.9 if a.row_count == b.row_count and a.col_count == b.col_count else None


def _caption_similarity_signal(a: Table, b: Table) -> Optional[float]:
    if not a.caption or not b.caption:
        return None
    ratio = difflib.SequenceMatcher(None, _normalize(a.caption), _normalize(b.caption)).ratio()
    return ratio if ratio >= _CAPTION_SIMILARITY_MATCH_MIN else None


def _page_proximity_signal(a: Table, b: Table) -> Optional[float]:
    diff = abs(a.page_number - b.page_number)
    if diff == 0:
        return 0.55
    if diff == 1:
        return 0.5
    return None


def _positional_signal(_a: Any, _b: Any) -> Optional[float]:
    """Last-resort fallback, identical in spirit to every other
    verifier's own — pairs the Nth remaining canonical table with the
    Nth remaining PDF candidate via MultiSignalMatcher's stable ordering."""
    return 0.05


def _encode_repair(table: Table) -> str:
    return json.dumps(
        {
            "caption": table.caption,
            "row_count": table.row_count,
            "col_count": table.col_count,
            "rows": [row.model_dump() for row in table.rows],
            "bbox": table.bbox.model_dump() if table.bbox else None,
        }
    )


def _decode_repair(payload: str) -> Dict[str, Any]:
    return json.loads(payload)


class TableVerifier(SemanticVerifier):
    asset_type = "table"

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        return MultiSignalMatcher(
            [
                WeightedSignal(name="dimensions", fn=_dimensions_signal, min_confidence=0.85),
                WeightedSignal(name="caption_similarity", fn=_caption_similarity_signal, min_confidence=_CAPTION_SIMILARITY_MATCH_MIN),
                WeightedSignal(name="page_proximity", fn=_page_proximity_signal, min_confidence=0.5),
                WeightedSignal(name="positional_fallback", fn=_positional_signal, min_confidence=0.01),
            ]
        )

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Table]:
        """Tables arrive from Mathpix already built (src/mathpix/ingestor.py)
        — same reasoning as Heading/List/Callout/Footnote. Identity
        passthrough."""
        return list(match_result.unmatched_a) + [pair.a for pair in match_result.pairs]

    def _is_mismatch(self, canonical: Table, pdf_table: Table) -> bool:
        return (
            canonical.row_count != pdf_table.row_count
            or canonical.col_count != pdf_table.col_count
            or _caption_differs(canonical.caption, pdf_table.caption)
        )

    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        findings: List[Finding] = []

        for decision in self.merge_decisions(match_result, self._is_mismatch):
            if decision.canonical is None:
                # RECOVER: a real PDF table Mathpix's package is missing entirely.
                pdf_table: Table = decision.pdf_evidence
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="missing_from_mathpix",
                        object_id=None,
                        confidence=None,
                        evidence=f"pdf_page={pdf_table.page_number}; {pdf_table.row_count}x{pdf_table.col_count}",
                        message=(
                            f"PDF page {pdf_table.page_number} has a "
                            f"{pdf_table.row_count}x{pdf_table.col_count} table not present "
                            "in the Mathpix package."
                        ),
                        proposed_value=pdf_table.model_dump_json(),
                    )
                )
                continue

            canonical: Table = decision.canonical
            pdf_table = decision.pdf_evidence

            if pdf_table is None:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="missing_from_pdf",
                        object_id=canonical.table_id,
                        confidence=None,
                        evidence="no PDF-side match found",
                        message=(
                            f"Table on page {canonical.page_number} "
                            f"({canonical.row_count}x{canonical.col_count}) could not be "
                            "confirmed against the PDF."
                        ),
                    )
                )
                continue

            if decision.confidence is not None and decision.confidence < _LOW_CONFIDENCE_THRESHOLD:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="low_confidence",
                        object_id=canonical.table_id,
                        confidence=decision.confidence,
                        evidence=f"matched_by={decision.signal}; confidence={decision.confidence:.2f}",
                        message=(
                            f"Table on page {canonical.page_number} matched a PDF candidate "
                            f"only weakly (confidence {decision.confidence:.2f}) — verify manually "
                            "before trusting any proposed repair."
                        ),
                    )
                )
                continue

            if decision.action != MergeAction.REPAIR:
                continue  # confirmed silently

            row_mismatch = canonical.row_count != pdf_table.row_count
            col_mismatch = canonical.col_count != pdf_table.col_count
            caption_mismatch = _caption_differs(canonical.caption, pdf_table.caption)
            original = _encode_repair(canonical)
            proposed = _encode_repair(pdf_table)

            if row_mismatch and col_mismatch:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="structure_mismatch",
                        object_id=canonical.table_id,
                        confidence=decision.confidence,
                        evidence=f"mathpix={canonical.row_count}x{canonical.col_count}; pdf={pdf_table.row_count}x{pdf_table.col_count}",
                        message=(
                            f"Table structure disagrees: Mathpix says "
                            f"{canonical.row_count}x{canonical.col_count}, PDF evidence "
                            f"suggests {pdf_table.row_count}x{pdf_table.col_count}."
                        ),
                        original_value=original,
                        proposed_value=proposed,
                    )
                )
            elif row_mismatch:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="row_count_mismatch",
                        object_id=canonical.table_id,
                        confidence=decision.confidence,
                        evidence=f"mathpix_rows={canonical.row_count}; pdf_rows={pdf_table.row_count}",
                        message=(
                            f"Table row count disagrees: Mathpix says {canonical.row_count}, "
                            f"PDF evidence suggests {pdf_table.row_count}."
                        ),
                        original_value=original,
                        proposed_value=proposed,
                    )
                )
            elif col_mismatch:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="column_count_mismatch",
                        object_id=canonical.table_id,
                        confidence=decision.confidence,
                        evidence=f"mathpix_cols={canonical.col_count}; pdf_cols={pdf_table.col_count}",
                        message=(
                            f"Table column count disagrees: Mathpix says {canonical.col_count}, "
                            f"PDF evidence suggests {pdf_table.col_count}."
                        ),
                        original_value=original,
                        proposed_value=proposed,
                    )
                )

            if caption_mismatch:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="caption_mismatch",
                        object_id=canonical.table_id,
                        confidence=decision.confidence,
                        evidence=f"mathpix_caption={canonical.caption!r}; pdf_caption={pdf_table.caption!r}",
                        message="Table caption differs from the PDF — possible OCR/recognition error.",
                        original_value=original,
                        proposed_value=proposed,
                    )
                )

        return findings

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {
            "missing_from_mathpix": RuleSpec(
                rule_id="TABLE_VERIFY_001", reason_code="TABLE_MISSING_FROM_MATHPIX", severity="warning"
            ),
            "missing_from_pdf": RuleSpec(
                rule_id="TABLE_VERIFY_002", reason_code="TABLE_MISSING_FROM_PDF", severity="info"
            ),
            "caption_mismatch": RuleSpec(
                rule_id="TABLE_VERIFY_003", reason_code="TABLE_CAPTION_MISMATCH", severity="warning"
            ),
            "row_count_mismatch": RuleSpec(
                rule_id="TABLE_VERIFY_004", reason_code="TABLE_ROW_COUNT_MISMATCH", severity="warning"
            ),
            "column_count_mismatch": RuleSpec(
                rule_id="TABLE_VERIFY_005", reason_code="TABLE_COLUMN_COUNT_MISMATCH", severity="warning"
            ),
            "low_confidence": RuleSpec(
                rule_id="TABLE_VERIFY_006", reason_code="TABLE_LOW_CONFIDENCE_MATCH", severity="info"
            ),
            "structure_mismatch": RuleSpec(
                rule_id="TABLE_VERIFY_007", reason_code="TABLE_STRUCTURE_MISMATCH", severity="warning"
            ),
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        if correction.field == "missing_from_mathpix":
            if not correction.proposed_value:
                return
            document.tables.append(Table.model_validate_json(correction.proposed_value))
            return

        if correction.object_id is None:
            return
        table = next((t for t in document.tables if t.table_id == correction.object_id), None)
        if table is None:
            return

        if (
            correction.field in ("caption_mismatch", "row_count_mismatch", "column_count_mismatch", "structure_mismatch")
            and correction.proposed_value
        ):
            data = _decode_repair(correction.proposed_value)
            table.caption = data["caption"]
            table.row_count = data["row_count"]
            table.col_count = data["col_count"]
            table.rows = [TableRow(**row) for row in data["rows"]]
            table.bbox = BoundingBox(**data["bbox"]) if data["bbox"] else None
        # "missing_from_pdf"/"low_confidence" are informational only — no-op.


def _register() -> None:
    from src.verification.engine import engine

    engine.register(TableVerifier())


_register()
