"""Equations: the twelfth registered asset type (docs/EQUATION_DESIGN.md §2).

A reviewer's change to an equation — its LaTeX, its number, its description —
is an ordinary correction, performed here through ``engine.apply_correction``
and undone by ``SemanticVerifier.revert()``'s generic swap. Nothing parses
Markdown or DOCX back: both projections read ``Equation`` from the Semantic
Document.

**Single source.** An equation's LaTeX is this document's own, so there is no
second source to reconcile it with and no question RAWRS could ask about it:
this verifier carries the reviewer's answer and proposes nothing. The review
queue comes from ``EQUATION_001`` in ``src/validation/validator.py``, one
issue per FLAGGED equation.

**Status is derived, never edited.** A LaTeX edit re-runs the same
``prepare()`` ingest used, so a flagged equation the reviewer fixes becomes
CONVERTED and one they break is flagged again — and reverting restores the old
LaTeX, whose status is derived the same way. (A DOCX-time conversion failure is
re-derived on the next generation.)

**Inline equations keep their paragraph in step.** The paragraph's text holds
the equation's Unicode rendering at ``anchor_offset``; changing the LaTeX
changes the rendering, so the paragraph text, the later anchors of its other
equations and the anchors of notes that point into it move together.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.equations.build import prepare
from src.models.correction import CorrectionRecord
from src.models.equation import Equation
from src.verification.base import SemanticVerifier
from src.verification.matching import MatchResult, MultiSignalMatcher

ASSET_TYPE = "equation"

#: The fields a reviewer can change. One kind each, because the verifier's
#: ``apply()`` dispatches on ``CorrectionRecord.field``.
LATEX_EDIT = "latex"
NUMBER_EDIT = "number"
DESCRIPTION_EDIT = "description"


class EquationVerifier(SemanticVerifier):
    asset_type = ASSET_TYPE

    def build_pdf_matcher(self) -> MultiSignalMatcher:
        """No second source — the default every single-source verifier uses."""
        return MultiSignalMatcher([])

    def to_canonical(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """An edit creates no equation; it changes one that exists."""
        return []

    def classify(self, match_result: MatchResult, **context: Any) -> List[Any]:
        """Not a producer; see the module docstring."""
        return []

    def rule_table(self) -> Dict[str, Any]:
        from src.models.verification import RuleSpec

        return {
            LATEX_EDIT: RuleSpec(
                rule_id="EQUATION_002", reason_code="EQUATION_LATEX_EDITED_BY_REVIEWER", severity="info"
            ),
            NUMBER_EDIT: RuleSpec(
                rule_id="EQUATION_003", reason_code="EQUATION_NUMBER_EDITED_BY_REVIEWER", severity="info"
            ),
            DESCRIPTION_EDIT: RuleSpec(
                rule_id="EQUATION_004",
                reason_code="EQUATION_DESCRIPTION_EDITED_BY_REVIEWER",
                severity="info",
            ),
        }

    def apply(self, document: Any, correction: CorrectionRecord) -> None:
        """Set the named field to ``proposed_value``.

        Symmetric and idempotent, so the generic ``revert()`` swap restores the
        previous value with no equation-specific undo. A correction naming an
        equation that is gone is a no-op, as for every other verifier.
        """
        equation = next(
            (e for e in (getattr(document, "equations", []) or []) if e.id == correction.object_id),
            None,
        )
        if equation is None:
            return
        value = correction.proposed_value
        if correction.field == LATEX_EDIT:
            _set_latex(document, equation, value)
        elif correction.field == NUMBER_EDIT:
            equation.number = value.strip() or None
            _restate(equation)
        elif correction.field == DESCRIPTION_EDIT:
            equation.description = value.strip() or None


def _restate(equation: Equation) -> None:
    """Re-derive status, reasons and text from the equation's current LaTeX."""
    prepared = prepare(
        equation.latex,
        numbered_without_tag=equation.numbered_environment and equation.number is None,
    )
    equation.latex = prepared.latex or equation.latex
    equation.status = prepared.status
    equation.flag_reasons = list(prepared.reasons)
    if prepared.before:
        equation.before_text = prepared.before
    if prepared.after:
        equation.after_text = prepared.after
    equation.text = prepared.text


def _set_latex(document: Any, equation: Equation, latex: str) -> None:
    old_text, old_length = equation.text, equation.anchor_length or 0
    equation.latex = latex
    _restate(equation)
    if not equation.display:
        _resize_inline(document, equation, old_text, old_length)


def _resize_inline(document: Any, equation: Equation, old_text: str, old_length: int) -> None:
    """Keep the paragraph, sibling anchors and note anchors in step with a new rendering."""
    paragraph = next(
        (p for p in (document.paragraphs or []) if p.id == equation.paragraph_id), None
    )
    start: Optional[int] = equation.anchor_offset
    if paragraph is None or start is None or paragraph.text[start:start + old_length] != old_text:
        return
    new_length = len(equation.text)
    delta = new_length - old_length
    previous = paragraph.text
    paragraph.text = previous[:start] + equation.text + previous[start + old_length:]
    equation.anchor_length = new_length
    for other in document.equations:
        if other is not equation and other.paragraph_id == paragraph.id:
            if other.anchor_offset is not None and other.anchor_offset > start:
                other.anchor_offset += delta
    for note in document.footnotes:
        if note.anchor_text != previous:
            continue
        note.anchor_text = paragraph.text
        if note.anchor_offset is not None and note.anchor_offset >= start + old_length:
            note.anchor_offset += delta


def _register() -> None:
    from src.verification.engine import engine

    engine.register(EquationVerifier())


_register()
