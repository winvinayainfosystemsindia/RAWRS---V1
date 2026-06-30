"""Tests for configurable page numbering policy.

Covers all four modes (AUTO, MANUAL_RANGE, MANUAL_NUMBER_OVERRIDE, DISABLED)
through both the heading-detection and markdown-rendering paths, including
the edge cases required by the feature spec:

- automatic detection: only detected printed labels are emitted
- manual range: markers only for pages within [start, end]
- manual number override: sequential labels from a user-specified start
- disabled: no markers at all
- pages with missing printed numbers (AUTO mode suppresses those pages)
- mixed documents where only some pages carry a printed page number
"""

from typing import List, Optional

from src.config.page_numbering import PageNumberingMode, PageNumberingPolicy
from src.headings.heading_detector import detect_headings
from src.markdown.markdown_builder import build_markdown
from src.models.contracts import Document, Heading, HeadingLevel, Metadata, Page


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_doc(
    page_texts: List[str],
    printed_labels: Optional[List[Optional[str]]] = None,
) -> Document:
    """Build a Document whose pages have pre-populated text and optional
    printed_label values (simulating what structure_detector.py sets).

    ``printed_labels`` must be the same length as ``page_texts`` when
    supplied.  Each entry is either a label string (e.g. "367") or None
    to indicate that no printed page number was detected on that page.
    """
    pages = []
    for i, text in enumerate(page_texts):
        label: Optional[str] = None
        if printed_labels is not None:
            label = printed_labels[i]
        pages.append(Page(page_number=i + 1, cleaned_text=text, printed_label=label))
    return Document(
        source_pdf_path="dummy.pdf",
        metadata=Metadata(filename="dummy.pdf"),
        pages=pages,
    )


def _markers(document: Document) -> List[Heading]:
    return [h for h in document.headings if h.is_page_marker]


def _marker_texts(document: Document) -> List[str]:
    return [h.text for h in _markers(document)]


def _marker_pages(document: Document) -> List[int]:
    return [h.page_number for h in _markers(document)]


# ---------------------------------------------------------------------------
# Unit tests: PageNumberingPolicy.resolve_marker_text
# ---------------------------------------------------------------------------


class TestResolveMarkerText:
    """Direct unit tests for the resolve_marker_text decision method."""

    def test_auto_with_label_returns_label(self) -> None:
        policy = PageNumberingPolicy(mode=PageNumberingMode.AUTO)
        assert policy.resolve_marker_text(5, "367") == "367"

    def test_auto_without_label_returns_none(self) -> None:
        policy = PageNumberingPolicy(mode=PageNumberingMode.AUTO)
        assert policy.resolve_marker_text(5, None) is None

    def test_disabled_always_returns_none(self) -> None:
        policy = PageNumberingPolicy(mode=PageNumberingMode.DISABLED)
        assert policy.resolve_marker_text(1, "1") is None
        assert policy.resolve_marker_text(1, None) is None

    def test_manual_range_inside_range_with_label(self) -> None:
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_RANGE, range_start=5, range_end=10
        )
        assert policy.resolve_marker_text(7, "99") == "99"

    def test_manual_range_inside_range_no_label_uses_page_number(self) -> None:
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_RANGE, range_start=5, range_end=10
        )
        assert policy.resolve_marker_text(7, None) == "7"

    def test_manual_range_outside_range_returns_none(self) -> None:
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_RANGE, range_start=5, range_end=10
        )
        assert policy.resolve_marker_text(4, "4") is None
        assert policy.resolve_marker_text(11, "11") is None

    def test_manual_range_boundary_pages_included(self) -> None:
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_RANGE, range_start=5, range_end=10
        )
        assert policy.resolve_marker_text(5, None) == "5"
        assert policy.resolve_marker_text(10, None) == "10"

    def test_manual_number_override_starts_at_number_start(self) -> None:
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_NUMBER_OVERRIDE, number_start=301
        )
        assert policy.resolve_marker_text(1, None) == "301"
        assert policy.resolve_marker_text(2, None) == "302"
        assert policy.resolve_marker_text(20, None) == "320"

    def test_manual_number_override_ignores_printed_label(self) -> None:
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_NUMBER_OVERRIDE, number_start=100
        )
        assert policy.resolve_marker_text(1, "xiv") == "100"

    def test_manual_number_override_default_start_is_1(self) -> None:
        policy = PageNumberingPolicy(mode=PageNumberingMode.MANUAL_NUMBER_OVERRIDE)
        assert policy.resolve_marker_text(1, None) == "1"
        assert policy.resolve_marker_text(3, None) == "3"


# ---------------------------------------------------------------------------
# Mode 1 — AUTO
# ---------------------------------------------------------------------------


class TestAutoMode:
    def test_page_with_detected_label_gets_that_label(self) -> None:
        doc = _build_doc(["body text"], printed_labels=["367"])
        detect_headings(doc, page_numbering_policy=PageNumberingPolicy(mode=PageNumberingMode.AUTO))
        assert _marker_texts(doc) == ["367"]

    def test_page_without_detected_label_gets_no_marker(self) -> None:
        doc = _build_doc(["body text"], printed_labels=[None])
        detect_headings(doc, page_numbering_policy=PageNumberingPolicy(mode=PageNumberingMode.AUTO))
        assert _markers(doc) == []

    def test_mixed_document_only_labelled_pages_get_markers(self) -> None:
        """Pages 1 and 3 have detected labels; page 2 does not."""
        doc = _build_doc(
            ["page one", "page two", "page three"],
            printed_labels=["10", None, "12"],
        )
        detect_headings(doc, page_numbering_policy=PageNumberingPolicy(mode=PageNumberingMode.AUTO))

        assert _marker_pages(doc) == [1, 3]
        assert _marker_texts(doc) == ["10", "12"]

    def test_no_page_has_detected_label_produces_empty_marker_list(self) -> None:
        doc = _build_doc(["a", "b", "c"], printed_labels=[None, None, None])
        detect_headings(doc, page_numbering_policy=PageNumberingPolicy(mode=PageNumberingMode.AUTO))
        assert _markers(doc) == []

    def test_roman_numeral_label_is_preserved(self) -> None:
        doc = _build_doc(["front matter"], printed_labels=["iii"])
        detect_headings(doc, page_numbering_policy=PageNumberingPolicy(mode=PageNumberingMode.AUTO))
        assert _marker_texts(doc) == ["iii"]

    def test_marker_text_never_contains_word_page(self) -> None:
        doc = _build_doc(["text"], printed_labels=["5"])
        detect_headings(doc, page_numbering_policy=PageNumberingPolicy(mode=PageNumberingMode.AUTO))
        for marker in _markers(doc):
            assert "page" not in marker.text.lower()
            assert "Page" not in marker.text

    def test_all_markers_are_h6_level(self) -> None:
        doc = _build_doc(["a", "b"], printed_labels=["1", "2"])
        detect_headings(doc, page_numbering_policy=PageNumberingPolicy(mode=PageNumberingMode.AUTO))
        assert all(m.level == HeadingLevel.H6 for m in _markers(doc))


# ---------------------------------------------------------------------------
# Mode 2 — MANUAL RANGE
# ---------------------------------------------------------------------------


class TestManualRangeMode:
    def test_pages_inside_range_get_markers(self) -> None:
        doc = _build_doc(["a", "b", "c", "d", "e"])  # pages 1-5, no printed labels
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_RANGE, range_start=2, range_end=4
        )
        detect_headings(doc, page_numbering_policy=policy)

        assert _marker_pages(doc) == [2, 3, 4]

    def test_pages_outside_range_get_no_marker(self) -> None:
        doc = _build_doc(["a", "b", "c", "d", "e"])
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_RANGE, range_start=2, range_end=4
        )
        detect_headings(doc, page_numbering_policy=policy)

        pages_with_markers = _marker_pages(doc)
        assert 1 not in pages_with_markers
        assert 5 not in pages_with_markers

    def test_30_page_doc_range_5_to_24(self) -> None:
        """Spec example: 30-page doc, markers only for pages 5–24."""
        doc = _build_doc(["x"] * 30)
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_RANGE, range_start=5, range_end=24
        )
        detect_headings(doc, page_numbering_policy=policy)

        pages = _marker_pages(doc)
        assert pages == list(range(5, 25))

    def test_range_start_equals_end_gives_single_marker(self) -> None:
        doc = _build_doc(["a", "b", "c"])
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_RANGE, range_start=2, range_end=2
        )
        detect_headings(doc, page_numbering_policy=policy)
        assert _marker_pages(doc) == [2]

    def test_marker_text_uses_printed_label_when_available(self) -> None:
        doc = _build_doc(["a", "b", "c"], printed_labels=["80", "81", "82"])
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_RANGE, range_start=2, range_end=2
        )
        detect_headings(doc, page_numbering_policy=policy)
        assert _marker_texts(doc) == ["81"]

    def test_marker_text_falls_back_to_page_number_without_label(self) -> None:
        doc = _build_doc(["a", "b", "c"])  # no printed labels
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_RANGE, range_start=2, range_end=3
        )
        detect_headings(doc, page_numbering_policy=policy)
        assert _marker_texts(doc) == ["2", "3"]


# ---------------------------------------------------------------------------
# Mode 3 — MANUAL NUMBER OVERRIDE
# ---------------------------------------------------------------------------


class TestManualNumberOverrideMode:
    def test_sequential_numbering_from_specified_start(self) -> None:
        """Spec example: 20-page doc, start=301 → 301..320."""
        doc = _build_doc(["x"] * 20)
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_NUMBER_OVERRIDE, number_start=301
        )
        detect_headings(doc, page_numbering_policy=policy)

        assert _marker_texts(doc) == [str(n) for n in range(301, 321)]

    def test_every_page_receives_a_marker(self) -> None:
        doc = _build_doc(["a", "b", "c"], printed_labels=[None, None, None])
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_NUMBER_OVERRIDE, number_start=10
        )
        detect_headings(doc, page_numbering_policy=policy)

        assert len(_markers(doc)) == 3

    def test_printed_labels_are_ignored_in_favour_of_override(self) -> None:
        doc = _build_doc(["a", "b"], printed_labels=["99", "100"])
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_NUMBER_OVERRIDE, number_start=1
        )
        detect_headings(doc, page_numbering_policy=policy)

        assert _marker_texts(doc) == ["1", "2"]

    def test_default_start_is_1(self) -> None:
        doc = _build_doc(["a", "b", "c"])
        policy = PageNumberingPolicy(mode=PageNumberingMode.MANUAL_NUMBER_OVERRIDE)
        detect_headings(doc, page_numbering_policy=policy)
        assert _marker_texts(doc) == ["1", "2", "3"]


# ---------------------------------------------------------------------------
# Mode 4 — DISABLED
# ---------------------------------------------------------------------------


class TestDisabledMode:
    def test_no_markers_emitted_at_all(self) -> None:
        doc = _build_doc(["a", "b", "c"])
        policy = PageNumberingPolicy(mode=PageNumberingMode.DISABLED)
        detect_headings(doc, page_numbering_policy=policy)
        assert _markers(doc) == []

    def test_disabled_with_detected_labels_still_produces_no_markers(self) -> None:
        doc = _build_doc(["a", "b"], printed_labels=["10", "11"])
        policy = PageNumberingPolicy(mode=PageNumberingMode.DISABLED)
        detect_headings(doc, page_numbering_policy=policy)
        assert _markers(doc) == []

    def test_content_headings_still_detected_when_disabled(self) -> None:
        doc = _build_doc(["Introduction\nbody text"])
        policy = PageNumberingPolicy(mode=PageNumberingMode.DISABLED)
        detect_headings(doc, page_numbering_policy=policy)
        content = [h for h in doc.headings if not h.is_page_marker]
        assert any(h.text == "Introduction" for h in content)


# ---------------------------------------------------------------------------
# Backward compatibility: no policy supplied
# ---------------------------------------------------------------------------


class TestNoPolicyPreservesLegacyBehavior:
    """When page_numbering_policy=None (the default), every page must
    receive a marker regardless of whether printed_label is set, matching
    the behaviour before this feature existed."""

    def test_every_page_gets_marker_without_printed_label(self) -> None:
        doc = _build_doc(["a", "b", "c"])
        detect_headings(doc)  # no policy
        assert len(_markers(doc)) == 3

    def test_fallback_uses_physical_page_number_when_no_label(self) -> None:
        doc = _build_doc(["a", "b", "c"])
        detect_headings(doc)
        assert _marker_texts(doc) == ["1", "2", "3"]

    def test_printed_label_preferred_over_physical_number_when_present(self) -> None:
        doc = _build_doc(["a", "b"], printed_labels=["80", "81"])
        detect_headings(doc)
        assert _marker_texts(doc) == ["80", "81"]


# ---------------------------------------------------------------------------
# Markdown rendering integration
# ---------------------------------------------------------------------------


class TestMarkdownRendering:
    """Verify that the correct markers (or their absence) appear in the
    generated markdown string."""

    def test_auto_detected_label_renders_as_h6_without_word_page(self) -> None:
        doc = _build_doc(["body"], printed_labels=["367"])
        policy = PageNumberingPolicy(mode=PageNumberingMode.AUTO)
        detect_headings(doc, page_numbering_policy=policy)
        md = build_markdown(doc, page_numbering_policy=policy)
        assert "###### 367" in md.splitlines()
        assert "###### Page 367" not in md
        assert "Page 367" not in md

    def test_auto_suppressed_page_has_no_h6_in_output(self) -> None:
        doc = _build_doc(["body"], printed_labels=[None])
        policy = PageNumberingPolicy(mode=PageNumberingMode.AUTO)
        detect_headings(doc, page_numbering_policy=policy)
        md = build_markdown(doc, page_numbering_policy=policy)
        lines = md.splitlines()
        h6_lines = [l for l in lines if l.startswith("######")]
        assert h6_lines == []

    def test_manual_range_only_range_pages_have_h6(self) -> None:
        doc = _build_doc(["a", "b", "c", "d", "e"])
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_RANGE, range_start=2, range_end=4
        )
        detect_headings(doc, page_numbering_policy=policy)
        md = build_markdown(doc, page_numbering_policy=policy)
        lines = md.splitlines()
        h6_lines = [l for l in lines if l.startswith("######")]
        assert "###### 2" in h6_lines
        assert "###### 3" in h6_lines
        assert "###### 4" in h6_lines
        assert "###### 1" not in h6_lines
        assert "###### 5" not in h6_lines

    def test_manual_number_override_renders_sequential_labels(self) -> None:
        doc = _build_doc(["a", "b", "c"])
        policy = PageNumberingPolicy(
            mode=PageNumberingMode.MANUAL_NUMBER_OVERRIDE, number_start=301
        )
        detect_headings(doc, page_numbering_policy=policy)
        md = build_markdown(doc, page_numbering_policy=policy)
        lines = md.splitlines()
        assert "###### 301" in lines
        assert "###### 302" in lines
        assert "###### 303" in lines

    def test_disabled_produces_no_h6_lines(self) -> None:
        doc = _build_doc(["a", "b", "c"])
        policy = PageNumberingPolicy(mode=PageNumberingMode.DISABLED)
        detect_headings(doc, page_numbering_policy=policy)
        md = build_markdown(doc, page_numbering_policy=policy)
        h6_lines = [l for l in md.splitlines() if l.startswith("######")]
        assert h6_lines == []

    def test_mixed_auto_labels_render_where_present(self) -> None:
        doc = _build_doc(
            ["page one", "page two", "page three"],
            printed_labels=["10", None, "12"],
        )
        policy = PageNumberingPolicy(mode=PageNumberingMode.AUTO)
        detect_headings(doc, page_numbering_policy=policy)
        md = build_markdown(doc, page_numbering_policy=policy)
        lines = md.splitlines()
        assert "###### 10" in lines
        assert "###### 12" in lines
        h6_lines = [l for l in lines if l.startswith("######")]
        assert len(h6_lines) == 2  # page 2 had no label — no marker

    def test_body_text_still_rendered_when_no_marker(self) -> None:
        """Suppressing a marker must not suppress the page's body content."""
        doc = _build_doc(["important body text"], printed_labels=[None])
        policy = PageNumberingPolicy(mode=PageNumberingMode.DISABLED)
        detect_headings(doc, page_numbering_policy=policy)
        md = build_markdown(doc, page_numbering_policy=policy)
        assert "important body text" in md

    def test_no_policy_legacy_path_still_synthesises_fallback_in_build_markdown(
        self,
    ) -> None:
        """build_markdown called without detect_headings (empty headings list)
        and without a policy must still synthesise a marker — legacy contract."""
        page = Page(page_number=1, cleaned_text="some text")
        doc = Document(
            source_pdf_path="dummy.pdf",
            metadata=Metadata(filename="dummy.pdf"),
            pages=[page],
        )
        # detect_headings never called → doc.headings is []
        md = build_markdown(doc)  # no policy
        assert "###### 1" in md.splitlines()
