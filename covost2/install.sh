#!/usr/bin/env bash
# Download one CoVoST 2 direction and split, then build the bench manifest.
# Idempotent: skips the download when the parquet is already there, and
# convert.py skips clips already decoded.
#
#   ./covost2/install.sh                          # de_en test (~585 MB)
#   PAIR=en_de ./covost2/install.sh               # en_de test (~670 MB)
#
# Comes from fixie-ai/covost2, a public parquet mirror with the Common Voice 4
# audio embedded. The official route needs Common Voice 4.0 itself, which is now
# released only on request from the Mozilla Data Collective; see README.md.
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
  PYTHON=.venv/bin/python ./covost2/install.sh
USAGE
  exit 1
fi

PAIR="${PAIR:-de_en}"
SPLIT="${SPLIT:-test}"

if compgen -G "data/${PAIR}/${SPLIT}-*.parquet" >/dev/null; then
  echo "[skip] ${PAIR}/${SPLIT} already downloaded"
else
  echo "[download] ${PAIR}/${SPLIT}"
  "${HF[@]}" download fixie-ai/covost2 --repo-type dataset \
    --include "${PAIR}/${SPLIT}-*.parquet" --local-dir data
fi

echo "[convert] pair=${PAIR} split=${SPLIT}"
"${RUN[@]}" convert.py --pair "$PAIR" --split "$SPLIT"
