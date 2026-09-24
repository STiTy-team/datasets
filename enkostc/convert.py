#!/usr/bin/env python3
"""EnKoST-C -> the bench dataset contract. English TED talks, Korean translations.

The release copies MuST-C's layout: one wav per talk, and per split a yaml that
lists every segment by talk, offset and duration, with <split>.en and <split>.ko
holding the matching sentence on the same line. Each segment becomes an item
pointing into its talk's wav with offset/duration -- nothing is cut. group is the
talk, so one handler lives for one talk and hears its segments in speaking order.

    python enkostc/convert.py --split tst-COMMON
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

import _contract as contract

NAME = "enkostc"
SPLITS = ("tst-COMMON", "tst-HE", "dev", "train")


def find_split(data: Path, split: str) -> Path:
    """The <split>.yaml wherever the archive put it (data/**/txt/<split>.yaml)."""
    found = sorted(data.rglob(f"{split}.yaml"))
    if not found:
        raise SystemExit(f"no {split}.yaml under {data}\nRun enkostc/install.sh first.")
    if len(found) > 1:
        raise SystemExit(f"several {split}.yaml under {data}: {[str(f) for f in found]}")
    return found[0]


def read_lines(path: Path) -> list[str]:
    if not path.is_file():
        raise SystemExit(f"missing {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]


def read_segments(yaml_path: Path, split: str) -> list[dict]:
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    entries = yaml.load(yaml_path.read_text(encoding="utf-8"), Loader=loader)
    english = read_lines(yaml_path.with_name(f"{split}.en"))
    korean = read_lines(yaml_path.with_name(f"{split}.ko"))
    if not len(entries) == len(english) == len(korean):
        raise SystemExit(f"{split}: {len(entries)} yaml segments, {len(english)} en lines, "
                         f"{len(korean)} ko lines -- they must match line for line")
    return [{"wav": e["wav"], "speaker": str(e.get("speaker_id", "")),
             "offset": float(e["offset"]), "duration": float(e["duration"]),
             "en": en, "ko": ko}
            for e, en, ko in zip(entries, english, korean) if en and ko]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default="tst-COMMON", choices=SPLITS)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    yaml_path = find_split(contract.require_dir(here / "data", "Run enkostc/install.sh first."),
                           args.split)
    wav_dir = contract.require_dir(yaml_path.parent.parent / "wav",
                                   f"expected the talk wavs beside {yaml_path.parent}")
    segments = read_segments(yaml_path, args.split)
    contract.report_lengths("en", (s["en"] for s in segments))
    contract.report_lengths("ko", (s["ko"] for s in segments))

    talks = sorted({s["wav"] for s in segments})
    missing = [t for t in talks if not (wav_dir / t).is_file()]
    if missing:
        raise SystemExit(f"{len(missing)} talk wav(s) missing from {wav_dir}: {missing[:5]}")
    # The paper says 16 kHz 16-bit wav; link as is when that holds, rewrite otherwise.
    if all(contract.audio_problem(wav_dir / t) is None for t in talks):
        audio_dir = wav_dir
    else:
        audio_dir = here / "data" / "wav16k" / args.split
        print(f"transcoding {len(talks)} talks -> {audio_dir} ...")
        contract.transcode_all([(wav_dir / t, audio_dir / t) for t in talks])
    contract.link_audio(here, audio_dir)

    segments.sort(key=lambda s: (s["wav"], s["offset"]))
    rows = []
    for s in segments:
        talk = Path(s["wav"]).stem
        rows.append(contract.row(item_id=f"{talk}_{s['offset']:09.3f}",
                                 audio_rel=f"audio/{s['wav']}", offset=s["offset"],
                                 duration=s["duration"], src_lang="en",
                                 transcript=s["en"], group=talk,
                                 speaker=s["speaker"] or talk,
                                 translations={"ko": s["ko"]}))
    hours = sum(s["duration"] for s in segments) / 3600
    print(f"  {len(talks)} talks, {len(rows)} segments, {hours:.2f} h of speech")

    contract.write_spec(here, name=NAME, split=args.split, languages=["en"],
                        primary_metric="wer", translations=["ko"], group_rule="talk",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
