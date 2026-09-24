#!/usr/bin/env bash
# Download the KsponSpeech evaluation audio and transcripts from AI Hub, extract
# them, then build the bench manifest. Idempotent: skips whatever is already done.
#
#   AIHUB_APIKEY=... ./ksponspeech/install.sh                    # eval_clean: 3,000 utterances, 2.6 h
#   AIHUB_APIKEY=... SPLIT=eval_other ./ksponspeech/install.sh   # eval_other: 3,000 utterances, 3.8 h
#
# AI Hub needs an account, an approved application for dataset 123 (한국어 음성,
# Korean nationals only) and an API key from the AI Hub site. Only the eval zip
# (536 MB) and the scripts zip (24 MB) are fetched, not the 70 GB of training
# audio. See README.md.
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
  PYTHON=.venv/bin/python ./ksponspeech/install.sh
USAGE
  exit 1
fi

SPLIT="${SPLIT:-eval_clean}"
DATASET_KEY=123
# KsponSpeech_eval.zip, KsponSpeech_scripts.zip (`aihubshell -mode l 123`).
FILE_KEYS="50216,50217"

mkdir -p data
cd data

have() { [[ -n "$(find . -name "$1" -print -quit)" ]]; }

if have KsponSpeech_eval.zip && have KsponSpeech_scripts.zip; then
  echo "[skip] eval + scripts zips already downloaded"
else
  if [[ -z "${AIHUB_APIKEY:-}" ]]; then
    cat >&2 <<'EOM'
[ERROR] AIHUB_APIKEY is not set.
  1. Sign in at https://aihub.or.kr and apply for 한국어 음성 (dataSetSn=123).
  2. Once approved, issue an API key on the AI Hub site.
  3. Re-run: AIHUB_APIKEY=<key> ./ksponspeech/install.sh
EOM
    exit 1
  fi
  if [[ ! -x aihubshell ]]; then
    echo "[download] aihubshell"
    curl -fsSL -o aihubshell https://api.aihub.or.kr/api/aihubshell.do
    chmod +x aihubshell
  fi
  echo "[download] KsponSpeech eval + scripts (560 MB)"
  # aihubshell's exit status does not reflect failure, so check for the zips after.
  ./aihubshell -mode d -datasetkey "$DATASET_KEY" -filekey "$FILE_KEYS" \
    -aihubapikey "$AIHUB_APIKEY" || true
  if ! have KsponSpeech_eval.zip || ! have KsponSpeech_scripts.zip; then
    echo "[ERROR] download failed -- is the application for dataset ${DATASET_KEY} approved and the key valid?" >&2
    exit 1
  fi
fi

for zip in KsponSpeech_eval KsponSpeech_scripts; do
  if [[ -f "${zip}.extracted" ]]; then
    echo "[skip] ${zip} already extracted"
    continue
  fi
  echo "[extract] ${zip}"
  unzip -q -o "$(find . -name "${zip}.zip" -print -quit)" -d .
  touch "${zip}.extracted"
done

cd "$HERE"
echo "[convert] split=${SPLIT}"
"${RUN[@]}" convert.py --split "$SPLIT"
