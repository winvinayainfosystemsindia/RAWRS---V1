"""Canonical front-matter semantic roles for RAWRS.

``FrontMatter`` (src/models/front_matter.py) already carries a document's
title, author(s) and affiliation(s) plus the exact source lines each was
extracted from. This module turns that data into *semantic roles* both
ingestion pipelines consume, so neither has to re-infer front-matter
structure from typography.

Why it exists (FE-0-005 / FE-0-006). After FE-0-004 established
page-marker parity, the only remaining semantic divergence between the
two pipelines was front matter, and each had the opposite half of the
problem:

    ┌───────────┬──────────────────┬─────────────────────┐
    │           │ title -> H1      │ byline excluded     │
    ├───────────┼──────────────────┼─────────────────────┤
    │ native    │ already correct  │ NO - promoted to H2 │
    │ mathpix   │ NO - no heading  │ already correct     │
    └───────────┴──────────────────┴─────────────────────┘

The native path promoted the author byline "Rohit Dhankar" to H2 purely
by font-size rank, while front matter had *already* classified that same
line as an author. Typography ranking is a reasonable signal for body
headings and a bad one for front matter, where a byline is legitimately
set larger than body text without being a heading.

Role assignment is therefore authoritative over typography: a line the
front-matter extractor claimed as an author or affiliation is never a
heading candidate, whatever its font size.

Scope note (YAGNI). Roles are limited to what ``FrontMatter`` actually
carries. Subtitle, abstract-heading and keywords-heading roles are
deliberately NOT modelled: no extractor populates them today, so adding
them would be speculative generality with no producer and no consumer.
Add them here when an extractor produces them — this enum is the place.
"""

from enum import Enum
from typing import Optional

from src.models.front_matter import FrontMatter
from src.models.heading import Heading, HeadingLevel


class FrontMatterRole(str, Enum):
    """The semantic role a front-matter line plays."""

    TITLE = "title"
    AUTHOR = "author"
    AFFILIATION = "affiliation"


#: Roles that may legitimately become a heading. The document title is
#: the document's H1; bylines and affiliations are metadata about the
#: document, not divisions within it (WCAG 2.4.6 / PDF-UA: heading
#: structure must describe document sections).
_HEADING_ELIGIBLE_ROLES = frozenset({FrontMatterRole.TITLE})


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip()


def classify_front_matter_line(
    text: str, front_matter: Optional[FrontMatter]
) -> Optional[FrontMatterRole]:
    """Return the front-matter role claiming ``text``, or None.

    Matching is against the exact source lines the extractor recorded,
    whitespace-normalized. A wrapped title contributes several source
    lines and each one matches TITLE.
    """
    if front_matter is None:
        return None

    needle = _normalize(text)
    if not needle:
        return None

    for sources, role in (
        (front_matter.title_source_texts, FrontMatterRole.TITLE),
        (front_matter.author_source_texts, FrontMatterRole.AUTHOR),
        (front_matter.affiliation_source_texts, FrontMatterRole.AFFILIATION),
    ):
        for source in sources:
            if _normalize(source) == needle:
                return role

    return None


def is_heading_eligible(role: Optional[FrontMatterRole]) -> bool:
    """True when a line carrying ``role`` may still become a heading.

    ``None`` (no front-matter role) is eligible — ordinary body lines are
    unaffected by front-matter classification.
    """
    return role is None or role in _HEADING_ELIGIBLE_ROLES


def build_title_heading(
    front_matter: Optional[FrontMatter],
    page_number: int = 1,
    document_order: int = 0,
) -> Optional[Heading]:
    """Return the H1 heading for the document title, or None.

    Used by ingestion paths that do not otherwise produce an H1 from the
    title. Returns None when there is no title, so a document without
    detected front matter simply gets no synthetic heading — never a
    guess.
    """
    if front_matter is None or not front_matter.title:
        return None

    return Heading(
        level=HeadingLevel.H1,
        text=front_matter.title,
        page_number=page_number,
        document_order=document_order,
        is_page_marker=False,
    )
