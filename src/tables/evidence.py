"""Evidence signals for RAWRS table detection.

Each detector contributes EvidenceSignal objects describing one specific
piece of evidence for or against a candidate table region. EvidenceBundle
aggregates signals into a weighted confidence score that is:

  - Explainable: the reviewer can inspect every signal that contributed
  - Extensible: new detectors add signals without changing existing ones
  - Calibrated: weights reflect how much each signal type actually matters

Evidence design: signals use a 0.0–1.0 scale for positive evidence.
Negative evidence (false-positive penalties) uses score < 0.5 combined
with a positive weight, so the penalty pulls confidence downward through
the weighted mean. Alternatively, set weight to a negative value to
invert a positive score into a penalty — both patterns work.

No detector "owns" the table detection decision. Every registered
detector votes through signals; the confidence aggregator decides.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class EvidenceSignal:
    """One piece of evidence for or against a candidate table region.

    name:   Stable snake_case identifier (e.g. "vector_borders",
            "span_column_alignment"). Displayed to reviewers.

    score:  0.0–1.0. Values close to 1.0 = strong positive evidence
            that the region is a table. Values close to 0.0 = strong
            evidence that it is NOT a table (used for penalties).

    weight: Relative importance of this signal. All weights must be
            positive. Penalty signals achieve their effect through a
            low score, not a negative weight.

    note:   One-sentence human-readable explanation shown in the
            workspace so reviewers understand each confidence factor.
    """

    name: str
    score: float    # 0.0–1.0
    weight: float   # > 0; larger = more important
    note: str


@dataclass
class EvidenceBundle:
    """Collection of evidence signals for one candidate table region.

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
            }
            for s in self.signals
        ]

    @staticmethod
    def from_dict_list(data: List[dict]) -> "EvidenceBundle":
        """Reconstruct from serialised form (e.g. loaded from JSON)."""
        bundle = EvidenceBundle()
        for d in data:
            bundle.add(EvidenceSignal(
                name=d["name"],
                score=d["score"],
                weight=d["weight"],
                note=d["note"],
            ))
        return bundle
