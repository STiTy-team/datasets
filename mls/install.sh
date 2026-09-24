#!/usr/bin/env bash
# Download one MLS language split, then build the bench manifest.
# Idempotent: skips the download when the parquet is already there, and
# convert.py skips clips already decoded.
#
#   ./mls/install.sh                              # german test
#   LANGUAGE=french SPLIT=dev ./mls/install.sh
#
# Public (CC BY 4.0), no Hugging Face account or token needed. Only the chosen
# split is fetched -- german test is ~214 MB; the OpenSLR tarball holds every
# split at once and is 29 GB (opus) or 115 GB (flac).
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
  PYTHON=.venv/bin/python ./mls/install.sh
USAGE
  exit 1
fi

LANGUAGE="${LANGUAGE:-german}"
SPLIT="${SPLIT:-test}"

if compgen -G "data/${LANGUAGE}/${SPLIT}-*.parquet" >/dev/null; then
  echo "[skip] ${LANGUAGE}/${SPLIT} already downloaded"
else
  echo "[download] ${LANGUAGE}/${SPLIT}"
  "${HF[@]}" download facebook/multilingual_librispeech --repo-type dataset \
    --include "${LANGUAGE}/${SPLIT}-*.parquet" --local-dir data
fi

echo "[convert] language=${LANGUAGE} split=${SPLIT}"
"${RUN[@]}" convert.py --language "$LANGUAGE" --split "$SPLIT"
