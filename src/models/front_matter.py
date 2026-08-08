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

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from src.models.semantic_object import SemanticObject


class FrontMatterRole(str, Enum):
    """The semantic role a front-matter line plays.

    Lives here rather than in src/frontmatter/front_matter_roles.py, which
    is where it was defined until L5'a and which still re-exports it: a
    ``FrontMatterItem`` has to carry its role, and AI-1 forbids the model
    layer importing a decision package. Moving the enum down is what lets
    the role travel *on the object* instead of being recomputed from text
    by whoever needs it - which AI-2 forbids a projection from doing at
    all, since src.frontmatter is a decision package.
    """

    TITLE = "title"
    AUTHOR = "author"
    AFFILIATION = "affiliation"


class FrontMatterItem(SemanticObject):
    """One front-matter line, with an identity and a recorded position.

    L5'a. Front matter was the only detected content the ContentStream
    could not carry, and the reason was structural rather than incidental:
    ``ContentNode`` holds *the id of the object it points at*, and a front
    matter title or byline had no id to point at - ``FrontMatter`` stored
    bare strings in three lists. It was also the only object of its class
    not deriving from ``SemanticObject``, so it carried no provenance and
    no ``correction_ids`` either.

    ``source_block_id`` is the recorded relationship to the ``TextBlock``
    this item was read from, written by the extractor at the moment it
    read the line. It is what lets ``build_content_stream`` place the item
    without matching text - the same reason ``Heading.source_block_id``
    (P2) and ``Image.source_block_id`` (P-IMG) exist, and the same defect
    both were introduced to remove: a text key cannot tell two identical
    lines apart.

    ``Optional`` because a provider genuinely may not have one: the
    Mathpix path (src/mathpix/ingestor.py) builds front matter from MMD
    metadata that records no position in the PDF at all. Such an item is
    real front matter with no recorded place in the document, and it is
    left out of the traversal rather than given an invented one.

    ``document_order`` is this item's position among the document's front
    matter, in the order the extractor read it - an ordering fact about
    the object, not a stream position (see ContentNode's rule 1).
    """

    role: FrontMatterRole
    text: str = Field(..., min_length=1)
    source_block_id: Optional[str] = None
    document_order: int = Field(..., ge=0)

    @model_validator(mode="after")
    def _backfill_semantic_object_id(self) -> "FrontMatterItem":
        if self.id is None:
            self.id = f"frontmatter-{self.document_order}"
        if not self.object_type:
            self.object_type = "front_matter_item"
        return self


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
    # L5'a: the same front matter, as identity-bearing objects - one per
    # source line, each with the block it was read from. This is what the
    # ContentStream carries and what the projections render; the flat
    # fields above are the older view of the same decision, kept because
    # every existing construction site and the persisted document shape
    # use them. The extractor writes both in one pass from one decision,
    # so they cannot disagree at the point of creation.
    #
    # Empty for a FrontMatter built without them - the Mathpix path and
    # older fixtures - which is exactly the case that keeps its historical
    # rendering (see src/markdown/markdown_builder.py).
    items: List[FrontMatterItem] = Field(default_factory=list)
