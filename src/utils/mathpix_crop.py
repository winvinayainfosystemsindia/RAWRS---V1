"""Read the crop box out of a Mathpix image reference.

Mathpix cuts each figure from its render of the page and records where:

* an uploaded image file is named ``{uuid}-{page}_{height}_{width}_{top_y}_{top_x}.jpg``
  (checked on O'Leary: every file's pixel size is exactly width x height);
* the MMD refers to the same crop as
  ``https://cdn.mathpix.com/cropped/{uuid}-{page}.jpg?height=..&width=..&top_left_y=..&top_left_x=..``.

Both the page estimator (which page a figure is on, and how far down) and the
DOCX projection (how wide the figure was printed) read this, so it lives in the
foundation layer both may import.
"""

import re
from pathlib import Path
from typing import NamedTuple, Optional, Union


class CropBox(NamedTuple):
    page: int
    height: int
    width: int
    top_y: int
    top_x: int

    def width_fraction(self) -> float:
        """How much of the page's width the figure spans. The render's width is
        taken as the crop plus an equal margin either side - figures in the
        corpus are centred in the text block."""
        render_width = self.width + 2 * self.top_x
        return self.width / render_width if render_width else 1.0


_FILENAME_BOX_RE = re.compile(r"-(\d{1,3})_(\d+)_(\d+)_(\d+)_(\d+)$")
_URL_PAGE_RE = re.compile(r"-(\d{1,3})\.\w+(?:\?|$)")


def crop_box(reference: Union[str, Path, None]) -> Optional[CropBox]:
    if not reference:
        return None
    text = str(reference)
    match = _FILENAME_BOX_RE.search(Path(text.split("?", 1)[0]).stem)
    if match:
        return CropBox(*(int(group) for group in match.groups()))
    page = _URL_PAGE_RE.search(text)
    query = dict(re.findall(r"(\w+)=(\d+)", text.split("?", 1)[1])) if "?" in text else {}
    if not page or not {"height", "width", "top_left_y", "top_left_x"} <= set(query):
        return None
    return CropBox(
        int(page.group(1)),
        int(query["height"]),
        int(query["width"]),
        int(query["top_left_y"]),
        int(query["top_left_x"]),
    )
