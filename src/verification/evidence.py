"""Shared evidence-fusion primitive for RAWRS (FEATURE_019).

Originally built for table detection (src/tables/ — see
docs/DECISIONS_LOG.md's "evidence-fusion architecture" note), and proven
across four independent table detectors before being promoted here as the
generic primitive every semantic object type's verifier uses: a detector/
signal source contributes EvidenceSignal objects describing one specific
piece of evidence for or against a candidate; EvidenceBundle aggregates
them into a weighted confidence score that is:

  - Explainable: the reviewer can inspect every signal that contributed
  - Extensible: new signal sources add signals without changing existing ones
  - Calibrated: weights reflect how much each signal type actually matters

Evidence design: signals use a 0.0-1.0 scale for positive evidence.
Negative evidence (false-positive penalties) uses score < 0.5 combined
with a positive weight, so the penalty pulls confidence downward through
the weighted mean. Alternatively, set weight to a negative value to
invert a positive score into a penalty - both patterns work.

No single source "owns" the decision. Every signal source votes through
signals; the confidence aggregator (this module) decides, and
src/verification/merge.py's decide_from_evidence() turns that confidence
into a KEEP/REPAIR/RECOVER/REMOVE decision.

src/tables/evidence.py re-exports this module unchanged so the table
detectors' existing imports keep working without modification.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EvidenceSignal:
    """One piece of evidence for or against a candidate semantic object.

    name:   Stable snake_case identifier (e.g. "vector_borders",
            "typography_font_size", "running_header_recurrence").
            Displayed to reviewers.

    score:  0.0-1.0. Values close to 1.0 = strong positive evidence
            for the proposed classification. Values close to 0.0 = strong
            evidence against it (used for penalties).

    weight: Relative importance of this signal. All weights must be
            positive. Penalty signals achieve their effect through a
            low score, not a negative weight.

    note:   One-sentence human-readable explanation shown in the
            workspace so reviewers understand each confidence factor.

    source_module: Optional dotted path naming the detector/rule that
            produced this signal (e.g. "src.tables.detectors.
            VectorBorderDetector"), for full audit traceability - see
            docs/ACCESSIBILITY_INTELLIGENCE_ENGINE_DESIGN.md Section 27
            (Rule Provenance). Defaults to None so every existing
            EvidenceSignal(...) construction site keeps behaving
            identically; only new/updated call sites where audit
            traceability is the point need to start populating it.
    """

    name: str
    score: float    # 0.0-1.0
    weight: float   # > 0; larger = more important
    note: str
    source_module: Optional[str] = None


@dataclass
class EvidenceBundle:
    """Collection of evidence signals for one candidate semantic object.

    confidence is the weighted mean of signal scores, clamped [0.0, 1.0].
    """

    signals: List[EvidenceSignal] = field(default_factory=list)

    def add(self, signal: EvidenceSignal) -> None:
        self.signals.append(signal)

    @property
    def confidence(self) -> float:
        """Weighted mean of all signal scores, clamped to [0.0, 1.0]."""
        if not self.signals:
            return 0.0
        total_weight = sum(s.weight for s in self.signals if s.weight > 0)
        if total_weight == 0:
            return 0.0
        weighted = sum(s.score * s.weight for s in self.signals if s.weight > 0)
        return max(0.0, min(1.0, weighted / total_weight))

    @property
    def explanation(self) -> str:
        """Human-readable confidence summary for workspace display."""
        if not self.signals:
            return "confidence=0.00 [no signals]"
        parts = [
            f"{s.name}={s.score:.2f}×{s.weight:.1f} ({s.note})"
            for s in self.signals
        ]
        return f"confidence={self.confidence:.2f} [{'; '.join(parts)}]"

    def to_dict_list(self) -> List[dict]:
        """Serialisable list for API responses and model storage."""
        return [
            {
                "name": s.name,
                "score": round(s.score, 4),
                "weight": round(s.weight, 4),
                "note": s.note,
                "source_module": s.source_module,
            }
            for s in self.signals
        ]

    @staticmethod
    def from_dict_list(data: List[dict]) -> "EvidenceBundle":
        """Reconstruct from serialised form (e.g. loaded from JSON).
        source_module defaults to None via .get() so data serialized before
        this field existed still round-trips."""
        bundle = EvidenceBundle()
        for d in data:
            bundle.add(EvidenceSignal(
                name=d["name"],
                score=d["score"],
                weight=d["weight"],
                note=d["note"],
                source_module=d.get("source_module"),
            ))
        return bundle
