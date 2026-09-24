#!/usr/bin/env bash
# Download the Zeroth-Korean parquet shards, then build the bench manifest.
# Idempotent: skips whatever is already downloaded.
#
#   ./zeroth/install.sh                   # test: 457 utterances, 10 speakers, 1.2 h
#   SPLIT=train ./zeroth/install.sh       # train: 22,263 utterances, 51.6 h
#
# The OpenSLR 40 tarball is 10 GB because it bundles the LM and lexicon; the
# kresnik/zeroth_korean mirror carries just the audio and text as parquet, with
# the original utterance and speaker ids. See README.md.
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
  PYTHON=.venv/bin/python ./zeroth/install.sh
USAGE
  exit 1
fi

SPLIT="${SPLIT:-test}"

if compgen -G "data/data/${SPLIT}-*.parquet" >/dev/null; then
  echo "[skip] ${SPLIT} already downloaded"
else
  echo "[download] ${SPLIT}"
  "${HF[@]}" download kresnik/zeroth_korean --repo-type dataset \
    --include "data/${SPLIT}-*.parquet" --local-dir data
fi

echo "[convert] split=${SPLIT}"
"${RUN[@]}" convert.py --split "$SPLIT"
