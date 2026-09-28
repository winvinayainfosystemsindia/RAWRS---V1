"""Alt text for every image, without waiting for a reviewer to ask.

The remediation checklist's first "Final Formatting" item is "Adding Alt
text for all images". Until now RAWRS wrote a placeholder ("Image from page
3: description pending human review") and generated a real description only
when a reviewer pressed a button, so every figure in every exported DOCX
failed that item. This stage does the reviewer's first pass itself:

* an image with no visual content (a blank panel, a grey gradient left by a
  scan), one that recurs on several pages (a margin icon, a drop shadow) or
  one only a few pixels tall (a rule, a banner strip) is marked
  **decorative** - it has nothing to describe, and a vision model asked
  about one invents something (measured: "a screenshot of a webpage" for a
  plain gradient). On Bryman this is 106 of 112 images, which is also what
  keeps a CPU-only model's ~2.5 minutes per image affordable;
* every other image gets the vision model's description as its alt text,
  status ``AI_GENERATED`` - still a proposal the reviewer can approve, edit
  or reject, exactly as if they had pressed the button.

Only a real model writes alt text. The test stub's canned output is never
put into a document, and when no model is available the placeholder stays,
so the checklist audit reports the gap instead of hiding it.
"""

import re
from pathlib import Path
from typing import Callable, List

from loguru import logger
from PIL import Image as PILImage
from PIL import ImageFilter, ImageStat

from src.models.figure import AltTextStatus, Figure

# Mean edge strength (PIL FIND_EDGES, greyscale) below which an image carries
# no shapes or text. Measured on the benchmark corpus: the four scan-residue
# panels on O'Leary p6 sit at 2.5-3.8; every real figure, chart and logo at
# 8.4 or above.
VISUALLY_EMPTY_EDGE_STRENGTH = 5.0
# A picture shorter or narrower than this is an ornament (a rule, a bullet
# glyph, a banner strip), not something a reader needs described.
ORNAMENT_MAX_SIDE_PX = 50
# Two images whose 64-bit difference hashes differ in at most this many bits
# are the same picture. Measured on Bryman: its 95 margin icons and shadows
# (lightbulbs, coin stacks, drop shadows) recur on 2-14 pages each within 10
# bits; no real figure in the corpus recurs at all.
SAME_PICTURE_MAX_HASH_DISTANCE = 10
_STUB_PROVIDER_NAME = "stub"


def _difference_hash(image_path: str) -> int:
    with PILImage.open(image_path) as image:
        pixels = list(image.convert("L").resize((9, 8)).getdata())
    return sum(
        1 << bit for bit in range(64) if pixels[(bit // 8) * 9 + bit % 8] > pixels[(bit // 8) * 9 + bit % 8 + 1]
    )


def recurring_image_ids(images: list) -> set:
    """Images whose picture appears on two or more pages: a repeated icon,
    ornament or page decoration. A document's figures are each printed once.

    ponytail: pairwise O(n^2) over a document's images (112 for the largest
    corpus document, ~6k comparisons); bucket by hash prefix if documents
    with thousands of images appear.
    """
    hashes = []
    for image in images:
        try:
            hashes.append((image, _difference_hash(image.file_path)))
        except Exception:
            continue
    recurring = set()
    for image, digest in hashes:
        pages = {
            other.page_number
            for other, other_digest in hashes
            if bin(digest ^ other_digest).count("1") <= SAME_PICTURE_MAX_HASH_DISTANCE
        }
        if len(pages) >= 2:
            recurring.add(image.image_id)
    return recurring


def is_ornament(image_path: str) -> bool:
    try:
        with PILImage.open(image_path) as image:
            return min(image.size) < ORNAMENT_MAX_SIDE_PX
    except Exception:
        return False


def is_visually_empty(image_path: str) -> bool:
    try:
        with PILImage.open(image_path) as image:
            grey = image.convert("L")
            return ImageStat.Stat(grey.filter(ImageFilter.FIND_EDGES)).mean[0] < VISUALLY_EMPTY_EDGE_STRENGTH
    except Exception as exc:
        logger.warning("Could not measure image '{}': {}", image_path, exc)
        return False


def speakable_alt_text(description: str, visible_text: str) -> str:
    """The description, plus any text printed in the image, with the symbols
    the checklist says a screen reader does not read ("In alt text box,
    symbols does not read") removed."""
    text = description.strip()
    visible = (visible_text or "").strip()
    if visible and visible.lower() not in ("none", "n/a", ""):
        text = f"{text} Text in the image: {visible}"
    text = re.sub(r"[*_#`~^|<>{}\[\]\\]", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def apply_automatic_alt_text(document, nearby_text: Callable[[object], List[str]]) -> dict:
    """Give every image still awaiting review its first alt text.

    Returns counts per outcome, for the pipeline log.
    """
    from src.ai.alt_text_generator import AltTextGenerationError, AltTextRequest, generate_alt_text
    from src.ai.provider import AIProviderUnavailableError
    from src.ai.registry import get_provider

    counts = {"decorative": 0, "described": 0, "unchanged": 0}
    pending = [
        image for image in document.images
        if not image.extraction_failed
        and image.file_path
        and Path(image.file_path).is_file()
        and (image.figure is None or image.figure.alt_text_status in (None, AltTextStatus.PENDING_REVIEW))
    ]
    remaining = []
    recurring = recurring_image_ids(pending)
    for image in pending:
        if (
            is_visually_empty(image.file_path)
            or image.image_id in recurring
            or is_ornament(image.file_path)
        ):
            if image.figure is None:
                image.figure = Figure()
            image.figure.alt_text = ""
            image.figure.alt_text_status = AltTextStatus.DECORATIVE
            counts["decorative"] += 1
        else:
            remaining.append(image)
    if not remaining:
        return counts

    try:
        provider = get_provider()
    except AIProviderUnavailableError as exc:
        logger.warning("Automatic alt text skipped for {} image(s): {}", len(remaining), exc)
        counts["unchanged"] = len(remaining)
        return counts
    if provider.name.lower().startswith(_STUB_PROVIDER_NAME):
        counts["unchanged"] = len(remaining)
        return counts

    for image in remaining:
        figure = image.figure or Figure()
        request = AltTextRequest(
            image_path=image.file_path,
            caption=figure.caption,
            figure_label=figure.label,
            nearby_text=nearby_text(image),
            page_number=image.page_number,
        )
        try:
            result = generate_alt_text(request)
        except AltTextGenerationError as exc:
            logger.warning("Automatic alt text failed for image {}: {}", image.image_id, exc)
            counts["unchanged"] += 1
            continue
        figure.ai_description = result.description
        figure.ai_purpose = result.purpose
        figure.ai_visible_text = result.visible_text
        figure.ai_confidence = result.confidence
        figure.ai_warnings = result.warnings
        figure.alt_text = speakable_alt_text(result.description, result.visible_text)
        figure.alt_text_status = AltTextStatus.AI_GENERATED
        image.figure = figure
        counts["described"] += 1
    return counts
