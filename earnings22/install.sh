#!/usr/bin/env bash
# Download the Earnings-22 calls and segment table, then build the bench
# manifest. Idempotent: skips whatever is already downloaded.
#
#   ./earnings22/install.sh                       # all 125 calls, 119 h, 1.9 GB of mp3
#   SUBSET=subset10 ./earnings22/install.sh       # 10 calls, 11 h
#
# The mp3s are git-lfs objects in revdotcom/speech-datasets, served one by one
# from media.githubusercontent.com -- no git or git-lfs needed. The segment
# table comes from distil-whisper/earnings22 without its audio; see README.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$HERE"

if [[ -n "${PYTHON:-}" ]]; then
  RUN=("$PYTHON")
  FETCH=("$PYTHON")
elif command -v uv >/dev/null 2>&1; then
  RUN=(uv run --project "$REPO" python)
  FETCH=(uv run --project "$REPO" --group download python)
else
  cat >&2 <<'USAGE'
[ERROR] uv not found. Install it:
  curl -LsSf https://astral.sh/uv/install.sh | sh

Or point PYTHON at an interpreter that already has the dependencies:
  PYTHON=.venv/bin/python ./earnings22/install.sh
USAGE
  exit 1
fi

SUBSET="${SUBSET:-}"
RAW="https://raw.githubusercontent.com/revdotcom/speech-datasets/main/earnings22"
MEDIA="https://media.githubusercontent.com/media/revdotcom/speech-datasets/main/earnings22/media"

mkdir -p data/media

if [[ -f data/metadata.csv ]]; then
  echo "[skip] metadata.csv already downloaded"
else
  echo "[download] metadata.csv"
  curl -fsSL -o data/metadata.csv.part "${RAW}/metadata.csv"
  mv data/metadata.csv.part data/metadata.csv
fi

if [[ -f data/segments.jsonl ]]; then
  echo "[skip] segment table already downloaded"
else
  echo "[download] segment table (text columns of distil-whisper/earnings22)"
  "${FETCH[@]}" fetch_segments.py
fi

for call in $("${RUN[@]}" convert.py ${SUBSET:+--subset "$SUBSET"} --list); do
  mp3="data/media/${call}.mp3"
  [[ -f "$mp3" ]] && continue
  echo "[download] ${call}.mp3"
  curl -fL --retry 5 -o "${mp3}.part" "${MEDIA}/${call}.mp3"
  mv "${mp3}.part" "$mp3"
done

echo "[convert] ${SUBSET:-all calls}"
"${RUN[@]}" convert.py ${SUBSET:+--subset "$SUBSET"}
