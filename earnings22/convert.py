#!/usr/bin/env python3
"""Earnings-22 -> the bench dataset contract. Earnings calls, accented English, ASR.

One call is one mp3 of 15 minutes to 2 hours, decoded once to wav. Segments come
from distil-whisper/earnings22's "chunked" config (fetch_segments.py): the
official reference cut at punctuation into pieces of mostly under 20 s, placed on the
call's timeline by forced alignment. Each segment becomes an item pointing into
the call wav with offset/duration -- nothing is cut. group is the call.

The official repo's own force-aligned token files leave a quarter of the tokens
untimed and place some sentences minutes wide, so they are not used.

    python earnings22/convert.py
    python earnings22/convert.py --subset subset10
"""
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _contract as contract

NAME = "earnings22"
# A segment this slow is an alignment failure or mostly silence: 494 s for six
# words, 43 s for twelve. Short ones are left alone -- "Thank you." can take 3 s.
MIN_WORDS_PER_SEC = 0.5
SLOW_CHECK_SEC = 10.0
# The 10 calls of the repo's subset10/ (11 h), re-transcribed verbatim there.
SUBSET10 = ["4453225", "4469088", "4470684", "4474506", "4479944",
            "4481952", "4482383", "4482613", "4483937", "4485192"]


def clean(text: str) -> str:
    """Drop the event tags (<inaudible>, <laugh>, <crosstalk>, ...)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", text)).strip()


def read_segments(path: Path) -> dict[str, list[dict]]:
    if not path.is_file():
        raise SystemExit(f"missing {path}\nRun earnings22/install.sh first.")
    calls = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                calls[row["file_id"]].append(row)
    return calls


def read_calls(path: Path) -> dict[str, dict]:
    """File ID -> its metadata.csv row."""
    if not path.is_file():
        raise SystemExit(f"missing {path}\nRun earnings22/install.sh first.")
    with open(path, encoding="utf-8", newline="") as f:
        return {r["File ID"]: r for r in csv.DictReader(f)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--subset", choices=["subset10"], default=None,
                   help="only the 10 calls of subset10/ (11 h)")
    p.add_argument("--list", action="store_true",
                   help="print the call ids and exit (install.sh uses this)")
    args = p.parse_args(argv)

    here = contract.here(__file__)
    metadata = read_calls(here / "data" / "metadata.csv")
    calls = SUBSET10 if args.subset else sorted(metadata)
    if args.list:
        print("\n".join(calls))
        return 0

    segments = read_segments(here / "data" / "segments.jsonl")
    media = here / "data" / "media"
    missing = [c for c in calls if not (media / f"{c}.mp3").is_file()]
    if missing:
        raise SystemExit(f"{len(missing)} mp3(s) missing from {media}: {missing[:3]}\n"
                         f"Run earnings22/install.sh first.")
    out = here / "data" / "wav16k"
    print(f"transcoding {len(calls)} calls -> {out} ...")
    lengths = contract.transcode_all([(media / f"{c}.mp3", out / f"{c}.wav") for c in calls])
    print(f"  {sum(lengths) / 3600:.2f} h of audio")
    contract.link_audio(here, out)

    rows, misplaced, past_end = [], 0, 0
    for call, length in zip(calls, lengths):
        if call not in segments:
            raise SystemExit(f"{call}: no segments in segments.jsonl")
        for s in sorted(segments[call], key=lambda s: s["start_ts"]):
            start, end = float(s["start_ts"]), min(float(s["end_ts"]), length)
            text = clean(s["transcription"])
            if end <= start:
                past_end += 1
                continue
            words = len(text.split())
            if (end - start > SLOW_CHECK_SEC and words / (end - start) < MIN_WORDS_PER_SEC
                    or words > contract.MAX_REASONABLE_WORDS):
                misplaced += 1
                continue
            if text:
                rows.append(contract.row(item_id=f"{call}_{int(s['segment_id']):04d}",
                                         audio_rel=f"audio/{call}.wav", offset=start,
                                         duration=end - start, src_lang="en",
                                         transcript=text, group=call, speaker=call))
    contract.report_lengths("en", (r["reference"]["transcript"] for r in rows))
    print(f"  {len(calls)} calls, {len(rows)} segments; dropped {misplaced} misplaced "
          f"or overlong and {past_end} past the end of their audio")

    contract.write_spec(here, name=NAME, split=f"test-{args.subset}" if args.subset else "test",
                        languages=["en"], primary_metric="wer", translations=[],
                        group_rule="call",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200},
                        extra={"accents": {c: metadata[c]["Language Family + Area Based"]
                                           for c in calls}})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
