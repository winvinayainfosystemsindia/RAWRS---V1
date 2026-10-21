"""Everything RAWRS has learned from remediators, in one report.

Combines the two signals of this package:

* the in-workspace correction log of every persisted document
  (``outputs/documents/*.json``), summarised by ``decisions.summarize``;
* every post-export review (``outputs/learning/*/review.json``), i.e. what was
  changed in Word after RAWRS's DOCX left the building.

…and ranks them into ``priorities``: plain-language statements of where human
time is still going, each with its count and evidence. ``iter_dataset``
exports the same material as JSON Lines - labelled examples for whoever tunes
a detector or fine-tunes a model next (RAWRS's own alt-text model included).
"""

from __future__ import annotations

import threading
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Dict, Iterator, List, Tuple

import pydantic_core
from loguru import logger
from pydantic import ValidationError

from src.learning import store
from src.learning.decisions import is_human_edit, outcome, summarize
from src.models.correction import CorrectionRecord

TOP_PRIORITIES = 10
TOP_SUBSTITUTIONS = 15
MAX_SUBSTITUTION_WORDS = 3
ACTIONABLE = frozenset({"candidate_auto_apply", "candidate_retire", "improve_proposed_value", "revisit_auto_apply"})

CATEGORY_PHRASE = {
    "HEADING_LEVEL_CHANGED": "changed a heading's level",
    "PROMOTED_TO_HEADING": "turned body text into a heading",
    "DEMOTED_FROM_HEADING": "turned a heading back into body text",
    "STYLE_CHANGED": "restyled a paragraph",
    "TEXT_EDITED": "edited text",
    "CONTENT_ADDED": "added text RAWRS did not produce",
    "CONTENT_REMOVED": "deleted text RAWRS produced",
    "ALT_TEXT_WRITTEN": "wrote alt text that was missing",
    "ALT_TEXT_REWRITTEN": "rewrote RAWRS's alt text",
    "MARKED_DECORATIVE": "marked an image decorative",
    "UNMARKED_DECORATIVE": "un-marked an image RAWRS called decorative",
    "IMAGE_ADDED": "added an image",
    "IMAGE_REMOVED": "removed an image",
    "TABLE_HEADER_CHANGED": "fixed a table's header row",
    "TABLE_STRUCTURE_CHANGED": "restructured a table",
    "TABLE_CONTENT_EDITED": "edited table cells",
    "TABLE_ADDED": "added a table",
    "TABLE_REMOVED": "removed a table",
    "METADATA_CHANGED": "changed document properties",
}


class _DecisionIndex:
    """Correction logs of every persisted document, re-read only when a file
    changes. A cold scan of ~1,400 sidecars (135 MB) takes ~4 s with
    pydantic_core's parser (stdlib json: ~40 s); a warm one is a stat per file.

    ponytail: in-memory only, so the first request after a restart pays the
    cold scan; persist the index when that starts to hurt.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: Dict[Path, Tuple[int, int, str, List[CorrectionRecord]]] = {}

    def jobs(self, documents_dir: Path) -> List[Tuple[str, str, List[CorrectionRecord]]]:
        with self._lock:
            seen = set()
            for path in documents_dir.glob("*.json") if documents_dir.is_dir() else ():
                try:
                    stat = path.stat()
                except OSError:
                    continue
                seen.add(path)
                cached = self._entries.get(path)
                if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
                    continue
                filename, records = _read_corrections(path)
                self._entries[path] = (stat.st_mtime_ns, stat.st_size, filename, records)
            for gone in set(self._entries) - seen:
                del self._entries[gone]
            return [(path.stem, entry[2], entry[3]) for path, entry in sorted(self._entries.items())]


def _read_corrections(path: Path) -> Tuple[str, List[CorrectionRecord]]:
    try:
        raw = pydantic_core.from_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        logger.warning("Skipping unreadable document sidecar {}: {}", path.name, exc)
        return "", []
    document = raw.get("document") if isinstance(raw, dict) else None
    if not isinstance(document, dict):
        return "", []
    filename = (document.get("metadata") or {}).get("filename") or ""
    records = []
    for item in document.get("corrections") or []:
        try:
            records.append(CorrectionRecord.model_validate(item))
        except ValidationError:
            continue  # one malformed record never hides the rest of the log
    return filename, records


_index = _DecisionIndex()


def _post_export(reviews: List[Tuple[str, dict]]) -> Dict[str, object]:
    counts: Counter = Counter()
    documents: Dict[Tuple[str, str], set] = defaultdict(set)
    substitutions: Counter = Counter()
    substitution_docs: Dict[Tuple[str, str], set] = defaultdict(set)
    fixed: Counter = Counter()
    regressed: Counter = Counter()
    requirements: Dict[str, str] = {}
    kept_shares: List[float] = []

    for job_id, review in reviews:
        diff = review.get("diff") or {}
        share = (diff.get("summary") or {}).get("kept_share")
        if share is not None:
            kept_shares.append(share)
        for edit in diff.get("edits") or []:
            key = (edit.get("category", ""), edit.get("object_type", ""))
            counts[key] += 1
            documents[key].add(job_id)
            for change in edit.get("word_changes") or []:
                before, after = change.get("from", ""), change.get("to", "")
                if (change.get("op") == "replace" and before and after
                        and len(before.split()) <= MAX_SUBSTITUTION_WORDS
                        and len(after.split()) <= MAX_SUBSTITUTION_WORDS):
                    substitutions[(before, after)] += 1
                    substitution_docs[(before, after)].add(job_id)
        checklist = review.get("checklist") or {}
        for bucket, counter in (("fixed_by_remediator", fixed), ("regressed_by_remediator", regressed)):
            for item in checklist.get(bucket) or []:
                counter[item["item_id"]] += 1
                requirements[item["item_id"]] = item.get("requirement", "")

    return {
        "documents": len(reviews),
        "mean_kept_share": round(mean(kept_shares), 4) if kept_shares else None,
        "categories": [
            {"category": cat, "object_type": obj, "count": n, "documents": len(documents[(cat, obj)]),
             "phrase": CATEGORY_PHRASE.get(cat, cat.lower())}
            for (cat, obj), n in counts.most_common()
        ],
        "word_substitutions": [
            {"from": before, "to": after, "count": n, "documents": len(substitution_docs[(before, after)])}
            for (before, after), n in substitutions.most_common(TOP_SUBSTITUTIONS)
        ],
        "checklist_fixed_by_remediators": [
            {"item_id": item, "requirement": requirements[item], "documents": n} for item, n in fixed.most_common()
        ],
        "checklist_regressed_by_remediators": [
            {"item_id": item, "requirement": requirements[item], "documents": n} for item, n in regressed.most_common()
        ],
    }


def _priorities(decisions: Dict, post_export: Dict) -> List[Dict[str, object]]:
    found: List[Dict[str, object]] = []
    for category in post_export["categories"]:
        found.append({
            "source": "after_export",
            "weight": category["count"],
            "message": f"After export, remediators {category['phrase']} {category['count']} times "
                       f"in {category['documents']} document(s).",
        })
    for item in post_export["checklist_fixed_by_remediators"]:
        found.append({
            "source": "checklist",
            "weight": item["documents"],
            "message": f"Checklist item {item['item_id']} failed on RAWRS's export and was fixed by hand "
                       f"in {item['documents']} document(s): {item['requirement']}",
        })
    for edit in decisions["human_edits"]:
        change = edit["top_changes"][0] if edit["top_changes"] else None
        detail = f" Most common: {change['from']} → {change['to']} ({change['count']}×)." if change else ""
        found.append({
            "source": "reviewer_edits",
            "weight": edit["count"],
            "message": f"Reviewers made {edit['count']} {edit['reason_code']} edit(s) to {edit['object_type']} "
                       f"in {edit['documents']} document(s) that RAWRS never proposed.{detail}",
        })
    for rule in decisions["rules"]:
        if rule["recommendation"] in ACTIONABLE:
            found.append({
                "source": "proposal_outcomes",
                "weight": rule["decided"] + rule["auto_applied"],
                "message": f"{rule['reason_code']} ({rule['object_type']}): {rule['rationale']}",
                "recommendation": rule["recommendation"],
            })
    found.sort(key=lambda p: -int(p["weight"]))
    return found[:TOP_PRIORITIES]


def build_insights(documents_dir: Path, output_root: Path) -> Dict[str, object]:
    jobs = _index.jobs(documents_dir)
    decisions = summarize((job_id, records) for job_id, _, records in jobs)
    reviews = list(store.iter_reviews(output_root))
    post_export = _post_export(reviews)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decisions": decisions,
        "after_export": post_export,
        "priorities": _priorities(decisions, post_export),
        "reviewed_documents": [
            {"job_id": job_id, "filename": review.get("filename", ""), "reviewed_at": review.get("reviewed_at"),
             "kept_share": ((review.get("diff") or {}).get("summary") or {}).get("kept_share"),
             "edits": ((review.get("diff") or {}).get("summary") or {}).get("edits", 0)}
            for job_id, review in reviews
        ],
    }


def iter_dataset(documents_dir: Path, output_root: Path) -> Iterator[Dict[str, object]]:
    """Labelled examples, one dict per JSON line."""
    for job_id, filename, records in _index.jobs(documents_dir):
        for record in records:
            human = is_human_edit(record)
            label = None if human else outcome(record)
            if label == "pending":
                continue  # nobody has judged it yet: not a label
            yield {
                "kind": "reviewer_edit" if human else "proposal_decision",
                "job_id": job_id,
                "filename": filename,
                "object_type": record.object_type,
                "reason_code": record.reason_code,
                "field": record.field,
                "provider": record.provider,
                "confidence": record.confidence,
                "evidence": [asdict(item) for item in record.evidence_items],
                "original_value": record.original_value,
                "proposed_value": record.proposed_value,
                "outcome": label,
            }
    for job_id, review in store.iter_reviews(output_root):
        for edit in (review.get("diff") or {}).get("edits") or []:
            yield {"kind": "post_export_edit", "job_id": job_id, "filename": review.get("filename", ""), **edit}
