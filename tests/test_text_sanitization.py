"""Tests for src/utils/text_sanitization.py (XML Sanitization Architecture, Layer 1).

Character-range choices here are grounded in lxml's actual, empirically-
verified rejection behavior (see the XML Sanitization Architecture
Review, docs/DECISIONS_LOG.md) - not assumed from the XML 1.0 spec text
alone.
"""

from src.utils.text_sanitization import sanitize_xml_text


class TestControlCharacterRemoval:
    def test_null_byte_is_removed(self) -> None:
        cleaned, removed = sanitize_xml_text("before\x00after")
        assert cleaned == "beforeafter"
        assert removed == ["U+0000"]

    def test_low_control_character_is_removed(self) -> None:
        cleaned, removed = sanitize_xml_text("bad\x01byte")
        assert cleaned == "badbyte"
        assert removed == ["U+0001"]

    def test_full_illegal_range_is_removed(self) -> None:
        # \x00-\x08, \x0B, \x0C, \x0E-\x1F - every codepoint lxml was
        # directly observed to reject, per the architecture review.
        dirty = "".join(chr(c) for c in range(0x00, 0x09)) + "\x0b\x0c" + "".join(
            chr(c) for c in range(0x0E, 0x20)
        )
        cleaned, removed = sanitize_xml_text(f"a{dirty}b")
        assert cleaned == "ab"
        assert len(removed) == len(dirty)

    def test_multiple_illegal_characters_each_recorded_in_order(self) -> None:
        cleaned, removed = sanitize_xml_text("a\x01b\x02c\x03")
        assert cleaned == "abc"
        assert removed == ["U+0001", "U+0002", "U+0003"]

    def test_clean_text_is_returned_unchanged_with_empty_removed_list(self) -> None:
        text = "Perfectly ordinary prose with no defects."
        cleaned, removed = sanitize_xml_text(text)
        assert cleaned == text
        assert removed == []


class TestLegitimateCharactersPreserved:
    """Mirrors src/ocr/router.py's own existing precedent
    (test_legitimate_typography_is_not_misclassified) - this character
    class distinction must hold here too, or sanitization would itself
    become a content-corruption bug."""

    def test_tab_newline_and_carriage_return_are_preserved(self) -> None:
        text = "line one\tindented\nline two\r\nline three"
        cleaned, removed = sanitize_xml_text(text)
        assert cleaned == text
        assert removed == []

    def test_delete_character_0x7f_is_preserved(self) -> None:
        # Empirically verified legal in XML (within [#x20-#xD7FF]) -
        # stripping it would be over-sanitization with no crash to
        # prevent. See module under test's module docstring.
        text = "a\x7fb"
        cleaned, removed = sanitize_xml_text(text)
        assert cleaned == text
        assert removed == []

    def test_em_dashes_curly_quotes_and_accents_are_preserved(self) -> None:
        text = (
            "The teacher's role—as both Calderhead and Delpit note—"
            "is to engage with café culture and naïve assumptions critically."
        )
        cleaned, removed = sanitize_xml_text(text)
        assert cleaned == text
        assert removed == []

    def test_non_latin_scripts_are_preserved(self) -> None:
        text = "日本語のテキスト and العربية and Ελληνικά"
        cleaned, removed = sanitize_xml_text(text)
        assert cleaned == text
        assert removed == []


class TestLoneSurrogates:
    """A different, rarer encoding defect than C0 controls - fails XML
    serialization with a UnicodeEncodeError rather than the ValueError
    this module primarily exists for, but the fix is the same: remove
    before any OOXML/XML serialization."""

    def test_lone_high_surrogate_is_removed(self) -> None:
        cleaned, removed = sanitize_xml_text("a\ud800b")
        assert cleaned == "ab"
        assert removed == ["U+D800"]

    def test_lone_low_surrogate_is_removed(self) -> None:
        cleaned, removed = sanitize_xml_text("a\udfffb")
        assert cleaned == "ab"
        assert removed == ["U+DFFF"]
