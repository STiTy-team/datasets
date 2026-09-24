#!/usr/bin/env bash
# Download the TED-LIUM 3 dev or test tarball, extract it, then build the bench
# manifest. Idempotent: skips whatever is already downloaded and extracted.
#
#   ./tedlium/install.sh                  # test: 11 talks, 307 MB
#   SPLIT=dev ./tedlium/install.sh        # dev: 8 talks, 175 MB
#
# OpenSLR and LIUM no longer serve TED-LIUM, and LIUM/tedlium on Hugging Face is
# gone. kfajdsl/tedlium is a public re-upload of the old LIUM tarballs; see
# README.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$HERE"

if [[ -n "${PYTHON:-}" ]]; then
  RUN=("$PYTHON")
  HF=(hf)
elif command -v uv >/dev/null 2>&1; then
  RUN=(uv run --project "$REPO" python)
  HF=(uv run --project "$REPO" --group download hf)
else
  cat >&2 <<'USAGE'
[ERROR] uv not found. Install it:
  curl -LsSf https://astral.sh/uv/install.sh | sh

Or point PYTHON at an interpreter that already has the dependencies:
  PYTHON=.venv/bin/python ./tedlium/install.sh
USAGE
  exit 1
fi

SPLIT="${SPLIT:-test}"
TARBALL="data/TEDLIUM_release3/legacy/${SPLIT}.tar.gz"

if [[ -f "$TARBALL" ]]; then
  echo "[skip] ${SPLIT} tarball already downloaded"
else
  echo "[download] ${SPLIT}"
  "${HF[@]}" download kfajdsl/tedlium --repo-type dataset \
    --include "TEDLIUM_release3/legacy/${SPLIT}.tar.gz" --local-dir data
fi

if [[ -d "data/${SPLIT}" ]]; then
  echo "[skip] ${SPLIT} already extracted"
else
  echo "[extract] ${SPLIT}"
  tar xzf "$TARBALL" -C data
fi

echo "[convert] split=${SPLIT}"
"${RUN[@]}" convert.py --split "$SPLIT"
