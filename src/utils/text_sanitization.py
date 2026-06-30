"""Shared XML/OOXML text sanitization for RAWRS (XML Sanitization Architecture, Layer 1).

A production PDF crashed src/docx/docx_generator.py with "All strings
must be XML compatible: Unicode or ASCII, no NULL bytes or control
characters" - a ValueError raised by lxml itself (apihelpers.pxi,
_utf8/_createTextNode) the instant any OOXML text node or attribute is
set to a string containing a character outside what XML 1.0 allows.
Root-cause audit traced this to broken PDF font ToUnicode mappings:
PyMuPDF (and, less commonly, an OCR engine) can legitimately decode a
glyph to a control-range codepoint while the rest of the page decodes
as ordinary prose - src/ocr/router.py's own existing
_unusable_char_ratio() already names this exact phenomenon, but only
ever used it for OCR routing, never to clean the text it measured.

This module is Layer 1 of a three-layer defense-in-depth design (see
the XML Sanitization Architecture Review, docs/DECISIONS_LOG.md):

  Layer 1 (here) - sanitize at every point text first enters the
    Document model, so Document.pages/Document.blocks - and therefore
    every downstream consumer (headings, captions, footnotes, Markdown,
    the in-memory model itself, any future API/frontend) - are clean
    without each consumer needing to know to ask.
  Layer 2 (src/validation/validator.py, rule DOC_004) - surfaces every
    place Layer 1 actually had to act, as an auditable ValidationIssue,
    since by design Layer 1 has already cleaned the text by the time
    Layer 2 runs - DOC_004 reports a disclosure, not a prediction.
  Layer 3 (src/docx/docx_generator.py) - a last-resort guard at the
    handful of call sites that actually construct OOXML text nodes/
    attributes, in case some future text-creation path (e.g. AI-
    generated alt text, equation/table/callout detection) is added
    without being wired into Layer 1 - this is what makes the system
    safe regardless of whether every future contributor remembers to.

Why not sanitize only at the DOCX boundary (Layer 3 alone): Markdown
generation (src/markdown/markdown_builder.py) renders the same
Page.cleaned_text/Heading.text/Figure.caption/Footnote.body fields
verbatim, and "Markdown is the source of truth for downstream
processing" is this project's own stated architecture principle
(docs/ARCHITECTURE.md). Sanitizing only at the DOCX boundary would let
Markdown and DOCX silently diverge - the DOCX would be clean while the
Markdown (and the in-memory Document) still carried the illegal
character. Layer 1 keeps every artifact consistent with each other.
"""

import re
from typing import List, Tuple

# Empirically verified against this project's installed lxml (not
# assumed from the XML 1.0 spec alone - see the architecture review):
# lxml rejects every C0 control character except tab (\x09), LF (\x0A),
# and CR (\x0D), which are explicitly legal XML whitespace. \x7F (DEL)
# was also checked and is legal (within XML's [#x20-#xD7FF] Char
# range) - deliberately NOT included here, since stripping a
# technically-legal character would be over-sanitization with no
# corresponding crash to prevent.
_ILLEGAL_XML_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

# Lone UTF-16 surrogates (U+D800-U+DFFF unpaired) are a separate,
# rarer encoding defect - never produced by legitimate text, only by
# malformed decoding - but fail XML serialization too (a
# UnicodeEncodeError, confirmed empirically, not the ValueError this
# module is primarily about). Same failure family, same fix: remove
# before the text reaches any OOXML/XML serialization.
_LOW_SURROGATE = 0xD800
_HIGH_SURROGATE = 0xDFFF


def sanitize_xml_text(text: str) -> Tuple[str, List[str]]:
    """Remove characters illegal in OOXML/XML 1.0 text nodes and attributes.

    Args:
        text: Any extracted/recovered text - direct extraction, OCR
            output, or a structure-detection text line. Safe to call on
            already-clean text (returns it unchanged, with an empty
            removed list).

    Returns:
        (clean_text, removed_codepoints). removed_codepoints lists each
        illegal character actually found and removed, as "U+XXXX"
        strings in encounter order - empty if text was already clean.
        Callers that want an audit trail (see
        src/models/sanitization.py) attach this list, with their own
        page_number/field context, to Document.sanitization_events;
        callers that don't (e.g. Layer 3's last-resort guard, which
        only logs) may simply discard it.
    """
    removed: List[str] = []

    def _replace_control(match: "re.Match[str]") -> str:
        removed.append(f"U+{ord(match.group(0)):04X}")
        return ""

    cleaned = _ILLEGAL_XML_CONTROL_PATTERN.sub(_replace_control, text)

    if any(_LOW_SURROGATE <= ord(ch) <= _HIGH_SURROGATE for ch in cleaned):
        kept_chars = []
        for ch in cleaned:
            if _LOW_SURROGATE <= ord(ch) <= _HIGH_SURROGATE:
                removed.append(f"U+{ord(ch):04X}")
            else:
                kept_chars.append(ch)
        cleaned = "".join(kept_chars)

    return cleaned, removed
