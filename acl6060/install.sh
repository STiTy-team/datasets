#!/usr/bin/env bash
# ACL 60/60 -> bench manifest. Two sources, and they are not the same dataset.
#
#   ./acl6060/install.sh                     SOURCE=hf (default), downloads
#   SOURCE=release ./acl6060/install.sh      the official release, extracted by hand
#   SPLIT=dev TGT="de ja" ./acl6060/install.sh
#
# hf       ymoslem/acl-6060 on HuggingFace, CC-BY-4.0. Downloads itself and needs
#          nothing else. Gold sentences and their translations, but no talk id --
#          every item is its own session, and there is no long-form run.
# release  the ACL 60/60 distribution page. Not downloaded here: the archive layout
#          has changed between drops and guessing it fetches the wrong thing
#          quietly. It carries the full talk wavs, which is what gives each
#          sentence its talk (`group`), its order inside that talk, and its offset.
#
# Expected layout for SOURCE=release:
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
  RUN_DOWNLOAD=("$PYTHON")
elif command -v uv >/dev/null 2>&1; then
  RUN=(uv run --project "$REPO" python)
  RUN_DOWNLOAD=(uv run --project "$REPO" --group download python)
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
SOURCE="${SOURCE:-hf}"

if [[ "$SOURCE" == "hf" ]]; then
  echo "[hf] split=${SPLIT} tgt=${TGT}"
  exec "${RUN_DOWNLOAD[@]}" hf_download.py --split "$SPLIT" --tgt $TGT
fi

if [[ "$SOURCE" != "release" ]]; then
  echo "[ERROR] SOURCE must be 'hf' or 'release', got '${SOURCE}'" >&2
  exit 2
fi

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
