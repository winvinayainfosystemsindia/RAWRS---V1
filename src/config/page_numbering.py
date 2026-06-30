"""Configurable page numbering policy for RAWRS."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PageNumberingMode(Enum):
    """Controls which pages receive H6 markers and what text those markers contain.

    AUTO: emit only detected printed page numbers (Page.printed_label);
        pages with no detected number get no marker.
    MANUAL_RANGE: emit markers for physical pages in the inclusive
        [range_start, range_end] window; text is the printed label if
        detected, else the physical page number.
    MANUAL_NUMBER_OVERRIDE: emit a marker for every page numbered
        sequentially from number_start (page 1 → number_start,
        page 2 → number_start + 1, …).
    DISABLED: emit no page markers.
    """

    AUTO = "auto"
    MANUAL_RANGE = "manual_range"
    MANUAL_NUMBER_OVERRIDE = "manual_number_override"
    DISABLED = "disabled"


@dataclass
class PageNumberingPolicy:
    """Configures how H6 page markers are generated during heading detection
    and markdown rendering.

    Fields are mode-specific:
    - range_start / range_end: MANUAL_RANGE only (1-based physical page
      number; range_start defaults to 1 if omitted).
    - number_start: MANUAL_NUMBER_OVERRIDE only (the label assigned to
      physical page 1; defaults to 1 if omitted).

    ``resolve_marker_text`` is the single decision point called per page.
    """

    mode: PageNumberingMode = PageNumberingMode.AUTO
    range_start: Optional[int] = None
    range_end: Optional[int] = None
    number_start: Optional[int] = None

    def resolve_marker_text(
        self, page_number: int, printed_label: Optional[str]
    ) -> Optional[str]:
        """Return the marker text for this page, or None to suppress it.

        Args:
            page_number: Physical 1-based position in the PDF.
            printed_label: The page number actually printed on the page
                (Page.printed_label), or None if none was detected.
        """
        if self.mode == PageNumberingMode.DISABLED:
            return None

        if self.mode == PageNumberingMode.AUTO:
            return printed_label  # None → no marker emitted

        if self.mode == PageNumberingMode.MANUAL_RANGE:
            lo = self.range_start if self.range_start is not None else 1
            hi = self.range_end
            if hi is None or lo <= page_number <= hi:
                return printed_label or str(page_number)
            return None

        if self.mode == PageNumberingMode.MANUAL_NUMBER_OVERRIDE:
            return str((self.number_start or 1) + (page_number - 1))

        return None  # unreachable; guard against future enum extension
