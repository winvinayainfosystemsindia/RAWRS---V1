"""L2 — artifact classification (additive, evidence-driven).

Unit-tests classify_artifacts over blocks carrying L1 evidence (physical zone +
repetition) and confirms structure_detector wires it into the real extraction
path. Additive: no consumer reads TextBlock.artifact yet.
"""

import fitz

from src.models.bounding_box import BoundingBox
from src.models.contracts import ArtifactClass, TextBlock
from src.models.text_block import PhysicalZone
from src.parser.pdf_parser import parse_pdf
from src.structure.layout_signals import annotate_repetition, classify_artifacts
from src.structure.structure_detector import detect_structure


def _blk(text, page, y, order, zone):
    b = TextBlock(page_number=page, text=text, bbox=BoundingBox(x0=72, y0=y, x1=300, y1=y + 10), order=order)
    b.physical_zone = zone
    return b


def _classified(blocks, page_labels=None):
    annotate_repetition(blocks, page_count=max((b.page_number for b in blocks), default=1))
    classify_artifacts(blocks, page_labels or {})
    return blocks


class TestClassifyArtifacts:
    def test_running_header(self):
        blocks = _classified([
            _blk("Journal of X", 1, 40, 0, PhysicalZone.HEADER),
            _blk("Journal of X", 2, 41, 0, PhysicalZone.HEADER),
            _blk("Journal of X", 3, 39, 0, PhysicalZone.HEADER),
        ])
        art = blocks[0].artifact
        assert art.artifact_class == ArtifactClass.RUNNING_HEADER
        assert 0.0 < art.confidence <= 1.0
        assert len(art.evidence) >= 2  # never one signal alone

    def test_running_footer(self):
        blocks = _classified([
            _blk("Chapter Two", 1, 760, 0, PhysicalZone.FOOTER),
            _blk("Chapter Two", 2, 760, 0, PhysicalZone.FOOTER),
        ])
        assert blocks[0].artifact.artifact_class == ArtifactClass.RUNNING_FOOTER

    def test_decorative_repeated_in_body(self):
        blocks = _classified([
            _blk("Confidential Draft", 1, 400, 0, PhysicalZone.BODY),
            _blk("Confidential Draft", 2, 400, 0, PhysicalZone.BODY),
        ])
        assert blocks[0].artifact.artifact_class == ArtifactClass.DECORATIVE_REPEATED

    def test_page_number_via_printed_label(self):
        blocks = _classified([_blk("iv", 4, 760, 0, PhysicalZone.FOOTER)], page_labels={4: "iv"})
        art = blocks[0].artifact
        assert art.artifact_class == ArtifactClass.PAGE_NUMBER
        assert any("printed label" in e for e in art.evidence)

    def test_content_not_classified(self):
        blocks = _classified([_blk("A unique sentence.", 1, 400, 0, PhysicalZone.BODY)])
        assert blocks[0].artifact is None

    def test_low_stability_repeat_not_classified(self):
        blocks = _classified([
            _blk("wanders", 1, 50, 0, PhysicalZone.HEADER),
            _blk("wanders", 2, 700, 0, PhysicalZone.HEADER),  # huge y jump -> unstable
        ])
        assert blocks[0].artifact is None  # below stability threshold

    def test_page_number_needs_zone_signal(self):
        # matches label but sits in BODY zone -> not enough signal for PAGE_NUMBER
        blocks = _classified([_blk("iv", 4, 400, 0, PhysicalZone.BODY)], page_labels={4: "iv"})
        assert blocks[0].artifact is None


class TestStructureDetectorWiring:
    def test_artifacts_classified_on_real_pdf(self, tmp_path):
        doc = fitz.open()
        for _ in range(3):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 40), "Running Header Line")
            page.insert_text((72, 400), f"Unique body {_}")
        path = tmp_path / "art.pdf"
        doc.save(str(path))

        document = detect_structure(parse_pdf(str(path)))

        headers = [b for b in document.blocks if b.text.strip() == "Running Header Line"]
        assert headers and all(b.artifact is not None for b in headers)
        assert headers[0].artifact.artifact_class == ArtifactClass.RUNNING_HEADER
        body = next(b for b in document.blocks if b.text.strip().startswith("Unique body"))
        assert body.artifact is None
