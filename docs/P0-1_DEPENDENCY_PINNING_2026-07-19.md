# P0-1 — Dependency Graph Pinning

**Date:** 2026-07-19 · **Scope:** reproducibility only — no functional change to RAWRS

---

## Dependency audit

Before this task, exactly **one** of 11 direct runtime dependencies was pinned.

| Package | Declared before | Installed | Now |
|---|---|---|---|
| pydantic | `>=2.0` | 2.13.4 | `==2.13.4` |
| pymupdf | *(floating)* | 1.28.0 | `==1.28.0` |
| loguru | *(floating)* | 0.7.3 | `==0.7.3` |
| python-docx | *(floating)* | 1.2.0 | `==1.2.0` |
| docling | *(floating)* | 2.87.0 | `==2.87.0` |
| surya-ocr | `==0.20.0` | 0.20.0 | `==0.20.0` *(unchanged)* |
| **rapidocr** | **undeclared** | **3.9.0** | `==3.9.0` **(newly declared)** |
| beautifulsoup4 | *(floating)* | 4.15.0 | `==4.15.0` |
| fastapi | *(floating)* | 0.138.2 | `==0.138.2` |
| uvicorn[standard] | *(floating)* | 0.49.0 | `==0.49.0` |
| python-multipart | *(floating)* | 0.0.32 | `==0.0.32` |
| pytest | *(floating)* | 9.1.1 | `==9.1.1` |
| pytest-cov | *(floating)* | 7.1.0 | `==7.1.0` |
| torch / transformers / qwen-vl-utils / psutil | *(floating)* | 2.12.1 / 4.57.6 / 0.0.14 / 7.2.2 | pinned |

No `pyproject.toml`, `setup.py` or CI workflow exists — these files are the complete dependency surface.

**Correction to `requirements-ai.txt`:** `torch` and `transformers` were documented as optional AI extras. They are not. `docling` requires `torch` and `torchvision` directly, and `docling-ibm-models` requires `transformers` unconditionally on non-darwin platforms. Only `qwen-vl-utils` and `psutil` are genuinely AI-only.

---

## Root cause of the failing `real_docling` test

Confirmed by reading rapidocr 3.9.0's own model registry (`rapidocr/default_models.yaml`):

| Backend | Model families available |
|---|---|
| `onnxruntime` | PP-OCRv4, PP-OCRv5, **PP-OCRv6** |
| `openvino` | PP-OCRv4, PP-OCRv5, **PP-OCRv6** |
| `torch` | PP-OCRv4, PP-OCRv5 — **no PP-OCRv6** |

docling 2.87.0 requests **PP-OCRv6**. `onnxruntime` is an *optional* rapidocr extra and is **not installed**, so rapidocr selects the torch backend (`[RapidOCR] base.py:23: Using engine_name: torch`), which has no v6 entry — producing `Unsupported configuration: torch.PP-OCRv6.det.small`.

The chain that allowed this: `docling` was unpinned, it accepts `rapidocr>=3.3,<4.0.0`, and `rapidocr` was undeclared — so a transitive package drifted to a version whose default model family the installed backend cannot serve.

**The fix is one dependency, not a code change:** install `onnxruntime` (docling's declared `rapidocr` extra).

**Deliberately NOT applied in P0-1.** Adding it would make Docling OCR start working — a functional change, outside this task's stated scope ("make no functional changes", "do not fix unrelated bugs"). Pinning `rapidocr==3.9.0` makes the failure deterministic and attributable instead of a moving target. Recommended as its own task.

---

## Files modified

| File | Change |
|---|---|
| `requirements.txt` | 10 packages pinned; `rapidocr==3.9.0` declared; header documents the rapidocr chain |
| `requirements-dev.txt` | `pytest`, `pytest-cov` pinned |
| `requirements-ai.txt` | 4 packages pinned; corrects the "optional" claim |
| `requirements.lock` | **NEW** — complete 124-package graph |

No source file touched. No API, schema or business logic change.

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Lockfile is platform-specific (Windows / Python 3.11.14) | Medium | Header records the source platform. A Linux CI machine will need its own resolution — `pip install -r requirements.txt` remains the portable path |
| Pinning freezes the known-broken `rapidocr==3.9.0` | Low | Intentional and documented; makes the failure reproducible rather than intermittent |
| Pins go stale without a refresh policy | Low | Regeneration command is in the lockfile header |
| No CI enforces the lockfile | Medium | Out of P0-1 scope; covered by backlog A11-2 |

---

## Rollback plan

```
git checkout -- requirements.txt requirements-dev.txt requirements-ai.txt
rm requirements.lock
```

No migration, no state change, no code dependency. Rollback is complete and instantaneous. The installed environment is untouched by this task — every pin records a version that was already present.
