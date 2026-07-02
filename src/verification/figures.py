"""Figures: the first asset type registered with the cross-source verification engine.

Two matching problems, both handled by the same generic
`MultiSignalMatcher` (src/verification/matching.py), just configured with
different signals:

1. Import-time: pair each MMD figure block (from the uploaded MMD) against
   an uploaded image file, so every uploaded image enters the canonical
   Document model — never silently dropped.
2. PDF-verification-time: pair each canonical (Mathpix-sourced) Image
   against an independently PDF-extracted Image, purely to flag
   discrepancies. The PDF never gets to decide whether a figure exists —
   it only produces Findings.

Headings, lists, and future asset types follow this same base-class shape
(``SemanticVerifier``, src/verification/base.py); nothing in
src/verification/engine.py or base.py is specific to figures. This is also
the first verifier migrated onto that base — see ``FigureVerifier`` below,
and its PDF-verification classify() built on the generic Document Merge
Layer (src/verification/merge.py) instead of a hand-written matched/
unmatched loop.
"""

from __future__ import annotations

import difflib
import hashlib
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.images.image_extractor import _build_placeholder_alt_text, _CAPTION_PATTERN
from src.mathpix.page_estimation import estimate_page
from src.models.correction import CorrectionRecord
from src.models.figure import AltTextStatus, Figure
from src.models.image import Image
from src.models.phase2_document import P2Block, P2BlockType
from src.models.verification import Finding, ImportSource, RuleSpec, VerificationStatus
from src.verification.base import SemanticVerifier
from src.verification.matching import MatchResult, MultiSignalMatcher, WeightedSignal
from src.verification.merge import MergeAction

try:
    from PIL import Image as PILImage
except ImportError:  # pragma: no cover - PIL is an existing transitive dependency
    PILImage = None

# Confidence below this on a PDF-verification match is flagged for review,
# not treated as a confirmed correspondence.
_LOW_CONFIDENCE_THRESHOLD = 0.5
# Minimum caption similarity for the caption_similarity *matching* signal to
# fire at all (i.e. propose these two images as the same figure).
_CAPTION_MATCH_MIN_CONFIDENCE = 0.5
# Once two images are already matched (by whatever signal won), caption
# similarity below this stricter ratio is reported as a mismatch worth a
# reviewer's attention. Deliberately higher than the matching threshold
# above: two captions sharing only a "Figure N." prefix still score ~0.6 on
# SequenceMatcher, which is fine to *match* on other signals but should
# still surface as "these captions actually disagree."
_CAPTION_MISMATCH_RATIO = 0.65


def _normalize_stem(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


# ── Import-time signals: MMD figure block <-> uploaded file ────────────

def _exact_mmd_ref_signal(block: P2Block, path: Path) -> Optional[float]:
    if block.figure is None or not block.figure.image_path:
        return None
    ref_name = Path(block.figure.image_path).name.lower()
    if ref_name == path.name.lower():
        return 1.0
    return None


def _loose_filename_signal(block: P2Block, path: Path) -> Optional[float]:
    if block.figure is None or not block.figure.image_path:
        return None
    ref_stem = _normalize_stem(Path(block.figure.image_path).stem)
    candidate_stem = _normalize_stem(path.stem)
    if not ref_stem or not candidate_stem:
        return None
    ratio = difflib.SequenceMatcher(None, ref_stem, candidate_stem).ratio()
    return ratio if ratio >= 0.6 else None


def _positional_signal(_a: Any, _b: Any) -> Optional[float]:
    """Last-resort fallback: a constant weak confidence for any remaining
    pair. MultiSignalMatcher processes ties in original encounter order
    with a stable sort, so this reduces to "pair the Nth remaining item of
    A with the Nth remaining item of B" — genuine positional/document-order
    matching — without this signal needing to know list indices itself."""
    return 0.05


# ── PDF-verification signals: canonical Image <-> PDF-extracted Image ──

def _filename_signal(a: Image, b: Image) -> Optional[float]:
    if not a.uploaded_filename:
        return None
    ratio = difflib.SequenceMatcher(
        None, _normalize_stem(Path(a.uploaded_filename).stem), _normalize_stem(Path(b.file_path).stem)
    ).ratio()
    return ratio if ratio >= 0.8 else None


def _caption_similarity_signal(a: Image, b: Image) -> Optional[float]:
    a_caption = a.figure.caption if a.figure else None
    b_caption = b.figure.caption if b.figure else None
    if not a_caption or not b_caption:
        return None
    ratio = difflib.SequenceMatcher(None, a_caption.lower(), b_caption.lower()).ratio()
    return ratio if ratio >= _CAPTION_MATCH_MIN_CONFIDENCE else None


def _page_number_signal(a: Image, b: Image) -> Optional[float]:
    diff = abs(a.page_number - b.page_number)
    if diff == 0:
        return 0.9
    if diff == 1:
        return 0.6
    return None


def _dimension_signal(a: Image, b: Image) -> Optional[float]:
    if not a.width or not a.height or not b.width or not b.height:
        return None
    ar_a = a.width / a.height
    ar_b = b.width / b.height
    if max(ar_a, ar_b) == 0:
        return None
    diff = abs(ar_a - ar_b) / max(ar_a, ar_b)
    confidence = max(0.0, 1.0 - diff)
    return confidence if confidence >= 0.5 else None


def _visual_similarity_signal(_a: Image, _b: Image) -> Optional[float]:
    """Future extension point: perceptual-hash or embedding-based visual
    similarity. Always returns None (no opinion) until implemented."""
    return None


def _read_dimensions(path: Path) -> tuple:
    if PILImage is None:
        return None, None
    try:
        with PILImage.open(path) as im:
            return im.size
    except Exception:
        return None, None


def _parse_caption_label(caption: Optional[str]) -> tuple:
    if not caption:
        return None, None
    m = _CAPTION_PATTERN.match(caption.strip())
    if not m:
        return None, None
    number_text = m.group(1)
    try:
        number = int(float(number_text))
    except ValueError:
        number = None
    return f"Figure {number_text}", number


def _file_digest(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


class FigureVerifier(SemanticVerifier):
    asset_type = "figure"

    def build_import_matcher(self) -> MultiSignalMatcher:
        return MultiSignalMatcher(
            [
                WeightedSignal(name="exact_mmd_ref", fn=_exact_mmd_ref_signal, min_confidence=0.99),
                WeightedSignal(name="loose_filename", fn=_loose_filename_signal, min_confidence=0.6),
                WeightedSignal(name="positional_fallback", fn=_positional_signal, min_confidence=0.01),
            ]
        )

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        return MultiSignalMatcher(
            [
                WeightedSignal(name="filename", fn=_filename_signal, min_confidence=0.8),
                WeightedSignal(name="caption_similarity", fn=_caption_similarity_signal, min_confidence=_CAPTION_MATCH_MIN_CONFIDENCE),
                WeightedSignal(name="page_number", fn=_page_number_signal, min_confidence=0.6),
                WeightedSignal(name="image_metadata", fn=_dimension_signal, min_confidence=0.5),
                WeightedSignal(name="visual_similarity", fn=_visual_similarity_signal, min_confidence=0.5),
                WeightedSignal(name="positional_fallback", fn=_positional_signal, min_confidence=0.01),
            ]
        )

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Image]:
        page_count: int = context["page_count"]
        total_blocks: int = context["total_blocks"]
        images: List[Image] = []

        for pair in match_result.pairs:
            images.append(
                self._build_image(
                    block=pair.a,
                    path=pair.b,
                    confidence=pair.confidence,
                    signal=pair.matched_by,
                    total_blocks=total_blocks,
                    page_count=page_count,
                )
            )

        # Every uploaded image the package included gets registered, even
        # if no MMD figure block referenced it — an uploaded figure must
        # never silently disappear.
        for path in match_result.unmatched_b:
            images.append(
                self._build_image(
                    block=None,
                    path=path,
                    confidence=None,
                    signal=None,
                    total_blocks=total_blocks,
                    page_count=page_count,
                    orphan=True,
                )
            )

        images.sort(key=lambda img: img.page_number)
        return images

    def _build_image(
        self,
        *,
        block: Optional[P2Block],
        path: Path,
        confidence: Optional[float],
        signal: Optional[str],
        total_blocks: int,
        page_count: int,
        orphan: bool = False,
    ) -> Image:
        caption = block.figure.caption if block and block.figure else None
        page_number = (
            estimate_page(block.source_line, total_blocks, page_count) if block else page_count
        )
        label, number = _parse_caption_label(caption)
        width, height = _read_dimensions(path)

        return Image(
            image_id=str(uuid.uuid4()),
            page_number=page_number,
            file_path=str(path),
            width=width,
            height=height,
            import_source=ImportSource.MATHPIX,
            source_reference=(block.figure.image_path if block and block.figure else None),
            uploaded_filename=path.name,
            match_confidence=confidence,
            match_signal=signal,
            verification_status=VerificationStatus.ORPHAN if orphan else VerificationStatus.UNVERIFIED,
            figure=Figure(
                caption=caption,
                label=label,
                number=number,
                alt_text=_build_placeholder_alt_text(page_number, caption),
                alt_text_status=AltTextStatus.PENDING_REVIEW,
            ),
        )

    def classify(self, match_result: MatchResult, **context: Any) -> List[Finding]:
        phase = context.get("phase")
        if phase == "import":
            return self._classify_import(match_result)
        return self._classify_pdf_verification(match_result)

    def _classify_import(self, match_result: MatchResult) -> List[Finding]:
        findings: List[Finding] = []

        for block in match_result.unmatched_a:
            ref = block.figure.image_path if block.figure else None
            findings.append(
                Finding(
                    asset_type=self.asset_type,
                    kind="missing_from_package",
                    object_id=None,
                    confidence=None,
                    evidence=f"mmd_source_line={block.source_line}; mmd_image_path={ref}",
                    message=(
                        f"The MMD referenced a figure (near line {block.source_line}) "
                        "with no matching uploaded image in the package."
                    ),
                )
            )

        # Duplicate-content check across every uploaded file this call saw
        # (matched or not) — an uploaded image is never dropped for being a
        # duplicate, just flagged.
        all_paths = [pair.b for pair in match_result.pairs] + list(match_result.unmatched_b)
        seen: Dict[str, Path] = {}
        for path in all_paths:
            digest = _file_digest(path)
            if digest is None:
                continue
            if digest in seen:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="duplicate",
                        object_id=None,
                        confidence=None,
                        evidence=f"uploaded files '{seen[digest].name}' and '{path.name}' are byte-identical",
                        message=f"Uploaded image '{path.name}' duplicates '{seen[digest].name}'.",
                    )
                )
            else:
                seen[digest] = path

        for path in match_result.unmatched_b:
            findings.append(
                Finding(
                    asset_type=self.asset_type,
                    kind="orphan",
                    object_id=None,
                    confidence=None,
                    evidence=f"uploaded_filename={path.name}",
                    message=(
                        f"Uploaded image '{path.name}' was not referenced by any figure "
                        "in the MMD."
                    ),
                )
            )

        return findings

    @staticmethod
    def _captions_mismatch(canonical: Image, pdf_image: Image) -> bool:
        a_caption = canonical.figure.caption if canonical.figure else None
        b_caption = pdf_image.figure.caption if pdf_image.figure else None
        return bool(
            a_caption
            and b_caption
            and difflib.SequenceMatcher(None, a_caption.lower(), b_caption.lower()).ratio()
            < _CAPTION_MISMATCH_RATIO
        )

    def _classify_pdf_verification(self, match_result: MatchResult) -> List[Finding]:
        """Built on the generic Document Merge Layer (merge_decisions())
        instead of three hand-written matched/unmatched_a/unmatched_b loops.
        Confidence still takes priority over a caption disagreement for a
        matched pair (a low-confidence match is reported as such even when
        it also happens to disagree on caption) — page mismatch is an
        independent, additional check layered on top of any decision,
        exactly mirroring the pre-refactor behavior."""
        findings: List[Finding] = []

        for decision in self.merge_decisions(match_result, self._captions_mismatch):
            if decision.pdf_evidence is None:
                # unmatched_a: a canonical figure with no PDF confirmation.
                canonical: Image = decision.canonical
                canonical.verification_status = VerificationStatus.MISSING_FROM_PDF
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="missing_from_pdf",
                        object_id=canonical.image_id,
                        confidence=None,
                        evidence=f"page={canonical.page_number}",
                        message="This figure from the Mathpix package could not be confirmed against the PDF.",
                    )
                )
                continue

            if decision.canonical is None:
                # unmatched_b (RECOVER): a PDF image with no canonical counterpart.
                pdf_image: Image = decision.pdf_evidence
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="unmatched_pdf_image",
                        object_id=None,
                        confidence=None,
                        evidence=f"pdf_page={pdf_image.page_number}",
                        message=(
                            f"PDF page {pdf_image.page_number} contains an image not present "
                            "in the uploaded Mathpix package."
                        ),
                    )
                )
                continue

            # Matched pair: KEEP (captions agree) or REPAIR (captions disagree).
            canonical = decision.canonical
            pdf_image = decision.pdf_evidence
            canonical.match_confidence = decision.confidence
            canonical.match_signal = decision.signal
            a_caption = canonical.figure.caption if canonical.figure else None
            b_caption = pdf_image.figure.caption if pdf_image.figure else None

            if decision.confidence < _LOW_CONFIDENCE_THRESHOLD:
                canonical.verification_status = VerificationStatus.LOW_CONFIDENCE
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="low_confidence",
                        object_id=canonical.image_id,
                        confidence=decision.confidence,
                        evidence=f"matched_by={decision.signal}",
                        message=f"Figure match confidence is low ({decision.confidence:.2f}).",
                    )
                )
            elif decision.action == MergeAction.REPAIR:
                canonical.verification_status = VerificationStatus.MISMATCH
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="caption_mismatch",
                        object_id=canonical.image_id,
                        confidence=decision.confidence,
                        evidence=f"mathpix_caption={a_caption!r}; pdf_caption={b_caption!r}",
                        message="Caption text differs between the Mathpix package and the PDF.",
                        original_value=a_caption or "",
                        proposed_value=b_caption or "",
                    )
                )
            else:
                canonical.verification_status = VerificationStatus.VERIFIED
                if canonical.bbox is None:
                    canonical.bbox = pdf_image.bbox

            if canonical.page_number != pdf_image.page_number:
                findings.append(
                    Finding(
                        asset_type=self.asset_type,
                        kind="wrong_page",
                        object_id=canonical.image_id,
                        confidence=decision.confidence,
                        evidence=f"mathpix_page={canonical.page_number}; pdf_page={pdf_image.page_number}",
                        message=(
                            f"Figure page assignment disagrees: Mathpix page "
                            f"{canonical.page_number} vs PDF page {pdf_image.page_number}."
                        ),
                        original_value=str(canonical.page_number),
                        proposed_value=str(pdf_image.page_number),
                    )
                )

        return findings

    def rule_table(self) -> Dict[str, RuleSpec]:
        return {
            "missing_from_package": RuleSpec(
                rule_id="IMAGE_VERIFY_001", reason_code="FIGURE_MISSING_FROM_PACKAGE", severity="warning"
            ),
            "unmatched_pdf_image": RuleSpec(
                rule_id="IMAGE_VERIFY_002", reason_code="FIGURE_MISSING_FROM_PROVIDER", severity="warning"
            ),
            "orphan": RuleSpec(
                rule_id="IMAGE_VERIFY_003", reason_code="FIGURE_ORPHAN_UPLOAD", severity="warning"
            ),
            "caption_mismatch": RuleSpec(
                rule_id="IMAGE_VERIFY_004", reason_code="FIGURE_CAPTION_MISMATCH", severity="warning"
            ),
            "duplicate": RuleSpec(
                rule_id="IMAGE_VERIFY_005", reason_code="FIGURE_DUPLICATE_UPLOAD", severity="warning"
            ),
            "low_confidence": RuleSpec(
                rule_id="IMAGE_VERIFY_006", reason_code="FIGURE_LOW_CONFIDENCE_MATCH", severity="warning"
            ),
            "wrong_page": RuleSpec(
                rule_id="IMAGE_VERIFY_007", reason_code="FIGURE_PAGE_MISMATCH", severity="warning"
            ),
            "missing_from_pdf": RuleSpec(
                rule_id="IMAGE_VERIFY_008", reason_code="FIGURE_MISSING_FROM_PDF", severity="info"
            ),
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        """Adopt the PDF-detected value for the two kinds that propose one.

        ``caption_mismatch`` -> replace Figure.caption with the PDF's.
        ``wrong_page`` -> replace Image.page_number with the PDF's.
        Every other kind (low_confidence, missing_from_pdf,
        unmatched_pdf_image, orphan, duplicate, missing_from_package) is
        informational only — no proposed_value describes a document
        mutation, so this is a documented no-op for those.
        """
        if correction.object_id is None:
            return
        image = next((img for img in document.images if img.image_id == correction.object_id), None)
        if image is None:
            return

        if correction.field == "caption_mismatch" and image.figure is not None:
            image.figure.caption = correction.proposed_value
        elif correction.field == "wrong_page" and correction.proposed_value:
            image.page_number = int(correction.proposed_value)


# Backward-compatible alias — existing tests import/instantiate this name
# directly (pre-dating the SemanticVerifier base class migration).
FigureAssetVerifier = FigureVerifier


def _register() -> None:
    from src.verification.engine import engine

    engine.register(FigureVerifier())


_register()
