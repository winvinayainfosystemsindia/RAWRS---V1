"""Headings: the second asset type registered with the cross-source
verification engine, and the first built directly on the Document Merge
Layer + SemanticVerifier base class from day one (see
src/verification/figures.py for the first, migrated-after-the-fact,
asset type).

Mathpix already builds canonical ``Heading`` objects directly
(src/mathpix/ingestor.py), so there is no separate "uploaded asset" to
match at import time the way Figure has. The PDF-side candidates come
from ``src/headings/heading_detector.py::detect_headings_from_pdf()``, a
pure function that reuses that module's existing classification helpers
— zero duplicated detection logic, and ``detect_headings()`` (the
Mathpix-independent native path) is untouched.

FEATURE_019 (Evidence Fusion Engine): classify() no longer decides
KEEP/REPAIR/RECOVER from the binary PDF-match alone. It builds an
EvidenceBundle (src/verification/evidence.py) per candidate from every
independent signal available — the PDF match itself, PDF typography
(font size vs. the document's own body-text baseline,
src/headings/heading_detector.py::build_heading_layout_context()),
whitespace isolation (gap above/below vs. the page's own median line
gap), and running-header recurrence (the same exact-text-repeats-across-
pages signature heading_detector.py's own Tier-4 guard already uses for
the RAWRS-native path, ported here since that guard never runs at all
for Mathpix-sourced headings otherwise) — then hands the fused
confidence to src/verification/merge.py::decide_from_evidence(). The
running-header signal is the one that works even with zero PDF text
layer (a pure scanned-image document): it only needs Mathpix's own
heading list, not PDF geometry.

Content headings only (H1-H5); page markers (H6) are out of scope for
this verifier (a future PageLabelVerifier's job — see the roadmap in
docs/DECISIONS_LOG.md).
"""

from __future__ import annotations

import difflib
import json
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from src.headings.heading_detector import HeadingLayoutContext, build_heading_layout_context
from src.models.contracts import BoundingBox
from src.models.correction import CorrectionRecord
from src.models.heading import Heading, HeadingLevel
from src.models.verification import Finding, RuleSpec, VerificationStatus
from src.ocr.targeted import TargetedOCRError, ocr_region
from src.verification.base import SemanticVerifier
from src.verification.evidence import EvidenceBundle, EvidenceSignal
from src.verification.matching import MatchResult, MultiSignalMatcher, WeightedSignal
from src.verification.merge import MergeAction, decide_from_evidence
from src.verification.text_resolution import TextResolver

# A heading whose exact normalized text recurs on this many or more
# distinct pages is treated as a likely running header/footer, not a
# real content heading — mirrors heading_detector.py's own Tier 4
# Recurrence Guard, which only ever declines a *second* occurrence, so 2
# distinct pages is already "recurs" in that same spirit.
_RUNNING_HEADER_RECURRENCE_MIN_PAGES = 2

# A candidate's font size must exceed the document's body size by at
# least this ratio to count as strong typography evidence for a heading
# (mirrors heading_detector.py's own bold-and-larger-than-body signal,
# expressed as a continuous score instead of a hard gate).
_TYPOGRAPHY_STRONG_SIZE_RATIO = 1.15

# Same boundary decide_from_evidence()'s default ConfidenceThresholds
# uses — the running-header recurrence signal is checked directly
# (rather than through decide_from_evidence()) since it answers "does
# this belong as a heading at all", not "is the level/text correct", and
# has no PDF-proposed replacement value to REPAIR toward.
_RUNNING_HEADER_REPAIR_THRESHOLD = 0.5

# Two headings whose normalized text similarity is at least this high are
# considered "the same heading" for matching purposes even when the exact
# text differs (e.g. an OCR/recognition typo) — classify() then reports
# the text difference as a text_correction finding rather than treating
# them as two unrelated headings.
_TEXT_SIMILARITY_MATCH_MIN = 0.6

# M-5.1 — targeted OCR is evidence of last resort: only called when the
# bundle's confidence *before* it is added is already at or below this
# boundary. Same value as _RUNNING_HEADER_REPAIR_THRESHOLD/
# decide_from_evidence()'s own default confidence boundary — one shared
# notion of "ambiguous" reused, not a second threshold invented. A
# weighted-mean bundle where signals genuinely disagree already lands
# near this boundary on its own, so a single confidence check covers both
# "low confidence" and "competing evidence disagrees" without a separate
# disagreement formula.
_OCR_AMBIGUOUS_CONFIDENCE_THRESHOLD = 0.5

# Horizontal crop padding, in PDF points, wide enough to cover any
# realistic page width. HeadingLayoutContext.bbox_index only tracks
# vertical extent (y0/y1) — it was built for the whitespace-gap signal,
# which never needed x0/x1 — so this crops the full page width at that
# y-range rather than a tight box. Surya's recognizer isolates one line
# of text within a wider strip without issue; a tight x-crop would need
# extending _build_layout_index (src/headings/heading_detector.py), out
# of scope for a single-verifier evidence addition.
_OCR_CROP_X1 = 3000.0
_OCR_CROP_Y_PADDING = 2.0


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _exact_text_signal(a: Heading, b: Heading) -> Optional[float]:
    return 1.0 if _normalize(a.text) == _normalize(b.text) else None


def _text_similarity_signal(a: Heading, b: Heading) -> Optional[float]:
    ratio = difflib.SequenceMatcher(None, _normalize(a.text), _normalize(b.text)).ratio()
    return ratio if ratio >= _TEXT_SIMILARITY_MATCH_MIN else None


def _page_proximity_signal(a: Heading, b: Heading) -> Optional[float]:
    diff = abs(a.page_number - b.page_number)
    if diff == 0:
        return 0.55
    if diff == 1:
        return 0.5
    return None


def _positional_signal(_a: Any, _b: Any) -> Optional[float]:
    """Last-resort fallback, identical in spirit to figures.py's own —
    pairs the Nth remaining canonical heading with the Nth remaining PDF
    candidate via MultiSignalMatcher's stable-sort/dict-insertion-order
    behavior, not by inspecting indices itself."""
    return 0.05


def _encode_recovery(pdf_heading: Heading) -> str:
    return json.dumps(
        {"level": int(pdf_heading.level), "text": pdf_heading.text, "page_number": pdf_heading.page_number}
    )


def _decode_recovery(payload: str) -> Heading:
    data = json.loads(payload)
    return Heading(
        level=HeadingLevel(data["level"]),
        text=data["text"],
        page_number=data["page_number"],
        document_order=0,  # placeholder — _insert_recovered_heading assigns the real slot
        is_page_marker=False,
        source="rawrs_recovery",
    )


def _insert_recovered_heading(document: Any, recovered: Heading) -> None:
    """Insert a RECOVER'd heading into document.headings at the right
    document_order slot, shifting every subsequent heading's order by one
    to preserve uniqueness — rather than merely appending, which would
    put a page-3 recovery after a page-10 heading in document order."""
    insert_after: Optional[int] = None
    for h in document.headings:
        if h.page_number <= recovered.page_number:
            if insert_after is None or h.document_order > insert_after:
                insert_after = h.document_order
    new_order = insert_after + 1 if insert_after is not None else 0
    for h in document.headings:
        if h.document_order >= new_order:
            h.document_order += 1
    recovered.document_order = new_order
    document.headings.append(recovered)
    document.headings.sort(key=lambda h: h.document_order)


# ── Evidence signal builders (FEATURE_019) ──────────────────────────────
#
# Each function below inspects one independent source and returns an
# EvidenceSignal (or None when that source has nothing to say about this
# candidate — e.g. typography/whitespace need a PDF text layer that a
# pure scanned-image document simply doesn't have). classify() combines
# whichever signals are actually available into one EvidenceBundle; a
# candidate with only one or two available signals is still evaluated,
# just with less to go on — never an error.


def _pdf_match_signal(decision_confidence: Optional[float], is_mismatch: bool) -> Optional[EvidenceSignal]:
    """The existing binary PDF-vs-Mathpix match, folded in as one signal
    among several rather than the sole source of truth. None when the PDF
    pass found no candidate to compare against at all (unconfirmed).

    ``decision_confidence`` is identity-match confidence (are the
    canonical and PDF-derived headings the same real-world heading —
    from src/verification/matching.py's exact_text/text_similarity/
    page_proximity signals), not "is Mathpix's classification correct."
    A high-confidence match that happens to disagree on level/text is
    still strong evidence — it means we can trust the PDF's proposed
    correction, not that the comparison itself is worthless — so the
    score reports match confidence either way; only a genuinely weak
    match (e.g. matching.py's positional last-resort fallback) pulls
    the fused bundle toward REMOVE via decide_from_evidence() rather
    than a confident REPAIR.
    """
    if decision_confidence is None:
        return None
    return EvidenceSignal(
        name="pdf_match",
        score=decision_confidence,
        weight=1.5,
        note=f"PDF-derived candidate {'disagrees' if is_mismatch else 'confirms'} (match confidence {decision_confidence:.2f})",
    )


def _typography_signal(
    heading: Heading, context: HeadingLayoutContext, layout_resolver: Optional[TextResolver]
) -> Optional[EvidenceSignal]:
    """Font size vs. the document's own body-text baseline. None when the
    PDF has no native text layer for this line (context.body_profile is
    None) or no line on this page resolves to this heading's text via
    layout_resolver's tiered matching (M-5.3) — Mathpix's text and
    PyMuPDF's own line extraction rarely agree on the exact string, even
    when they agree on content."""
    if context.body_profile is None or layout_resolver is None:
        return None
    resolved = layout_resolver.resolve(heading.text)
    if resolved is None:
        return None
    (size, is_bold), _tier = resolved
    body_size, body_is_bold = context.body_profile
    if body_size <= 0:
        return None
    size_ratio = size / body_size
    score = min(1.0, max(0.0, (size_ratio - 1.0) / (_TYPOGRAPHY_STRONG_SIZE_RATIO - 1.0)))
    if is_bold and not body_is_bold:
        score = min(1.0, score + 0.3)
    return EvidenceSignal(
        name="typography",
        score=score,
        weight=1.0,
        note=f"{size:.0f}pt vs {body_size:.0f}pt body ({'bold' if is_bold else 'not bold'})",
    )


def _whitespace_signal(
    heading: Heading, context: HeadingLayoutContext, bbox_resolver: Optional[TextResolver]
) -> Optional[EvidenceSignal]:
    """Vertical isolation: gap above/below this line vs. the page's own
    median line-to-line gap — self-calibrating per page, same pattern
    src/validation/validator.py's reading-order-anomaly check already
    uses, rather than a fixed point value. None when this page has fewer
    than 3 lines of bbox data (nothing to calibrate against) or bbox_resolver
    (M-5.3) can't resolve this heading's text to any line on the page."""
    page_bboxes = context.bbox_index.get(heading.page_number, {})
    if bbox_resolver is None or len(page_bboxes) < 3:
        return None
    resolved = bbox_resolver.resolve(heading.text)
    if resolved is None:
        return None
    target, _tier = resolved

    ordered = sorted(page_bboxes.values(), key=lambda b: b[1])  # sort by y0
    gaps = [max(0.0, b[1] - a[2]) for a, b in zip(ordered, ordered[1:])]  # y0(next) - y1(prev)
    if not gaps:
        return None
    median_gap = sorted(gaps)[len(gaps) // 2]
    if median_gap <= 0:
        return None

    _, target_y0, target_y1 = target
    gap_above = next((target_y0 - b[2] for b in ordered if b[2] <= target_y0), 0.0)
    gap_below = next((b[1] - target_y1 for b in ordered if b[1] >= target_y1), 0.0)
    isolation = max(0.0, gap_above) + max(0.0, gap_below)
    score = min(1.0, isolation / (2.5 * median_gap))
    return EvidenceSignal(
        name="whitespace",
        score=score,
        weight=0.75,
        note=f"{isolation:.0f}pt surrounding gap vs {median_gap:.0f}pt page median",
    )


def _running_header_signal(heading: Heading, all_canonical: List[Heading]) -> EvidenceSignal:
    """Exact-text recurrence across distinct pages — the running-header/
    footer signature heading_detector.py's own Tier 4 Recurrence Guard
    already relies on for the RAWRS-native path, ported here since that
    guard never runs at all for Mathpix-sourced headings otherwise (it
    lives inside detect_headings()'s classification loop, which the
    Mathpix import path skips entirely). Unlike typography/whitespace,
    this signal needs no PDF text layer — it only reads Mathpix's own
    heading list, so it is the one signal still available for a pure
    scanned-image document."""
    normalized = _normalize(heading.text)
    pages = {h.page_number for h in all_canonical if _normalize(h.text) == normalized}
    if len(pages) < _RUNNING_HEADER_RECURRENCE_MIN_PAGES:
        return EvidenceSignal(name="running_header_recurrence", score=1.0, weight=1.0, note="text is unique in this document")
    # More recurring pages -> lower score (stronger running-header signal).
    score = max(0.0, 1.0 - (len(pages) - 1) / 4.0)
    return EvidenceSignal(
        name="running_header_recurrence",
        score=score,
        weight=1.25,
        note=f"identical text repeats on {len(pages)} pages — likely a running header/footer",
    )


def _targeted_ocr_signal(
    heading: Heading,
    context: Optional[HeadingLayoutContext],
    pdf_path: Any,
    bbox_resolver: Optional[TextResolver],
) -> Optional[EvidenceSignal]:
    """M-5.1 — evidence of last resort: an independent OCR read of this
    heading's own line, compared against Mathpix's text. Only ever called
    by classify() when the bundle is already ambiguous (see
    _OCR_AMBIGUOUS_CONFIDENCE_THRESHOLD) — never for an already-confident
    candidate. None (no signal, not an error) whenever the inputs needed
    to crop a region don't exist: no pdf_path, no layout context, or
    bbox_resolver (M-5.3) can't resolve this heading's text to any line on
    the page (context.bbox_index is only populated for pages with a
    native PDF text layer — a pure scanned page has none, the one gap
    this integration doesn't close, out of scope here).
    """
    if not pdf_path or context is None or bbox_resolver is None:
        return None
    resolved = bbox_resolver.resolve(heading.text)
    if resolved is None:
        return None
    target, _tier = resolved
    _, y0, y1 = target

    bbox = BoundingBox(
        x0=0.0,
        y0=max(0.0, y0 - _OCR_CROP_Y_PADDING),
        x1=_OCR_CROP_X1,
        y1=y1 + _OCR_CROP_Y_PADDING,
    )
    try:
        ocr_text = ocr_region(pdf_path, heading.page_number, bbox)
    except TargetedOCRError as exc:
        logger.debug("Targeted OCR unavailable for heading '{}': {}", heading.text, exc)
        return None
    except Exception as exc:  # noqa: BLE001 - defensive: evidence of last
        # resort must never crash verification. ocr_region()'s own
        # docstring promises "never raises... only for genuinely unusable
        # input", but M-5.3's real-corpus validation run surfaced a raw
        # Surya library ValueError escaping uncaught (an underlying
        # dependency-version API mismatch, "layout_results required when
        # full_page=False") the first time this code path was ever
        # actually reached on a real document — this OCR-engine-internal
        # failure is graceful-degradation territory, same as the
        # documented TargetedOCRError case, not a fix for the underlying
        # Surya incompatibility (out of scope here).
        logger.warning("Targeted OCR failed unexpectedly for heading '{}': {}", heading.text, exc)
        return None

    if not ocr_text:
        return EvidenceSignal(
            name="targeted_ocr_confirmation", score=0.0, weight=1.0,
            note="targeted OCR recognized no text at this heading's location",
        )
    ratio = difflib.SequenceMatcher(None, _normalize(ocr_text), _normalize(heading.text)).ratio()
    return EvidenceSignal(
        name="targeted_ocr_confirmation",
        score=ratio,
        weight=1.0,
        note=f"OCR read '{ocr_text}' vs Mathpix '{heading.text}' (similarity {ratio:.2f})",
    )


class HeadingVerifier(SemanticVerifier):
    asset_type = "heading"

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        return MultiSignalMatcher(
            [
                WeightedSignal(name="exact_text", fn=_exact_text_signal, min_confidence=0.99),
                WeightedSignal(name="text_similarity", fn=_text_similarity_signal, min_confidence=_TEXT_SIMILARITY_MATCH_MIN),
                WeightedSignal(name="page_proximity", fn=_page_proximity_signal, min_confidence=0.5),
                WeightedSignal(name="positional_fallback", fn=_positional_signal, min_confidence=0.01),
            ]
        )

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Heading]:
        """Headings arrive from Mathpix already as canonical Heading
        objects (src/mathpix/ingestor.py) — there is no separate uploaded
        asset to match at import time (unlike Figure). Identity passthrough;
        not currently invoked by the pipeline (headings only go through
        run_pdf_verification this session) — implemented for base-class
        completeness and future import-time use."""
        return list(match_result.unmatched_a) + [pair.a for pair in match_result.pairs]

    def _is_mismatch(self, canonical: Heading, pdf_heading: Heading) -> bool:
        return canonical.level != pdf_heading.level or _normalize(canonical.text) != _normalize(pdf_heading.text)

    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        """FEATURE_019: every candidate with a canonical (Mathpix) heading
        gets a fused, multi-signal EvidenceBundle — the PDF match, PDF
        typography, whitespace isolation, and running-header recurrence —
        rather than a decision from the binary PDF match alone. See the
        module docstring and the _*_signal() builders above.
        """
        findings: List[Finding] = []

        all_canonical: List[Heading] = [pair.a for pair in match_result.pairs] + list(match_result.unmatched_a)

        layout_context: Optional[HeadingLayoutContext] = None
        pdf_path = context.get("pdf_path")
        if pdf_path:
            layout_context = build_heading_layout_context(pdf_path)

        # M-5.3 — one TextResolver per page, built lazily and reused
        # across every heading on that page (the "cached normalization"
        # this milestone's performance requirement asks for) rather than
        # re-normalizing the same page's lines once per heading.
        layout_resolvers: Dict[int, TextResolver] = {}
        bbox_resolvers: Dict[int, TextResolver] = {}

        def _layout_resolver(page_number: int) -> Optional[TextResolver]:
            if layout_context is None:
                return None
            if page_number not in layout_resolvers:
                layout_resolvers[page_number] = TextResolver(layout_context.layout_index.get(page_number, {}))
            return layout_resolvers[page_number]

        def _bbox_resolver(page_number: int) -> Optional[TextResolver]:
            if layout_context is None:
                return None
            if page_number not in bbox_resolvers:
                bbox_resolvers[page_number] = TextResolver(layout_context.bbox_index.get(page_number, {}))
            return bbox_resolvers[page_number]

        for decision in self.merge_decisions(match_result, self._is_mismatch):
            if decision.canonical is None:
                # RECOVER: a real PDF heading Mathpix flattened to body text.
                pdf_heading: Heading = decision.pdf_evidence
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="missing_from_package",
                        object_id=None,
                        confidence=None,
                        evidence=f"pdf_page={pdf_heading.page_number}; pdf_level=H{int(pdf_heading.level)}",
                        message=(
                            f"PDF page {pdf_heading.page_number} has a heading "
                            f"('{pdf_heading.text}') not present in the Mathpix package."
                        ),
                        proposed_value=_encode_recovery(pdf_heading),
                        evidence_items=[
                            EvidenceSignal(name="pdf_typography", score=1.0, weight=1.0, note=f"H{int(pdf_heading.level)} by font-size rank"),
                            EvidenceSignal(name="pdf_page", score=1.0, weight=1.0, note=str(pdf_heading.page_number)),
                        ],
                    )
                )
                continue

            canonical: Heading = decision.canonical
            pdf_heading = decision.pdf_evidence
            pdf_mismatch = pdf_heading is not None and self._is_mismatch(canonical, pdf_heading)

            bundle = EvidenceBundle()
            pdf_signal = _pdf_match_signal(decision.confidence, pdf_mismatch)
            if pdf_signal is not None:
                bundle.add(pdf_signal)
            if layout_context is not None:
                typography = _typography_signal(canonical, layout_context, _layout_resolver(canonical.page_number))
                if typography is not None:
                    bundle.add(typography)
                whitespace = _whitespace_signal(canonical, layout_context, _bbox_resolver(canonical.page_number))
                if whitespace is not None:
                    bundle.add(whitespace)
            running_header = _running_header_signal(canonical, all_canonical)
            bundle.add(running_header)

            # M-5.1 — targeted OCR as one more EvidenceSignal, evidence of
            # last resort: only called when the bundle built from every
            # other signal is still ambiguous. Never runs for an
            # already-confident candidate, and never changes how
            # confidence itself is calculated (EvidenceBundle's weighted
            # mean is unchanged) — it only ever contributes one more
            # signal into the same existing formula.
            if bundle.confidence <= _OCR_AMBIGUOUS_CONFIDENCE_THRESHOLD:
                ocr_signal = _targeted_ocr_signal(
                    canonical, layout_context, pdf_path, _bbox_resolver(canonical.page_number)
                )
                if ocr_signal is not None:
                    bundle.add(ocr_signal)

            canonical.confidence = bundle.confidence

            # Running-header recurrence answers a different question ("does
            # this belong as a heading at all") than the level/text repair
            # check below ("if it belongs, is the level/text right") — a
            # weak running-header score proposes REMOVE regardless of
            # whether the PDF pass separately confirmed level/text, since
            # there is no PDF-proposed replacement value to repair toward.
            if running_header.score < _RUNNING_HEADER_REPAIR_THRESHOLD:
                canonical.verification_status = VerificationStatus.MISMATCH
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="likely_running_header",
                        object_id=canonical.id,
                        confidence=bundle.confidence,
                        evidence=bundle.explanation,
                        message=(
                            f"'{canonical.text}' on page {canonical.page_number} looks like a "
                            "running header/footer, not a real heading."
                        ),
                        original_value=canonical.text,
                        # Not "nothing" — the restore payload revert() needs
                        # once apply() has deleted the live object (see
                        # revert() below). Same encoding _encode_recovery()
                        # already uses for the RECOVER case.
                        proposed_value=_encode_recovery(canonical),
                        evidence_items=list(bundle.signals),
                    )
                )
                continue

            if pdf_heading is None:
                canonical.verification_status = VerificationStatus.MISSING_FROM_PDF
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="unconfirmed",
                        object_id=canonical.id,
                        confidence=bundle.confidence,
                        evidence=bundle.explanation,
                        message=f"Heading '{canonical.text}' could not be confirmed against the PDF.",
                    )
                )
                continue

            action = decide_from_evidence(bundle, has_canonical=True, is_mismatch=pdf_mismatch)
            if action != MergeAction.REPAIR:
                canonical.verification_status = VerificationStatus.VERIFIED
                continue

            canonical.verification_status = VerificationStatus.MISMATCH
            if canonical.level != pdf_heading.level:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="level_mismatch",
                        object_id=canonical.id,
                        confidence=bundle.confidence,
                        evidence=bundle.explanation,
                        message=(
                            f"Heading level disagrees: Mathpix says H{int(canonical.level)}, "
                            f"PDF typography suggests H{int(pdf_heading.level)}."
                        ),
                        original_value=str(int(canonical.level)),
                        proposed_value=str(int(pdf_heading.level)),
                        evidence_items=list(bundle.signals),
                    )
                )
            if _normalize(canonical.text) != _normalize(pdf_heading.text):
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="text_correction",
                        object_id=canonical.id,
                        confidence=bundle.confidence,
                        evidence=bundle.explanation,
                        message="Heading text differs from the PDF — possible OCR/recognition error.",
                        original_value=canonical.text,
                        proposed_value=pdf_heading.text,
                        evidence_items=list(bundle.signals),
                    )
                )

        return findings

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {
            "unconfirmed": RuleSpec(
                rule_id="HEADING_VERIFY_001", reason_code="HEADING_UNCONFIRMED_BY_PDF", severity="info"
            ),
            "missing_from_package": RuleSpec(
                rule_id="HEADING_VERIFY_002", reason_code="HEADING_MISSING_FROM_PACKAGE", severity="warning"
            ),
            "level_mismatch": RuleSpec(
                rule_id="HEADING_VERIFY_003", reason_code="HEADING_LEVEL_MISMATCH", severity="warning"
            ),
            "text_correction": RuleSpec(
                rule_id="HEADING_VERIFY_004", reason_code="HEADING_TEXT_OCR_ERROR", severity="warning"
            ),
            "likely_running_header": RuleSpec(
                rule_id="HEADING_VERIFY_005", reason_code="HEADING_LIKELY_RUNNING_HEADER", severity="warning"
            ),
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        if correction.field == "missing_from_package":
            if not correction.proposed_value:
                return
            _insert_recovered_heading(document, _decode_recovery(correction.proposed_value))
            return

        if correction.object_id is None:
            return
        heading = next((h for h in document.headings if h.id == correction.object_id), None)
        if heading is None:
            return

        if correction.field == "level_mismatch" and correction.proposed_value:
            heading.level = HeadingLevel(int(correction.proposed_value))
        elif correction.field == "text_correction" and correction.proposed_value:
            heading.text = correction.proposed_value
        elif correction.field == "likely_running_header":
            # REMOVE, reviewer-accepted (FEATURE_019 — every REMOVE lands
            # PROPOSED and only reaches apply() once a human has Accepted
            # it via the Corrections API; see src/verification/merge.py).
            document.headings = [h for h in document.headings if h.id != heading.id]
        # "unconfirmed" is informational only — no proposed_value, no-op.

    def revert(self, document: Any, correction: CorrectionRecord) -> None:
        """likely_running_header's REMOVE needs a real restore, not the
        base class's default "replay apply() with values swapped" — by
        the time revert() runs, apply() has already deleted the Heading
        object entirely, so there is nothing left to swap values on.
        proposed_value carries the full reconstruction payload (level/
        text/page_number) set at classify() time, in the same encoding
        _encode_recovery()/_decode_recovery() already use for RECOVER —
        reused here rather than inventing a second format.
        """
        if correction.field == "likely_running_header":
            if correction.proposed_value:
                _insert_recovered_heading(document, _decode_recovery(correction.proposed_value))
            return
        super().revert(document, correction)


def _register() -> None:
    from src.verification.engine import engine

    engine.register(HeadingVerifier())


_register()
