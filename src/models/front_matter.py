"""FrontMatter model for RAWRS scholarly-article front-matter extraction.

See the Front-Matter Semantic Extraction Design (Scholarly Article
Semantics Audit follow-up) for the gap this exists to close: a
document's title, author(s), and affiliation(s) were previously
detected as nothing at all - not a heading, not metadata - and ended up
silently flattened into ordinary, undifferentiated body text. This
model is a small, additive bolt-on (one optional field on Document),
deliberately not a redesign of Document into a general scholarly-
article model: it carries exactly the three things
src/frontmatter/front_matter_extractor.py confidently extracts, nothing
more (no journal/volume/DOI/citation modeling).
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class FrontMatter(BaseModel):
    """A document's confidently-extracted title/author(s)/affiliation(s).

    Every field defaults to empty/None - a document with no detected
    front matter (e.g. a book chapter with no title page, as already
    confirmed for 3 of the 4 benchmark PDFs) simply gets a FrontMatter
    with everything unset, never a guess.

    ``title_source_texts``/``author_source_texts``/
    ``affiliation_source_texts`` each hold the exact source line(s) the
    corresponding field was extracted from, in document order - the
    same exact-line-matching technique already used by
    ``Footnote.body_source_text``/``body_continuation_source_texts``
    and ``Figure.caption_source_text``, so
    src/markdown/markdown_builder.py can suppress those lines from
    ordinary body rendering instead of rendering them a second time.
    """

    title: Optional[str] = None
    title_source_texts: List[str] = Field(default_factory=list)
    authors: List[str] = Field(default_factory=list)
    author_source_texts: List[str] = Field(default_factory=list)
    affiliations: List[str] = Field(default_factory=list)
    affiliation_source_texts: List[str] = Field(default_factory=list)
