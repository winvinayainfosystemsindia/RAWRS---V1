"""F0 — Benchmark Differ (read-only measurement infrastructure).

This package is NOT part of the production remediation pipeline and is imported
by nothing under src/ outside this package. It exists to compare RAWRS output
against the human-remediated benchmark corpus (samples/benchmark/remediated_docx)
and emit a structured, machine-readable remediation-gap report that later
implementation stages use as their regression specification.

See docs/RAWRS_AUTONOMOUS_REMEDIATION_BLUEPRINT.md §2.1 / F0.
"""
