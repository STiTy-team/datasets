#!/usr/bin/env python3
import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
RECIPES_FILE = ROOT / "recipes.yml"
SHARED_SCRIPT = ROOT / "_contract.py"
BUILD_RECORD = "build.json"
STATUS_FILE = ".status"
INSTALLED = "success"
OUTPUT_FILES = ("dataset.yml", "manifest.jsonl")

READY, MISSING, UNRECORDED, STALE = "ok", "missing", "unrecorded", "stale"
MANUAL, NEEDS_ENV = "manual", "needs_env"
EXIT_READY, EXIT_FAILED, EXIT_UNKNOWN, EXIT_MANUAL = 0, 1, 2, 3


class NeedsManualStep(Exception):
    pass


class BuildFailed(Exception):
    pass


@dataclass
class Status:
    state: str
    reason: str


def load_recipes() -> dict:
    return yaml.safe_load(RECIPES_FILE.read_text(encoding="utf-8")) or {}


def _file_name(name: str) -> str:
    return name.replace("/", "__")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_built(name: str) -> bool:
    return all((ROOT / name / file).is_file() for file in OUTPUT_FILES)


def _manifest_sha256(name: str) -> str:
    return _sha256(ROOT / name / "manifest.jsonl")


def _build_record(name: str) -> dict | None:
    path = ROOT / name / BUILD_RECORD
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _scripts_that_shape_the_data(name: str, recipe: dict) -> list[Path]:
    corpus_dir = ROOT / name.split("/")[0]
    corpus_scripts = [
        path for path in corpus_dir.iterdir() if path.is_file() and path.suffix in (".sh", ".py")
    ]
    called_scripts = [
        ROOT / word
        for word in str(recipe.get("run", "")).split()
        if word.endswith(".py") and (ROOT / word).is_file()
    ]
    return sorted({*corpus_scripts, *called_scripts, SHARED_SCRIPT})


def _scripts_hash(name: str, recipe: dict) -> str:
    digest = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode())
    for path in _scripts_that_shape_the_data(name, recipe):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _source_manifests(recipe: dict) -> dict:
    return {
        source: (_build_record(source) or {}).get("manifest_sha256")
        for source in recipe.get("needs", [])
    }


def _status_of_committed(name: str) -> Status:
    if _is_built(name):
        return Status(READY, "committed to git")
    return Status(MANUAL, "its files are committed to git but missing; check them out")


def _status_of_manual(name: str, recipe: dict) -> Status:
    if _is_built(name):
        return Status(READY, "built by hand")
    return Status(MANUAL, recipe["manual"])


def _status_of_scripted(name: str, recipe: dict, recipes: dict) -> Status:
    if not _is_built(name):
        missing_env = [
            variable for variable in recipe.get("needs_env", []) if not os.environ.get(variable)
        ]
        if missing_env:
            return Status(NEEDS_ENV, f"set {', '.join(missing_env)} to build it")
        return Status(MISSING, "not built")
    record = _build_record(name)
    if record is None:
        return Status(UNRECORDED, "built before build.json existed")
    for source in recipe.get("needs", []):
        source_status = status_of(source, recipes)
        if source_status.state != READY:
            return Status(STALE, f"{source} is {source_status.state}")
    if record.get("needs", {}) != _source_manifests(recipe):
        return Status(STALE, "a dataset it is made from was rebuilt")
    if record.get("scripts_hash") != _scripts_hash(name, recipe):
        return Status(STALE, "the recipe or its scripts changed")
    if record.get("manifest_sha256") != _manifest_sha256(name):
        return Status(STALE, "manifest.jsonl was changed after the build")
    return Status(READY, "build.json matches")


def status_of(name: str, recipes: dict) -> Status:
    recipe = recipes[name]
    if recipe.get("committed"):
        return _status_of_committed(name)
    if "manual" in recipe:
        return _status_of_manual(name, recipe)
    return _status_of_scripted(name, recipe, recipes)


def _datasets_commit() -> str | None:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return result.stdout.strip() or None


def record_build(name: str, recipe: dict) -> None:
    record = {
        "name": name,
        "recipe": recipe,
        "scripts_hash": _scripts_hash(name, recipe),
        "datasets_commit": _datasets_commit(),
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "manifest_sha256": _manifest_sha256(name),
        "needs": _source_manifests(recipe),
    }
    (ROOT / name / BUILD_RECORD).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def mark_installed(name: str) -> None:
    (ROOT / name / STATUS_FILE).write_text(INSTALLED + "\n", encoding="utf-8")


def clear_installed(name: str) -> None:
    (ROOT / name / STATUS_FILE).unlink(missing_ok=True)


def build_lock(name: str):
    path = ROOT / ".locks" / f"{_file_name(name)}.lock"
    path.parent.mkdir(exist_ok=True)
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"[install] waiting for another build of {name}", flush=True)
        fcntl.flock(handle, fcntl.LOCK_EX)
    return handle


def _run_recipe(name: str, recipe: dict) -> None:
    log_path = ROOT / ".logs" / f"{_file_name(name)}.log"
    log_path.parent.mkdir(exist_ok=True)
    recipe_env = {key: str(value) for key, value in (recipe.get("env") or {}).items()}
    print(f"[install] {name}: {recipe['run']} (log: {log_path})", flush=True)
    with open(log_path, "w", encoding="utf-8") as log:
        build = subprocess.Popen(
            recipe["run"],
            shell=True,
            cwd=ROOT,
            env={**os.environ, **recipe_env},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        for line in build.stdout:
            sys.stdout.write(line)
            log.write(line)
        if build.wait() != 0:
            raise BuildFailed(f"{name}: build exited {build.returncode}, see {log_path}")
    if not _is_built(name):
        raise BuildFailed(f"{name}: the build finished without {' and '.join(OUTPUT_FILES)}")


def install(name: str, recipes: dict) -> None:
    recipe = recipes[name]
    for source in recipe.get("needs", []):
        install(source, recipes)
    with build_lock(name):
        current = status_of(name, recipes)
        if current.state in (MANUAL, NEEDS_ENV):
            raise NeedsManualStep(current.reason)
        if current.state == UNRECORDED:
            print(f"[install] {name}: adopting the build already here", flush=True)
            record_build(name, recipe)
        elif current.state != READY:
            print(f"[install] {name}: {current.state} ({current.reason}), building", flush=True)
            clear_installed(name)
            _run_recipe(name, recipe)
            record_build(name, recipe)
        mark_installed(name)


def adopt(name: str, recipes: dict) -> int:
    if not _is_built(name):
        print(f"[install] {name} is not built; nothing to adopt", file=sys.stderr)
        return EXIT_FAILED
    with build_lock(name):
        record_build(name, recipes[name])
        mark_installed(name)
    return EXIT_READY


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a dataset from its recipe in recipes.yml, unless build.json says it is current. "
        "Exit codes: 0 ready, 1 build failed, 2 unknown name, 3 needs a manual step."
    )
    parser.add_argument("name", help="dataset directory, e.g. fleurs/ko_kr")
    parser.add_argument("--status", action="store_true", help='print {"state", "reason"} and exit')
    parser.add_argument(
        "--adopt", action="store_true", help="record the build that is there without rebuilding"
    )
    args = parser.parse_args()

    recipes = load_recipes()
    if args.name not in recipes:
        print(f"[install] no recipe for {args.name!r} in {RECIPES_FILE.name}", file=sys.stderr)
        return EXIT_UNKNOWN
    if args.status:
        print(json.dumps(asdict(status_of(args.name, recipes))))
        return EXIT_READY
    if args.adopt:
        return adopt(args.name, recipes)
    try:
        install(args.name, recipes)
    except NeedsManualStep as e:
        print(f"[install] {args.name} needs a manual step: {e}", file=sys.stderr)
        return EXIT_MANUAL
    except BuildFailed as e:
        print(f"[install] {e}", file=sys.stderr)
        return EXIT_FAILED
    print(f"[install] {args.name} is ready", flush=True)
    return EXIT_READY


if __name__ == "__main__":
    raise SystemExit(main())
