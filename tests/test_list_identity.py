"""P4c-4′ commit 1 — a ListBlock has a stable identity, and the traversal uses it.

``ListBlock`` was the last populated object type with no ``id``, and the
consequences were silent rather than loud: ``build_content_stream``'s ``emit()``
drops any node whose ``object_id`` is falsy, so ``ContentKind.LIST`` had never
been emitted once — 48 lists across the benchmark corpus, 0 nodes — and
``markdown_builder._render_lists`` wrote the literal anchor
``<!-- list-id: None -->`` 48 times.

This module pins the identity and the node, and pins that **nothing consumes the
node yet**: both projections still render lists from markdown lines, so an id
must change no output at all.
"""

from pathlib import Path
from typing import List, Optional

from src.docx.docx_generator import generate_docx
from src.markdown.markdown_builder import build_markdown
from src.models.content_stream import ContentKind
from src.models.contracts import Document, Metadata, Page, Paragraph
from src.models.list_block import ListBlock, ListItem, ListType
from src.structure.content_stream import build_content_stream


def _list(
    source_line: Optional[int],
    document_order: int = 0,
    page: int = 1,
    list_type: ListType = ListType.BULLET,
    items: Optional[List[str]] = None,
) -> ListBlock:
    return ListBlock(
        list_type=list_type,
        items=[ListItem(text=t) for t in (items or ["Alpha", "Beta"])],
        page_number=page,
        document_order=document_order,
        source_line=source_line,
    )


def _document(lists: List[ListBlock], pages: int = 1) -> Document:
    """A Mathpix-shaped Document: paragraphs carry ``source_line`` and no
    blocks, which is what routes rendering through the semantic path."""
    return Document(
        source_pdf_path="lists.pdf",
        metadata=Metadata(filename="lists.pdf", page_count=pages),
        pages=[
            Page(page_number=p, cleaned_text="Body text.") for p in range(1, pages + 1)
        ],
        paragraphs=[
            Paragraph(page_number=1, text="Body text.", source_line=1, document_order=0)
        ],
        lists=lists,
    )


class TestIdentity:
    def test_a_list_is_named_by_its_source_line(self):
        assert _list(source_line=42).id == "list-line-42"

    def test_a_list_with_no_source_line_keeps_no_id(self):
        """Every ListBlock from detect_lists_from_pdf is in this state: built
        from PDF geometry, with no coordinate in a source document to name.
        An unstable id would be worse than none — a correction recorded
        against it would move when a neighbouring list did."""
        assert _list(source_line=None).id is None

    def test_an_explicit_id_is_never_overwritten(self):
        """Round-tripping through persistence keeps whatever was stored."""
        stored = ListBlock(
            id="list-line-7",
            list_type=ListType.BULLET,
            items=[ListItem(text="Alpha")],
            page_number=1,
            document_order=3,
            source_line=99,
        )
        assert stored.id == "list-line-7"

    def test_identity_is_not_positional(self):
        """The sibling convention is ``{type}-{document_order}``; this is the
        one thing it must not copy. ``document_order`` is a counter, so a list
        inserted ahead of another would rename it."""
        before = _list(source_line=80, document_order=1)
        after = _list(source_line=80, document_order=5)
        assert before.id == after.id == "list-line-80"

    def test_two_lists_do_not_collide(self):
        lists = [
            _list(source_line=10, document_order=0),
            _list(source_line=20, document_order=1),
        ]
        assert len({lst.id for lst in lists}) == 2


class TestStream:
    def test_every_identified_list_is_one_node(self):
        document = _document(
            [_list(source_line=10), _list(source_line=20, document_order=1)]
        )
        nodes = [
            n for n in build_content_stream(document).nodes if n.kind is ContentKind.LIST
        ]
        assert [n.object_id for n in nodes] == ["list-line-10", "list-line-20"]

    def test_a_node_resolves_to_the_list_that_made_it(self):
        document = _document([_list(source_line=10)])
        node = next(
            n for n in build_content_stream(document).nodes if n.kind is ContentKind.LIST
        )
        assert node.object_id == document.lists[0].id
        assert node.page_number == document.lists[0].page_number

    def test_a_list_with_no_identity_emits_no_node(self):
        """emit() drops a falsy object_id — the behaviour that made LIST a
        dead node kind for every document until now."""
        document = _document([_list(source_line=None)])
        assert not [
            n for n in build_content_stream(document).nodes if n.kind is ContentKind.LIST
        ]

    def test_nodes_carry_no_duplicates(self):
        document = _document(
            [_list(source_line=s, document_order=i) for i, s in enumerate((10, 20, 30))]
        )
        nodes = [
            n for n in build_content_stream(document).nodes if n.kind is ContentKind.LIST
        ]
        assert len(nodes) == len({n.object_id for n in nodes}) == 3


class TestProjectionsAreUnchanged:
    def test_the_markdown_anchor_carries_the_real_id(self):
        markdown = build_markdown(_document([_list(source_line=10)]))
        assert "<!-- list-id: list-line-10 -->" in markdown
        assert "list-id: None" not in markdown

    def test_the_node_is_not_consumed_by_either_projection(self, tmp_path: Path):
        """The whole of commit 1's claim: identity exists, and it changes
        nothing. Rendering the same lists with and without ids produces the
        same DOCX list paragraphs, and the same markdown but for the anchor,
        because both projections still read the markdown lines."""
        from docx import Document as DocxDocument

        with_id = _document(
            [_list(source_line=10), _list(source_line=20, document_order=1)]
        )
        without_id = _document(
            [_list(source_line=None), _list(source_line=None, document_order=1)]
        )

        markdowns, list_styles = [], []
        for index, document in enumerate((with_id, without_id)):
            markdown = build_markdown(document)
            out = tmp_path / f"lists-{index}.docx"
            generate_docx(document, markdown, out)
            rendered = DocxDocument(str(out))
            markdowns.append(
                markdown.replace("list-line-10", "X").replace("list-line-20", "X")
            )
            list_styles.append(
                [
                    (p.style.name, p.text)
                    for p in rendered.paragraphs
                    if p.style.name in ("List Bullet", "List Number")
                ]
            )

        assert markdowns[0] == markdowns[1].replace("None", "X")
        assert list_styles[0] == list_styles[1]
        assert len(list_styles[0]) == 4
