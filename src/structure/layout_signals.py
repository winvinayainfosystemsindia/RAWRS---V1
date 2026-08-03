"""Shared PDF per-line layout-signal extraction for RAWRS.

Computes (text, font size, is-bold, char count) for one line of
PyMuPDF's ``page.get_text("dict")`` output. Originally lived only in
src/headings/heading_detector.py (Phase B), where it still drives
heading classification unchanged; extracted here in Phase H so
src/structure/structure_detector.py can reuse the exact same signal
for every line on a page, rather than duplicating this logic per
docs/CLAUDE_INSTRUCTIONS.md's "Do not create duplicate data
structures" rule (read broadly to include duplicate extraction logic,
not just duplicate models).
"""

import statistics
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from src.models.text_block import (
    ArtifactClass,
    ArtifactClassification,
    PhysicalZone,
    RepetitionEvidence,
    TextBlock,
)

LineLayout = Tuple[float, bool]  # (font size, is_bold)

_BOLD_FONT_FLAG = 16  # PyMuPDF span flags bit 4
# A line's bold status is "true" when a majority of its characters (not
# just any single span) come from a bold-flagged or bold-named font -
# this avoids misclassifying a body sentence that merely contains one
# bold word (inline emphasis) as bold.
_BOLD_MAJORITY_THRESHOLD = 0.5


def line_layout(line_dict: dict) -> Optional[Tuple[str, float, bool, int]]:
    """Aggregate a PyMuPDF dict-mode line's spans into (text, size, is_bold, char_count).

    size is the largest span size on the line; is_bold is true when a
    majority of the line's characters come from a bold span. Returns
    None for a line with no non-blank text.
    """
    spans = line_dict.get("spans", [])
    text = "".join(span["text"] for span in spans).strip()
    if not text:
        return None

    total_chars = sum(len(span["text"]) for span in spans)
    if total_chars == 0:
        return None

    bold_chars = sum(len(span["text"]) for span in spans if span_is_bold(span))
    is_bold = (bold_chars / total_chars) > _BOLD_MAJORITY_THRESHOLD
    size = round(max(span["size"] for span in spans), 1)

    return text, size, is_bold, total_chars


def span_is_bold(span: dict) -> bool:
    font_name = span.get("font", "")
    return "bold" in font_name.lower() or bool(span.get("flags", 0) & _BOLD_FONT_FLAG)


_HEADER_FOOTER_BAND_RATIO = 0.12  # top/bottom fraction of page height treated as header/footer


def assign_physical_zone(y0: float, y1: float, page_height: float) -> PhysicalZone:
    """Classify a line into a vertical physical zone by its bbox centre.

    HEADER when the line's vertical centre falls in the top
    ``_HEADER_FOOTER_BAND_RATIO`` of the page, FOOTER when in the bottom band,
    BODY otherwise. Purely geometric - a calibration knob, not an
    interpretation. Returns BODY on a degenerate (non-positive) page height
    rather than raising.
    """
    if page_height <= 0:
        return PhysicalZone.BODY
    centre = (y0 + y1) / 2
    if centre < page_height * _HEADER_FOOTER_BAND_RATIO:
        return PhysicalZone.HEADER
    if centre > page_height * (1 - _HEADER_FOOTER_BAND_RATIO):
        return PhysicalZone.FOOTER
    return PhysicalZone.BODY


_REPETITION_MIN_PAGES = 2  # a signature must span this many distinct pages to count
_STABILITY_SCALE = 20.0  # pt; positional_stability = scale / (scale + y-centre stdev)


def _repetition_signature(text: str) -> str:
    return " ".join(text.lower().split()).strip()


def annotate_repetition(blocks: List[TextBlock], page_count: int) -> None:
    """Document-wide pass: attach RepetitionEvidence to every block whose
    normalized text recurs across >= _REPETITION_MIN_PAGES distinct pages.

    Mutates ``blocks`` in place and is purely additive - blocks below the
    threshold keep ``repetition = None``. Evidence only - this function
    classifies nothing and suppresses nothing; ``classify_artifacts`` below is
    its consumer. The reusable, model-attached successor to the
    per-interpreter recurrence heuristics scattered elsewhere (e.g.
    heading_detector's Tier-4 guard), which later stages will converge onto.
    """
    groups: dict = defaultdict(list)
    for block in blocks:
        signature = _repetition_signature(block.text)
        if signature:
            groups[signature].append(block)

    for signature, group in groups.items():
        pages = sorted({block.page_number for block in group})
        if len(pages) < _REPETITION_MIN_PAGES:
            continue
        centres = [(block.bbox.y0 + block.bbox.y1) / 2 for block in group]
        stdev = statistics.pstdev(centres) if len(centres) > 1 else 0.0
        if all(page % 2 == 1 for page in pages):
            alternation = "odd"
        elif all(page % 2 == 0 for page in pages):
            alternation = "even"
        else:
            alternation = None
        evidence = RepetitionEvidence(
            signature=signature,
            recurrence_count=len(group),
            page_numbers=pages,
            recurrence_ratio=round(len(pages) / page_count, 4) if page_count else 0.0,
            positional_stability=round(_STABILITY_SCALE / (_STABILITY_SCALE + stdev), 4),
            alternation=alternation,
        )
        for block in group:
            block.repetition = evidence


_ARTIFACT_MIN_STABILITY = 0.5  # a repeated line below this y-band stability is not a running artifact
_PAGE_NUMBER_CONFIDENCE = 0.9

# L2.1 Running-title classification: a running title (book/section/chapter
# masthead repeated across pages) often lands in the BODY zone in reflowed or
# two-column PDFs and wanders enough vertically to fall below
# _ARTIFACT_MIN_STABILITY, so the RUNNING_HEADER/FOOTER/DECORATIVE branch below
# misses it entirely. Strong cross-page recurrence of a MULTI-WORD phrase is
# itself the artifact signature here, standing in for the tight y-band the 0.5
# stability gate demands. The thresholds separate the measured running-title
# cluster (benchmark: BODY zone, stability 0.29-0.40, multi-word, recurring on
# 3-12 pages) from repeated-body-word / column-split noise (stability <= 0.19,
# or single tokens) with margin on both sides - a general property of running
# titles, not fitted to any one document. Only the [_RUNNING_TITLE_MIN_STABILITY,
# _ARTIFACT_MIN_STABILITY) band is new; at/above 0.5 the existing branch already
# fires (DECORATIVE_REPEATED in BODY), so the two never overlap.
_RUNNING_TITLE_MIN_STABILITY = 0.25
_RUNNING_TITLE_MIN_PAGES = 3
_RUNNING_TITLE_MIN_WORDS = 2


def classify_artifacts(blocks: List[TextBlock], page_labels: Dict[int, str]) -> None:
    """Attach an evidence-driven ArtifactClassification to blocks the L1 layer
    identifies as artifacts rather than content.

    Consumes only already-computed evidence - PhysicalZone + RepetitionEvidence
    on each block, plus the page's printed label (feature_009, reused via
    ``page_labels``). Multi-signal by construction: every class requires at
    least two agreeing signals, never one. Purely additive - content blocks
    keep ``artifact = None``. Classification only: what a line *is*. The
    decision to act on it lives in src/verification/artifacts.py, which turns a
    classification into a reversible CorrectionRecord; L3 heading candidacy is
    the other consumer.
    """
    labels = {pn: " ".join((lbl or "").lower().split()).strip() for pn, lbl in page_labels.items()}
    for block in blocks:
        zone = block.physical_zone
        rep = block.repetition
        norm = " ".join(block.text.lower().split()).strip()

        # PAGE_NUMBER: the line is this page's printed label (feature_009) AND
        # sits in a header/footer zone - two independent signals.
        if norm and labels.get(block.page_number) == norm and zone in (PhysicalZone.HEADER, PhysicalZone.FOOTER):
            block.artifact = ArtifactClassification(
                artifact_class=ArtifactClass.PAGE_NUMBER,
                confidence=_PAGE_NUMBER_CONFIDENCE,
                evidence=[f"matches page {block.page_number}'s printed label", f"{zone.value} zone"],
            )
            continue

        # Repetition-driven artifacts: text recurs across pages. A running
        # artifact is either a tightly-banded repeat (>= _ARTIFACT_MIN_STABILITY)
        # or - L2.1 - a strongly-recurring MULTI-WORD phrase whose looser band
        # (>= _RUNNING_TITLE_MIN_STABILITY) is compensated by that recurrence:
        # a masthead/running title that wanders vertically and alternates zone
        # across pages, which the tight-band gate alone misses. The per-block
        # zone still names the class - a BODY-zone strong-recurrence phrase is a
        # RUNNING_TITLE - so the same running title is caught on every page it
        # appears, whichever zone each occurrence lands in. Occurrences with
        # stability >= 0.5 are classified exactly as before (identical class,
        # confidence, and evidence); only the [_RUNNING_TITLE_MIN_STABILITY, 0.5)
        # multi-word strong-recurrence band is newly reached.
        is_multiword_recurrence = (
            rep is not None
            and len(rep.page_numbers) >= _RUNNING_TITLE_MIN_PAGES
            and len(rep.signature.split()) >= _RUNNING_TITLE_MIN_WORDS
        )
        if rep is not None and (
            rep.positional_stability >= _ARTIFACT_MIN_STABILITY
            or (is_multiword_recurrence and rep.positional_stability >= _RUNNING_TITLE_MIN_STABILITY)
        ):
            tight = rep.positional_stability >= _ARTIFACT_MIN_STABILITY
            if zone == PhysicalZone.HEADER:
                artifact_class = ArtifactClass.RUNNING_HEADER
            elif zone == PhysicalZone.FOOTER:
                artifact_class = ArtifactClass.RUNNING_FOOTER
            elif tight:
                artifact_class = ArtifactClass.DECORATIVE_REPEATED
            else:
                artifact_class = ArtifactClass.RUNNING_TITLE
            evidence = [
                f"repeats on {len(rep.page_numbers)} page(s) (ratio {rep.recurrence_ratio})",
                f"positional stability {rep.positional_stability}",
                f"{zone.value if zone else 'unzoned'} zone",
            ]
            if not tight:
                evidence.append(
                    f"multi-word phrase; strong recurrence compensates for stability "
                    f"below the {_ARTIFACT_MIN_STABILITY} gate (L2.1)"
                )
            if rep.alternation:
                evidence.append(f"{rep.alternation}-page alternation")
            block.artifact = ArtifactClassification(
                artifact_class=artifact_class,
                confidence=round(min(1.0, rep.recurrence_ratio) * rep.positional_stability, 4),
                evidence=evidence,
            )
