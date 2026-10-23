"""Recognition-quality signals for OCR text.

Docling's recognizer (RapidOCR, PP-OCRv6) garbles emphasized runs - bold
lead-ins, italic phrases - on flattened and scanned pages, and it does so
*confidently*: "Indicate whether you foresee a relationship" comes out as
"In nde o o ad  ie  ef o n adhn". The router cannot catch it (the text is long
and contains no control characters), and before this module nothing
downstream could either. See docs/OCR_QUALITY.md.

The signature, measured on every Docling text item of the corpus's two OCR
documents (O'Leary, Bryman: 368 items with text, each read by eye):

* nonsense tokens cluster: a 1-2 letter token that is not an English short
  word ("ie", "ef", "n") or a 3+ letter token with no vowel ("sdd",
  "prrr") - several inside a few words of each other;
* recognizers pad garbled runs with irregular spacing ("o  oor  oor").

A line is garbled when a six-token window holds three or more nonsense
tokens, or when irregular spacing (two or more gaps of 2+ spaces) comes with
at least one. That flags all 17 garbled items (12 O'Leary, 5 Bryman) and
none of the 351 clean ones; tests/fixtures/ocr_quality/ pins the set.

ponytail: lexicon-free on purpose (no word-list dependency). Ceiling: garble
made only of plausible-looking long words ("Jaeuoen ueod") is caught only
through its spacing; a dictionary hit rate is the upgrade if that ever misses.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import List

# English one- and two-letter words, plus the abbreviations academic prose
# uses; anything else that short inside a sentence is a recognition fragment.
_SHORT_WORDS = frozenset(
    """a i o an as at be by do go he if in is it me my no of oh on or so to up us
    we ok ad am ox ex vs eg id pp ed et al mr ms dr st nd rd th co uk un uh eh ah
    oz cm mm kg km lb ft hr""".split()
)
# A contraction or possessive is one token ("Bryman's", "you're"), so its
# tail is never mistaken for a fragment; URLs are dropped before tokenizing.
_TOKEN = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*\.?")
_URL = re.compile(r"(?:https?://|www\.)\S+|\S+\.(?:com|org|net|edu|uk|ac|gov|php|html?)\S*", re.IGNORECASE)
_VOWEL = re.compile(r"[aeiouyAEIOUY]")
_SPACING_GAP = re.compile(r"\S {2,}(?=\S)")

WINDOW = 6
MIN_NONSENSE_IN_WINDOW = 3
MIN_SPACING_GAPS = 2


def _tokens(text: str) -> List[str]:
    return _TOKEN.findall(_URL.sub(" ", text))


def _nonsense(token: str) -> bool:
    word = re.split(r"['’]", token.rstrip("."))[0]
    if len(word) <= 2:
        if token.endswith(".") and (word[:1].isupper() or len(word) == 1):
            return False  # an initial or abbreviation: "P. H. Hirst", "e.g."
        return word.lower() not in _SHORT_WORDS and not ("'" in token or "’" in token)
    return not _VOWEL.search(word) and not word.isupper()  # "sdd", not "BBC"


def _densest_window(tokens: List[str]) -> int:
    flags = [_nonsense(token) for token in tokens]
    if len(flags) <= WINDOW:
        return sum(flags)
    return max(sum(flags[i : i + WINDOW]) for i in range(len(flags) - WINDOW + 1))


def is_garbled(text: str) -> bool:
    """True when ``text`` (one line or paragraph) carries the garble signature."""
    densest = _densest_window(_tokens(text))
    if densest >= MIN_NONSENSE_IN_WINDOW:
        return True
    return densest >= 1 and len(_SPACING_GAP.findall(text)) >= MIN_SPACING_GAPS


def garbled_lines(text: str) -> List[str]:
    """The non-empty lines of a page's text that look garbled, in order."""
    return [line.strip() for line in text.splitlines() if line.strip() and is_garbled(line)]


def _clean_words(text: str) -> List[str]:
    return [
        token.lower().rstrip(".")
        for token in _tokens(text)
        if len(token.rstrip(".")) >= 4 and not _nonsense(token)
    ]


def agreement(original: str, reading: str) -> float:
    """Share of the original's readable words (4+ letters) that the second
    reading also contains - the anti-hallucination check for a re-read.

    A garbled line is mostly fine: "In nde o o ad ie ef o n adhn whether you
    are looking for impacts, increases ..." keeps every word after the
    lead-in. A trustworthy second reading must reproduce those, so a reading
    that paraphrases, truncates or invents scores low. 1.0 when the original
    has no readable words to check against.
    """
    wanted = Counter(_clean_words(original))
    if not wanted:
        return 1.0
    have = Counter(_clean_words(reading))
    found = sum(min(count, have[word]) for word, count in wanted.items())
    return found / sum(wanted.values())
