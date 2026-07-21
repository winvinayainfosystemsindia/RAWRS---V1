"""FE-0-005 / FE-0-006 — front-matter semantic role regression tests.

Guards the behaviour confirmed by H-001
(docs/H-001_heading_reproducibility_2026-07-20.md):

  * the document title becomes an H1 on both ingestion paths
  * author bylines and affiliations are metadata, never headings
  * the two pipelines agree on front-matter semantics

These assert *intended* behaviour only. The "native title split" that
earlier reports described was a stale-__pycache__ artifact and is
deliberately not encoded here — no test asserts a split title.

Native-path coverage targets the exact predicate heading_detector.py
consults (``is_heading_eligible(classify_front_matter_line(...))``)
rather than driving detect_headings() end to end, because that function
re-opens the source PDF for layout metadata and the benchmark corpus is
gitignored — a PDF-dependent test would fail on a fresh clone.
"""

from __future__ import annotations

from pathlib import Path

from src.frontmatter.front_matter_roles import (
    FrontMatterRole,
    build_title_heading,
    classify_front_matter_line,
    is_heading_eligible,
)
from src.mathpix.ingestor import MathpixImportProvider
from src.models.contracts import Document, HeadingLevel
from src.models.front_matter import FrontMatter
from src.models.metadata import Metadata
from src.models.page import Page


def _make_document(page_count: int = 2) -> Document:
    return Document(
        source_pdf_path="test.pdf",
        metadata=Metadata(filename="test.pdf", page_count=page_count),
        pages=[Page(page_number=i + 1) for i in range(page_count)],
    )


def _run_mathpix(mmd_text: str, tmp_path: Path, page_count: int = 2) -> Document:
    mmd_file = tmp_path / "t.mmd"
    mmd_file.write_text(mmd_text, encoding="utf-8")
    return MathpixImportProvider().import_document(_make_document(page_count), mmd_path=mmd_file)


def _content(doc: Document):
    return [h for h in doc.headings if not h.is_page_marker]


# ── 1. Mathpix title promoted to H1 ────────────────────────────────────

class TestTitlePromotedToH1:
    def test_mathpix_title_becomes_h1(self, tmp_path):
        doc = _run_mathpix(r"\title{The Nature of Enquiry}" + "\n\n" + r"\section*{Intro}", tmp_path)
        h1s = [h for h in _content(doc) if h.level == HeadingLevel.H1]
        assert len(h1s) == 1
        assert h1s[0].text == "The Nature of Enquiry"

    def test_title_heading_is_not_a_page_marker(self, tmp_path):
        doc = _run_mathpix(r"\title{Doc}", tmp_path)
        h1s = [h for h in doc.headings if h.level == HeadingLevel.H1]
        assert all(not h.is_page_marker for h in h1s)

    def test_title_h1_precedes_content_headings(self, tmp_path):
        doc = _run_mathpix(r"\title{T}" + "\n\n" + r"\section*{First Section}", tmp_path)
        content = _content(doc)
        assert content[0].level == HeadingLevel.H1
        assert content[0].text == "T"


# ── 2. Native byline excluded ──────────────────────────────────────────

class TestBylineExcluded:
    """The predicate heading_detector.py consults before classification."""

    def test_author_line_is_not_heading_eligible(self):
        fm = FrontMatter(
            title="A Title",
            title_source_texts=["A Title"],
            authors=["Rohit Dhankar"],
            author_source_texts=["Rohit Dhankar"],
        )
        assert classify_front_matter_line("Rohit Dhankar", fm) is FrontMatterRole.AUTHOR
        assert is_heading_eligible(FrontMatterRole.AUTHOR) is False

    def test_affiliation_line_is_not_heading_eligible(self):
        fm = FrontMatter(
            title="T",
            affiliations=["Azim Premji University"],
            affiliation_source_texts=["Azim Premji University"],
        )
        assert classify_front_matter_line("Azim Premji University", fm) is FrontMatterRole.AFFILIATION
        assert is_heading_eligible(FrontMatterRole.AFFILIATION) is False

    def test_title_line_remains_heading_eligible(self):
        """The title must stay eligible — only bylines are declined."""
        fm = FrontMatter(title="A Title", title_source_texts=["A Title"])
        assert classify_front_matter_line("A Title", fm) is FrontMatterRole.TITLE
        assert is_heading_eligible(FrontMatterRole.TITLE) is True

    def test_ordinary_body_line_unaffected(self):
        fm = FrontMatter(title="T", title_source_texts=["T"], authors=["A"], author_source_texts=["A"])
        assert classify_front_matter_line("Some ordinary body sentence.", fm) is None
        assert is_heading_eligible(None) is True

    def test_wrapped_title_matches_every_source_line(self):
        """A wrapped title contributes several source lines; all are TITLE."""
        fm = FrontMatter(
            title="AIMS OF EDUCATION: DO TEACHERS NEED TO BOTHER ABOUT THEM?",
            title_source_texts=["AIMS OF EDUCATION: DO TEACHERS NEED", "TO BOTHER ABOUT THEM?"],
        )
        for line in fm.title_source_texts:
            assert classify_front_matter_line(line, fm) is FrontMatterRole.TITLE

    def test_matching_is_whitespace_insensitive(self):
        fm = FrontMatter(title="T", authors=["Jane Doe"], author_source_texts=["Jane  Doe"])
        assert classify_front_matter_line("Jane Doe", fm) is FrontMatterRole.AUTHOR


# ── 3. Native / Mathpix semantic parity ────────────────────────────────

class TestPipelineParity:
    def test_both_paths_use_the_same_role_classifier(self):
        """Guards against either path growing a divergent copy."""
        from src.headings import heading_detector
        from src.frontmatter.front_matter_roles import (
            classify_front_matter_line as canonical,
            is_heading_eligible as canonical_eligible,
        )
        assert heading_detector.classify_front_matter_line is canonical
        assert heading_detector.is_heading_eligible is canonical_eligible

    def test_mathpix_path_uses_canonical_title_builder(self):
        from src.mathpix import ingestor
        from src.frontmatter.front_matter_roles import build_title_heading as canonical
        assert ingestor.build_title_heading is canonical

    def test_byline_never_heading_eligible_regardless_of_source(self):
        """Role -> eligibility is source-independent by construction."""
        for role in (FrontMatterRole.AUTHOR, FrontMatterRole.AFFILIATION):
            assert is_heading_eligible(role) is False
        assert is_heading_eligible(FrontMatterRole.TITLE) is True


# ── 4. Multiple-author document ────────────────────────────────────────

class TestMultipleAuthors:
    def test_every_author_line_declined(self):
        fm = FrontMatter(
            title="Teacher as a Person",
            title_source_texts=["Teacher as a Person"],
            authors=["Michael Fullan", "Andy Hargreaves"],
            author_source_texts=["Michael Fullan", "Andy Hargreaves"],
        )
        for author_line in fm.author_source_texts:
            role = classify_front_matter_line(author_line, fm)
            assert role is FrontMatterRole.AUTHOR
            assert is_heading_eligible(role) is False

    def test_multi_author_mathpix_still_yields_single_h1(self, tmp_path):
        mmd = "\\title{Joint Paper}\n\n\\author{Alice Smith \\and Bob Jones}\n\n\\section*{Body}"
        doc = _run_mathpix(mmd, tmp_path)
        h1s = [h for h in _content(doc) if h.level == HeadingLevel.H1]
        assert len(h1s) == 1
        assert h1s[0].text == "Joint Paper"

    def test_authors_preserved_in_front_matter_not_headings(self):
        """FE-0-006's point: the byline is metadata, not discarded."""
        fm = FrontMatter(
            title="T",
            authors=["Michael Fullan", "Andy Hargreaves"],
            author_source_texts=["Michael Fullan", "Andy Hargreaves"],
        )
        assert fm.authors == ["Michael Fullan", "Andy Hargreaves"]
        assert all(
            not is_heading_eligible(classify_front_matter_line(a, fm))
            for a in fm.author_source_texts
        )


# ── 5. Missing-title fallback ──────────────────────────────────────────

class TestMissingTitleFallback:
    def test_no_front_matter_yields_no_title_heading(self):
        assert build_title_heading(None) is None

    def test_empty_title_yields_no_title_heading(self):
        assert build_title_heading(FrontMatter(title=None, authors=["A"])) is None

    def test_blank_title_yields_no_title_heading(self):
        assert build_title_heading(FrontMatter(title="")) is None

    def test_mathpix_without_title_produces_no_h1(self, tmp_path):
        """A chapter excerpt with no title page must not gain a synthetic H1."""
        doc = _run_mathpix(r"\section*{Only A Section}", tmp_path)
        assert [h for h in _content(doc) if h.level == HeadingLevel.H1] == []

    def test_classify_returns_none_when_front_matter_absent(self):
        assert classify_front_matter_line("Anything at all", None) is None

    def test_empty_line_never_classified(self):
        fm = FrontMatter(title="T", title_source_texts=["T"])
        assert classify_front_matter_line("", fm) is None
        assert classify_front_matter_line("   ", fm) is None
