"""W-1 (Group A) — every reviewer-visible mutation enters the rail.

The architecture's central claim is that a reviewer decision is a
reversible, auditable transaction. Before this milestone five HTTP
handlers falsified it by mutating the Semantic Document directly. Group A
converts three of them — images, tables and footnotes — each of which
already had a registered verifier with a working ``apply()``/``revert()``;
only the endpoints bypassed it.

Scope is stated honestly in the last class: reading order and metadata
still bypass the rail and are covered here as *measured, declared*
violations, not as passing behaviour.
"""

import json
import tempfile
from pathlib import Path
from typing import Any, List

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.models.correction import APPLIED_STATUSES, CorrectionStatus

client = TestClient(app)
TMP_DIR = tempfile.mkdtemp(prefix='w1-groupb-')

SAMPLE_PDF = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "benchmark"
    / "pdfs"
    / "7.brinkman-learner-centred-education-reform-india-missing-beliefs.pdf"
)


def _document(job_id: str):
    from src.api.routes import _require_document

    return _require_document(job_id)


@pytest.fixture(scope="module")
def job_id() -> str:
    """Upload one corpus PDF and wait for the pipeline to finish.

    Processing is asynchronous, and _require_document() answers 409 until
    it completes — so every mutation below acts on a real, fully-built
    Semantic Document rather than a half-populated one.
    """
    import time

    with SAMPLE_PDF.open("rb") as handle:
        response = client.post(
            "/api/documents", files={"file": (SAMPLE_PDF.name, handle, "application/pdf")}
        )
    assert response.status_code in (200, 201), response.text
    job = response.json()["job_id"]

    deadline = time.time() + 300
    while time.time() < deadline:
        status = client.get(f"/api/documents/{job}").json().get("status")
        if status not in ("queued", "processing"):
            break
        time.sleep(1)
    else:  # pragma: no cover - only on a pathologically slow machine
        pytest.skip("document did not finish processing in time")
    return job


def _corrections(job_id: str, object_type: str) -> List[Any]:
    return [c for c in _document(job_id).corrections if c.object_type == object_type]


class TestTableMutationsEnterTheRail:
    def test_creation_is_a_correction_and_undo_removes_the_table(self, job_id: str) -> None:
        before = len(_corrections(job_id, "table"))
        created = client.post(f"/api/documents/{job_id}/tables", json={}).json()
        table_id = created["table_id"]

        corrections = _corrections(job_id, "table")
        assert len(corrections) == before + 1
        correction = corrections[-1]
        assert correction.field == "table_state"
        assert correction.reason_code == "TABLE_CREATED_BY_REVIEWER"
        assert correction.original_value == ""  # did not exist
        assert correction.status in APPLIED_STATUSES
        assert any(t.table_id == table_id for t in _document(job_id).tables)

        undo = client.patch(
            f"/api/documents/{job_id}/corrections/{correction.correction_id}",
            json={"action": "undo"},
        )
        assert undo.status_code == 200
        assert not any(t.table_id == table_id for t in _document(job_id).tables)

    def test_an_edit_is_one_correction_and_undo_restores_the_caption(self, job_id: str) -> None:
        table_id = client.post(f"/api/documents/{job_id}/tables", json={}).json()["table_id"]
        client.patch(f"/api/documents/{job_id}/tables/{table_id}", json={"caption": "First caption"})
        client.patch(
            f"/api/documents/{job_id}/tables/{table_id}", json={"caption": "Second caption"}
        )

        table = next(t for t in _document(job_id).tables if t.table_id == table_id)
        assert table.caption == "Second caption"

        last = _corrections(job_id, "table")[-1]
        assert last.reason_code == "TABLE_EDITED_BY_REVIEWER"
        client.patch(
            f"/api/documents/{job_id}/corrections/{last.correction_id}", json={"action": "undo"}
        )

        table = next(t for t in _document(job_id).tables if t.table_id == table_id)
        assert table.caption == "First caption"  # the previous decision, not the original

    def test_deletion_is_a_correction_and_undo_restores_the_table(self, job_id: str) -> None:
        table_id = client.post(f"/api/documents/{job_id}/tables", json={}).json()["table_id"]
        client.patch(f"/api/documents/{job_id}/tables/{table_id}", json={"caption": "Doomed"})
        client.delete(f"/api/documents/{job_id}/tables/{table_id}")

        assert not any(t.table_id == table_id for t in _document(job_id).tables)
        correction = _corrections(job_id, "table")[-1]
        assert correction.reason_code == "TABLE_DELETED_BY_REVIEWER"
        assert correction.proposed_value == ""

        client.patch(
            f"/api/documents/{job_id}/corrections/{correction.correction_id}",
            json={"action": "undo"},
        )
        restored = next(t for t in _document(job_id).tables if t.table_id == table_id)
        assert restored.caption == "Doomed"  # content came back, not just the row

    def test_deleting_a_missing_table_records_nothing(self, job_id: str) -> None:
        before = len(_corrections(job_id, "table"))
        response = client.delete(f"/api/documents/{job_id}/tables/table-does-not-exist")

        assert response.status_code == 404
        assert len(_corrections(job_id, "table")) == before


class TestImageMutationsEnterTheRail:
    def _first_image_id(self, job_id: str):
        images = _document(job_id).images
        return images[0].image_id if images else None

    def test_alt_text_edit_is_a_correction_and_undo_restores_it(self, job_id: str) -> None:
        image_id = self._first_image_id(job_id)
        if image_id is None:
            pytest.skip("this corpus document extracted no images")

        client.patch(
            f"/api/documents/{job_id}/images/{image_id}",
            json={"action": "edit", "alt_text": "A reviewer's alt text"},
        )
        image = next(i for i in _document(job_id).images if i.image_id == image_id)
        assert image.figure.alt_text == "A reviewer's alt text"

        correction = _corrections(job_id, "figure")[-1]
        assert correction.field == "alt_text_review"
        assert correction.reason_code == "FIGURE_ALT_TEXT_REVIEWED"

        client.patch(
            f"/api/documents/{job_id}/corrections/{correction.correction_id}",
            json={"action": "undo"},
        )
        image = next(i for i in _document(job_id).images if i.image_id == image_id)
        assert image.figure.alt_text != "A reviewer's alt text"

    def test_a_bulk_action_is_one_transaction(self, job_id: str) -> None:
        image_ids = [i.image_id for i in _document(job_id).images[:3]]
        if len(image_ids) < 2:
            pytest.skip("needs at least two images")

        before = len(_corrections(job_id, "figure"))
        client.post(
            f"/api/documents/{job_id}/images/bulk-action",
            json={"image_ids": image_ids, "action": "mark_decorative"},
        )

        new = _corrections(job_id, "figure")[before:]
        assert len(new) == len(image_ids)
        # W-3: one judgement, one transaction — so undoing the decision
        # undoes all of it, not one image at a time.
        transaction_ids = {c.transaction_id for c in new}
        assert len(transaction_ids) == 1
        assert None not in transaction_ids

    def test_the_ai_suggestion_path_stays_off_the_rail(self, job_id: str) -> None:
        # generate-alt-text writes only ai_* fields and a status; it
        # proposes, it does not decide, so it correctly produces no
        # correction. (No AI call is made here — the classification is
        # what this pins.)
        from src.api import routes

        source = Path(routes.__file__).read_text(encoding="utf-8")
        marker = source.index("def generate_image_alt_text")
        body = source[marker : marker + 3000]
        assert "image.figure.ai_description" in body
        assert "_record_reviewer_edit" not in body


class TestFootnoteMutationsEnterTheRail:
    def _first_note_id(self, job_id: str):
        notes = _document(job_id).footnotes
        return notes[0].footnote_id if notes else None

    def test_body_edit_is_a_correction_and_undo_restores_the_previous_body(
        self, job_id: str
    ) -> None:
        note_id = self._first_note_id(job_id)
        if note_id is None:
            pytest.skip("this corpus document detected no notes")

        original = next(n for n in _document(job_id).footnotes if n.footnote_id == note_id).body
        client.patch(f"/api/documents/{job_id}/footnotes/{note_id}", json={"body": "Edited body."})

        note = next(n for n in _document(job_id).footnotes if n.footnote_id == note_id)
        assert note.body == "Edited body."

        correction = _corrections(job_id, "footnote")[-1]
        assert correction.field == "body_edit"
        assert correction.reason_code == "FOOTNOTE_BODY_EDITED_BY_REVIEWER"
        assert correction.original_value == original

        client.patch(
            f"/api/documents/{job_id}/corrections/{correction.correction_id}",
            json={"action": "undo"},
        )
        note = next(n for n in _document(job_id).footnotes if n.footnote_id == note_id)
        assert note.body == original


class TestRailMechanics:
    def test_every_reviewer_correction_bumps_the_document_version(self, job_id: str) -> None:
        before = _document(job_id).version
        client.post(f"/api/documents/{job_id}/tables", json={})
        assert _document(job_id).version > before

    def test_a_reviewer_edit_is_recorded_as_terminal(self, job_id: str) -> None:
        # EDITED is terminal, so REVIEW_001 does not block export on a
        # decision the reviewer has already made.
        client.post(f"/api/documents/{job_id}/tables", json={})
        assert _corrections(job_id, "table")[-1].status is CorrectionStatus.EDITED

    def test_repeated_apply_does_not_duplicate_state(self, job_id: str) -> None:
        from src.verification.engine import engine

        table_id = client.post(f"/api/documents/{job_id}/tables", json={}).json()["table_id"]
        document = _document(job_id)
        correction = _corrections(job_id, "table")[-1]

        engine.apply_correction(document, correction)
        engine.apply_correction(document, correction)

        assert len([t for t in document.tables if t.table_id == table_id]) == 1

    def test_undo_leaves_the_audit_row_behind(self, job_id: str) -> None:
        table_id = client.post(f"/api/documents/{job_id}/tables", json={}).json()["table_id"]
        correction = _corrections(job_id, "table")[-1]
        client.patch(
            f"/api/documents/{job_id}/corrections/{correction.correction_id}",
            json={"action": "undo"},
        )

        # The decision is reverted, but the row survives — an undo does not
        # rewrite history.
        assert correction.correction_id in {c.correction_id for c in _document(job_id).corrections}
        assert not any(t.table_id == table_id for t in _document(job_id).tables)


class TestScopeIsStatedHonestly:
    """Group B is out of scope, and these pin that it is still broken
    rather than letting the milestone imply a completeness it lacks."""

    def test_reading_order_is_now_on_the_rail(self, job_id: str) -> None:
        # W-1 Group B closed this. The assertion is inverted deliberately
        # rather than deleted: it was the pin that proved the gap, and it
        # is now the pin that proves the gap is shut.
        from src.api import routes

        source = Path(routes.__file__).read_text(encoding="utf-8")
        marker = source.index("def update_reading_order")
        body = source[marker : marker + 4000]
        assert "_record_reviewer_edit" in body

    def test_metadata_is_now_on_the_rail(self, job_id: str) -> None:
        from src.api import routes

        source = Path(routes.__file__).read_text(encoding="utf-8")
        marker = source.index("def update_metadata")
        body = source[marker : marker + 2500]
        assert "_record_reviewer_edit" in body

    def test_administrative_state_is_not_forced_onto_the_rail(self, job_id: str) -> None:
        # A validation issue's triage status changes no semantic content
        # and no projection, so it correctly produces no CorrectionRecord.
        from src.api import routes

        source = Path(routes.__file__).read_text(encoding="utf-8")
        marker = source.index("def review_validation_issue")
        body = source[marker : marker + 2000]
        assert "issue.status" in body
        assert "_record_reviewer_edit" not in body


class TestReadingOrderEntersTheRail:
    """W-1 Group B. build_content_stream reads corrected_order in
    preference to order, so a reorder rewrites both projections — which is
    exactly why it must be one auditable, reversible decision."""

    def _page_with_blocks(self, job_id: str):
        document = _document(job_id)
        for page in document.pages:
            blocks = [b for b in document.blocks if b.page_number == page.page_number]
            if len(blocks) >= 3:
                return page.page_number, blocks
        pytest.skip("no page with at least three blocks")

    def test_a_reorder_is_one_correction_carrying_the_whole_page(self, job_id: str) -> None:
        page_num, blocks = self._page_with_blocks(job_id)
        before = len(_corrections(job_id, "reading_order"))
        sequence = [b.order for b in blocks][::-1]

        response = client.patch(
            f"/api/documents/{job_id}/pages/{page_num}/reading-order",
            json={"action": "reorder", "block_sequence": sequence},
        )
        assert response.status_code == 200

        corrections = _corrections(job_id, "reading_order")
        assert len(corrections) == before + 1  # one decision, not one per block
        correction = corrections[-1]
        assert correction.field == "block_order"
        assert correction.reason_code == "READING_ORDER_CORRECTED_BY_REVIEWER"
        assert correction.object_id == str(page_num)

        payload = json.loads(correction.proposed_value)
        assert payload["status"] == "corrected"
        # Keyed by stable block identity, never by text.
        assert set(payload["order"]) == {b.block_id for b in blocks}

    def test_the_corrected_order_reaches_the_content_stream(self, job_id: str) -> None:
        from src.models.content_stream import ContentKind
        from src.structure.content_stream import build_content_stream

        page_num, blocks = self._page_with_blocks(job_id)
        reversed_ids = [b.block_id for b in blocks][::-1]
        client.patch(
            f"/api/documents/{job_id}/pages/{page_num}/reading-order",
            json={"action": "reorder", "block_sequence": [b.order for b in blocks][::-1]},
        )

        stream = build_content_stream(_document(job_id))
        body_ids = [
            n.object_id
            for n in stream.nodes
            if n.kind is ContentKind.BODY_LINE and n.page_number == page_num
        ]
        # Blocks another object absorbed (front matter, note bodies) are
        # not body lines, so compare against the ones that are - the claim
        # is about order, not membership.
        expected = [bid for bid in reversed_ids if bid in set(body_ids)]
        assert body_ids == expected

    def test_undo_restores_the_exact_previous_override_map(self, job_id: str) -> None:
        page_num, blocks = self._page_with_blocks(job_id)
        # Two successive decisions, so undo must land on the first one's
        # state rather than on "no override at all".
        client.patch(
            f"/api/documents/{job_id}/pages/{page_num}/reading-order",
            json={"action": "reorder", "block_sequence": [b.order for b in blocks]},
        )
        first = {
            b.block_id: b.corrected_order
            for b in _document(job_id).blocks
            if b.page_number == page_num
        }
        client.patch(
            f"/api/documents/{job_id}/pages/{page_num}/reading-order",
            json={"action": "reorder", "block_sequence": [b.order for b in blocks][::-1]},
        )
        correction = _corrections(job_id, "reading_order")[-1]

        client.patch(
            f"/api/documents/{job_id}/corrections/{correction.correction_id}",
            json={"action": "undo"},
        )

        after = {
            b.block_id: b.corrected_order
            for b in _document(job_id).blocks
            if b.page_number == page_num
        }
        assert after == first

    def test_repeated_apply_is_safe(self, job_id: str) -> None:
        from src.verification.engine import engine

        page_num, blocks = self._page_with_blocks(job_id)
        client.patch(
            f"/api/documents/{job_id}/pages/{page_num}/reading-order",
            json={"action": "reorder", "block_sequence": [b.order for b in blocks][::-1]},
        )
        document = _document(job_id)
        correction = _corrections(job_id, "reading_order")[-1]
        once = {b.block_id: b.corrected_order for b in document.blocks}

        engine.apply_correction(document, correction)
        engine.apply_correction(document, correction)

        assert {b.block_id: b.corrected_order for b in document.blocks} == once

    def test_a_reorder_bumps_the_document_version(self, job_id: str) -> None:
        page_num, blocks = self._page_with_blocks(job_id)
        before = _document(job_id).version
        client.patch(
            f"/api/documents/{job_id}/pages/{page_num}/reading-order",
            json={"action": "reorder", "block_sequence": [b.order for b in blocks][::-1]},
        )
        assert _document(job_id).version > before

    def test_approving_an_order_is_not_a_correction(self, job_id: str) -> None:
        # It sets reading_order_status and changes no ordering, and that
        # field is read by no projection and no validation rule — review
        # state, not document content.
        page_num, _ = self._page_with_blocks(job_id)
        before = len(_corrections(job_id, "reading_order"))

        response = client.patch(
            f"/api/documents/{job_id}/pages/{page_num}/reading-order",
            json={"action": "approve"},
        )

        assert response.status_code == 200
        assert len(_corrections(job_id, "reading_order")) == before


class TestMetadataEntersTheRail:
    """One document-level owner; one request is one decision."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("language", "fr-FR"),
            ("title", "A Reviewed Title"),
            ("author", "A. Reviewer"),
            ("subject", "A Reviewed Subject"),
        ],
    )
    def test_each_editable_field_enters_the_rail_and_undoes(
        self, job_id: str, field: str, value: str
    ) -> None:
        original = getattr(_document(job_id).metadata, field)
        response = client.patch(f"/api/documents/{job_id}/metadata", json={field: value})
        assert response.status_code == 200
        assert getattr(_document(job_id).metadata, field) == value

        correction = _corrections(job_id, "metadata")[-1]
        assert correction.field == "document_metadata"
        assert correction.reason_code == "DOCUMENT_METADATA_EDITED_BY_REVIEWER"
        assert correction.object_id is None  # the document is the object

        client.patch(
            f"/api/documents/{job_id}/corrections/{correction.correction_id}",
            json={"action": "undo"},
        )
        assert getattr(_document(job_id).metadata, field) == original

    def test_a_multi_field_edit_is_one_transaction(self, job_id: str) -> None:
        before = len(_corrections(job_id, "metadata"))
        client.patch(
            f"/api/documents/{job_id}/metadata",
            json={"language": "de-DE", "title": "Both At Once", "author": "Two Fields"},
        )

        corrections = _corrections(job_id, "metadata")
        assert len(corrections) == before + 1  # one request, one decision
        payload = json.loads(corrections[-1].proposed_value)
        assert payload["language"] == "de-DE"
        assert payload["title"] == "Both At Once"
        assert payload["author"] == "Two Fields"

    def test_undo_restores_every_field_of_the_prior_state(self, job_id: str) -> None:
        client.patch(
            f"/api/documents/{job_id}/metadata",
            json={"language": "en-GB", "title": "First State"},
        )
        first = {
            f: getattr(_document(job_id).metadata, f)
            for f in ("language", "title", "author", "subject")
        }
        client.patch(
            f"/api/documents/{job_id}/metadata",
            json={"language": "es-ES", "title": "Second State"},
        )
        correction = _corrections(job_id, "metadata")[-1]

        client.patch(
            f"/api/documents/{job_id}/corrections/{correction.correction_id}",
            json={"action": "undo"},
        )

        after = {
            f: getattr(_document(job_id).metadata, f)
            for f in ("language", "title", "author", "subject")
        }
        assert after == first

    def test_a_metadata_edit_bumps_the_document_version(self, job_id: str) -> None:
        before = _document(job_id).version
        client.patch(f"/api/documents/{job_id}/metadata", json={"subject": "Version Check"})
        assert _document(job_id).version > before

    def test_derived_metadata_is_not_carried_by_the_correction(self, job_id: str) -> None:
        # filename/page_count/image_count are set by the pipeline, not
        # decided by anyone, so a correction must not claim them.
        client.patch(f"/api/documents/{job_id}/metadata", json={"title": "Payload Check"})
        payload = json.loads(_corrections(job_id, "metadata")[-1].proposed_value)

        assert set(payload) == {"language", "title", "author", "subject"}

    def test_the_change_reaches_the_docx_core_properties(self, job_id: str) -> None:
        import zipfile

        from src.docx.docx_generator import generate_docx
        from src.markdown.markdown_builder import build_markdown

        client.patch(
            f"/api/documents/{job_id}/metadata",
            json={"title": "Core Property Title", "language": "en-CA"},
        )
        document = _document(job_id)
        out = Path(TMP_DIR) / "metadata.docx"
        generate_docx(document, build_markdown(document), output_path=out)

        with zipfile.ZipFile(str(out)) as zf:
            core = zf.read("docProps/core.xml").decode("utf-8")
        assert "Core Property Title" in core

    def test_validation_sees_the_changed_language(self, job_id: str) -> None:
        from src.validation.validator import validate_document

        client.patch(f"/api/documents/{job_id}/metadata", json={"language": ""})
        cleared = [i for i in validate_document(_document(job_id)) if i.rule_id == "META_001"]

        client.patch(f"/api/documents/{job_id}/metadata", json={"language": "en-US"})
        restored = [i for i in validate_document(_document(job_id)) if i.rule_id == "META_001"]

        assert len(cleared) > len(restored)


class TestEveryRegisteredAssetTypeCanBeUndone:
    """The global W-1 invariant, stated once over the engine itself: a
    verifier that cannot revert is a mutation with no way back."""

    def test_every_verifier_implements_the_full_rail(self) -> None:
        from src.architecture.invariants import check_correction_rail

        assert check_correction_rail() == []

    def test_reading_order_and_metadata_are_registered(self) -> None:
        from src.verification.engine import engine

        assert "reading_order" in engine._verifiers  # noqa: SLF001
        assert "metadata" in engine._verifiers  # noqa: SLF001
