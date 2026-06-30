"""Table detector plugins for RAWRS evidence-fusion detection.

Each module in this package implements one TableDetector that contributes
evidence signals to the table detection pipeline. Import the concrete
implementations from their own modules; this package provides no public
API of its own.

Available detectors:
  vector_border    — detects tables with PDF vector border lines (high confidence)
  span_alignment   — detects borderless tables via text span column alignment
  caption          — finds caption text associated with detected regions
"""
