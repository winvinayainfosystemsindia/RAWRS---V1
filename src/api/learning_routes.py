"""Learning endpoints: the remediator's finished DOCX, and what RAWRS learned.

POST   /api/documents/{job_id}/final-docx   upload the DOCX finished in Word; diff + checklist
GET    /api/documents/{job_id}/final-docx   that comparison, as stored
DELETE /api/documents/{job_id}/final-docx   forget it
GET    /api/learning/insights               everything learned, across documents
GET    /api/learning/dataset                the same as labelled JSON Lines

Read-only with respect to the Document: nothing here changes a document, an
export or the pipeline (docs/LEARNING_LOOP.md).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from loguru import logger

from src.api.document_store import DOCUMENTS_DIR
from src.api.routes import _ensure_current_export, _require_job
from src.learning import store
from src.learning.docx_diff import diff_docx
from src.learning.insights import build_insights, iter_dataset
from src.pipeline.phase1_pipeline import DEFAULT_OUTPUT_ROOT

router = APIRouter(prefix="/api")

_NEEDS_ATTENTION = frozenset({"fail", "warn"})


def _checklist_delta(exported: Dict, final: Dict) -> Dict:
    """Which checklist items the remediator fixed, and which they broke."""
    before = {r["item_id"]: r for r in exported["results"]}
    after = {r["item_id"]: r for r in final["results"]}

    def _item(item_id: str) -> Dict:
        return {"item_id": item_id, "requirement": after[item_id]["requirement"],
                "before": before[item_id]["status"], "after": after[item_id]["status"],
                "evidence": after[item_id]["evidence"]}

    shared = [item_id for item_id in after if item_id in before]
    return {
        "exported": {"passed": exported["passed"], "summary": exported["summary"]},
        "final": {"passed": final["passed"], "summary": final["summary"]},
        "fixed_by_remediator": [
            _item(i) for i in shared
            if before[i]["status"] in _NEEDS_ATTENTION and after[i]["status"] == "pass"
        ],
        "regressed_by_remediator": [
            _item(i) for i in shared
            if before[i]["status"] == "pass" and after[i]["status"] in _NEEDS_ATTENTION
        ],
    }


def _audit(docx_path: Path, document) -> Optional[Dict]:
    from src.validation.checklist_audit import audit_docx

    try:
        return audit_docx(
            docx_path, document.source_pdf_path if document else None,
            expected_pages=len(document.pages) if document else None,
            equations=document.equations if document else None,
        ).to_dict()
    except Exception as exc:  # the diff is still worth returning without it
        logger.warning("Checklist audit of {} failed: {}", docx_path.name, exc)
        return None


@router.post("/documents/{job_id}/final-docx")
def upload_final_docx(job_id: str, file: UploadFile = File(...)) -> Dict:
    """Compare the remediator's finished DOCX with what RAWRS exported."""
    job = _require_job(job_id)
    if job.result is None:
        raise HTTPException(status_code=409, detail="This document has not finished processing.")
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only .docx files are accepted.")

    data = file.file.read(store.MAX_DOCX_BYTES + 1)
    try:
        final_path = store.save_final(DEFAULT_OUTPUT_ROOT, job_id, data)
    except store.InvalidDocx as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    baseline = store.exported_snapshot(DEFAULT_OUTPUT_ROOT, job_id)
    baseline_kind = "downloaded_copy"
    if baseline is None:
        baseline, baseline_kind = _ensure_current_export(job, "docx"), "current_export"
    if baseline is None or not Path(baseline).is_file():
        raise HTTPException(status_code=404, detail="RAWRS has no exported DOCX for this document to compare with.")

    try:
        diff = diff_docx(baseline, final_path)
    except Exception as exc:
        logger.error("Could not compare final DOCX for job {}: {}", job_id, exc)
        raise HTTPException(status_code=400, detail="The uploaded document could not be read as a Word file.") from exc

    document = job.result.document
    exported_audit, final_audit = _audit(Path(baseline), document), _audit(final_path, document)
    review = {
        "job_id": job_id,
        "filename": job.filename,
        "final_filename": file.filename,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "baseline": baseline_kind,
        "diff": diff,
        "checklist": _checklist_delta(exported_audit, final_audit) if exported_audit and final_audit else None,
    }
    return store.save_review(DEFAULT_OUTPUT_ROOT, job_id, review)


@router.get("/documents/{job_id}/final-docx")
def get_final_docx_review(job_id: str) -> Dict:
    _require_job(job_id)
    review = store.load_review(DEFAULT_OUTPUT_ROOT, job_id)
    if review is None:
        raise HTTPException(status_code=404, detail="No finished DOCX has been uploaded for this document.")
    return review


@router.delete("/documents/{job_id}/final-docx", status_code=204)
def delete_final_docx_review(job_id: str) -> None:
    _require_job(job_id)
    if not store.delete_review(DEFAULT_OUTPUT_ROOT, job_id):
        raise HTTPException(status_code=404, detail="No finished DOCX has been uploaded for this document.")


@router.get("/learning/insights")
def get_learning_insights() -> Dict:
    return build_insights(DOCUMENTS_DIR, DEFAULT_OUTPUT_ROOT)


@router.get("/learning/dataset")
def download_learning_dataset() -> StreamingResponse:
    lines = (
        json.dumps(row, ensure_ascii=False, default=str) + "\n"
        for row in iter_dataset(DOCUMENTS_DIR, DEFAULT_OUTPUT_ROOT)
    )
    return StreamingResponse(
        lines,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="rawrs-learning-dataset.jsonl"'},
    )
