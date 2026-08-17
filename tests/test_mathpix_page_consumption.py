"""P-1 C3 — the ingestor consumes proven page evidence, and nothing else.

The rule under test: a page the PDF proves replaces the estimate; a page it
only brackets constrains the estimate; no evidence leaves the estimate exactly
as it was. Figures add one bounded step - Mathpix's own filename states the
page its pixels came from - which may never outrank proven evidence.
"""

from pathlib import Path
from typing import Optional

import fitz
import pytest

import src.mathpix.ingestor as ingestor_module
from src.mathpix.ingestor import MathpixImportProvider, _resolved_page
from src.mathpix.page_alignment import AlignmentStatus, PageAlignment, PageBracket
from src.parser.pdf_parser import parse_pdf
from src.verification.figures import _page_from_filename, _resolve_image_page

TOTAL_BLOCKS = 10
PAGE_COUNT = 10


def _aligned(**brackets: PageBracket) -> PageAlignment:
    """An ALIGNED alignment carrying the given source_line -> bracket map."""
    return PageAlignment(
        status=AlignmentStatus.ALIGNED,
        page_count=PAGE_COUNT,
        brackets={int(line.lstrip("l")): bracket for line, bracket in brackets.items()},
        accepted=len(brackets),
    )


def _resolve(line: int, alignment: Optional[PageAlignment]) -> int:
    return _resolved_page(line, TOTAL_BLOCKS, PAGE_COUNT, alignment)


def _estimate(line: int) -> int:
    return _resolved_page(line, TOTAL_BLOCKS, PAGE_COUNT, None)


class TestTheRule:
    def test_a_stated_page_replaces_the_estimate(self) -> None:
        alignment = _aligned(l5=PageBracket(lower=3, upper=3))

        assert _estimate(5) == 5
        assert _resolve(5, alignment) == 3

    def test_an_estimate_below_the_bracket_is_raised_to_the_lower_bound(self) -> None:
        alignment = _aligned(l2=PageBracket(lower=7, upper=9))

        assert _estimate(2) == 2
        assert _resolve(2, alignment) == 7

    def test_an_estimate_above_the_bracket_is_lowered_to_the_upper_bound(self) -> None:
        alignment = _aligned(l9=PageBracket(lower=2, upper=4))

        assert _estimate(9) == 9
        assert _resolve(9, alignment) == 4

    def test_an_estimate_inside_the_bracket_is_left_alone(self) -> None:
        alignment = _aligned(l5=PageBracket(lower=2, upper=9))

        assert _resolve(5, alignment) == _estimate(5) == 5

    def test_an_open_lower_bound_never_raises_the_estimate(self) -> None:
        alignment = _aligned(l1=PageBracket(lower=None, upper=4))

        assert _resolve(1, alignment) == _estimate(1)

    def test_an_open_upper_bound_never_lowers_the_estimate(self) -> None:
        alignment = _aligned(l9=PageBracket(lower=4, upper=None))

        assert _resolve(9, alignment) == _estimate(9)

    def test_no_evidence_preserves_the_estimate_exactly(self) -> None:
        alignment = PageAlignment(
            status=AlignmentStatus.NO_EVIDENCE, page_count=PAGE_COUNT
        )

        assert alignment.usable is False
        assert all(_resolve(line, alignment) == _estimate(line) for line in range(10))

    def test_a_rejected_alignment_preserves_the_estimate_exactly(self) -> None:
        alignment = PageAlignment(
            status=AlignmentStatus.REJECTED, page_count=PAGE_COUNT, accepted=3
        )

        assert alignment.usable is False
        assert all(_resolve(line, alignment) == _estimate(line) for line in range(10))

    def test_resolution_is_keyed_on_the_block_own_source_line(self) -> None:
        alignment = _aligned(
            l2=PageBracket(lower=8, upper=8), l3=PageBracket(lower=1, upper=1)
        )

        assert _resolve(2, alignment) == 8
        assert _resolve(3, alignment) == 1
        assert _resolve(4, alignment) == _estimate(4)  # unknown line, untouched


def _synthetic_pdf(path: Path, pages: int) -> Path:
    with fitz.open() as doc:
        for index in range(pages):
            doc.new_page().insert_text((72, 72), f"page body number {index + 1}")
        doc.save(str(path))
    return path


MMD = """\\title{A Title}

\\section*{A Heading}

Some prose that belongs to a paragraph block and is long enough to be real.

- first bullet item
- second bullet item

Prose citing ${ }^{1}$ a note here.

1. Body of note one.
"""


@pytest.fixture
def imported(tmp_path, monkeypatch):
    """One import whose page evidence states page 4 for every block."""
    everywhere = PageAlignment(
        status=AlignmentStatus.ALIGNED,
        page_count=6,
        brackets={line: PageBracket(lower=4, upper=4) for line in range(0, 40)},
        accepted=40,
    )
    monkeypatch.setattr(
        ingestor_module, "_align_to_pdf_pages", lambda *a, **k: everywhere
    )
    mmd = tmp_path / "doc.mmd"
    mmd.write_text(MMD, encoding="utf8")
    document = parse_pdf(_synthetic_pdf(tmp_path / "doc.pdf", 6))
    return MathpixImportProvider().import_document(document, mmd_path=mmd)


class TestEveryObjectTypeObeysTheSameRule:
    def test_headings_paragraphs_lists_and_notes_take_the_stated_page(
        self, imported
    ) -> None:
        content_headings = [
            h for h in imported.headings if not h.is_page_marker and h.source == "mathpix"
        ]

        assert content_headings, "the fixture must produce a heading"
        assert imported.paragraphs and imported.lists and imported.footnotes
        assert {h.page_number for h in content_headings} == {4}
        assert {p.page_number for p in imported.paragraphs} == {4}
        assert {lst.page_number for lst in imported.lists} == {4}
        assert {n.anchor_page_number for n in imported.footnotes} == {4}

    def test_document_order_still_follows_source_line(self, imported) -> None:
        lines = [p.source_line for p in imported.paragraphs]

        assert lines == sorted(lines)
        assert [p.document_order for p in imported.paragraphs] == sorted(
            p.document_order for p in imported.paragraphs
        )


class TestFigureFilenameFallback:
    PATH = Path("a1b2-03_102_111_1847_317.jpg")

    def test_a_valid_filename_page_is_used_when_nothing_was_proven(self) -> None:
        page = _resolve_image_page(
            9, source_line=1, path=self.PATH, page_count=10, page_evidence=None
        )

        assert page == 3

    def test_a_filename_without_the_page_token_is_ignored(self) -> None:
        path = Path("figure-one.jpg")

        assert _page_from_filename(path, 10) is None
        assert (
            _resolve_image_page(
                9, source_line=1, path=path, page_count=10, page_evidence=None
            )
            == 9
        )

    def test_a_filename_page_outside_the_document_is_ignored(self) -> None:
        path = Path("a1b2-99_102_111_1847_317.jpg")

        assert _page_from_filename(path, 10) is None
        assert (
            _resolve_image_page(
                9, source_line=1, path=path, page_count=10, page_evidence=None
            )
            == 9
        )

    def test_a_proven_page_outranks_the_filename(self) -> None:
        evidence = _aligned(l1=PageBracket(lower=5, upper=5))

        page = _resolve_image_page(
            9, source_line=1, path=self.PATH, page_count=10, page_evidence=evidence
        )

        assert page == 5

    def test_the_filename_is_consulted_only_when_no_page_was_proven(self) -> None:
        bracketed = _aligned(l1=PageBracket(lower=2, upper=8))

        assert (
            _resolve_image_page(
                9, source_line=1, path=self.PATH, page_count=10, page_evidence=bracketed
            )
            == 3
        )

    def test_with_no_evidence_and_no_token_the_estimate_stands(self) -> None:
        page = _resolve_image_page(
            7,
            source_line=None,
            path=Path("plain.png"),
            page_count=10,
            page_evidence=None,
        )

        assert page == 7

    def test_resolving_a_page_does_not_touch_the_file_or_its_path(self) -> None:
        path = Path("a1b2-03_102_111_1847_317.jpg")

        _resolve_image_page(
            9, source_line=1, path=path, page_count=10, page_evidence=None
        )

        assert path == Path("a1b2-03_102_111_1847_317.jpg")
        assert path.stem == "a1b2-03_102_111_1847_317"


class TestTheNativePathIsOutOfReach:
    def test_only_the_mathpix_ingestor_consumes_the_alignment(self) -> None:
        """Structural: the native pipeline must not be able to supply page
        evidence, so nothing outside src/mathpix may build one."""
        src = Path(__file__).resolve().parents[1] / "src"
        callers = {
            path.relative_to(src).as_posix()
            for path in src.rglob("*.py")
            if "align_blocks_to_pages(" in path.read_text(encoding="utf8")
        }

        assert callers == {"mathpix/ingestor.py", "mathpix/page_alignment.py"}

    def test_a_figure_built_without_evidence_keeps_its_estimate(self) -> None:
        """The native path never passes page_evidence, and an absent evidence
        object must change nothing."""
        assert (
            _resolve_image_page(
                6,
                source_line=2,
                path=Path("native-image.png"),
                page_count=10,
                page_evidence=None,
            )
            == 6
        )
