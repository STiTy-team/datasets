#!/usr/bin/env bash
# Download the noise and room impulse responses bench's `augment` mixes in, then
# write them as noise/<place>/*.wav and room/<place>/*.wav. Idempotent.
#
#   ./augment/install.sh
#
# DEMAND SCAFE comes as one 326 MB zip (md5-checked). Only four RIRs are read out
# of the Arvedi Auditorium zip with HTTP range requests, so it never lands on disk.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$HERE"

if [[ -n "${PYTHON:-}" ]]; then
  RUN=("$PYTHON")
elif command -v uv >/dev/null 2>&1; then
  RUN=(uv run --project "$REPO" --group download python)
else
  cat >&2 <<'USAGE'
[ERROR] uv not found. Install it:
  curl -LsSf https://astral.sh/uv/install.sh | sh

Or point PYTHON at an interpreter that already has the dependencies (and remotezip):
  PYTHON=.venv/bin/python ./augment/install.sh
USAGE
  exit 1
fi

SCAFE_URL="https://zenodo.org/records/1227121/files/SCAFE_48k.zip?download=1"
SCAFE_MD5="1a4ee387f1900f4b15ba219481c76556"
ARVEDI_URL="https://zenodo.org/records/20098848/files/arvedi_auditorium_dataset.zip?download=1"
RECEIVERS="A105 A306 A406 A506"

mkdir -p _src

if [[ -f _src/SCAFE_48k.zip ]] && echo "$SCAFE_MD5  _src/SCAFE_48k.zip" | md5sum -c --status; then
  echo "[skip] DEMAND SCAFE already downloaded"
else
  echo "[download] DEMAND SCAFE_48k.zip (326 MB)"
  curl -fL -C - -o _src/SCAFE_48k.zip.part "$SCAFE_URL"
  echo "$SCAFE_MD5  _src/SCAFE_48k.zip.part" | md5sum -c --status \
    || { echo "[ERROR] SCAFE_48k.zip md5 mismatch" >&2; rm -f _src/SCAFE_48k.zip.part; exit 1; }
  mv _src/SCAFE_48k.zip.part _src/SCAFE_48k.zip
fi

missing=()
for r in $RECEIVERS; do
  [[ -f "_src/rir-S0-${r}.wav" ]] || missing+=("$r")
done
if [[ ${#missing[@]} -eq 0 ]]; then
  echo "[skip] Arvedi RIRs already downloaded"
else
  echo "[download] Arvedi RIRs S0-{${missing[*]}} (range requests)"
  "${RUN[@]}" - "$ARVEDI_URL" "${missing[@]}" <<'PY'
import sys
from pathlib import Path
from remotezip import RemoteZip

url, *receivers = sys.argv[1:]
with RemoteZip(url) as z:
    for r in receivers:
        dest = Path("_src") / f"rir-S0-{r}.wav"
        dest.with_suffix(".part").write_bytes(z.read(f"arvedi_auditorium_dataset/rirs/{dest.name}"))
        dest.with_suffix(".part").replace(dest)
PY
fi

echo "[convert] noise/cafe, room/hall"
"${RUN[@]}" convert.py
