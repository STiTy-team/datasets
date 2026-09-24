#!/usr/bin/env bash
# Download MUSAN (noise and music by default), then mix it into a dataset that
# is already built. Idempotent: skips what is already extracted and mixed.
#
#   ./musan/install.sh                                        # download only
#   SOURCE=fleurs/en_us ./musan/install.sh                    # noise at 0/5/10/15 dB
#   SOURCE=zeroth KIND=music SNRS="5 10" ./musan/install.sh   # -> musan/zeroth.music-snr5/, ...
#   KINDS="noise music speech" ./musan/install.sh             # also the 60 h of babble speech
#
# OpenSLR ships MUSAN as one 11 GB tar.gz. It is streamed and only the wanted
# parts are kept (noise 0.9 GB, music 5 GB, speech 7 GB), so the archive never
# lands on disk -- but an interrupted download restarts from the beginning.
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
  PYTHON=.venv/bin/python ./musan/install.sh
USAGE
  exit 1
fi

KINDS="${KINDS:-noise music}"
KIND="${KIND:-noise}"
SNRS="${SNRS:-0 5 10 15}"
SOURCE="${SOURCE:-}"
# https://www.openslr.org/17/ -- mirrors: openslr.trmal.net, openslr.elda.org,
# openslr.magicdatatech.com (same path).
URL="${MUSAN_URL:-https://www.openslr.org/resources/17/musan.tar.gz}"

mkdir -p data
missing=()
for kind in $KINDS; do
  [[ -f "data/musan/${kind}.extracted" ]] || missing+=("musan/${kind}")
done
if [[ ${#missing[@]} -eq 0 ]]; then
  echo "[skip] MUSAN ${KINDS} already extracted"
else
  echo "[download] MUSAN ${missing[*]} (streaming the 11 GB archive)"
  curl -fL "$URL" | tar xz -C data "${missing[@]}"
  for part in "${missing[@]}"; do
    touch "data/${part}.extracted"
  done
fi

if [[ -z "$SOURCE" ]]; then
  echo "Set SOURCE=<dataset dir> to mix, e.g. SOURCE=fleurs/en_us ./musan/install.sh"
  exit 0
fi
for snr in $SNRS; do
  echo "[convert] source=${SOURCE} kind=${KIND} snr=${snr}"
  "${RUN[@]}" convert.py --source "$SOURCE" --kind "$KIND" --snr "$snr"
done
