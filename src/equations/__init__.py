"""Equation remediation (docs/EQUATION_DESIGN.md): pure LaTeX helpers, the
mhchem subset translator and the LaTeX -> Word-equation converter.

Nothing here touches the Document model; ``src/mathpix/ingestor.py`` builds
``Equation`` objects from these helpers and the DOCX projection asks the
converter for OMML."""
