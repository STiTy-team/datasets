#!/usr/bin/env bash
# Fetch the kosp2e split lists and just the wavs they name, then build the bench
# manifest. Idempotent and resumable: wavs already on disk are skipped.
#
#   ./kosp2e/install.sh                   # test: 2,320 wavs, 484 MB
#   PART=dev ./kosp2e/install.sh
#
# The audio lives in one 17 GB zip on Dropbox. Rather than download all of it,
# remotezip reads the zip's index and pulls each wanted member with an HTTP range
# request. One at a time on purpose: Dropbox starts refusing range requests when
# several run in parallel. Expect about an hour for test (53 min for 2,000 wavs).
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
  PYTHON=.venv/bin/python ./kosp2e/install.sh
USAGE
  exit 1
fi

PART="${PART:-test}"
SPLITS_URL="https://raw.githubusercontent.com/warnikchow/kosp2e/main/split"
ZIP_URL="https://www.dropbox.com/s/y74ew1c1evdoxs1/data.zip?dl=1"

mkdir -p data
for corpus in zeroth kss stylekqc covid; do
  xlsx="data/${corpus}_${PART}.xlsx"
  if [[ ! -f "$xlsx" ]]; then
    echo "[download] ${xlsx}"
    curl -fsSL -o "$xlsx" "${SPLITS_URL}/${corpus}_${PART}.xlsx"
  fi
done

echo "[download] ${PART} wavs from the Dropbox zip"
"${FETCH[@]}" - "$PART" "$ZIP_URL" <<'PY'
import sys
import time
from pathlib import Path

import openpyxl
import remotezip

part, url = sys.argv[1], sys.argv[2]
data = Path("data")
want = []
for corpus in ("zeroth", "kss", "stylekqc", "covid"):
    sheet = openpyxl.load_workbook(data / f"{corpus}_{part}.xlsx", read_only=True).active
    want += [f"{corpus}/{row[1]}.wav"
             for row in list(sheet.iter_rows(values_only=True))[1:] if row[1]]
todo = [w for w in want if not (data / w).is_file()]
print(f"  {len(want) - len(todo)} of {len(want)} already here, fetching {len(todo)}",
      flush=True)

zf = None
failed = 0
for i, member in enumerate(todo, start=1):
    for attempt in range(8):
        try:
            if zf is None:
                zf = remotezip.RemoteZip(url)
            # Extract beside the target, then rename: an interrupted run never
            # leaves a truncated wav where a finished one is expected.
            zf.extract(member, data / "partial")
            (data / member).parent.mkdir(exist_ok=True)
            (data / "partial" / member).replace(data / member)
            break
        except Exception as e:
            print(f"  retry {member}: {type(e).__name__}", flush=True)
            zf = None
            time.sleep(min(60, 5 * 2 ** attempt))
    else:
        failed += 1
    if i % 200 == 0:
        print(f"  {i}/{len(todo)}", flush=True)
if failed:
    sys.exit(f"{failed} wav(s) could not be fetched; re-run to retry them")
PY
rm -rf data/partial

echo "[convert] part=${PART}"
"${RUN[@]}" convert.py --part "$PART"
