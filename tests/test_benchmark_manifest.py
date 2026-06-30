"""Tests for tests/conftest.py's benchmark manifest infrastructure.

See samples/benchmark/manifest.json and the Benchmark Infrastructure
Audit for why this exists: filename-hardcoded and index-based
("SAMPLE_PDFS[0]") benchmark PDF selection broke when the corpus grew
from 4 to 10 files.
"""

from conftest import (
    BENCHMARK_DIR,
    BENCHMARK_MANIFEST,
    a_born_digital_pdf,
    a_scanned_pdf,
    benchmark_pdfs_with,
    benchmark_pdfs_without,
    validate_manifest_completeness,
)


def test_manifest_loads_and_is_non_empty() -> None:
    assert BENCHMARK_MANIFEST
    assert all(isinstance(entry, dict) for entry in BENCHMARK_MANIFEST.values())


def test_manifest_is_complete() -> None:
    validate_manifest_completeness()


def test_every_capability_filter_returns_paths_that_exist() -> None:
    for capability in (
        "born_digital",
        "scanned",
        "ocr_required",
        "figures",
        "footnotes",
        "front_matter",
        "tables",
    ):
        for path in benchmark_pdfs_with(capability):
            assert path.is_file(), f"{path} (capability={capability}) is not on disk"


def test_with_and_without_partition_the_full_corpus() -> None:
    for capability in ("born_digital", "scanned", "ocr_required"):
        with_it = set(benchmark_pdfs_with(capability))
        without_it = set(benchmark_pdfs_without(capability))
        assert with_it.isdisjoint(without_it)
        assert with_it | without_it == {BENCHMARK_DIR / name for name in BENCHMARK_MANIFEST}


def test_a_scanned_pdf_is_actually_ocr_required() -> None:
    path = a_scanned_pdf()
    assert BENCHMARK_MANIFEST[path.name]["ocr_required"] is True


def test_a_born_digital_pdf_is_actually_born_digital() -> None:
    path = a_born_digital_pdf()
    assert BENCHMARK_MANIFEST[path.name]["born_digital"] is True
