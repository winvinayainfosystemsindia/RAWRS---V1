"""Checklist text rules for the Word projection.

``docs/Checklist for Document Remediation1.docx`` asks a remediator to fix
spacing, spell out initialisms for screen readers, space units and write
numbered headings as ``6.1 - INTRODUCTION``. These are presentation rules
for the DOCX a reader opens, so they are applied where DOCX text is written
and never to the model: ``Paragraph.text`` stays the source's own words.

Every function here is pure and idempotent, so the auditor
(``src/validation/checklist_audit.py``) can ask the same question of a
finished DOCX that the generator answered while writing it.
"""

import re
from typing import Callable, List

# URLs are copied through untouched: a comma or bracket inside one is part
# of its address, not punctuation.
URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"]+[^\s<>\".,;:!?)\]]", re.IGNORECASE)

# --- punctuation (checklist "Proper spacing between the punctuations") -------

# Typographic ligatures (ﬁ, ﬀ ...) are single glyphs a screen reader may skip or
# misread, and they break search: "ﬁnd" does not match "find".
_LIGATURES = str.maketrans({
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
    "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
})
# En/em/thin spaces and the like are spaces to a reader, not layout.
_ODD_SPACES = re.compile(r"[  -   　]")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def has_ligatures(text: str) -> bool:
    return text != text.translate(_LIGATURES)


# Some publishers' math fonts (Sage's, measured on Brinkman) map "=" to the
# code point of "¼", so the text layer reads "r ¼ .66" where the page shows
# "r = .66". A spaced "¼" before a number is that "=", never a quarter: a
# real fraction is written against its number ("1¼").
_MISMAPPED_EQUALS = re.compile(r"(?<=\s)¼(?=\s*[-−]?\.?\d)")
_SPACE_BEFORE_COMMA = re.compile(r"(?<=\S)[ \t]+,")
# After a comma: a space, unless a digit follows (1,000).
_NO_SPACE_AFTER_COMMA = re.compile(r",(?=[A-Za-z(\[])")
# Before an open bracket: a space. "teacher(s)" and "f(x)" style suffixes of
# one or two lowercase letters are word-internal and stay joined.
_NO_SPACE_BEFORE_PAREN = re.compile(r"(?<=[A-Za-z0-9.,;:])\((?![a-z]{1,2}\))")
# After a close bracket: a space before a following word, except after such a suffix.
_NO_SPACE_AFTER_PAREN = re.compile(r"(?<!\([a-z])(?<!\([a-z]{2})\)(?=[A-Za-z0-9])")
# A hyphen used as a separator has a space on one side only ("a -b", "a- b");
# the checklist wants spaces on both. Compound words ("well-known") have none
# and are left alone.
_LOPSIDED_HYPHEN = re.compile(r"(?<=\w) -(?=\w)|(?<=\w)- (?=\w)")


def normalize_punctuation_spacing(text: str) -> str:
    text = _ODD_SPACES.sub(" ", text.translate(_LIGATURES))
    text = _MISMAPPED_EQUALS.sub("=", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = _SPACE_BEFORE_COMMA.sub(",", text)
    text = _NO_SPACE_AFTER_COMMA.sub(", ", text)
    text = _NO_SPACE_BEFORE_PAREN.sub(" (", text)
    text = _NO_SPACE_AFTER_PAREN.sub(") ", text)
    text = _LOPSIDED_HYPHEN.sub(" - ", text)
    return text


# --- units ("Before the kg or units leave the space") ------------------------

# Multi-letter units only: a single letter after a number is far more often a
# label ("Section 2A", "3D") or a decade ("1990s") than a unit.
_UNIT_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)(kg|mg|km|cm|mm|nm|ml|mL|kW|kV|mA|Hz|kHz|MHz|GHz|kJ|kPa|mol)\b"
)


def space_units(text: str) -> str:
    return _UNIT_PATTERN.sub(r"\1 \2", text)


# --- initialisms ("write 'US' as 'U S' ... keep 'UNESCO' as is") -------------

_CAPS_TOKEN = re.compile(r"\b[A-Z]{2,}\b")
_ROMAN = re.compile(r"^[IVX]+$")
# Capitalised ordinary words (emphasis like "do NOT") are words, not initialisms.
# "US" and "WHO" are deliberately absent: in mixed-case prose they are the
# country and the organisation.
_COMMON_WORDS = frozenset(
    "A I AN AS AT BE BY DO GO HE IF IN IS IT ME MY NO OF OH OK ON OR SO TO UP WE "
    "ALL AND ANY ARE BUT CAN DID FOR GET HAD HAS HER HIM HIS HOW ITS LET MAY NEW NOT "
    "NOW OFF OLD ONE OUR OUT OWN SAY SEE SHE THE TOO TWO USE WAS WAY WHY YES YET YOU".split()
)
_ONSETS = frozenset(
    "BL BR CH CL CR DR FL FR GL GR PH PL PR SC SH SK SL SM SN SP ST SW TH TR TW WH".split()
)
_CODAS = frozenset(
    "CH CK CT FT LD LF LK LM LP LT MP ND NG NK NT PT RB RC RD RF RG RK RL RM RN RP RS RT "
    "SH SK SP ST TH".split()
)
_VOWELS = set("AEIOU")


def _is_pronounceable(token: str) -> bool:
    """Whether an all-caps token reads as a word (UNESCO, NASA) rather than
    letter by letter (NCERT, OECD).

    ponytail: a phonotactic heuristic, not a lexicon — a token it misjudges
    needs a lexicon of acronyms, which is the upgrade path.
    """
    if len(token) < 4 or not any(ch in _VOWELS for ch in token):
        return False
    runs = re.findall(r"[^AEIOU]+", token)
    if any(len(run) > 2 for run in runs):
        return False
    if token[0] not in _VOWELS and token[1] not in _VOWELS and token[:2] not in _ONSETS:
        return False
    if token[-1] not in _VOWELS and token[-2] not in _VOWELS and token[-2:] not in _CODAS:
        return False
    return True


def is_spoken_as_letters(token: str) -> bool:
    return (
        len(token) >= 2
        and token.isalpha()
        and token.isupper()
        and token not in _COMMON_WORDS
        and not _ROMAN.match(token)
        and not _is_pronounceable(token)
    )


def _is_shouting(text: str) -> bool:
    """A mostly-uppercase line (a heading, a running title) is not prose, and
    spelling its words out letter by letter would wreck it."""
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) >= 4 and sum(ch.isupper() for ch in letters) / len(letters) > 0.6


def space_initialisms(text: str) -> str:
    if _is_shouting(text):
        return text
    return _CAPS_TOKEN.sub(
        lambda m: " ".join(m.group(0)) if is_spoken_as_letters(m.group(0)) else m.group(0),
        text,
    )


def unspaced_initialisms(text: str) -> List[str]:
    """The initialisms in ``text`` a screen reader would mispronounce."""
    if _is_shouting(text):
        return []
    return [tok for tok in _CAPS_TOKEN.findall(text) if is_spoken_as_letters(tok)]


# --- numbered headings ("6.1 - INTRODUCTION") --------------------------------

_NUMBERED_HEADING = re.compile(
    r"^(\d{1,3}(?:\.\d{1,3})*)\.?\s*[-–—:]?\s+(?=[A-Za-z])(.+)$"
)
_FORMATTED_NUMBERED_HEADING = re.compile(r"^\d{1,3}(?:\.\d{1,3})* - \S")


def format_numbered_heading(text: str) -> str:
    text = text.strip()
    if _FORMATTED_NUMBERED_HEADING.match(text):
        return text
    match = _NUMBERED_HEADING.match(text)
    return f"{match.group(1)} - {match.group(2)}" if match else text


def is_unformatted_numbered_heading(text: str) -> bool:
    text = text.strip()
    return bool(_NUMBERED_HEADING.match(text)) and not _FORMATTED_NUMBERED_HEADING.match(text)


# --- labels and bullet glyphs --------------------------------------------------

# A line that labels something (a figure's source, a table's note) rather than
# saying something: it ends without punctuation by nature, so it is never the
# open sentence at the foot of a page.
_LABEL_PREFIX = re.compile(r"^(sources?|notes?|figure|fig\.|table|chart|plate)\b", re.IGNORECASE)
_MIN_SENTENCE_WORDS = 4
# A paragraph that is nothing but a bullet: symbol fonts often extract their
# bullet as a letter ("O", "o") or a shape, on a line of its own.
_BULLET_GLYPH = re.compile(r"^[•◦▪▫■□●○◆◇❍❏❑➢➤►▸–*oOq✓✔§]$")


def is_label(text: str) -> bool:
    text = text.strip()
    return len(text.split()) < _MIN_SENTENCE_WORDS or bool(_LABEL_PREFIX.match(text))


def is_bullet_glyph(text: str) -> bool:
    return bool(_BULLET_GLYPH.match(text.strip()))


# --- composition ---------------------------------------------------------------


def _outside_urls(text: str, rule: Callable[[str], str]) -> str:
    pieces: List[str] = []
    position = 0
    for match in URL_PATTERN.finditer(text):
        pieces.append(rule(text[position : match.start()]))
        pieces.append(match.group(0))
        position = match.end()
    pieces.append(rule(text[position:]))
    return "".join(pieces)


def remediate_prose(text: str) -> str:
    """Every checklist text rule, applied to one run of body text."""
    return _outside_urls(
        text, lambda part: space_initialisms(space_units(normalize_punctuation_spacing(part)))
    )


def remediate_heading(text: str) -> str:
    return format_numbered_heading(remediate_prose(text))
