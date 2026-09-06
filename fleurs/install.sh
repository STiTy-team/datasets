#!/usr/bin/env bash
# Download + extract the FLEURS languages this dataset repo uses.
# Idempotent: safe to re-run, skips anything already downloaded/extracted.
#
# Usage:
#   ./install.sh                    # default language set (see LANGS below)
#   ./install.sh ar_eg ko_kr en_us  # only these languages
#
# Requires the `hf` CLI (pip install -U huggingface_hub). FLEURS is fully
# public — no Hugging Face account, token, or `hf auth login` needed.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if [[ $# -gt 0 ]]; then
  LANGS=("$@")
else
  LANGS=(en_us de_de ko_kr ja_jp cmn_hans_cn es_419 ar_eg)
fi

if ! command -v hf >/dev/null 2>&1; then
  echo "[ERROR] 'hf' CLI not found on PATH. Install it with: pip install -U huggingface_hub" >&2
  exit 1
fi

for lang in "${LANGS[@]}"; do
  tsv="data/${lang}/test.tsv"
  tarball="data/${lang}/audio/test.tar.gz"
  extracted="data/${lang}/audio/test"

  if [[ -f "$tsv" && -d "$extracted" ]]; then
    echo "[skip] ${lang} already downloaded + extracted"
    continue
  fi

  echo "[download] ${lang}"
  hf download google/fleurs --repo-type dataset \
    --include "data/${lang}/test.tsv" "data/${lang}/audio/test.tar.gz" \
    --local-dir .

  if [[ ! -d "$extracted" ]]; then
    echo "[extract] ${lang}"
    tar xzf "$tarball" -C "data/${lang}/audio/"
  fi
done

echo
echo "done — languages ready:"
for lang in "${LANGS[@]}"; do
  n=$(find "data/${lang}/audio/test" -name '*.wav' 2>/dev/null | wc -l | tr -d ' ')
  echo "  ${lang}: ${n} wav files"
done
