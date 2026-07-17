"""RAWRS Accessibility Intelligence Engine.

See docs/ACCESSIBILITY_INTELLIGENCE_ENGINE_DESIGN.md for the full architecture.
Phase 1 (this package, as it stands): engine core (models/registry/scoring/
pipeline) plus every rule marked "Existing" in the design doc's Section 20
taxonomy. Manual attestation generalization (Section 10, beyond the legacy
status fields Phase 1 rules read directly), AI-assisted rules (Section 15),
and the readiness.py/get_export_readiness backward-compatible adapters
(Section 22 roadmap items 3/5) are not yet built - see PHASE_STATUS.md.
"""
