#!/usr/bin/env bash
# ACL 60/60 -> bench manifest.
#
# Nothing is downloaded here: the release comes from the ACL 60/60 page and the
# archive layout has changed between drops. Fetch it, extract it into acl6060/,
# then run this.
#
#   ./acl6060/install.sh
#   SPLIT=dev TGT="de ja" ./acl6060/install.sh
#
# Expected layout after extraction:
#   acl6060/acl_6060/<split>/{text/xml,full_wavs,segmented_wavs/gold}
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$HERE"

# Dependencies come from the repo's pyproject.toml via uv, which builds the
# environment on demand -- there is no venv to activate and no way to forget.
# Set PYTHON to bypass uv when the dependencies are already on an interpreter.
if [[ -n "${PYTHON:-}" ]]; then
  RUN=("$PYTHON")
elif command -v uv >/dev/null 2>&1; then
  RUN=(uv run --project "$REPO" python)
else
  cat >&2 <<'USAGE'
[ERROR] uv not found. Install it:
  curl -LsSf https://astral.sh/uv/install.sh | sh

Or point PYTHON at an interpreter that already has the dependencies:
  PYTHON=.venv/bin/python ./acl6060/install.sh
USAGE
  exit 1
fi

SPLIT="${SPLIT:-eval}"
TGT="${TGT:-de}"

if [[ ! -d "acl_6060/${SPLIT}" ]]; then
  cat >&2 <<USAGE
[ERROR] expected ${HERE}/acl_6060/${SPLIT} to exist.

Obtain the ACL 60/60 release and extract it here so that
  ${HERE}/acl_6060/${SPLIT}/{text,full_wavs,segmented_wavs}
exists. See acl6060/README.md.
USAGE
  exit 1
fi

# The release ships no timestamps. They are recovered by byte-matching each gold
# sentence wav inside its full talk wav -- exact, not approximate. The recovery
# script lives in the STiTy checkout.
if [[ ! -f "timings_${SPLIT}.json" ]]; then
  STITY="${STITY_REPO:-$HERE/../../STiTy}"
  RECOVER="$STITY/evaluation/ast/recover_acl6060_timings.py"
  if [[ ! -f "$RECOVER" ]]; then
    cat >&2 <<USAGE
[ERROR] timings_${SPLIT}.json is missing and the recovery script was not found at
  $RECOVER

Point STITY_REPO at your STiTy checkout and re-run, or generate it yourself:
  python evaluation/ast/recover_acl6060_timings.py --split ${SPLIT} --acl-root ${HERE}
USAGE
    exit 1
  fi
  echo "[timings] recovering sentence timestamps for ${SPLIT}"
  "${RUN[@]}" "$RECOVER" --split "$SPLIT" --acl-root "$HERE"
fi

echo "[convert] split=${SPLIT} tgt=${TGT}"
"${RUN[@]}" convert.py --split "$SPLIT" --tgt $TGT
