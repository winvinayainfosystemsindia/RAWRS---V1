"""Free PDF accessibility audit of a public website.

    python -m src.audit https://www.example.gov [--out DIR] [--max-pdfs 40] [--max-pages 150] [--delay 1.0]

Finds the site's PDFs (sitemap.xml, else a shallow same-site crawl), downloads
them into ``<out>/<host>-<date>/pdfs``, scores each one (src/audit/score.py)
and writes results.json, report.html and report.pdf beside them. Downloaded
files are untrusted: run this in the Codespace, not on a workstation.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from src.audit import crawl, report
from src.audit.score import score_pdf
from src.docx import pdf_export


def run(url: str, out_root: Path, limits: crawl.Limits) -> Path:
    url = crawl.resolve(url, limits)
    fetcher = crawl.open_site(url, limits)
    folder = out_root / f"{fetcher.site}-{date.today().isoformat()}"
    pdf_urls, info = crawl.discover(url, fetcher)
    print(f"{info['pdf_links_found']} PDF links found via {info['source']} ({info['pages_read']} pages read)", flush=True)
    saved = crawl.download(pdf_urls, fetcher, folder / "pdfs")
    results = []
    for number, (pdf_url, path) in enumerate(saved, start=1):
        results.append(score_pdf(pdf_url, path))
        print(f"  {number}/{len(saved)} {path.name} {len(results[-1]['problems'])} problem(s)", flush=True)
    info["requests"] = fetcher.requests
    summary = report.summarise(results, info["pdf_links_found"])
    stored = {k: v for k, v in summary.items() if k != "worst"}
    (folder / "results.json").write_text(
        json.dumps({"site": fetcher.site, "crawl": info, "results": results, "summary": stored}, indent=2),
        encoding="utf-8")
    html_path = folder / "report.html"
    html_path.write_text(report.render_html(fetcher.site, date.today().isoformat(), summary, info), encoding="utf-8")
    pdf_path = report.render_pdf(fetcher.site, date.today().isoformat(), summary, info, folder / "report.pdf")
    compliant = (pdf_export.verapdf_verdict(pdf_path) or {}).get("compliant") if pdf_path else None
    print(f"{summary['failing']}/{summary['pdfs_checked']} failing; report {html_path}; "
          f"PDF {pdf_path or 'not made (no LibreOffice)'}, its own PDF/UA-1 verdict: {compliant}")
    return folder


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("--out", default="outputs/audit")
    parser.add_argument("--max-pdfs", type=int, default=crawl.Limits.max_pdfs)
    parser.add_argument("--max-pages", type=int, default=crawl.Limits.max_pages)
    parser.add_argument("--delay", type=float, default=crawl.Limits.delay_seconds)
    args = parser.parse_args(argv)
    if not args.url.startswith(("http://", "https://")):
        parser.error("the URL must start with http:// or https://")
    if args.delay < 0.5 or args.max_pdfs < 1 or args.max_pages < 1:
        parser.error("--delay must be at least 0.5 s, and the caps at least 1")
    limits = crawl.Limits(max_pdfs=args.max_pdfs, max_pages=args.max_pages, delay_seconds=args.delay)
    run(args.url, Path(args.out), limits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
