#!/usr/bin/env bash
# Download + extract FLEURS, then build the bench manifest.
# Idempotent: safe to re-run, skips anything already downloaded and extracted.
#
#   ./fleurs/install.sh                       # default language set
#   SRC=en_us TGT="ko_kr de_de ja_jp" ./fleurs/install.sh
#   ./fleurs/install.sh ar_eg ko_kr en_us     # download only these, then convert
#
# Needs the `hf` CLI, which uv provides from the repo's `download` dependency
# group. FLEURS is fully public -- no Hugging Face account, token, or
# `hf auth login`. A 401 here means you are looking at a different, gated dataset.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$HERE"

# Dependencies come from the repo's pyproject.toml via uv, which builds the
# environment on demand -- there is no venv to activate and no way to forget.
# Set PYTHON to bypass uv when the dependencies are already on an interpreter.
if [[ -n "${PYTHON:-}" ]]; then
  RUN=("$PYTHON")
  HF=(hf)
elif command -v uv >/dev/null 2>&1; then
  RUN=(uv run --project "$REPO" --group download python)
  HF=(uv run --project "$REPO" --group download hf)
else
  cat >&2 <<'USAGE'
[ERROR] uv not found. Install it:
  curl -LsSf https://astral.sh/uv/install.sh | sh

Or point PYTHON at an interpreter that already has the dependencies:
  PYTHON=.venv/bin/python ./fleurs/install.sh
USAGE
  exit 1
fi

SPLIT="${SPLIT:-test}"
SRC="${SRC:-en_us}"
TGT="${TGT:-ko_kr de_de}"

if [[ $# -gt 0 ]]; then
  LANGS=("$@")
else
  # Source needs audio; targets need only their TSV. Download both here and let
  # convert.py pick what it uses.
  LANGS=("$SRC" $TGT)
fi

if [[ -n "${PYTHON:-}" ]] && ! command -v hf >/dev/null 2>&1; then
  echo "[ERROR] PYTHON is set but the 'hf' CLI is not on PATH." >&2
  echo "        Install it there, or unset PYTHON to let uv provide it." >&2
  exit 1
fi

for lang in "${LANGS[@]}"; do
  tsv="data/${lang}/${SPLIT}.tsv"
  tarball="data/${lang}/audio/${SPLIT}.tar.gz"
  extracted="data/${lang}/audio/${SPLIT}"

  # Only the source language needs audio. Pulling audio for every target would
  # download hundreds of MB per language for files nothing reads.
  if [[ "$lang" == "$SRC" ]]; then
    if [[ -f "$tsv" && -d "$extracted" ]]; then
      echo "[skip] ${lang} (source) already downloaded + extracted"
    else
      echo "[download] ${lang} (source: tsv + audio)"
      "${HF[@]}" download google/fleurs --repo-type dataset \
        --include "data/${lang}/${SPLIT}.tsv" "data/${lang}/audio/${SPLIT}.tar.gz" \
        --local-dir .
      if [[ ! -d "$extracted" ]]; then
        echo "[extract] ${lang}"
        tar xzf "$tarball" -C "data/${lang}/audio/"
      fi
    fi
  else
    if [[ -f "$tsv" ]]; then
      echo "[skip] ${lang} (target) tsv already present"
    else
      echo "[download] ${lang} (target: tsv only)"
      "${HF[@]}" download google/fleurs --repo-type dataset \
        --include "data/${lang}/${SPLIT}.tsv" --local-dir .
    fi
  fi
done

echo
echo "[convert] src=${SRC} tgt=${TGT}"
"${RUN[@]}" convert.py --src "$SRC" --tgt $TGT --split "$SPLIT"
