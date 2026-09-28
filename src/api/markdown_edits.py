"""A reviewer's hand edits to the Markdown, and the DOCX built from them.

Normally both deliverables are projections of the Document model, and every
reviewer decision goes through the correction rail. Editing the Markdown by
hand is the last-mile exception: the reviewer is fixing the output itself
("this sentence reads badly", "move this line"), so once edits are saved the
edited Markdown *is* the Markdown deliverable, and the DOCX is rendered from
it through docx_generator's markdown path - the same path hand-written
markdown has always taken.

Edits are stored beside the outputs as ``edits/<job>.json``:
``{"content": ..., "base_version": <document version edited>, "saved_at": ...}``.
``base_version`` lets the UI say when corrections were accepted after the
edit, since those changed the model but not the edited text. Discarding the
edit file returns both deliverables to the model's own projection.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

# A textbook chapter's Markdown is ~100 KB; this refuses anything absurd.
MAX_MARKDOWN_BYTES = 5_000_000


def edits_dir(output_root: Path) -> Path:
    return output_root / "edits"


def _edit_file(output_root: Path, job_id: str) -> Path:
    return edits_dir(output_root) / f"{job_id}.json"


def load_edit(output_root: Path, job_id: str) -> Optional[dict]:
    path = _edit_file(output_root, job_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.error("Unreadable Markdown edit for job {}: {}", job_id, exc)
        return None


def save_edit(output_root: Path, job_id: str, content: str, base_version: Optional[int]) -> dict:
    record = {
        "content": content,
        "base_version": base_version,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _edit_file(output_root, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic: a reader never sees half an edit
    return record


def discard_edit(output_root: Path, job_id: str) -> bool:
    removed = False
    for path in (
        _edit_file(output_root, job_id),
        edits_dir(output_root) / f"{job_id}.md",
        edits_dir(output_root) / f"{job_id}.docx",
    ):
        if path.is_file():
            path.unlink()
            removed = True
    return removed


def render_docx_from_markdown(document, markdown: str, output_path: Path) -> Path:
    """The DOCX a reader would get for ``markdown``.

    The model's objects are deliberately *not* handed to the generator: it
    prefers them over markdown lines wherever it can (prose, tables,
    headings), which is right for generated markdown and exactly wrong for
    edited markdown - the reviewer's words must win. Only what the markdown
    cannot carry comes from the model: properties (title, author, language),
    each image file's identity, and whether a note is a footnote or an
    endnote. Copies, so rendering never writes back into the live document.
    """
    from src.docx.docx_generator import generate_docx
    from src.models.contracts import Document

    shell = Document(
        source_pdf_path=document.source_pdf_path,
        metadata=document.metadata.model_copy(),
        images=[image.model_copy(deep=True) for image in document.images],
        footnotes=[note.model_copy(deep=True) for note in document.footnotes],
    )
    return generate_docx(shell, markdown, output_path=output_path)


def edited_export(output_root: Path, job_id: str, document, kind: str, edit: dict) -> Optional[Path]:
    """The edited Markdown, or the DOCX rendered from it, rebuilt only when the
    edit is newer than the cached file."""
    edit_path = _edit_file(output_root, job_id)
    target = edits_dir(output_root) / f"{job_id}.{'md' if kind == 'markdown' else 'docx'}"
    if target.is_file() and target.stat().st_mtime >= edit_path.stat().st_mtime:
        return target
    try:
        if kind == "markdown":
            target.write_bytes(edit["content"].encode("utf-8"))  # byte-exact: no CRLF translation
        else:
            if document is None:
                return None
            with tempfile.TemporaryDirectory() as scratch:
                built = render_docx_from_markdown(document, edit["content"], Path(scratch) / "out.docx")
                target.write_bytes(built.read_bytes())
    except Exception as exc:
        logger.error("Could not build the edited {} for job {}: {}", kind, job_id, exc)
        return target if target.is_file() else None
    return target
