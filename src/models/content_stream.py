"""ContentStream — one reading-order traversal of the semantic document.

**Not the document.** The document is a graph, and this is one walk of it.
That is not speculation about the future; the graph already exists:

  * ``Callout`` references its anchoring ``Heading`` by id (src/models/callout.py)
  * ``Footnote`` references its anchor by page + text
  * ``Paragraph.source_block_ids`` references the ``TextBlock`` lines it contains
  * a ``Footnote`` renders at the page bottom and an endnote at the document
    end — the same node, two placements, chosen by ``note_type``

That last one is already "one graph, two linearizations" in production. So a
second traversal (sidebars, logical vs print order, a column-aware walk) is
something this design must not preclude. Four rules keep that door open at no
cost today:

1. **Identity lives on the nodes, not on stream positions.** A ``ContentNode``
   carries the id of the object it points at, so an id survives re-traversal,
   reordering, and a future graph walk. "Third block on page 2" would not.
2. **The stream is derived, never stored on Document.** ``build_content_stream``
   computes it. Persisting it would create a second place where reading order
   lives, free to drift from the objects — which is precisely the defect this
   whole architecture is removing from Markdown, recreated one layer up.
3. **Nodes reference; they never copy.** A node holds an id and a kind, not
   text. Copied content drifts.
4. **It is named as a traversal.** Adding another one is additive.

See docs/RAWRS_PROJECTION_ARCHITECTURE.md for the whole target architecture.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ContentKind(str, Enum):
    """What kind of semantic object a node points at.

    Deliberately coarse: the kinds a projection must dispatch on to render.
    Anything finer (heading level, note type, table shape) is read from the
    referenced object, never duplicated here — see rule 3 above.
    """

    PAGE_MARKER = "page_marker"          # H6 page marker heading
    HEADING = "heading"                  # content heading H1-H5
    BODY_LINE = "body_line"              # one TextBlock of body prose
    LIST = "list"
    TABLE = "table"
    IMAGE = "image"
    NOTE_DEFINITION = "note_definition"  # footnote/endnote body
    FRONT_MATTER = "front_matter"        # one FrontMatterItem (title/author/affiliation)


class ContentNode(BaseModel):
    """One position in a traversal, pointing at one semantic object.

    ``object_id`` is the referenced object's own stable identity
    (``Heading.id``, ``Table.table_id``, ``TextBlock.block_id``, ...) — the
    node does not mint identities of its own, so two traversals of the same
    document produce nodes that are recognisably about the same things.

    ``order`` is this node's position *within this traversal* and is
    therefore meaningful only relative to the stream that produced it. It is
    not an identity and must never be used as one.
    """

    object_id: str
    kind: ContentKind
    page_number: int = Field(..., ge=1)
    order: int = Field(..., ge=0)


class ContentStream(BaseModel):
    """An ordered walk of the document's renderable content.

    A projection consumes this instead of re-deriving order for itself.
    Today both renderers reconstruct reading order independently, by walking
    page text in lockstep with ``document.blocks`` — the same semantic
    decision made twice, in two projections, which is the thing this exists
    to end.
    """

    nodes: List[ContentNode] = Field(default_factory=list)

    def for_page(self, page_number: int) -> List[ContentNode]:
        return [node for node in self.nodes if node.page_number == page_number]

    def by_object_id(self, object_id: str) -> Optional[ContentNode]:
        return next((node for node in self.nodes if node.object_id == object_id), None)

    def kind_counts(self) -> Dict[str, int]:
        """Per-kind totals — the cheap shape assertion for tests and for the
        parity gates P3/P4 will run against the renderers."""
        counts: Dict[str, int] = {}
        for node in self.nodes:
            counts[node.kind.value] = counts.get(node.kind.value, 0) + 1
        return counts
