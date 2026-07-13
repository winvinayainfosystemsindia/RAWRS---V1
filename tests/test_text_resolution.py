"""Tests for src/verification/text_resolution.py::TextResolver (M-5.3).

Several cases below are modeled directly on real mismatches a diagnostic
run against the benchmark corpus (2.FolkPedagogy_Bruner_PsychDimensions_New.pdf)
surfaced — not purely synthetic guesses. Specifically: a running header
("Folk Pedagogy") that PyMuPDF's own line grouping combines with an
adjacent page number into one line, and a short numeric Mathpix "heading"
("47") that a naive fuzzy match would wrongly pair with an unrelated
nearby number ("49") a single digit away by edit distance.
"""

import unicodedata

from src.verification.text_resolution import TextResolver


class TestExactAndNormalizedTiers:
    def test_exact_match(self):
        resolver = TextResolver({"Introduction": "value-a"})
        assert resolver.resolve("Introduction") == ("value-a", "exact")

    def test_whitespace_difference_resolves_via_normalized_tier(self):
        # Real-world shape: Mathpix collapses/reflows whitespace
        # differently than PyMuPDF's own per-line extraction.
        resolver = TextResolver({"Folk  Pedagogy   Chapter": "value-a"})
        assert resolver.resolve("Folk Pedagogy Chapter") == ("value-a", "normalized")

    def test_unicode_normalization_resolves_via_normalized_tier(self):
        # "Café" as a single precomposed character (NFC) vs. as base
        # letter + combining acute accent (NFD) — both real, both
        # visually identical, byte-different without NFKC normalization.
        precomposed = unicodedata.normalize("NFC", "Café Culture")
        decomposed = unicodedata.normalize("NFD", "Café Culture")
        assert precomposed != decomposed  # sanity: the two forms really are byte-different
        resolver = TextResolver({precomposed: "value-a"})
        assert resolver.resolve(decomposed) == ("value-a", "normalized")

    def test_punctuation_difference_resolves_via_normalized_tier(self):
        resolver = TextResolver({"Folk Pedagogy:": "value-a"})
        assert resolver.resolve("Folk Pedagogy") == ("value-a", "normalized")

    def test_hyphenation_artifact_resolves_via_normalized_tier(self):
        # Line-wrap hyphenation: PyMuPDF sometimes preserves a hyphen
        # Mathpix's own text never had (punctuation-stripped by
        # normalization, so "Self-Regulation" and "SelfRegulation"
        # normalize to the same string).
        resolver = TextResolver({"Self-Regulation in Learning": "value-a"})
        assert resolver.resolve("SelfRegulation in Learning") == ("value-a", "normalized")


class TestContainmentTier:
    def test_running_header_merged_with_adjacent_text_resolves_via_containment(self):
        """Real diagnostic finding: 'Folk Pedagogy' (Mathpix's running
        header) never equals any single PyMuPDF line, because PyMuPDF
        grouped it with an adjacent page number into one combined line."""
        resolver = TextResolver({"6 Folk Pedagogy": "value-a"})
        assert resolver.resolve("Folk Pedagogy") == ("value-a", "containment")

    def test_ambiguous_containment_is_a_miss_not_a_guess(self):
        resolver = TextResolver({"Folk Pedagogy 1": "value-a", "Folk Pedagogy 2": "value-b"})
        assert resolver.resolve("Folk Pedagogy") is None


class TestFuzzyTier:
    def test_ocr_noise_resolves_via_fuzzy_tier(self):
        # Simulated OCR misread: a zero substituted for a lowercase o.
        resolver = TextResolver({"Introducti0n to Research": "value-a"})
        assert resolver.resolve("Introduction to Research") == ("value-a", "fuzzy")

    def test_short_numeric_strings_never_fuzzy_match(self):
        """Real diagnostic finding: Mathpix heading '47' vs. the actual
        nearby PDF text '49' — a single-digit difference, dangerously
        close by raw edit-distance, but a genuinely wrong match. Fuzzy
        tier must not fire below _MIN_FUZZY_LENGTH."""
        resolver = TextResolver({"49": "wrong-value"})
        assert resolver.resolve("47") is None

    def test_below_fuzzy_threshold_is_a_miss(self):
        resolver = TextResolver({"Completely Unrelated Heading Text": "value-a"})
        assert resolver.resolve("Something Else Entirely Different") is None


class TestNoMatch:
    def test_empty_candidates_returns_none(self):
        resolver = TextResolver({})
        assert resolver.resolve("Anything") is None

    def test_empty_target_returns_none(self):
        resolver = TextResolver({"Something": "value-a"})
        assert resolver.resolve("") is None

    def test_caching_reuses_normalization_across_multiple_resolves(self):
        """Construction computes normalization once; resolve() itself
        does no per-call re-normalization of the candidate dict (the
        'cached normalization' performance requirement)."""
        resolver = TextResolver({"Introduction": "value-a", "Chapter One": "value-b"})
        assert resolver.resolve("introduction") == ("value-a", "normalized")
        assert resolver.resolve("chapter one") == ("value-b", "normalized")
        # Internal cache built exactly once, not rebuilt per resolve() call.
        assert len(resolver._normalized) == 2
