"""Tests for src/ai/alt_text_generator.py.

All tests run in RAWRS_AI_STUB mode so no model is loaded or invoked.
The stub returns deterministic results based on image_path.
"""

import os
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def stub_mode(tmp_path, monkeypatch):
    """Force stub mode and create a fake image file for all tests."""
    monkeypatch.setenv("RAWRS_AI_STUB", "1")
    (tmp_path / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    return tmp_path


def test_stub_returns_result(stub_mode):
    from src.ai.alt_text_generator import AltTextRequest, generate_alt_text

    req = AltTextRequest(
        image_path=str(stub_mode / "img.png"),
        caption="Figure 1. A chart.",
        figure_label="Figure 1",
        nearby_text=["Some nearby paragraph."],
        page_number=3,
    )
    result = generate_alt_text(req)
    assert result.description
    assert result.purpose
    assert result.visible_text
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.warnings, list)


def test_stub_is_deterministic(stub_mode):
    from src.ai.alt_text_generator import AltTextRequest, generate_alt_text

    req = AltTextRequest(
        image_path=str(stub_mode / "img.png"),
        caption=None,
        figure_label=None,
        nearby_text=[],
        page_number=1,
    )
    r1 = generate_alt_text(req)
    r2 = generate_alt_text(req)
    assert r1.description == r2.description
    assert r1.confidence == r2.confidence


def test_stub_warns_about_stub_mode(stub_mode):
    from src.ai.alt_text_generator import AltTextRequest, generate_alt_text

    req = AltTextRequest(
        image_path=str(stub_mode / "img.png"),
        caption=None,
        figure_label=None,
        nearby_text=[],
        page_number=1,
    )
    result = generate_alt_text(req)
    assert any("RAWRS_AI_STUB" in w for w in result.warnings)


def test_stub_includes_page_number_in_description(stub_mode):
    from src.ai.alt_text_generator import AltTextRequest, generate_alt_text

    req = AltTextRequest(
        image_path=str(stub_mode / "img.png"),
        caption=None,
        figure_label=None,
        nearby_text=[],
        page_number=7,
    )
    result = generate_alt_text(req)
    assert "7" in result.description


def test_parse_response_all_fields():
    from src.ai.providers.qwen import _parse_response

    raw = (
        "IMAGE_TYPE: CHART\n"
        "DESCRIPTION: A bar chart showing annual revenue.\n"
        "PURPOSE: Illustrates growth over five years.\n"
        "VISIBLE_TEXT: 2020, 2021, 2022, Revenue ($M)\n"
        "CONFIDENCE: 0.87\n"
        "WARNINGS: Image is slightly blurry\n"
    )
    result = _parse_response(raw)
    assert result.description == "A bar chart showing annual revenue."
    assert result.purpose == "Illustrates growth over five years."
    assert result.visible_text == "2020, 2021, 2022, Revenue ($M)"
    assert abs(result.confidence - 0.87) < 0.001
    assert result.warnings == ["Image is slightly blurry"]


def test_parse_response_none_warnings():
    from src.ai.providers.qwen import _parse_response

    raw = (
        "IMAGE_TYPE: PHOTOGRAPH\n"
        "DESCRIPTION: A photo of a microscope.\n"
        "PURPOSE: Shows the laboratory setup.\n"
        "VISIBLE_TEXT: None\n"
        "CONFIDENCE: 0.95\n"
        "WARNINGS: None\n"
    )
    result = _parse_response(raw)
    assert result.warnings == []


def test_parse_response_clamps_confidence():
    from src.ai.providers.qwen import _parse_response

    raw = (
        "IMAGE_TYPE: OTHER\n"
        "DESCRIPTION: x.\n"
        "PURPOSE: y.\n"
        "VISIBLE_TEXT: None\n"
        "CONFIDENCE: 1.5\n"
        "WARNINGS: None\n"
    )
    result = _parse_response(raw)
    assert result.confidence == 1.0


def test_parse_response_missing_field_raises():
    from src.ai.providers.qwen import _parse_response
    from src.ai.alt_text_generator import AltTextGenerationError

    raw = (
        "DESCRIPTION: x.\n"
        "PURPOSE: y.\n"
        "CONFIDENCE: 0.5\n"
        "WARNINGS: None\n"
        # IMAGE_TYPE is missing (VISIBLE_TEXT too, but that one is optional)
    )
    with pytest.raises(AltTextGenerationError, match="IMAGE_TYPE"):
        _parse_response(raw)


def test_parse_response_accepts_a_detailed_answer_without_purpose_and_with_wrapped_text():
    """qwen2.5vl:7b with the detailed prompt skipped PURPOSE and listed the
    image's text one label per line (benchmark figure O'Leary #2, 2026-11-06)."""
    from src.ai.providers.qwen import _parse_response

    result = _parse_response(
        "IMAGE_TYPE: DIAGRAM\nDESCRIPTION: A three-tier pyramid.\nVISIBLE_TEXT: Researchable Questions\n"
        "Generating Questions\nCONFIDENCE: 1.0\nWARNINGS: None\n"
    )
    assert result.description == "A three-tier pyramid."
    assert result.visible_text == "Researchable Questions Generating Questions"
    assert result.purpose == ""


def test_parse_response_multiple_warnings():
    from src.ai.providers.qwen import _parse_response

    raw = (
        "IMAGE_TYPE: DIAGRAM\n"
        "DESCRIPTION: A complex figure.\n"
        "PURPOSE: Shows data.\n"
        "VISIBLE_TEXT: None\n"
        "CONFIDENCE: 0.4\n"
        "WARNINGS: low quality, complex layout, OCR required\n"
    )
    result = _parse_response(raw)
    assert len(result.warnings) == 3
    assert "low quality" in result.warnings
    assert "OCR required" in result.warnings
