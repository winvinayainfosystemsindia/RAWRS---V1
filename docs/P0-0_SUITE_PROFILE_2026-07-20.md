# P0-0 — Suite Profile

**Date:** 2026-07-20 · RES v1 · Source: `pytest -q --durations=100`, cleared bytecode, commit `a30fa7a` + FE-0-004/005/006 working tree.

## Run Result

| Metric | Baseline (2026-07-19) | This run | Δ |
|---|---|---|---|
| Passed | 1617 | **1645** | +28 |
| Failed | 1 | **0** | −1 |
| Skipped | 7 | 7 | — |
| Wall time | 42m58s | **37m46s** | −5m12s |

The baseline failure `test_oleary_single_page_recovers_real_text` now **passes** — executed, 116.7s call, not skipped. Cause: P0-1 dependency pinning, as `ENGINEERING_READINESS_2026-07-19.md:154` predicted.

## Ranked Cost

Top-100 calls = 1851s of 2266s (**82%** of runtime).

| # | Test | Sec |
|---|---|---|
| 1 | `test_pipeline::TestSuryaIntegration::test_docling_empty_falls_back_to_real_surya_through_full_pipeline` | 416.3 |
| 2 | `test_surya_engine::TestRealSuryaIntegration::test_oleary_page_recovers_real_text_via_fallback` | 276.7 |
| 3 | `test_pipeline::TestDoclingIntegration::test_enable_ocr_true_recovers_real_text_through_full_pipeline` | 127.9 |
| 4 | `test_docling_engine::TestRealDoclingIntegration::test_oleary_single_page_recovers_real_text` | 116.7 |
| 5 | `TestStructureDetectionDoesNotChangeExistingOutputs[Bruner]` | 61.2 |
| 6 | `TestAltTextDoesNotChangeExistingOutputsOutsideImages[Bruner]` | 51.0 |

### By file

| File | Sec | Tests in top-100 |
|---|---|---|
| `test_pipeline.py` | 1164.0 | 51 |
| `test_surya_engine.py` | 276.7 | 1 |
| `test_docling_engine.py` | 116.7 | 1 |
| `test_docx.py` | 108.3 | 14 |
| `test_images.py` | 44.0 | 10 |
| `test_table_detection_benchmark.py` | 34.4 | 5 |

## Findings

| # | Finding | Consequence for P0-2 |
|---|---|---|
| F1 | **4 real-OCR tests = 937s = 41% of runtime** | `real_docling`/`real_surya` markers already exist (`pytest.ini`). Deselecting them alone: 37m46s → ~22m. Highest return, lowest risk. |
| F2 | `test_pipeline.py` = 1164s over 51 tests = **51% of runtime** | Dominated by per-benchmark-PDF parametrization running the full pipeline. Needs `benchmark_pdf` marker + `Document` JSON fixtures (P0-3), not deletion. |
| F3 | Bruner PDF is the costliest fixture (61.2 + 51.0 + 25.0s in top-12) | Single-document cost; a fixture-level cache would pay for itself. |
| F4 | Top-100 = 82% of runtime | Tiering ~100 tests governs the whole suite; the long tail is already cheap. |

**Acceptance (P0-0): met** — ranked cost table produced; top-N accounting for ≥80% of runtime named (top-100 = 82%).

## Correction to `ENGINEERING_READINESS_2026-07-19.md:70`

That document states the suite's cost is **"diffuse, not concentrated in 4 inference tests"**, and revised P0-2's effort up to 1-3d on that basis.

**Measurement contradicts it.** Those 4 tests are 937s of 2266s — 41%, the single most concentrated cost in the suite. The claim was itself an inference from source inspection, which is the exact error that document warned against two lines earlier.

The effort revision may still stand on F2 (the diffuse half is real, and it is `test_pipeline.py`), but its stated basis is wrong and should be re-derived rather than inherited.

## Recommended P0-2 tiering

| Tier | Contents | Est. |
|---|---|---|
| Fast | Everything unmarked | ~6m |
| Medium | `benchmark_pdf` | ~22m |
| Slow | `real_docling`, `real_surya` | ~16m |

Fast does **not** reach the <2min P0-2 target by deselection alone — per F2, `test_pipeline.py`'s benchmark parametrization must also move to Medium, which is what P0-3's fixtures enable.

**P0-2 cannot be closed by markers alone; it depends on P0-3.** That contradicts the backlog's `P0-2 → P0-3` edge (`MASTER_IMPLEMENTATION_BACKLOG.md:162`) and should be reconciled before P0-2 starts. Estimates above are arithmetic from this run, not measured tier times; P0-2 must time the three tiers to close.
