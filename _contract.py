"""The bench dataset contract, in one place.

Deliberately self-contained: this repo does not import STiTy. Two checkouts
sitting side by side is an assumption that breaks the first time someone clones
only one of them, and a dataset repo that cannot run on its own is not really a
separate concern.

The authority on whether a dataset is valid is still bench:

    python -m bench.data.manifest --validate $STITY_DATA_ROOT/<name>

What runs here is the same check in cheaper form, so a converter fails at the end
of conversion instead of at the start of a benchmark.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import yaml

AUDIO_FORMATS = {"flac", "wav", "pcm_s16le"}
PRIMARY_METRICS = {"wer", "cer"}
DURATION_TOLERANCE_SEC = 0.05

# A sentence longer than this is almost always a parsing failure rather than a
# real utterance. Checked before conversion because a small smoke test will not
# surface it: a merged-row fragment of 2,916 words once reached a live run,
# blew the model's token limit, and cost real money.
MAX_REASONABLE_WORDS = 200


def probe_duration(path: Path, fmt: str, sample_rate: int = 16000) -> float:
    if fmt == "pcm_s16le":
        return path.stat().st_size / 2 / sample_rate
    import soundfile as sf
    info = sf.info(str(path))
    return float(info.frames) / float(info.samplerate)


def link_audio(dataset_dir: Path, source: Path) -> Path:
    """Symlink <dataset>/audio -> source. Never copies; corpora are huge."""
    link = dataset_dir / "audio"
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        raise SystemExit(f"{link} exists and is not a symlink; remove it first")
    if not source.is_dir():
        raise SystemExit(f"audio source is not a directory: {source}")
    link.symlink_to(source)
    return link


def row(*, item_id: str, audio_rel: str, duration: float, src_lang: str,
        transcript: str, group: str | None = None, speaker: str = "",
        offset: float | None = None, translations: dict | None = None) -> dict:
    out = {
        "id": item_id,
        "audio": audio_rel,
        "duration": round(float(duration), 3),
        "group": group or item_id,
        "speaker": speaker,
        "src_lang": src_lang,
        "reference": {"transcript": transcript,
                      "translations": dict(translations or {})},
    }
    if offset is not None:
        out["offset"] = round(float(offset), 3)
    return out


def write_spec(dataset_dir: Path, *, name: str, split: str, languages: list[str],
               audio_format: str, primary_metric: str, translations: list[str],
               group_rule: str, bench_defaults: dict,
               sample_rate: int = 16000) -> Path:
    if audio_format not in AUDIO_FORMATS:
        raise SystemExit(f"audio.format must be one of {sorted(AUDIO_FORMATS)}")
    if primary_metric not in PRIMARY_METRICS:
        raise SystemExit(f"primary_metric must be one of {sorted(PRIMARY_METRICS)}")
    dataset_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "name": name,
        "split": split,
        "languages": list(languages),
        "audio": {"format": audio_format, "sample_rate": sample_rate},
        "provides": {"transcript": True, "translations": list(translations)},
        "primary_metric": primary_metric,
        "group_rule": group_rule,
        "bench_defaults": dict(bench_defaults),
    }
    path = dataset_dir / "dataset.yml"
    path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return path


def write_manifest(dataset_dir: Path, rows: list[dict]) -> Path:
    if not rows:
        raise SystemExit("no items to write -- check the source paths and filters")
    path = dataset_dir / "manifest.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for item in rows:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return path


def report_lengths(label: str, texts) -> None:
    """Print the word-count distribution and refuse absurd rows."""
    counts = [len(t.split()) for t in texts if t and t.strip()]
    if not counts:
        raise SystemExit(f"{label}: every sentence was empty")
    print(f"  {label}: {len(counts)} sentences, words min {min(counts)} "
          f"median {int(statistics.median(counts))} max {max(counts)}")
    if max(counts) > MAX_REASONABLE_WORDS:
        raise SystemExit(
            f"{label}: longest sentence is {max(counts)} words, past the "
            f"{MAX_REASONABLE_WORDS}-word sanity limit. That is the signature of a "
            f"parsing problem, not a real sentence -- inspect before converting."
        )


def verify(dataset_dir: Path) -> int:
    """Re-read what was written and check it. Returns a process exit code."""
    spec = yaml.safe_load((dataset_dir / "dataset.yml").read_text(encoding="utf-8"))
    fmt = spec["audio"]["format"]
    sample_rate = int(spec["audio"].get("sample_rate", 16000))
    want_translations = list(spec["provides"].get("translations") or [])

    problems: list[str] = []
    seen: set[str] = set()
    groups: list[str] = []
    n = 0

    with open(dataset_dir / "manifest.jsonl", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            n += 1
            item_id = item["id"]
            if item_id in seen:
                problems.append(f"{item_id}: duplicate id (line {lineno})")
            seen.add(item_id)
            if item["group"] not in groups:
                groups.append(item["group"])
            if Path(item["audio"]).is_absolute():
                problems.append(f"{item_id}: audio path is absolute")
                continue
            audio = dataset_dir / item["audio"]
            if not audio.is_file():
                problems.append(f"{item_id}: audio missing at {item['audio']}")
                continue
            if not (item["reference"].get("transcript") or "").strip():
                problems.append(f"{item_id}: empty transcript")
            for lang in want_translations:
                if not (item["reference"]["translations"].get(lang) or "").strip():
                    problems.append(f"{item_id}: missing {lang} reference translation")
            if item.get("offset") is None:
                actual = probe_duration(audio, fmt, sample_rate)
                if abs(actual - float(item["duration"])) > DURATION_TOLERANCE_SEC:
                    problems.append(
                        f"{item_id}: duration {item['duration']:.3f}s but the file is "
                        f"{actual:.3f}s")

    # Sessions must be contiguous: bench keeps one handler alive per group, and a
    # group that reappears later would silently get a second, stateless one.
    if len(groups) != len(set(groups)):
        problems.append("group values are not contiguous -- sort items by group")

    print()
    print(f"{spec['name']}: {n} items, {len(set(groups))} sessions, "
          f"languages {spec['languages']}, references "
          f"{['transcript'] + want_translations}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for line in problems[:20]:
            print(f"  - {line}")
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more")
        return 1
    print(f"OK -> {dataset_dir}")
    print(f"   validate from STiTy: python -m bench.data.manifest --validate "
          f"{dataset_dir}")
    return 0


def here(script_file: str) -> Path:
    """The dataset directory a converter writes into: its own directory."""
    return Path(script_file).resolve().parent


def require_dir(path: Path, hint: str) -> Path:
    if not path.is_dir():
        print(f"missing directory: {path}\n{hint}", file=sys.stderr)
        raise SystemExit(2)
    return path
