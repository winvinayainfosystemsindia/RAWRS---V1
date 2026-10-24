"""OCR garble detection and VLM re-reading (docs/OCR_QUALITY.md).

src/ocr/quality.py (the signature), src/ocr/docling_engine.py (marking
garbled regions), src/ocr/reread.py (the second reading and its judgement),
src/verification/ocr_text.py (accepted readings on the correction rail) and
validation rule OCR_004 (whatever is still garbled). No network: the reader
is injected, and stub mode keeps the real one off.
"""

import json
from pathlib import Path
from typing import List

import pytest

from conftest import a_scanned_pdf
from src.models.contracts import (
    Document,
    ExtractionMethod,
    Metadata,
    OCRReread,
    Page,
)
from src.models.correction import CorrectionStatus
from src.ocr import docling_engine, reread
from src.ocr.docling_engine import OCRTimingMetrics, _DoclingPage, _garbled_regions
from src.ocr.quality import agreement, garbled_lines, is_garbled
from src.validation.validator import validate_document
from src.verification.engine import engine
from src.verification.ocr_text import ASSET_TYPE, OcrTextVerifier, page_object_id

FIXTURE = Path(__file__).parent / "fixtures" / "ocr_quality" / "docling_items.json"

# Real O'Leary Docling output and GLM-OCR's reading of the same crop.
GARBLED = (
    "In nde o o ad  ie  ef o n adhn whether you are looking for impacts, increases, "
    "decreases, relationships, correlations, causes etc."
)
READING = (
    "Indicate whether you foresee a relationship between concepts you are exploring whether "
    "you are looking for impacts, increases, decreases, relationships, correlations, causes etc."
)
CLEAN = "Define the topic - whether your focus is on youth suicide, environmental degradation, secularization, etc."


# --- the signature ----------------------------------------------------------


class TestGarbleSignature:
    def test_every_hand_labelled_corpus_item_is_classified_as_labelled(self) -> None:
        items = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]
        wrong = [(i["pdf"], i["page"], i["text"][:60]) for i in items if is_garbled(i["text"]) != i["garbled"]]
        assert wrong == []
        assert sum(i["garbled"] for i in items) == 17
        assert len(items) == 368

    @pytest.mark.parametrize(
        "text",
        [
            GARBLED,
            "Hyp   s o  l i ol ss it relationships between two or more variables",
            "-  l   sdd  d  -d ence) with a tremendous amount of information",
            "Do ¿s s as s s s s as s n not, can the skills be developed?",
        ],
    )
    def test_recognizer_fragments_are_garbled(self, text: str) -> None:
        assert is_garbled(text)

    @pytest.mark.parametrize(
        "text",
        [
            CLEAN,
            "Bryman's study, McKeganey and Barnard's (1996) work, and you're right that I'd agree.",
            "P. H. Hirst and R. S. Peters, The Logic of Education, p.74, RKP, 1970.",
            "e.g. labour process theory, i.e. the BBC and NHS data.",
            "Visit www.oxfordtextbooks.co.uk/orc/brymansrm4e/ for more.",
            "",
        ],
    )
    def test_ordinary_prose_is_not_garbled(self, text: str) -> None:
        assert not is_garbled(text)

    def test_garbled_lines_returns_only_the_garbled_lines(self) -> None:
        assert garbled_lines(f"{CLEAN}\n\n{GARBLED}\n") == [GARBLED.strip()]


class TestAgreement:
    def test_a_correct_reading_keeps_the_readable_words(self) -> None:
        # 8 of 9: "adhn" is a garble fragment with a vowel, so it counts as
        # readable and the correct reading cannot contain it.
        assert agreement(GARBLED, READING) == pytest.approx(8 / 9)
        assert agreement(GARBLED, READING) >= reread.MIN_AGREEMENT

    def test_a_paraphrase_or_truncation_scores_low(self) -> None:
        assert agreement(GARBLED, "Indicate whether you foresee a relationship.") < 0.3

    def test_nothing_readable_to_check_is_full_agreement(self) -> None:
        assert agreement("o n ie", "anything") == 1.0


# --- marking regions (Docling) ---------------------------------------------


class TestGarbledRegions:
    def test_only_garbled_items_found_verbatim_in_the_page_text_are_kept(self) -> None:
        page_text = f"{CLEAN}\n\n- {GARBLED}"
        items = [(CLEAN, [0, 0, 1, 1]), (GARBLED, [10, 20, 30, 40]), ("ppo oor odor o  oor r", [0, 0, 1, 1])]
        regions = _garbled_regions(items, page_text)
        assert [(r.original, r.bbox) for r in regions] == [(GARBLED, [10, 20, 30, 40])]

    def test_no_positions_means_no_regions(self) -> None:
        assert _garbled_regions(None, GARBLED) == []

    def test_a_docling_page_marks_garbled_items_but_never_a_heading(self) -> None:
        heading = "Hyp   s o  l i ol ss it"
        cached = _DoclingPage(
            text=f"{heading}\n\n{GARBLED}\n\n{CLEAN}",
            header_items=[("section_header", heading, 1)],
            text_items=[(heading, [1, 2, 3, 4]), (GARBLED, [5, 6, 7, 8]), (CLEAN, [9, 9, 9, 9])],
            from_cache=True,
        )
        page = Page(page_number=1)
        docling_engine._run_single_page(None, Path("x.pdf"), page, OCRTimingMetrics(), cached=cached)
        assert [r.original for r in page.ocr_rereads] == [GARBLED]
        assert page.cleaned_text.count(GARBLED) == 1


# --- the second reading -----------------------------------------------------


def _scanned_document(original: str = GARBLED, bbox=(100.0, 150.0, 480.0, 200.0)) -> Document:
    pdf = a_scanned_pdf()
    page = Page(
        page_number=1,
        cleaned_text=f"{CLEAN}\n\n- {original}",
        extraction_method=ExtractionMethod.DOCLING,
        ocr_rereads=[OCRReread(original=original, bbox=list(bbox) if bbox else None)],
    )
    return Document(
        source_pdf_path=str(pdf),
        pages=[page],
        metadata=Metadata(filename=pdf.name, page_count=1, language="en-US", title="T"),
    )


class _Reader:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: List[bytes] = []

    def __call__(self, png: bytes, original_length: int) -> str:
        self.calls.append(png)
        return self.answer


class TestReread:
    def test_an_agreeing_reading_is_accepted_and_the_page_text_is_untouched(self) -> None:
        document = _scanned_document()
        reader = _Reader(READING)
        reread.reread_garbled_regions(document, reader=reader)

        region = document.pages[0].ocr_rereads[0]
        assert reader.calls and reader.calls[0][:8] == b"\x89PNG\r\n\x1a\n"
        assert region.accepted and region.reason == ""
        assert region.reading == READING
        assert region.engine == reread.model()
        assert region.agreement == pytest.approx(8 / 9, abs=0.001)
        assert GARBLED in document.pages[0].cleaned_text  # evidence only

    @pytest.mark.parametrize(
        "answer, reason",
        [
            ("Indicate whether you foresee a relationship.", "readable words"),
            ("ppo oor odor o  oor  oor r or os y Dnels  nss  a   n s", "garbled too"),
            ("", "empty"),
        ],
    )
    def test_a_disagreeing_reading_is_rejected_with_a_reason(self, answer: str, reason: str) -> None:
        document = _scanned_document()
        reread.reread_garbled_regions(document, reader=_Reader(answer))
        region = document.pages[0].ocr_rereads[0]
        assert not region.accepted
        assert reason in region.reason

    def test_a_reading_far_longer_than_the_original_is_rejected(self) -> None:
        document = _scanned_document()
        reread.reread_garbled_regions(document, reader=_Reader(READING * 3))
        assert "length" in document.pages[0].ocr_rereads[0].reason

    def test_an_all_garble_original_cannot_vouch_for_any_reading(self) -> None:
        # Nothing readable to agree on: a hallucination would pass agreement.
        document = _scanned_document(original="In nde o o ad ie ef o n")
        reread.reread_garbled_regions(document, reader=_Reader("Indicate the nature of the evidence here"))
        region = document.pages[0].ocr_rereads[0]
        assert not region.accepted
        assert "too few readable words" in region.reason

    def test_failing_reads_stop_after_a_few_in_a_row(self) -> None:
        document = _scanned_document()
        page = document.pages[0]
        page.ocr_rereads = [
            OCRReread(original=f"{GARBLED} {i}", bbox=[100.0, 150.0 + i, 480.0, 200.0]) for i in range(6)
        ]
        calls: List[bytes] = []

        def broken(png: bytes, original_length: int) -> str:
            calls.append(png)
            raise TimeoutError("stalled")

        reread.reread_garbled_regions(document, reader=broken)
        assert len(calls) == reread.MAX_CONSECUTIVE_FAILURES
        assert all(region.reading is None for region in page.ocr_rereads)

    def test_past_the_budget_the_rest_stay_flagged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(reread, "BUDGET_SECONDS", -1)
        reader = _Reader(READING)
        document = _scanned_document()
        reread.reread_garbled_regions(document, reader=reader)
        assert reader.calls == []
        assert document.pages[0].ocr_rereads[0].reading is None

    def test_a_non_http_ollama_url_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAWRS_OLLAMA_URL", "file:///etc")
        assert "http(s)" in reread._unavailable_reason()

    def test_a_region_without_a_position_is_not_read(self) -> None:
        document = _scanned_document(bbox=None)
        reader = _Reader(READING)
        reread.reread_garbled_regions(document, reader=reader)
        assert reader.calls == []
        assert document.pages[0].ocr_rereads[0].reading is None

    def test_stub_mode_never_reaches_a_model(self) -> None:
        # conftest sets RAWRS_AI_STUB: the default reader must stay off.
        document = _scanned_document()
        reread.reread_garbled_regions(document)
        assert document.pages[0].ocr_rereads[0].reading is None

    def test_the_off_switch_disables_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RAWRS_AI_STUB", raising=False)
        monkeypatch.setenv("RAWRS_OCR_REREAD", "off")
        assert not reread.enabled()

    def test_an_unreachable_ollama_leaves_regions_unread(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RAWRS_AI_STUB", raising=False)
        monkeypatch.setenv("RAWRS_OLLAMA_URL", "http://127.0.0.1:9")
        document = _scanned_document()
        reread.reread_garbled_regions(document)
        assert document.pages[0].ocr_rereads[0].reading is None

    def test_readings_are_cached_per_pdf_page(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("RAWRS_OCR_CACHE", "on")
        monkeypatch.setenv("RAWRS_OCR_CACHE_DIR", str(tmp_path))
        reread.reread_garbled_regions(_scanned_document(), reader=_Reader(READING))

        second = _Reader("must not be asked")
        document = _scanned_document()
        reread.reread_garbled_regions(document, reader=second)
        assert second.calls == []
        assert document.pages[0].ocr_rereads[0].reading == READING


class TestCleanReading:
    def test_emphasis_and_an_invented_bullet_are_dropped(self) -> None:
        assert reread.clean_reading("- **Indicate**  whether\nyou", "In nde o") == "Indicate whether you"

    def test_a_leading_symbol_the_vlm_skipped_is_kept(self) -> None:
        assert reread.clean_reading("Supervision - not many", "☑ Supervision – not") == "☑ Supervision - not many"

    def test_ascii_junk_at_the_start_of_the_original_is_not_carried_over(self) -> None:
        assert reread.clean_reading("A well-articulated question", "-  l   sdd  d") == "A well-articulated question"

    def test_stray_non_ascii_noise_is_not_carried_over(self) -> None:
        assert reread.clean_reading("Hypothesis: a hunch", "© Hyp s o l") == "Hypothesis: a hunch"

    def test_markdown_markers_are_stripped(self) -> None:
        assert reread.clean_reading("## *Hypothesis*: a `hunch`", "Hyp s o l") == "Hypothesis: a hunch"

    def test_arithmetic_asterisks_survive(self) -> None:
        assert reread.clean_reading("2 * 3 = 6", "2 x o") == "2 * 3 = 6"


# --- the correction rail ----------------------------------------------------


def _read_document(answer: str = READING) -> Document:
    document = _scanned_document()
    reread.reread_garbled_regions(document, reader=_Reader(answer))
    return document


class TestOcrTextVerifier:
    def test_an_accepted_reading_is_auto_applied_and_undoable(self) -> None:
        document = _read_document()
        findings = OcrTextVerifier().inspect(document)
        assert len(findings) == 1 and findings[0].auto_apply
        assert findings[0].object_id == page_object_id(1)

        engine.record_findings(document, findings, provider="rawrs_native")
        correction = document.corrections[-1]
        assert correction.object_type == ASSET_TYPE
        assert correction.status == CorrectionStatus.AUTO_APPLIED
        assert READING in document.pages[0].cleaned_text
        assert GARBLED not in document.pages[0].cleaned_text
        assert CLEAN in document.pages[0].cleaned_text
        assert document.verification_findings == []  # terminal: not in the queue

        engine.revert_correction(document, correction)
        assert GARBLED in document.pages[0].cleaned_text
        assert READING not in document.pages[0].cleaned_text

    def test_a_rejected_reading_produces_no_finding(self) -> None:
        assert OcrTextVerifier().inspect(_read_document("Indicate whether.")) == []

    def test_text_edited_since_produces_no_finding_and_apply_is_a_no_op(self) -> None:
        document = _read_document()
        document.pages[0].cleaned_text = "Rewritten by a reviewer."
        assert OcrTextVerifier().inspect(document) == []

    def test_a_repeated_text_is_never_guessed_at(self) -> None:
        # Which occurrence is the region? Unknowable - so neither apply nor
        # undo touches either.
        document = _read_document()
        page = document.pages[0]
        correction_findings = OcrTextVerifier().inspect(document)
        engine.record_findings(document, correction_findings, provider="rawrs_native")
        page.cleaned_text = f"{READING}\n\n{page.cleaned_text}"  # the reading now occurs twice
        engine.revert_correction(document, document.corrections[-1])
        assert page.cleaned_text.count(READING) == 2
        assert GARBLED not in page.cleaned_text

        doubled = _read_document()
        doubled.pages[0].cleaned_text += f"\n\n{GARBLED}"
        assert OcrTextVerifier().inspect(doubled) == []

    def test_auto_batches_of_different_asset_types_are_separate_transactions(self) -> None:
        from src.models.verification import Finding
        from src.verification import artifacts  # registers the text_block verifier

        document = _read_document()
        other = Finding(asset_type=artifacts.ASSET_TYPE, kind="suppress_artifact", object_id="missing", auto_apply=True)
        engine.record_findings(document, OcrTextVerifier().inspect(document) + [other], provider="rawrs_native")
        transactions = {c.object_type: c.transaction_id for c in document.corrections}
        assert transactions[ASSET_TYPE] != transactions[artifacts.ASSET_TYPE]


# --- OCR_004 ----------------------------------------------------------------


def _ocr_004(document: Document):
    return [i for i in validate_document(document) if i.rule_id == "OCR_004"]


class TestGarbledOcrRule:
    def test_an_unread_garbled_page_is_flagged_with_the_way_to_fix_it(self) -> None:
        issues = _ocr_004(_scanned_document())
        assert len(issues) == 1
        assert issues[0].page_number == 1
        assert "No second reading was obtained" in issues[0].message
        assert issues[0].suggested_action

    def test_a_rejected_reading_is_named(self) -> None:
        issues = _ocr_004(_read_document("Indicate whether."))
        assert "rejected" in issues[0].message

    def test_a_repaired_page_is_not_flagged(self) -> None:
        document = _read_document()
        engine.record_findings(document, OcrTextVerifier().inspect(document), provider="rawrs_native")
        assert _ocr_004(document) == []

    def test_native_text_pages_are_out_of_scope(self) -> None:
        document = _scanned_document()
        document.pages[0].extraction_method = ExtractionMethod.DIRECT_TEXT_EXTRACTION
        assert _ocr_004(document) == []

    def test_clean_ocr_is_not_flagged(self) -> None:
        document = _scanned_document()
        document.pages[0].cleaned_text = CLEAN
        document.pages[0].ocr_rereads = []
        assert _ocr_004(document) == []


# --- pipeline wiring --------------------------------------------------------


def test_the_pipeline_rereads_after_the_ocr_engines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from conftest import a_born_digital_pdf
    from src.pipeline import phase1_pipeline

    calls: List[str] = []

    def _track(name):
        def _stage(document, **_):
            calls.append(name)
            return document

        return _stage

    monkeypatch.setattr(phase1_pipeline, "run_docling_ocr", _track("docling"))
    monkeypatch.setattr(phase1_pipeline, "run_surya_ocr", _track("surya"))
    monkeypatch.setattr(phase1_pipeline, "reread_garbled_regions", _track("reread"))
    result = phase1_pipeline.run_pipeline(a_born_digital_pdf(), output_root=tmp_path, enable_ocr=True)
    assert result.success
    assert calls == ["docling", "surya", "reread"]
