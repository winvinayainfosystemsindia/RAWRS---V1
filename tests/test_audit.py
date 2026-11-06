"""Task 4 audit (src/audit): crawl rules, scoring and the report, all offline.

The crawl test serves a tiny site from a local HTTP server, so the real
urllib / robots.txt / sitemap code runs without touching the internet.
"""
import gzip
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import fitz
import pytest

from src.audit import crawl, report
from src.audit.score import input_checks, problems, severity
from src.docx import pdf_export

_SITEMAP = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>{base}/docs/a.pdf</loc></url><url><loc>{base}/page.html</loc></url></urlset>"""


@pytest.fixture
def site(tmp_path):
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    base = f"http://127.0.0.1:{server.server_port}"
    (tmp_path / "docs").mkdir()
    (tmp_path / "private").mkdir()
    (tmp_path / "docs" / "a.pdf").write_bytes(b"%PDF-1.4 a")
    (tmp_path / "docs" / "b.pdf").write_bytes(b"%PDF-1.4 b")
    (tmp_path / "docs" / "copy-of-a.pdf").write_bytes(b"%PDF-1.4 a")  # same bytes, other address
    (tmp_path / "docs" / "fake.pdf").write_bytes(b"<html>not a pdf</html>")
    (tmp_path / "private" / "c.pdf").write_bytes(b"%PDF-1.4 c")
    (tmp_path / "robots.txt").write_text(f"User-agent: *\nDisallow: /private/\nSitemap: {base}/sitemap.xml\n")
    (tmp_path / "sitemap.xml").write_text(_SITEMAP.format(base=base))
    (tmp_path / "page.html").write_text(
        '<a href="docs/b.pdf">b</a><a href="/docs/fake.pdf">f</a><a href="/private/c.pdf">c</a>'
        '<a href="/docs/copy-of-a.pdf">copy</a>'
        '<a href="https://elsewhere.example/x.pdf">x</a><a href="docs/b.pdf#p2">dup</a>'
        f'<a href="{base.replace("127.0.0.1", "www.127.0.0.1")}/docs/b.pdf">same file via www</a>')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield base
    server.shutdown()


def test_crawl_obeys_robots_stays_on_site_and_keeps_only_real_pdfs(site, tmp_path):
    limits = crawl.Limits(delay_seconds=0, max_pdfs=10)
    fetcher = crawl.open_site(site, limits)
    urls, info = crawl.discover(site, fetcher)

    assert info["source"] == "sitemap"
    assert urls == [f"{site}/docs/a.pdf", f"{site}/docs/b.pdf", f"{site}/docs/fake.pdf", f"{site}/private/c.pdf",
                    f"{site}/docs/copy-of-a.pdf"]
    saved = crawl.download(urls, fetcher, tmp_path / "out")
    assert [(u.rsplit("/", 1)[1], p.name) for u, p in saved] == [("a.pdf", "0001.pdf"), ("b.pdf", "0002.pdf")]
    assert fetcher.get(f"{site}/private/c.pdf", 100) is None  # robots.txt
    assert fetcher.get("https://elsewhere.example/x.pdf", 100) is None  # other site


def test_download_respects_the_pdf_cap(site, tmp_path):
    fetcher = crawl.open_site(site, crawl.Limits(delay_seconds=0, max_pdfs=1))
    urls, _ = crawl.discover(site, fetcher)
    assert len(crawl.download(urls, fetcher, tmp_path / "out")) == 1


def test_sitemap_index_and_gzip_are_read():
    index = b'<sitemapindex xmlns="x"><sitemap><loc>https://a.gov/s1.xml</loc></sitemap></sitemapindex>'
    assert crawl.sitemap_locs(index) == (["https://a.gov/s1.xml"], [])
    urlset = gzip.compress(b'<urlset xmlns="x"><url><loc> https://a.gov/f.PDF </loc></url></urlset>')
    assert crawl.sitemap_locs(urlset) == ([], ["https://a.gov/f.PDF"])
    assert crawl.sitemap_locs(b"not xml") == ([], [])
    assert crawl.is_pdf_link("https://a.gov/f.PDF") and not crawl.is_pdf_link("https://a.gov/f.pdf.html")
    assert crawl.is_pdf_link("https://a.gov/DocumentCenter/View/123/Budget-2026")
    assert not crawl.is_pdf_link("https://a.gov/files/minutes.docx") and not crawl.is_pdf_link("https://a.gov/909/Forms")
    assert crawl.same_site("https://docs.a.gov/x", "a.gov") and not crawl.same_site("https://nota.gov/x", "a.gov")


def _pdf(path, *, text, title="", tagged=False):
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    doc.set_metadata({"title": title})
    if tagged:
        cat = doc.pdf_catalog()
        doc.xref_set_key(cat, "MarkInfo", "<</Marked true>>")
        struct = doc.get_new_xref()
        doc.update_object(struct, "<</Type/StructTreeRoot>>")
        doc.xref_set_key(cat, "StructTreeRoot", f"{struct} 0 R")
        doc.xref_set_key(cat, "Lang", "(en-US)")
    doc.save(str(path))
    return path


def test_input_checks_read_tags_title_and_language(tmp_path):
    plain = input_checks(_pdf(tmp_path / "p.pdf", text="Hello world, this is a page of text."))
    assert (plain["tagged"], plain["title"], plain["language"], plain["pages"]) == (False, "", "", 1)
    tagged = input_checks(_pdf(tmp_path / "t.pdf", text="Hello", title="Budget 2026", tagged=True))
    assert (tagged["tagged"], tagged["title"], tagged["language"]) == (True, "Budget 2026", "en-US")


def test_problems_in_plain_english():
    checks = {"pages": 3, "tagged": False, "title": "", "language": "", "images": 2}
    scanned = problems(checks, {"pages_without_text": [1, 2, 3]}, None)
    assert [p["issue"] for p in scanned] == ["scanned", "untagged", "images_no_alt", "no_language", "no_title"]
    assert scanned[2]["text"] == "2 image(s) without a text description."

    tagged = {"pages": 3, "tagged": True, "title": "T", "language": "en", "images": 2}
    vera = {"failed_rules": [
        {"clause": "7.3", "test": 1, "failed_checks": 1, "description": "Figure shall have alternate text"},
        {"clause": "7.5", "test": 1, "failed_checks": 4, "description": "TH needs Scope"},
        {"clause": "7.21.4.1", "test": 1, "failed_checks": 1, "description": "font embedded"},
    ]}
    found = problems(tagged, {"pages_without_text": [2]}, vera)
    assert [p["issue"] for p in found] == ["missing_text", "images_no_alt", "table_headers", "other_pdfua"]
    assert found[0]["text"] == "1 of 3 pages have no readable text."
    assert severity({"problems": scanned}) > severity({"problems": found})

    # A link without a description is not an image without one (Burlington 0001.pdf: 0 images).
    links_only = {"failed_rules": [{"clause": "7.18.5", "test": 2, "failed_checks": 3,
                                    "description": "Links shall contain an alternate description"}]}
    assert [p["issue"] for p in problems(tagged, {"pages_without_text": []}, links_only)] == ["other_pdfua"]


def test_report_ranks_worst_and_escapes_html():
    bad = {"url": "https://a.gov/<script>.pdf", "pages": 2, "pdfua1_compliant": False,
           "problems": [{"issue": "scanned", "text": "Scanned image with no text: a screen reader reads nothing."}]}
    fine = {"url": "https://a.gov/ok.pdf", "pages": 9, "pdfua1_compliant": True, "problems": []}
    summary = report.summarise([fine, bad, {"url": "u", "error": "could not open", "problems": []}], found=5)
    assert (summary["pdfs_checked"], summary["failing"], summary["failing_share"], summary["unreadable"]) == (2, 1, 50.0, 1)
    assert summary["worst"][0] is bad
    page = report.render_html("a.gov", "2026-11-06", summary, {"source": "sitemap", "requests": 7})
    assert "<script>.pdf" not in page and "&lt;script&gt;.pdf" in page
    assert "not a certification" in page and "no hours figure" in page
    assert "ok.pdf" not in page  # a passing file is not listed among the worst


def _summary():
    bad = {"url": "https://a.gov/x.pdf", "pages": 2, "pdfua1_compliant": False,
           "problems": [{"issue": "untagged", "text": "Not tagged."}]}
    return report.summarise([bad], found=1)


def test_report_docx_has_real_headings_and_header_rows(tmp_path):
    import docx
    from docx.oxml.ns import qn

    path = report.render_docx("a.gov", "2026-11-06", _summary(), {"source": "crawl"}, tmp_path / "r.docx")
    document = docx.Document(str(path))
    assert [p.style.name for p in document.paragraphs if p.style.name.startswith("Heading")][:2] == ["Heading 1", "Heading 2"]
    assert all(t.rows[0]._tr.find(qn("w:trPr")).find(qn("w:tblHeader")) is not None for t in document.tables)
    assert document.core_properties.title == "PDF accessibility check: a.gov"


@pytest.mark.skipif(not (pdf_export.soffice_binary() and pdf_export.verapdf_binary()),
                    reason="needs LibreOffice and veraPDF (Codespace)")
def test_report_pdf_passes_pdfua1(tmp_path):
    pdf = report.render_pdf("a.gov", "2026-11-06", _summary(), {"source": "crawl"}, tmp_path / "r.pdf")
    assert pdf_export.verapdf_verdict(pdf)["compliant"] is True
