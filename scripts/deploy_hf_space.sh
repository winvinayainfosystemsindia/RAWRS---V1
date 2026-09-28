#!/usr/bin/env bash
# Push the RAWRS backend to a Hugging Face Docker Space.
#
#   HF_TOKEN=hf_xxx scripts/deploy_hf_space.sh <hf-username>/<space-name>
#
# The Space repo gets only what the image needs: Dockerfile, requirements,
# src/ and the Space README (deploy/hf-space/README.md, whose front matter
# tells Spaces to build the Dockerfile and route to port 8001).
set -euo pipefail
space="${1:?usage: HF_TOKEN=... $0 <hf-username>/<space-name>}"
: "${HF_TOKEN:?set HF_TOKEN to a write token from huggingface.co/settings/tokens}"
root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

git clone -q "https://user:${HF_TOKEN}@huggingface.co/spaces/${space}" "$work"
find "$work" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp "$root/Dockerfile" "$root/requirements.txt" "$root/requirements-ai.txt" "$work/"
cp "$root/deploy/hf-space/README.md" "$work/README.md"
cp -r "$root/src" "$work/src"
find "$work/src" -name __pycache__ -prune -exec rm -rf {} +

cd "$work"
git add -A
git -c user.name="rawrs-deploy" -c user.email="deploy@rawrs.local" commit -qm "Deploy RAWRS $(git -C "$root" rev-parse --short HEAD)" || { echo "Nothing changed."; exit 0; }
git push -q
echo "Pushed. Build log: https://huggingface.co/spaces/${space}"
