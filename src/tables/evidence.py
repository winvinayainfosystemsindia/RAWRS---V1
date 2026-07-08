"""Re-export shim (FEATURE_019).

EvidenceSignal/EvidenceBundle moved to src/verification/evidence.py once
they became the shared evidence-fusion primitive for every semantic object
type, not just tables. Kept here so existing imports
(`from src.tables.evidence import EvidenceBundle, EvidenceSignal`) across
the table detectors keep working unchanged. Prefer importing from
src.verification.evidence in new code.
"""

from src.verification.evidence import EvidenceBundle, EvidenceSignal

__all__ = ["EvidenceBundle", "EvidenceSignal"]
