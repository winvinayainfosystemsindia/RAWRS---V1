"""Image model for RAWRS image/figure extraction.

See docs/VALIDATION_RULES.md (Image Validation) for the checks this
model exists to support: extraction failures, missing image files,
duplicate extractions, and missing figure references.
"""

from typing import Optional

from pydantic import Field, model_validator

from src.models.figure import Figure
from src.models.semantic_object import ProvenanceSource, SemanticObject
from src.models.verification import ImportSource

_IMPORT_SOURCE_TO_PROVENANCE = {
    ImportSource.PDF: ProvenanceSource.PDF_NATIVE,
    ImportSource.MATHPIX: ProvenanceSource.MATHPIX,
    ImportSource.MANUAL: ProvenanceSource.MANUAL_REVIEWER,
}


class Image(SemanticObject):
    """An image or figure extracted from a PDF page.

    ``figure`` is populated when the image has an associated figure
    label/caption (see approved architecture decision #4: Figure is
    composed within Image rather than a sibling top-level entity).

    ``bbox`` (added Phase F.1) is the image's position on its page, in
    the same PyMuPDF page-coordinate system as
    src/models/text_block.py's TextBlock.bbox - this is what makes
    proximity-based figure/caption detection (Phase F.2) possible:
    before this field existed, src/images/image_extractor.py computed
    this exact data internally (for its background-image filter) and
    discarded it, the same discard pattern Phase H's audit found and
    fixed for text. Optional and defaulted to None so existing Image
    construction sites (e.g. a synthetic Image built directly in a
    test) remain valid unchanged.

    ``import_source``/``source_reference``/``uploaded_filename``/
    ``match_confidence``/``match_signal``/``verification_status`` (added
    for the cross-source verification engine, src/verification/) are
    provenance and match-quality facts about the asset itself — kept here
    rather than on Figure, mirroring the existing boundary where
    bbox/file_path/width/height are asset facts and caption/alt_text are
    accessibility facts. ``import_source`` defaults to PDF so every
    existing (pre-verification-engine) Image construction site remains
    valid unchanged; only the Mathpix import path sets MATHPIX.

    Image is the first model migrated onto ``SemanticObject`` (see
    src/models/semantic_object.py). ``import_source``/``ImportSource``
    stays as its own real field rather than being retired in favor of the
    base's ``provenance`` — a genuine cross-file check found existing
    tests constructing ``Image(..., import_source=ImportSource.MATHPIX)``
    and asserting on it directly, so collapsing the two would have broken
    real, passing tests. ``provenance`` is instead kept in sync with
    ``import_source`` (see the validator below) so generic code written
    against ``SemanticObject.provenance`` still works uniformly across
    every migrated type; ``import_source`` remains the field this model's
    own code should keep setting.
    """

    object_type: str = "image"
    image_id: str = Field(..., min_length=1)
    page_number: int = Field(..., ge=1)
    file_path: str = Field(..., min_length=1)
    width: Optional[int] = Field(default=None, ge=0)
    height: Optional[int] = Field(default=None, ge=0)
    figure: Optional[Figure] = None
    extraction_failed: bool = False
    embedded_in_docx: Optional[bool] = None
    # Legacy provenance + cross-source verification fields (src/verification/).
    import_source: ImportSource = ImportSource.PDF
    source_reference: Optional[str] = None
    uploaded_filename: Optional[str] = None
    match_confidence: Optional[float] = None
    match_signal: Optional[str] = None

    @model_validator(mode="after")
    def _backfill_semantic_object_fields(self) -> "Image":
        if self.id is None:
            self.id = self.image_id
        if self.confidence is None:
            self.confidence = self.match_confidence
        # provenance mirrors import_source (the field this model's own
        # code actually sets) so generic SemanticObject-level code sees a
        # consistent value without every call site needing to set both.
        self.provenance = _IMPORT_SOURCE_TO_PROVENANCE.get(self.import_source, ProvenanceSource.PDF_NATIVE)
        return self
