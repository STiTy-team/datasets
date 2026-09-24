#!/usr/bin/env bash
# Download BSTC dev (text + audio), extract it, then build the bench manifest.
# Idempotent: skips whatever is already downloaded and extracted.
#
#   ./bstc/install.sh
#
# Both files are public and need no login: the text from PaddleNLP's mirror, the
# 16 dev talks from the AutoSimTrans 2020 shared-task page (signed URL with no
# expiry). Train audio is only partly public and test was never released; see
# README.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$HERE"

if [[ -n "${PYTHON:-}" ]]; then
  RUN=("$PYTHON")
elif command -v uv >/dev/null 2>&1; then
  RUN=(uv run --project "$REPO" python)
else
  cat >&2 <<'USAGE'
[ERROR] uv not found. Install it:
  curl -LsSf https://astral.sh/uv/install.sh | sh

Or point PYTHON at an interpreter that already has the dependencies:
  PYTHON=.venv/bin/python ./bstc/install.sh
USAGE
  exit 1
fi

TEXT_URL="https://bj.bcebos.com/paddlenlp/datasets/bstc_transcription_translation.tar.gz"
TEXT_MD5="236800188e397c42a3251982aeee48ee"
DEV_URL="http://bj.bcebos.com/v1/ai-studio-online/4e3fce487a3943f0a56e85f4c2b5f6535864ecd434164788a86677700e8118b6?responseContentDisposition=attachment%3B%20filename%3Ddevdata.zip&authorization=bce-auth-v1%2F0ef6765c1e494918bc0d4c3ca3e5c6d1%2F2020-02-19T08%3A00%3A16Z%2F-1%2F%2F98c5e852c7543b6386024fef611c0886fccf07c3855d5581025d368f1b1dd3a2"

mkdir -p data
cd data

if [[ -f bstc_transcription_translation.tar.gz ]]; then
  echo "[skip] text already downloaded"
else
  echo "[download] text"
  curl -fL -o bstc_transcription_translation.tar.gz.part "$TEXT_URL"
  mv bstc_transcription_translation.tar.gz.part bstc_transcription_translation.tar.gz
fi
echo "${TEXT_MD5}  bstc_transcription_translation.tar.gz" | md5sum -c --quiet
if [[ ! -d bstc_transcription_translation ]]; then
  echo "[extract] text"
  tar xzf bstc_transcription_translation.tar.gz
fi

if [[ -f devdata.zip ]]; then
  echo "[skip] dev audio already downloaded"
else
  echo "[download] dev audio (143 MB)"
  curl -fL -o devdata.zip.part "$DEV_URL"
  mv devdata.zip.part devdata.zip
fi
if [[ ! -d devdata ]]; then
  echo "[extract] dev audio"
  unzip -q devdata.zip -x '__MACOSX/*' '*.DS_Store'
fi

cd "$HERE"
echo "[convert] dev"
"${RUN[@]}" convert.py
