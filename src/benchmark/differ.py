"""Per-element diff, corpus metrics, and the machine-readable gap report (F0).

Compares a benchmark (human-remediated) ``BenchmarkProfile`` against a RAWRS
``BenchmarkProfile`` and produces:
  * a structured, per-element diff (headings, front matter, page structure,
    running headers/footers, figures, tables, footnotes, endnotes, metadata);
  * per-document metrics (heading P/R/F1, page-break fidelity, front-page
    similarity, footnote placement accuracy, running-header suppression);
  * a corpus-level aggregate.

The report is a plain JSON-serializable dict so later stages can load it as
their regression specification. Read-only; no production module imports this.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.benchmark.profile import BenchmarkProfile, profile_from_docx


# --------------------------------------------------------------------------- #
# alignment helpers
# --------------------------------------------------------------------------- #

def _norm(text: str) -> str:
    return " ".join((text or "").lower().split()).strip()


def _align_by_text(bench: List[str], rawrs: List[str]) -> Tuple[int, List[Dict[str, Any]]]:
    """Greedy exact-normalized-text alignment. Returns (matched, per_item)."""
    r_norm = [_norm(x) for x in rawrs]
    used = [False] * len(r_norm)
    matched = 0
    per: List[Dict[str, Any]] = []
    for b in bench:
        bn = _norm(b)
        hit = next((i for i, rn in enumerate(r_norm) if not used[i] and rn == bn), -1)
        if hit >= 0:
            used[hit] = True
            matched += 1
            per.append({"status": "matched", "benchmark": b, "rawrs": rawrs[hit]})
        else:
            per.append({"status": "missing", "benchmark": b, "rawrs": None})
    for i, r in enumerate(rawrs):
        if not used[i]:
            per.append({"status": "extra", "benchmark": None, "rawrs": r})
    return matched, per


def _pr(matched: int, bench_total: int, rawrs_total: int) -> Dict[str, float]:
    precision = matched / rawrs_total if rawrs_total else (1.0 if bench_total == 0 else 0.0)
    recall = matched / bench_total if bench_total else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def _ratio_fidelity(a: int, b: int) -> float:
    """1.0 when equal; degrades with absolute difference relative to the larger."""
    if a == 0 and b == 0:
        return 1.0
    return round(1 - abs(a - b) / max(a, b, 1), 4)


def _front_signature(prof: BenchmarkProfile) -> str:
    parts = [prof.metadata.get("title") or ""]
    parts += [h.text for h in prof.headings[:3]]
    return _norm(" ".join(parts))


def _note_accuracy(prof_b: BenchmarkProfile, prof_r: BenchmarkProfile) -> float:
    """Fraction of benchmark notes that RAWRS reproduces on the CORRECT side
    (footnote vs endnote), matched by normalized text."""
    bench = [(_norm(n.text), "footnote") for n in prof_b.footnotes] + [
        (_norm(n.text), "endnote") for n in prof_b.endnotes
    ]
    if not bench:
        return 1.0
    side: Dict[str, str] = {}
    for n in prof_r.footnotes:
        side[_norm(n.text)] = "footnote"
    for n in prof_r.endnotes:
        side.setdefault(_norm(n.text), "endnote")
    correct = sum(1 for text, want in bench if side.get(text) == want)
    return round(correct / len(bench), 4)


def _running_header_suppression(prof_b: BenchmarkProfile, prof_r: BenchmarkProfile) -> float:
    """1.0 when RAWRS leaves no repeated masthead the benchmark removed.

    Leakage = repeated-line candidates present in RAWRS body but NOT in the
    benchmark (i.e. a running header the human suppressed and RAWRS did not).
    """
    r = set(prof_r.running_header_candidates)
    if not r:
        return 1.0
    leak = r - set(prof_b.running_header_candidates)
    return round(1 - len(leak) / len(r), 4)


# --------------------------------------------------------------------------- #
# diff + metrics
# --------------------------------------------------------------------------- #

def diff_profiles(prof_b: BenchmarkProfile, prof_r: BenchmarkProfile) -> Dict[str, Any]:
    """Structured per-element diff between benchmark and RAWRS profiles."""
    h_matched, h_items = _align_by_text([h.text for h in prof_b.headings], [h.text for h in prof_r.headings])
    fn_matched, fn_items = _align_by_text([n.text for n in prof_b.footnotes], [n.text for n in prof_r.footnotes])
    en_matched, en_items = _align_by_text([n.text for n in prof_b.endnotes], [n.text for n in prof_r.endnotes])
    rh_matched, rh_items = _align_by_text(prof_b.running_header_candidates, prof_r.running_header_candidates)

    return {
        "headings": {"benchmark": len(prof_b.headings), "rawrs": len(prof_r.headings), "matched": h_matched, "items": h_items},
        "front_matter": {
            "benchmark_title": prof_b.metadata.get("title"),
            "rawrs_title": prof_r.metadata.get("title"),
            "similarity": round(SequenceMatcher(None, _front_signature(prof_b), _front_signature(prof_r)).ratio(), 4),
        },
        "page_structure": {"benchmark_page_breaks": prof_b.page_breaks, "rawrs_page_breaks": prof_r.page_breaks},
        "running_headers": {"benchmark": len(prof_b.running_header_candidates), "rawrs": len(prof_r.running_header_candidates), "matched": rh_matched, "items": rh_items},
        "figures": {"benchmark": len(prof_b.figures), "rawrs": len(prof_r.figures)},
        "tables": {"benchmark": len(prof_b.tables), "rawrs": len(prof_r.tables)},
        "footnotes": {"benchmark": len(prof_b.footnotes), "rawrs": len(prof_r.footnotes), "matched": fn_matched, "items": fn_items},
        "endnotes": {"benchmark": len(prof_b.endnotes), "rawrs": len(prof_r.endnotes), "matched": en_matched, "items": en_items},
        "metadata": {"benchmark": prof_b.metadata, "rawrs": prof_r.metadata},
    }


def metrics(prof_b: BenchmarkProfile, prof_r: BenchmarkProfile) -> Dict[str, Any]:
    """Per-document metrics used as regression gates by later stages."""
    h_matched, _ = _align_by_text([h.text for h in prof_b.headings], [h.text for h in prof_r.headings])
    return {
        "heading": _pr(h_matched, len(prof_b.headings), len(prof_r.headings)),
        "page_break_fidelity": _ratio_fidelity(prof_b.page_breaks, prof_r.page_breaks),
        "front_page_similarity": round(SequenceMatcher(None, _front_signature(prof_b), _front_signature(prof_r)).ratio(), 4),
        "footnote_placement_accuracy": _note_accuracy(prof_b, prof_r),
        "running_header_suppression_accuracy": _running_header_suppression(prof_b, prof_r),
        "figure_count_fidelity": _ratio_fidelity(len(prof_b.figures), len(prof_r.figures)),
        "table_count_fidelity": _ratio_fidelity(len(prof_b.tables), len(prof_r.tables)),
    }


def _mean(values: List[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def build_report(pairs: List[Tuple[str, BenchmarkProfile, BenchmarkProfile]]) -> Dict[str, Any]:
    """Assemble the full machine-readable remediation-gap report."""
    documents: List[Dict[str, Any]] = []
    for name, prof_b, prof_r in pairs:
        documents.append({"document": name, "diff": diff_profiles(prof_b, prof_r), "metrics": metrics(prof_b, prof_r)})

    def col(path: List[str]) -> List[float]:
        out = []
        for d in documents:
            node: Any = d["metrics"]
            for k in path:
                node = node[k]
            out.append(node)
        return out

    corpus = {
        "document_count": len(documents),
        "heading_precision": _mean(col(["heading", "precision"])),
        "heading_recall": _mean(col(["heading", "recall"])),
        "heading_f1": _mean(col(["heading", "f1"])),
        "page_break_fidelity": _mean(col(["page_break_fidelity"])),
        "front_page_similarity": _mean(col(["front_page_similarity"])),
        "footnote_placement_accuracy": _mean(col(["footnote_placement_accuracy"])),
        "running_header_suppression_accuracy": _mean(col(["running_header_suppression_accuracy"])),
        "figure_count_fidelity": _mean(col(["figure_count_fidelity"])),
        "table_count_fidelity": _mean(col(["table_count_fidelity"])),
    }
    return {"schema": "rawrs.benchmark-gap-report/v1", "corpus": corpus, "documents": documents}


# --------------------------------------------------------------------------- #
# corpus runner (DOCX-vs-DOCX)
# --------------------------------------------------------------------------- #

def _stem_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", Path(name).stem.lower())


def _best_match(target: str, candidates: List[Path], threshold: float = 0.6) -> Optional[Path]:
    tk = _stem_key(target)
    best, best_ratio = None, 0.0
    for c in candidates:
        r = SequenceMatcher(None, tk, _stem_key(c.name)).ratio()
        if r > best_ratio:
            best, best_ratio = c, r
    return best if best_ratio >= threshold else None


def run_corpus(benchmark_docx_dir: Path | str, rawrs_docx_dir: Path | str, out_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """Diff every benchmark remediated DOCX against its RAWRS-generated DOCX.

    Matches files across the two directories by fuzzy stem (their names differ
    slightly). Writes the JSON report to ``out_path`` when given.
    """
    bench_dir, rawrs_dir = Path(benchmark_docx_dir), Path(rawrs_docx_dir)
    rawrs_files = sorted(rawrs_dir.glob("*.docx"))
    pairs: List[Tuple[str, BenchmarkProfile, BenchmarkProfile]] = []
    unmatched: List[str] = []

    for bench_docx in sorted(bench_dir.glob("*.docx")):
        rawrs_docx = _best_match(bench_docx.name, rawrs_files)
        if rawrs_docx is None:
            unmatched.append(bench_docx.name)
            continue
        pairs.append((bench_docx.stem, profile_from_docx(bench_docx), profile_from_docx(rawrs_docx)))

    report = build_report(pairs)
    report["unmatched_benchmark_documents"] = unmatched
    if out_path is not None:
        Path(out_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
