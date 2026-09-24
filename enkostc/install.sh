#!/usr/bin/env bash
# Unpack a manually downloaded EnKoST-C release, then build the bench manifest.
# Idempotent: skips archives already extracted.
#
#   ./enkostc/install.sh                        # tst-COMMON: 27 talks, 2,532 segments, 4.0 h
#   SPLIT=tst-HE ./enkostc/install.sh           # 11 talks, 1.1 h
#
# EnKoST-C is only distributed from ETRI's AI Nanum portal
# (https://nanum.etri.re.kr/share/seungyun/EnKoSTCv10), which needs a browser
# and is often unreachable. Download the release there and drop its archive(s)
# into enkostc/data/ before running this; see README.md.
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
  PYTHON=.venv/bin/python ./enkostc/install.sh
USAGE
  exit 1
fi

SPLIT="${SPLIT:-tst-COMMON}"
mkdir -p data

shopt -s nullglob
archives=(data/*.tar.gz data/*.tgz data/*.tar data/*.zip)
if [[ ${#archives[@]} -eq 0 ]] && [[ -z "$(find data -name "${SPLIT}.yaml" -print -quit)" ]]; then
  cat >&2 <<EOM
[ERROR] nothing in enkostc/data/.
  1. Open https://nanum.etri.re.kr/share/seungyun/EnKoSTCv10 and sign in.
  2. Download the release (at least the ${SPLIT} part).
  3. Put the archive(s) in ${HERE}/data/ and re-run this script.
EOM
  exit 1
fi

for archive in "${archives[@]}"; do
  marker="${archive}.extracted"
  if [[ -f "$marker" ]]; then
    echo "[skip] ${archive} already extracted"
    continue
  fi
  echo "[extract] ${archive}"
  case "$archive" in
    *.zip) unzip -q -o "$archive" -d data ;;
    *) tar xf "$archive" -C data ;;
  esac
  touch "$marker"
done

echo "[convert] split=${SPLIT}"
"${RUN[@]}" convert.py --split "$SPLIT"
