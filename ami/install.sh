#!/usr/bin/env bash
# Download the AMI manual annotations and one wav per meeting, then build the
# bench manifest. Idempotent: skips whatever is already downloaded.
#
#   ./ami/install.sh                      # test: 16 meetings, headset mix, 9 h, 1.1 GB
#   MIC=sdm ./ami/install.sh              # test: first microphone of array 1 (far field)
#   SPLIT=dev ./ami/install.sh            # dev: 18 meetings
#
# Everything comes from the University of Edinburgh's public mirror; no login.
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
  PYTHON=.venv/bin/python ./ami/install.sh
USAGE
  exit 1
fi

SPLIT="${SPLIT:-test}"
MIC="${MIC:-ihm-mix}"
case "$MIC" in
  ihm-mix) STREAM=Mix-Headset ;;
  sdm) STREAM=Array1-01 ;;
  *) echo "[ERROR] MIC must be ihm-mix or sdm" >&2; exit 1 ;;
esac
ANNOTATIONS_URL="https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip"
AUDIO_URL="https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus"

mkdir -p data/audio

if [[ -d data/annotations/words ]]; then
  echo "[skip] annotations already extracted"
else
  echo "[download] annotations (23 MB)"
  curl -fL -o data/annotations.zip.part "$ANNOTATIONS_URL"
  mv data/annotations.zip.part data/annotations.zip
  unzip -q -o data/annotations.zip 'words/*' 'segments/*' 'corpusResources/*' 'LICENCE.txt' \
    -d data/annotations
  rm data/annotations.zip
fi

for meeting in $("${RUN[@]}" convert.py --split "$SPLIT" --list); do
  wav="data/audio/${meeting}.${STREAM}.wav"
  if [[ -f "$wav" ]]; then
    continue
  fi
  echo "[download] ${meeting}.${STREAM}.wav"
  curl -fL --retry 5 -o "${wav}.part" "${AUDIO_URL}/${meeting}/audio/${meeting}.${STREAM}.wav"
  mv "${wav}.part" "$wav"
done

echo "[convert] split=${SPLIT} mic=${MIC}"
"${RUN[@]}" convert.py --split "$SPLIT" --mic "$MIC"
