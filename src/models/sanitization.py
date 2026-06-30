"""SanitizationEvent model for RAWRS (XML Sanitization Architecture, Layer 1 audit trail).

See the XML Sanitization Architecture Review (docs/DECISIONS_LOG.md) for
why this model exists: Layer 1 (src/utils/text_sanitization.py, called
at extraction/structure-detection time) removes XML/OOXML-illegal
characters from text before it is ever assigned into a Page/TextBlock
field. By the time DOC_004 (src/validation/validator.py, Layer 2) runs,
the text in Document.pages/Document.blocks is already clean - there is
nothing left to re-detect by inspecting those fields after the fact.
This model is the record Layer 1 itself emits at the moment it acts, so
Layer 2 has something to surface as an auditable ValidationIssue rather
than re-deriving (and re-running) extraction a second time.
"""

from typing import List

from pydantic import BaseModel, Field


class SanitizationEvent(BaseModel):
    """One occurrence of Layer 1 removing illegal character(s) from a
    specific piece of extracted text.

    ``field`` names which kind of text was affected (e.g. "page_text",
    "text_block") rather than a specific model field path, since the
    exact consumer (a heading, a caption, a footnote body) is often
    determined only later, by code that has no knowledge this
    sanitization already happened upstream - see module docstring.
    ``removed_codepoints`` records each illegal character actually
    found, as "U+XXXX" strings in encounter order, so a human reviewer
    (via DOC_004) can see exactly what was removed without needing the
    original, already-discarded dirty text.
    """

    page_number: int = Field(..., ge=1)
    field: str = Field(..., min_length=1)
    removed_codepoints: List[str] = Field(default_factory=list)
