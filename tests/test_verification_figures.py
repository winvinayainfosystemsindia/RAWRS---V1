"""Tests for src/verification/figures.py — FigureAssetVerifier, the first
asset type registered with the cross-source verification engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from src.models.figure import Figure
from src.models.image import Image
from src.models.phase2_document import P2Block, P2BlockType, P2Figure
from src.models.verification import ImportSource, VerificationStatus
from src.verification.engine import engine
from src.verification.figures import FigureAssetVerifier
import src.verification.figures  # noqa: F401 - ensures registration


def _make_png(path: Path, size: tuple) -> Path:
    from PIL import Image as PILImage

    PILImage.new("RGB", size, color="white").save(path)
    return path


def _figure_block(source_line: int, image_path: Optional[str], caption: Optional[str] = None) -> P2Block:
    return P2Block(
        block_type=P2BlockType.FIGURE,
        figure=P2Figure(image_path=image_path, caption=caption),
        source_line=source_line,
    )


class TestEngineRegistration:
    def test_figure_asset_verifier_is_registered_on_the_shared_engine(self) -> None:
        assert "figure" in engine._verifiers
        assert isinstance(engine._verifiers["figure"], FigureAssetVerifier)


class TestImportMatching:
    def test_exact_mmd_ref_matches_by_basename(self, tmp_path: Path) -> None:
        img = _make_png(tmp_path / "img-0.jpeg", (100, 50))
        block = _figure_block(10, image_path="images/img-0.jpeg", caption="Figure 1. A chart")

        verifier = FigureAssetVerifier()
        result = verifier.build_import_matcher().match([block], [img])

        assert len(result.pairs) == 1
        assert result.pairs[0].matched_by == "exact_mmd_ref"

    def test_loose_filename_matches_when_basename_differs_slightly(self, tmp_path: Path) -> None:
        img = _make_png(tmp_path / "img_0_final.jpeg", (100, 50))
        block = _figure_block(10, image_path="images/img-0.jpeg")

        verifier = FigureAssetVerifier()
        result = verifier.build_import_matcher().match([block], [img])

        assert len(result.pairs) == 1
        assert result.pairs[0].matched_by == "loose_filename"

    def test_positional_fallback_used_when_no_image_path_at_all(self, tmp_path: Path) -> None:
        img = _make_png(tmp_path / "totally_unrelated_name.png", (100, 50))
        block = _figure_block(10, image_path=None, caption="Figure 1")

        verifier = FigureAssetVerifier()
        result = verifier.build_import_matcher().match([block], [img])

        assert len(result.pairs) == 1
        assert result.pairs[0].matched_by == "positional_fallback"

    def test_to_canonical_registers_matched_and_unmatched_uploaded_files(self, tmp_path: Path) -> None:
        matched_img = _make_png(tmp_path / "img-0.jpeg", (100, 50))
        orphan_img = _make_png(tmp_path / "orphan.png", (20, 20))
        block = _figure_block(10, image_path="images/img-0.jpeg", caption="Figure 1. A chart")

        verifier = FigureAssetVerifier()
        result = verifier.build_import_matcher().match([block], [matched_img, orphan_img])
        images = verifier.to_canonical(result, page_count=3, total_blocks=1)

        assert len(images) == 2
        by_name = {img.uploaded_filename: img for img in images}
        matched = by_name["img-0.jpeg"]
        orphan = by_name["orphan.png"]

        assert matched.import_source == ImportSource.MATHPIX
        assert matched.source_reference == "images/img-0.jpeg"
        assert matched.figure.caption == "Figure 1. A chart"
        assert matched.figure.label == "Figure 1"
        assert matched.figure.number == 1
        assert matched.verification_status == VerificationStatus.UNVERIFIED
        assert matched.width == 100 and matched.height == 50

        assert orphan.verification_status == VerificationStatus.ORPHAN
        assert orphan.source_reference is None

    def test_no_uploaded_image_never_fabricates_an_image(self) -> None:
        block = _figure_block(10, image_path="images/img-missing.jpeg")
        verifier = FigureAssetVerifier()
        result = verifier.build_import_matcher().match([block], [])
        images = verifier.to_canonical(result, page_count=1, total_blocks=1)
        assert images == []


class TestImportClassify:
    def test_unmatched_figure_block_produces_missing_from_package_finding(self, tmp_path: Path) -> None:
        block = _figure_block(10, image_path="images/img-missing.jpeg")
        verifier = FigureAssetVerifier()
        result = verifier.build_import_matcher().match([block], [])
        findings = verifier.classify(result, phase="import")
        assert len(findings) == 1
        assert findings[0].kind == "missing_from_package"

    def test_unmatched_uploaded_file_produces_orphan_finding(self, tmp_path: Path) -> None:
        img = _make_png(tmp_path / "unreferenced.png", (10, 10))
        verifier = FigureAssetVerifier()
        result = verifier.build_import_matcher().match([], [img])
        findings = verifier.classify(result, phase="import")
        assert len(findings) == 1
        assert findings[0].kind == "orphan"
        assert "unreferenced.png" in findings[0].evidence

    def test_duplicate_uploaded_files_are_flagged(self, tmp_path: Path) -> None:
        img1 = _make_png(tmp_path / "a.png", (10, 10))
        img2 = tmp_path / "b.png"
        img2.write_bytes(img1.read_bytes())  # byte-identical copy

        verifier = FigureAssetVerifier()
        result = verifier.build_import_matcher().match([], [img1, img2])
        findings = verifier.classify(result, phase="import")

        kinds = [f.kind for f in findings]
        assert "duplicate" in kinds


class TestPdfVerificationMatching:
    def _mathpix_image(self, page_number=1, caption=None, width=None, height=None, uploaded_filename=None) -> Image:
        return Image(
            image_id="mx-1",
            page_number=page_number,
            file_path="/tmp/whatever.png",
            width=width,
            height=height,
            import_source=ImportSource.MATHPIX,
            uploaded_filename=uploaded_filename,
            figure=Figure(caption=caption) if caption is not None else None,
        )

    def _pdf_image(self, page_number=1, caption=None, width=None, height=None) -> Image:
        return Image(
            image_id="pdf-1",
            page_number=page_number,
            file_path="/tmp/pdf_extracted.png",
            width=width,
            height=height,
            import_source=ImportSource.PDF,
            figure=Figure(caption=caption) if caption is not None else None,
        )

    def test_caption_similarity_matches_close_captions(self) -> None:
        a = self._mathpix_image(caption="Figure 1. Sales by quarter")
        b = self._pdf_image(caption="Figure 1. Sales by quarter chart")
        verifier = FigureAssetVerifier()
        result = verifier.build_pdf_matcher().match([a], [b])
        assert len(result.pairs) == 1

    def test_page_number_signal_matches_same_page(self) -> None:
        a = self._mathpix_image(page_number=5)
        b = self._pdf_image(page_number=5)
        verifier = FigureAssetVerifier()
        result = verifier.build_pdf_matcher().match([a], [b])
        assert len(result.pairs) == 1
        assert result.pairs[0].matched_by == "page_number"

    def test_dimension_signal_matches_same_aspect_ratio(self) -> None:
        a = self._mathpix_image(page_number=1, width=200, height=100)
        b = self._pdf_image(page_number=99, width=400, height=200)  # different page, same AR
        verifier = FigureAssetVerifier()
        result = verifier.build_pdf_matcher().match([a], [b])
        assert len(result.pairs) == 1
        assert result.pairs[0].matched_by == "image_metadata"

    def test_visual_similarity_signal_never_matches_anything_yet(self) -> None:
        from src.verification.figures import _visual_similarity_signal
        a = self._mathpix_image()
        b = self._pdf_image()
        assert _visual_similarity_signal(a, b) is None


class TestPdfVerificationClassify:
    def test_high_confidence_match_sets_verified_and_copies_bbox(self) -> None:
        from src.models.bounding_box import BoundingBox

        a = Image(image_id="a", page_number=1, file_path="/a.png", import_source=ImportSource.MATHPIX, figure=Figure(caption="Figure 1. Same"))
        b = Image(
            image_id="b", page_number=1, file_path="/b.png", import_source=ImportSource.PDF,
            figure=Figure(caption="Figure 1. Same"),
            bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10),
        )
        from src.verification.matching import MatchedPair, MatchResult

        result = MatchResult(pairs=[MatchedPair(a=a, b=b, confidence=0.95, matched_by="caption_similarity")])
        verifier = FigureAssetVerifier()
        findings = verifier.classify(result, phase="pdf_verification")

        assert a.verification_status == VerificationStatus.VERIFIED
        assert a.match_confidence == 0.95
        assert a.bbox == b.bbox
        assert findings == []

    def test_low_confidence_match_flags_low_confidence(self) -> None:
        a = Image(image_id="a", page_number=1, file_path="/a.png", import_source=ImportSource.MATHPIX)
        b = Image(image_id="b", page_number=1, file_path="/b.png", import_source=ImportSource.PDF)
        from src.verification.matching import MatchedPair, MatchResult

        result = MatchResult(pairs=[MatchedPair(a=a, b=b, confidence=0.3, matched_by="positional_fallback")])
        verifier = FigureAssetVerifier()
        findings = verifier.classify(result, phase="pdf_verification")

        assert a.verification_status == VerificationStatus.LOW_CONFIDENCE
        assert any(f.kind == "low_confidence" for f in findings)

    def test_caption_mismatch_flagged_even_at_decent_confidence(self) -> None:
        a = Image(image_id="a", page_number=1, file_path="/a.png", import_source=ImportSource.MATHPIX, figure=Figure(caption="Figure 1. Revenue"))
        b = Image(image_id="b", page_number=1, file_path="/b.png", import_source=ImportSource.PDF, figure=Figure(caption="Figure 2. Headcount"))
        from src.verification.matching import MatchedPair, MatchResult

        result = MatchResult(pairs=[MatchedPair(a=a, b=b, confidence=0.9, matched_by="page_number")])
        verifier = FigureAssetVerifier()
        findings = verifier.classify(result, phase="pdf_verification")

        assert a.verification_status == VerificationStatus.MISMATCH
        assert any(f.kind == "caption_mismatch" for f in findings)

    def test_page_mismatch_between_matched_pair_is_flagged(self) -> None:
        a = Image(image_id="a", page_number=1, file_path="/a.png", import_source=ImportSource.MATHPIX)
        b = Image(image_id="b", page_number=4, file_path="/b.png", import_source=ImportSource.PDF)
        from src.verification.matching import MatchedPair, MatchResult

        result = MatchResult(pairs=[MatchedPair(a=a, b=b, confidence=0.9, matched_by="filename")])
        verifier = FigureAssetVerifier()
        findings = verifier.classify(result, phase="pdf_verification")

        assert any(f.kind == "wrong_page" for f in findings)

    def test_unmatched_canonical_image_is_missing_from_pdf(self) -> None:
        a = Image(image_id="a", page_number=1, file_path="/a.png", import_source=ImportSource.MATHPIX)
        from src.verification.matching import MatchResult

        result = MatchResult(unmatched_a=[a])
        verifier = FigureAssetVerifier()
        findings = verifier.classify(result, phase="pdf_verification")

        assert a.verification_status == VerificationStatus.MISSING_FROM_PDF
        assert any(f.kind == "missing_from_pdf" for f in findings)

    def test_unmatched_pdf_image_is_flagged_without_touching_canonical_state(self) -> None:
        b = Image(image_id="b", page_number=2, file_path="/b.png", import_source=ImportSource.PDF)
        from src.verification.matching import MatchResult

        result = MatchResult(unmatched_b=[b])
        verifier = FigureAssetVerifier()
        findings = verifier.classify(result, phase="pdf_verification")

        assert len(findings) == 1
        assert findings[0].kind == "unmatched_pdf_image"
        assert findings[0].object_id is None  # no canonical Image exists to attach to


class TestRuleTable:
    def test_every_kind_produced_by_classify_has_a_rule_spec(self) -> None:
        verifier = FigureAssetVerifier()
        table = verifier.rule_table()
        expected_kinds = {
            "missing_from_package", "unmatched_pdf_image", "orphan",
            "caption_mismatch", "duplicate", "low_confidence", "wrong_page",
            "missing_from_pdf",
        }
        assert expected_kinds <= set(table.keys())
        rule_ids = {spec.rule_id for spec in table.values()}
        assert len(rule_ids) == len(table)  # every rule_id is unique
