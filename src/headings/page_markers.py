"""Canonical page-marker construction for RAWRS.

Every page of every document carries exactly one H6 page marker
(``is_page_marker=True``) in ``Document.headings``, unless the active
page-numbering policy suppresses it. See docs/PAGE_RULES.md.

This module is the single source of truth for building those markers.
It exists because the rule was previously implemented independently in
each ingestion path, and the Mathpix path simply omitted it:

  * ``headings/heading_detector.py`` (native PDF) built markers inline.
  * ``mathpix/ingestor.py``          built none at all.
  * ``markdown/markdown_builder.py`` silently synthesized a replacement
    at render time when the model had none.

The third of those hid the second. Markdown output looked correct
(``###### 1``, ``###### 2``, ...) because the renderer patched over the
gap, while ``Document.headings`` — the canonical model every validator
and API reads — contained no markers at all. PAGE_001 therefore
reported "Page N has no H6 page marker" for every page of every Mathpix
document, and those phantom errors drove the accessibility readiness
score (FE-0-004).

Both ingestion paths now call ``build_page_marker()``, so the two cannot
drift apart again without changing this function.
"""

from typing import Optional

from src.models.heading import Heading, HeadingLevel
from src.models.page import Page


def build_page_marker(
    page: Page,
    page_numbering_policy: Optional[object] = None,
    document_order: int = 0,
) -> Optional[Heading]:
    """Return the H6 page marker for ``page``, or None if suppressed.

    Label precedence is the reviewed ``page_label`` (FEATURE_018), then
    the detected ``printed_label`` (feature_009), then the physical page
    number.

    When ``page_numbering_policy`` is supplied it is the sole decision
    point: returning None suppresses the marker entirely (AUTO mode on a
    page with no detected printed number, DISABLED, or a page outside a
    MANUAL_RANGE). When it is None the legacy behaviour is preserved —
    always emit a marker — so callers predating the policy are unchanged.
    """
    effective_label = page.page_label or page.printed_label

    if page_numbering_policy is not None:
        marker_text: Optional[str] = page_numbering_policy.resolve_marker_text(
            page.page_number, effective_label
        )
    else:
        marker_text = effective_label or str(page.page_number)

    if marker_text is None:
        return None

    return Heading(
        level=HeadingLevel.H6,
        text=marker_text,
        page_number=page.page_number,
        document_order=document_order,
        is_page_marker=True,
    )
