#!/usr/bin/env python3
"""TED-LIUM 3 -> the bench dataset contract. TED talks, English ASR.

A talk is one NIST sphere file plus an STM listing its segments by start and end
time. The talk is decoded once to wav, and each scored segment becomes an item
that points into it with offset/duration -- nothing is cut. group is the talk, so
one handler lives for one talk and hears its segments in speaking order.

    python tedlium/convert.py --split test
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _contract as contract

NAME = "tedlium"
SPLITS = ("test", "dev")
# Gaps between segments carry this in place of text; they are not speech.
IGNORE = "ignore_time_segment_in_scoring"


def normalize(words: list[str]) -> str:
    """TED-LIUM splits contractions ("i 'm", "don 't"). Rejoin them so a system
    that writes "I'm" is not charged two errors for one word."""
    return re.sub(r" '(?=\w)", "'", " ".join(words))


def read_stm(path: Path) -> list[dict]:
    segments = []
    for line in path.read_text(encoding="utf-8").splitlines():
        talk, _channel, speaker, start, end, _label, *words = line.split()
        if not words or words == [IGNORE]:
            continue
        segments.append({"talk": talk, "speaker": speaker, "start": float(start),
                         "end": float(end), "text": normalize(words)})
    if not segments:
        raise SystemExit(f"no scored segments in {path}")
    return segments


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default="test", choices=SPLITS)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    src_dir = contract.require_dir(here / "data" / args.split,
                                   "Run tedlium/install.sh first.")
    talks = sorted(src_dir.glob("*.sph"))
    if not talks:
        raise SystemExit(f"no .sph files in {src_dir}")

    segments = [s for sph in talks for s in read_stm(sph.with_suffix(".stm"))]
    contract.report_lengths("en", (s["text"] for s in segments))

    out = here / "data" / "wav16k" / args.split
    print(f"transcoding {len(talks)} talks -> {out} ...")
    durations = contract.transcode_all([(sph, out / f"{sph.stem}.wav") for sph in talks])
    print(f"  {sum(durations) / 3600:.2f} h of audio")
    contract.link_audio(here, out)

    # Speaking order inside a talk; bench keeps manifest order within a group.
    segments.sort(key=lambda s: (s["talk"], s["start"]))
    rows = [contract.row(item_id=f"{s['talk']}_{s['start']:09.2f}",
                         audio_rel=f"audio/{s['talk']}.wav",
                         offset=s["start"], duration=s["end"] - s["start"],
                         src_lang="en", transcript=s["text"],
                         group=s["talk"], speaker=s["speaker"])
            for s in segments]

    contract.write_spec(here, name=NAME, split=f"{args.split}-legacy",
                        languages=["en"], primary_metric="wer", translations=[],
                        group_rule="talk",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
