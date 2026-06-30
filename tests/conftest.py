"""Shared benchmark-corpus fixtures for the RAWRS test suite.

samples/benchmark/manifest.json is the single source of truth for which
capabilities each benchmark PDF exercises (born_digital/scanned/
ocr_required/figures/footnotes/front_matter/tables). Tests should select
benchmark PDFs through benchmark_pdfs_with()/benchmark_pdfs_without()/
a_scanned_pdf()/a_born_digital_pdf() below instead of re-declaring
SAMPLE_PDF_DIR/SAMPLE_PDFS and then hardcoding a filename, indexing
SAMPLE_PDFS[0], or filtering by a filename substring - those patterns
broke when the corpus grew from 4 to 10 files (see the Benchmark
Infrastructure Audit). This module does not remove the old
SAMPLE_PDF_DIR/SAMPLE_PDFS pattern from every test file - only the
highest-value duplicated cases were migrated.
"""

import json
from pathlib import Path
from typing import Dict, List

import pytest

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "pdfs"
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "samples" / "benchmark" / "manifest.json"


def load_manifest() -> Dict[str, dict]:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)["pdfs"]


BENCHMARK_MANIFEST: Dict[str, dict] = load_manifest()


def benchmark_pdfs_with(capability: str) -> List[Path]:
    """All manifest-declared benchmark PDFs with `capability: true`, sorted by name."""
    names = sorted(name for name, entry in BENCHMARK_MANIFEST.items() if entry.get(capability))
    return [BENCHMARK_DIR / name for name in names]


def benchmark_pdfs_without(capability: str) -> List[Path]:
    """All manifest-declared benchmark PDFs with `capability: false` (or absent), sorted by name."""
    names = sorted(
        name for name, entry in BENCHMARK_MANIFEST.items() if not entry.get(capability)
    )
    return [BENCHMARK_DIR / name for name in names]


def _smallest(paths: List[Path]) -> Path:
    # Smallest-by-size, not alphabetically-first: several call sites run
    # real OCR (enable_ocr=True) against whatever this resolves to, so
    # picking the cheapest matching fixture keeps those tests fast and
    # avoids silently swapping in an expensive new corpus addition (e.g.
    # a 32MB scanned PDF) just because it happens to sort first.
    return min(paths, key=lambda path: path.stat().st_size)


def a_scanned_pdf() -> Path:
    """The smallest manifest-declared ocr_required benchmark PDF.

    Replaces the 5 independently-hardcoded
    `SCANNED_PDF = SAMPLE_PDF_DIR / "4. O Leary...".pdf` declarations.
    """
    candidates = benchmark_pdfs_with("ocr_required")
    if not candidates:
        raise LookupError("manifest.json declares no ocr_required benchmark PDF")
    return _smallest(candidates)


def a_born_digital_pdf() -> Path:
    """The smallest manifest-declared born-digital benchmark PDF.

    Replaces `SAMPLE_PDFS[0]`-style index access, which silently assumed
    the alphabetically-first file was born-digital (or, in
    tests/test_pipeline.py's case, scanned - the assumption flips
    depending on which file happens to sort first, which is exactly the
    fragility this fixture removes).
    """
    candidates = benchmark_pdfs_with("born_digital")
    if not candidates:
        raise LookupError("manifest.json declares no born_digital benchmark PDF")
    return _smallest(candidates)


def validate_manifest_completeness() -> None:
    """Raise AssertionError if manifest.json and samples/benchmark/pdfs/ disagree.

    A corpus drift (PDF added/removed/renamed without updating the
    manifest) should fail here, once, with a clear message - not as 26
    scattered failures across unrelated test files.
    """
    on_disk = {p.name for p in BENCHMARK_DIR.glob("*.pdf")}
    in_manifest = set(BENCHMARK_MANIFEST.keys())
    missing_from_manifest = on_disk - in_manifest
    missing_from_disk = in_manifest - on_disk
    assert not missing_from_manifest, (
        f"PDF(s) present in {BENCHMARK_DIR} but missing from manifest.json: "
        f"{sorted(missing_from_manifest)}"
    )
    assert not missing_from_disk, (
        f"manifest.json entry(ies) with no matching file in {BENCHMARK_DIR}: "
        f"{sorted(missing_from_disk)}"
    )


@pytest.fixture(scope="session", autouse=True)
def _benchmark_manifest_is_complete() -> None:
    validate_manifest_completeness()
