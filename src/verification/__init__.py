"""Generic cross-source verification framework.

This package is asset-agnostic: it knows nothing about figures, headings,
tables, or any other RAWRS domain object.  `matching.py` provides a
priority-cascade multi-signal matcher; `base.py` defines the `AssetVerifier`
protocol every asset type implements; `engine.py` is the registry that
dispatches to whichever verifiers have registered themselves and translates
their findings into the existing `CorrectionRecord` / `ValidationIssue`
surfaces.

Figures (`src/verification/figures.py`) are the first registered asset type.
Future asset types (headings, footnotes, tables, equations, diagrams, ...)
register their own `AssetVerifier` the same way, without requiring any
change to this package or to `src/validation/validator.py`.
"""
