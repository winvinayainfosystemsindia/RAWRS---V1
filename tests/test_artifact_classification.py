"""L2 — artifact classification (additive, evidence-driven).

Unit-tests classify_artifacts over blocks carrying L1 evidence (physical zone +
repetition) and confirms structure_detector wires it into the real extraction
path. Additive: no consumer reads TextBlock.artifact yet.
"""

import fitz

from src.models.bounding_box import BoundingBox
from src.models.contracts import ArtifactClass, TextBlock
from src.models.text_block import PhysicalZone, RepetitionEvidence
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
        # The body text must differ by more than a digit: since L2.3-b, lines
        # that differ only in a number share one normalized family, and three
        # of those at an identical y IS a running head carrying its page number.
        for words in ("apples pears", "rivers valleys", "copper tin"):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 40), "Running Header Line")
            page.insert_text((72, 400), f"Unique body {words}")
        path = tmp_path / "art.pdf"
        doc.save(str(path))

        document = detect_structure(parse_pdf(str(path)))

        headers = [b for b in document.blocks if b.text.strip() == "Running Header Line"]
        assert headers and all(b.artifact is not None for b in headers)
        assert headers[0].artifact.artifact_class == ArtifactClass.RUNNING_HEADER
        body = next(b for b in document.blocks if b.text.strip().startswith("Unique body"))
        assert body.artifact is None


def _blk_rep(text, zone, pages, stability):
    """A block carrying a hand-built RepetitionEvidence, so a test can pin an
    exact positional_stability rather than reverse-engineer y-positions."""
    b = TextBlock(page_number=pages[0], text=text, bbox=BoundingBox(x0=72, y0=400, x1=300, y1=412), order=0)
    b.physical_zone = zone
    b.repetition = RepetitionEvidence(
        signature=" ".join(text.lower().split()).strip(),
        recurrence_count=len(pages),
        page_numbers=sorted(pages),
        recurrence_ratio=round(len(pages) / max(pages), 4),
        positional_stability=stability,
        alternation=None,
    )
    return b


class TestRunningTitleClassification:
    """L2.1 — recurring running titles the tight-band stability gate misses.

    A multi-word phrase recurring across several pages is a running artifact
    even when its y-band is looser than _ARTIFACT_MIN_STABILITY (0.5); the
    recurrence compensates. The per-block zone still names the class, so the
    same title is caught on every page whichever zone that occurrence lands in.
    Thresholds derived from the benchmark distribution (running titles: stability
    0.29-0.40, multi-word; noise: <= 0.19 or single tokens).
    """

    def test_body_low_stability_multiword_is_running_title(self):
        b = _blk_rep("The Culture of Education", PhysicalZone.BODY, [1, 4, 6, 8], 0.40)
        classify_artifacts([b], {})
        assert b.artifact is not None
        assert b.artifact.artifact_class == ArtifactClass.RUNNING_TITLE
        assert any("multi-word" in e for e in b.artifact.evidence)

    def test_header_low_stability_multiword_is_running_header(self):
        # The same title on pages where it lands in the HEADER band must also
        # be caught (as RUNNING_HEADER), so every occurrence is classified.
        b = _blk_rep("The Culture of Education", PhysicalZone.HEADER, [2, 3, 5], 0.30)
        classify_artifacts([b], {})
        assert b.artifact.artifact_class == ArtifactClass.RUNNING_HEADER

    def test_single_word_recurrence_not_classified(self):
        # 'professional' recurs but is a single token (body-word noise).
        b = _blk_rep("professional", PhysicalZone.BODY, [1, 2, 3, 4, 5], 0.30)
        classify_artifacts([b], {})
        assert b.artifact is None

    def test_below_stability_floor_not_classified(self):
        # Scattered repeat (stability below the 0.25 noise floor).
        b = _blk_rep("of professionalism", PhysicalZone.BODY, [1, 2, 3], 0.15)
        classify_artifacts([b], {})
        assert b.artifact is None

    def test_two_page_recurrence_not_classified(self):
        # Needs >= 3 distinct pages; a 2-page repeat is not pervasive enough.
        b = _blk_rep("the teacher as a person", PhysicalZone.BODY, [1, 2], 0.40)
        classify_artifacts([b], {})
        assert b.artifact is None

    def test_high_stability_body_still_decorative_repeated(self):
        # Existing behaviour is unchanged: a tightly-banded (>=0.5) BODY repeat
        # is DECORATIVE_REPEATED, not RUNNING_TITLE.
        b = _blk_rep("Confidential Draft Watermark", PhysicalZone.BODY, [1, 2, 3], 0.80)
        classify_artifacts([b], {})
        assert b.artifact.artifact_class == ArtifactClass.DECORATIVE_REPEATED


class TestRunningFurniturePromotion:
    """L2.3-c — a tightly-banded BODY repeat that covers much of the document.

    DECORATIVE_REPEATED is where a running head lands when the header band
    missed it. That bucket's NEVER policy is right for what it usually holds —
    repeated body fragments — so the promotion has to separate the two
    populations rather than loosen the bucket. Measured over the benchmark
    corpus they do not overlap: every false positive spans 2 pages at
    stability <= 0.8547, the true furniture 8-9 pages at 1.0.
    """

    def test_promotes_at_the_stability_boundary(self):
        b = _blk_rep("Understanding resistance to conservation", PhysicalZone.BODY,
                     [1, 3, 5], 0.90)
        classify_artifacts([b], {})
        assert b.artifact.artifact_class == ArtifactClass.RUNNING_TITLE

    def test_does_not_promote_just_below_the_boundary(self):
        b = _blk_rep("Understanding resistance to conservation", PhysicalZone.BODY,
                     [1, 3, 5], 0.89)
        classify_artifacts([b], {})
        assert b.artifact.artifact_class == ArtifactClass.DECORATIVE_REPEATED

    def test_two_pages_never_promote_however_stable(self):
        """Every corpus false positive spans exactly two pages."""
        b = _blk_rep("for children.", PhysicalZone.BODY, [1, 3], 1.0)
        classify_artifacts([b], {})
        assert b.artifact.artifact_class == ArtifactClass.DECORATIVE_REPEATED

    def test_single_word_family_never_promotes(self):
        b = _blk_rep("practice.", PhysicalZone.BODY, [1, 3, 5], 1.0)
        classify_artifacts([b], {})
        assert b.artifact.artifact_class == ArtifactClass.DECORATIVE_REPEATED

    def test_three_pages_two_words_full_stability_promotes(self):
        b = _blk_rep("George Holmes", PhysicalZone.BODY, [1, 3, 5], 1.0)
        classify_artifacts([b], {})
        assert b.artifact.artifact_class == ArtifactClass.RUNNING_TITLE

    def test_alternation_alone_never_promotes(self):
        """'for children.' (even) and 'practice.' (odd) both alternate cleanly
        on the corpus, because any two-page family shares parity about half the
        time. Alternation is recorded and never decisive.
        """
        b = _blk_rep("for children.", PhysicalZone.BODY, [2, 4], 0.8547)
        classify_artifacts([b], {})
        assert b.artifact.artifact_class == ArtifactClass.DECORATIVE_REPEATED

    def test_every_occurrence_of_a_family_agrees(self):
        blocks = [_blk("Understanding resistance to conservation / %d" % (184 + p),
                       p, 124.0, 0, PhysicalZone.BODY) for p in (2, 4, 6, 8)]
        _classified(blocks)
        assert {b.artifact.artifact_class for b in blocks} == {ArtifactClass.RUNNING_TITLE}

    def test_classification_suppresses_nothing(self):
        blocks = [_blk("Understanding resistance to conservation / %d" % (184 + p),
                       p, 124.0, 0, PhysicalZone.BODY) for p in (2, 4, 6, 8)]
        _classified(blocks)
        assert not any(b.suppressed for b in blocks)


class TestNormalizedEvidenceRoute:
    """The route may only reach BODY-zone, multi-word families."""

    def test_page_number_bearing_header_is_seen_through_normalization(self):
        blocks = [_blk("Understanding resistance to conservation / %d" % (184 + p),
                       p, 124.0, 0, PhysicalZone.BODY) for p in (2, 4, 6, 8)]
        _classified(blocks)
        assert blocks[0].repetition is None          # the literal text differs per page
        assert blocks[0].repetition_normalized is not None
        assert blocks[0].artifact.artifact_class == ArtifactClass.RUNNING_TITLE
        assert any("tolerant signature" in e for e in blocks[0].artifact.evidence)

    def test_literal_evidence_is_never_replaced(self):
        blocks = [_blk("/ George Holmes", p, 124.0, 0, PhysicalZone.BODY)
                  for p in (1, 3, 5, 7)]
        _classified(blocks)
        assert blocks[0].repetition.signature == "/ george holmes"
        assert blocks[0].repetition_normalized is None
        assert blocks[0].artifact.artifact_class == ArtifactClass.RUNNING_TITLE

    def test_normalized_route_never_reaches_an_auto_class(self):
        """Unconstrained, this auto-suppressed a real corpus line — Bruner's
        'NOTES TO PAGES 60-71', off two pages, through the HEADER zone.
        """
        blocks = [_blk("NOTES TO PAGES %d-%d" % (40 + p, 50 + p), p, 20.0, 0,
                       PhysicalZone.HEADER) for p in (1, 2, 3)]
        _classified(blocks)
        assert all(b.artifact is None for b in blocks)

    def test_bare_numeric_family_is_left_to_page_number(self):
        blocks = [_blk(str(184 + p), p, 124.0, 0, PhysicalZone.BODY) for p in (1, 3, 5)]
        _classified(blocks)
        assert all(b.artifact is None for b in blocks)


class TestPolicyTiersUnchanged:
    def test_running_title_proposes_and_never_auto_applies(self):
        from src.verification.artifacts import SuppressionPolicy, _POLICY

        assert _POLICY[ArtifactClass.RUNNING_TITLE] == SuppressionPolicy.PROPOSE
        assert _POLICY[ArtifactClass.DECORATIVE_REPEATED] == SuppressionPolicy.NEVER
        assert _POLICY[ArtifactClass.RUNNING_HEADER] == SuppressionPolicy.AUTO
