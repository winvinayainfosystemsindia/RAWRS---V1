"""AI provider implementations for RAWRS.

Each module in this package implements the AIProvider interface from
src/ai/provider.py. The registry (src/ai/registry.py) selects and
caches the best available provider at request time.

Available providers:
  qwen    — Qwen2.5-VL-7B-Instruct (local, vision-capable, GPU or CPU)
  stub    — Deterministic test stub (no model required)
"""
