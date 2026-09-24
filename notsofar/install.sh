#!/usr/bin/env bash
# Download the NOTSOFAR-1 ground truth and one far-field channel per meeting,
# then build the bench manifest. Idempotent: skips whatever is already downloaded.
#
#   ./notsofar/install.sh                         # eval_full: 129 meetings, 13.3 h, ~1.5 GB
#   VERSION=eval_small ./notsofar/install.sh      # the CHiME-8 eval set: 80 meetings, 8.3 h
#   DEVICE=mc_plaza_0 ./notsofar/install.sh       # channel 0 of a 7-channel array instead
#
# microsoft/NOTSOFAR on Hugging Face is public; no token needed despite what the
# challenge code asserts. Each meeting holds every device (up to 26 wavs), so the
# ground-truth JSONs come first and then only the one wav convert.py picks.
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
  PYTHON=.venv/bin/python ./notsofar/install.sh
USAGE
  exit 1
fi

VERSION="${VERSION:-eval_full}"
DEVICE="${DEVICE:-sc_meetup_0}"
case "$VERSION" in
  eval_full) SUBSET=eval_set/240825.1_eval_full_with_GT ;;
  eval_small) SUBSET=eval_set/240629.1_eval_small_with_GT ;;
  dev) SUBSET=dev_set/240825.1_dev1 ;;
  *) echo "[ERROR] VERSION must be eval_full, eval_small or dev" >&2; exit 1 ;;
esac

if compgen -G "data/benchmark-datasets/${SUBSET}/MTG/*/gt_transcription.json" >/dev/null; then
  echo "[skip] ${VERSION} ground truth already downloaded"
else
  echo "[download] ${VERSION} ground truth"
  "${HF[@]}" download microsoft/NOTSOFAR --repo-type dataset \
    --include "benchmark-datasets/${SUBSET}/MTG/*/*.json" --local-dir data
fi

wanted=()
while read -r wav; do
  [[ -f "data/${wav}" ]] || wanted+=("$wav")
done < <("${RUN[@]}" convert.py --version "$VERSION" --device "$DEVICE" --list-wavs)
if [[ ${#wanted[@]} -eq 0 ]]; then
  echo "[skip] ${VERSION} ${DEVICE} audio already downloaded"
else
  echo "[download] ${#wanted[@]} meeting wav(s), device ${DEVICE}"
  "${HF[@]}" download microsoft/NOTSOFAR --repo-type dataset "${wanted[@]}" --local-dir data
fi

echo "[convert] version=${VERSION} device=${DEVICE}"
"${RUN[@]}" convert.py --version "$VERSION" --device "$DEVICE"
