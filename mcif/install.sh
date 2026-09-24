#!/usr/bin/env bash
# Download the MCIF long-form audio and references, then build the bench manifest.
# Idempotent: hf download skips files it already has.
#
#   ./mcif/install.sh                     # en -> de, zh
#   TGT="de it zh" ./mcif/install.sh
#
# Public (CC BY 4.0), no Hugging Face account needed. Fetches only the 100 talk
# wavs (1.1 GB) and the reference XMLs -- a plain clone also pulls 6.4 GB of video.
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
  PYTHON=.venv/bin/python ./mcif/install.sh
USAGE
  exit 1
fi

TGT="${TGT:-de zh}"

echo "[download] FBK-MT/MCIF long audio + references"
# One --include with both patterns: repeating the flag keeps only the last one.
"${HF[@]}" download FBK-MT/MCIF --repo-type dataset \
  --include "MCIF.long.*.ref.xml.gz" "MCIF_DATA/LONG_AUDIOS/*" \
  --local-dir data

echo "[convert] tgt=${TGT}"
"${RUN[@]}" convert.py --tgt $TGT
