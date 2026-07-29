"""L1 — physical-zone assignment (header/footer/body).

Unit-tests the geometric assigner and confirms structure_detector populates
TextBlock.physical_zone from a real PDF. Additive signal: no consumer reads it
yet, so this only asserts the new field is set correctly.
"""

import fitz

from src.models.contracts import PhysicalZone
from src.structure.layout_signals import assign_physical_zone
from src.structure.structure_detector import _extract_page_blocks

_H = 792.0  # US Letter height


class TestAssignPhysicalZone:
    def test_top_band_is_header(self):
        assert assign_physical_zone(10, 20, _H) == PhysicalZone.HEADER

    def test_bottom_band_is_footer(self):
        assert assign_physical_zone(770, 780, _H) == PhysicalZone.FOOTER

    def test_middle_is_body(self):
        assert assign_physical_zone(390, 410, _H) == PhysicalZone.BODY

    def test_boundary_just_inside_body(self):
        # centre exactly on the 12% line is not < threshold -> BODY
        centre = _H * 0.12
        assert assign_physical_zone(centre - 1, centre + 1, _H) == PhysicalZone.BODY

    def test_degenerate_height_defaults_body(self):
        assert assign_physical_zone(10, 20, 0) == PhysicalZone.BODY
        assert assign_physical_zone(10, 20, -5) == PhysicalZone.BODY


class TestStructureDetectorPopulatesZone:
    def test_real_pdf_blocks_carry_zones(self, tmp_path):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 40), "Running header line")
        page.insert_text((72, 400), "Body paragraph text")
        page.insert_text((72, 760), "Footer line 1")
        path = tmp_path / "zoned.pdf"
        doc.save(str(path))

        reopened = fitz.open(str(path))
        blocks, *_ = _extract_page_blocks(reopened[0], page_number=1)

        assert blocks, "expected extracted blocks"
        # Every block built by the real extraction path has a zone assigned.
        assert all(b.physical_zone is not None for b in blocks)
        by_text = {b.text: b.physical_zone for b in blocks}
        assert by_text["Running header line"] == PhysicalZone.HEADER
        assert by_text["Body paragraph text"] == PhysicalZone.BODY
        assert by_text["Footer line 1"] == PhysicalZone.FOOTER
