"""M-1 — an image python-docx cannot read is normalized, not dropped.

python-docx recognizes an image only by a literal signature: ``\\x89PNG`` and
friends at offset 0, or ``JFIF``/``Exif`` at offset 6 for a JPEG. A readable
image whose container lacks the expected marker raised UnrecognizedImageError
and was silently dropped — measured on the Mathpix corpus as 18 of 18 supplied
figures, every one a plain RGB JPEG beginning ``FF D8 FF DB``.

The repair asks the real question ("can python-docx read this?") instead of the
proxy one the CMYK repair asked ("is this CMYK?"). These tests pin both halves:
a file python-docx accepts is handed over untouched, and one it rejects is
normalized through Pillow into a format it accepts — PNG where the pixels need
alpha, JPEG otherwise — with dimensions preserved either way.
"""

import io
from pathlib import Path

from docx import Document as DocxDocument
from PIL import Image as PILImage

from src.docx.docx_generator import (
    _add_image,
    _docx_compatible_picture_source,
    _python_docx_reads,
)

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _strip_jfif(jpeg_bytes: bytes) -> bytes:
    """The same container shape Mathpix supplies: SOI followed straight by the
    next segment, with Pillow's APP0/JFIF header removed."""
    assert jpeg_bytes[:2] == b"\xff\xd8"
    assert jpeg_bytes[2:4] == b"\xff\xe0", "expected Pillow to write an APP0 segment"
    segment_length = int.from_bytes(jpeg_bytes[4:6], "big")
    return jpeg_bytes[:2] + jpeg_bytes[2 + 2 + segment_length :]


def _write(
    path: Path, image: PILImage.Image, image_format: str, strip: bool = False
) -> Path:
    buffer = io.BytesIO()
    image.save(buffer, format=image_format)
    data = _strip_jfif(buffer.getvalue()) if strip else buffer.getvalue()
    path.write_bytes(data)
    return path


def _bare_jpeg(path: Path, size=(40, 30), mode="RGB") -> Path:
    colour = 128 if mode in ("L", "1") else (200, 30, 30)
    return _write(path, PILImage.new(mode, size, colour), "JPEG", strip=True)


def _drawings(document: DocxDocument) -> list:
    return [
        p for p in document.element.body.iter(f"{_W}p") if list(p.iter(f"{_A}graphic"))
    ]


def _embed(tmp_path: Path, image_path: Path, alt: str = "alt") -> tuple:
    """Run the real embedding path; return (result, drawing count, extent)."""
    document = DocxDocument()
    embedded = _add_image(document, str(image_path), alt_text=alt)
    out = tmp_path / "out.docx"
    document.save(str(out))
    reopened = DocxDocument(str(out))
    drawings = _drawings(reopened)
    extent = None
    if drawings:
        inline = next(iter(drawings[0].iter(f"{_A}ext")), None)
        extent = None if inline is None else (inline.get("cx"), inline.get("cy"))
    return embedded, len(drawings), extent


class TestTheFastPath:
    def test_a_valid_jpeg_is_handed_over_untouched(self, tmp_path):
        """Nothing is re-encoded when python-docx can already read the file —
        no generation loss, and the file on disk stays the source of truth."""
        path = _write(
            tmp_path / "ok.jpg", PILImage.new("RGB", (40, 30), (1, 2, 3)), "JPEG"
        )
        assert _python_docx_reads(path) is True
        assert _docx_compatible_picture_source(path) == str(path)

    def test_a_valid_png_is_handed_over_untouched(self, tmp_path):
        path = _write(
            tmp_path / "ok.png", PILImage.new("RGB", (40, 30), (1, 2, 3)), "PNG"
        )
        assert _python_docx_reads(path) is True
        assert _docx_compatible_picture_source(path) == str(path)


class TestNormalisation:
    def test_a_jpeg_with_no_jfif_marker_embeds(self, tmp_path):
        """The Mathpix case: readable RGB pixels, unreadable container."""
        path = _bare_jpeg(tmp_path / "bare.jpg")
        assert path.read_bytes()[:4] == b"\xff\xd8\xff\xdb"
        assert _python_docx_reads(path) is False

        source = _docx_compatible_picture_source(path)
        assert isinstance(source, io.BytesIO)

        embedded, drawings, _ = _embed(tmp_path, path)
        assert embedded is True and drawings == 1

    def test_an_alpha_image_becomes_png_and_keeps_its_alpha(self, tmp_path):
        """JPEG cannot store alpha — Pillow raises rather than flattening — so
        transparency decides the format, not a preference."""
        path = tmp_path / "alpha.tga"  # a container python-docx does not read
        PILImage.new("RGBA", (40, 30), (255, 0, 0, 128)).save(str(path))
        assert _python_docx_reads(path) is False

        source = _docx_compatible_picture_source(path)
        assert isinstance(source, io.BytesIO)
        with PILImage.open(source) as normalized:
            assert normalized.format == "PNG"
            assert normalized.mode in ("RGBA", "LA", "PA", "P")

        embedded, drawings, _ = _embed(tmp_path, path)
        assert embedded is True and drawings == 1

    def test_a_palette_image_becomes_png(self, tmp_path):
        path = tmp_path / "palette.tga"
        PILImage.new("P", (40, 30)).save(str(path))
        source = _docx_compatible_picture_source(path)
        assert isinstance(source, io.BytesIO)
        with PILImage.open(source) as normalized:
            assert normalized.format == "PNG"

    def test_a_grayscale_image_embeds(self, tmp_path):
        path = _bare_jpeg(tmp_path / "gray.jpg", mode="L")
        assert _python_docx_reads(path) is False
        source = _docx_compatible_picture_source(path)
        assert isinstance(source, io.BytesIO)
        with PILImage.open(source) as normalized:
            assert normalized.format == "JPEG"
        embedded, drawings, _ = _embed(tmp_path, path)
        assert embedded is True and drawings == 1

    def test_dimensions_survive_normalisation(self, tmp_path):
        """Aspect ratio is what _MAX_IMAGE_WIDTH scaling and the rendered
        figure both depend on, and no branch here may change it."""
        path = _bare_jpeg(tmp_path / "wide.jpg", size=(120, 40))
        source = _docx_compatible_picture_source(path)
        with PILImage.open(source) as normalized:
            assert normalized.size == (120, 40)

        _, drawings, extent = _embed(tmp_path, path)
        assert drawings == 1
        cx, cy = int(extent[0]), int(extent[1])
        assert abs((cx / cy) - 3.0) < 0.01


class TestPreservedBehaviour:
    def test_cmyk_keeps_the_path_it_has_always_taken(self, tmp_path):
        """CMYK converts to RGB and saves JPEG, exactly as the CMYK repair
        did — and it cannot go to PNG, which has no CMYK representation."""
        path = tmp_path / "cmyk.jpg"
        PILImage.new("CMYK", (40, 30), (10, 20, 30, 40)).save(str(path))
        assert _python_docx_reads(path) is False

        source = _docx_compatible_picture_source(path)
        assert isinstance(source, io.BytesIO)
        with PILImage.open(source) as normalized:
            assert normalized.format == "JPEG"
            assert normalized.mode == "RGB"
            assert normalized.size == (40, 30)

        embedded, drawings, _ = _embed(tmp_path, path)
        assert embedded is True and drawings == 1

    def test_an_unreadable_file_still_fails_the_way_it_always_did(self, tmp_path):
        """Not a crash, not a normalisation: _add_image reports False so
        IMAGE_005 can surface the drop."""
        path = tmp_path / "broken.jpg"
        path.write_bytes(b"\xff\xd8\xff\xdb not an image at all")
        assert _docx_compatible_picture_source(path) == str(path)

        embedded, drawings, _ = _embed(tmp_path, path)
        assert embedded is False and drawings == 0

    def test_a_missing_file_still_reports_failure(self, tmp_path):
        embedded, drawings, _ = _embed(tmp_path, tmp_path / "nope.jpg")
        assert embedded is False and drawings == 0
