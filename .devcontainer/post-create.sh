#!/usr/bin/env bash
# Codespaces setup for RAWRS. Mirrors .github/workflows/tests.yml so a
# codespace and CI install the same thing; change both together.
set -euo pipefail

sudo apt-get update
sudo apt-get install -y --no-install-recommends libgl1 libglib2.0-0 pandoc

python -m pip install --upgrade pip
# requirements.lock was frozen on Windows; drop the Windows-only pins.
grep -viE '^(pywin32|win32_setctime)==' requirements.lock > /tmp/requirements.codespace.txt
# CPU-only torch of the pinned version: the default wheel pulls GBs of CUDA.
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.12.1 torchvision==0.27.1
python -m pip install -r /tmp/requirements.codespace.txt -r requirements-dev.txt

# `npm install`, not `npm ci`: see the note in tests.yml (Windows-written lockfile).
(cd frontend && npm install --no-audit --no-fund)

# Claude Code, so work can continue inside the codespace (`claude` to start; sign in on first run).
npm install -g @anthropic-ai/claude-code

echo "RAWRS codespace ready. Backend: uvicorn src.api.main:app --port 8001 · Frontend: cd frontend && npm run dev"
