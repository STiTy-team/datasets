#!/usr/bin/env python3
"""Zeroth-Korean -> the bench dataset contract. Read Korean news sentences, ASR.

Read from the kresnik/zeroth_korean parquet mirror of OpenSLR 40, which embeds
each flac next to its original utterance id, speaker and text. Every clip is
decoded once into data/wav16k/. The sentences are unrelated to each other, so
every item is its own session.

    python zeroth/convert.py --split test
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyarrow.parquet as pq

import _contract as contract

NAME = "zeroth"
SPLITS = ("test", "train")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default="test", choices=SPLITS)
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    shards = sorted((here / "data" / "data").glob(f"{args.split}-*.parquet"))
    if not shards:
        raise SystemExit(f"no {args.split}-*.parquet under {here}/data/data\n"
                         f"Run zeroth/install.sh first.")

    records = [r for shard in shards for r in pq.read_table(shard).to_pylist()]
    records.sort(key=lambda r: r["id"])
    if args.limit:
        records = records[:args.limit]
    contract.report_lengths("ko", (r["text"] for r in records))

    out = here / "data" / "wav16k" / args.split
    print(f"transcoding {len(records)} clips -> {out} ...")
    durations = contract.transcode_all(
        [(r["audio"]["bytes"], out / f"{r['id']}.wav") for r in records])
    print(f"  {sum(durations) / 3600:.2f} h of audio")
    contract.link_audio(here, out)

    rows = [contract.row(item_id=r["id"], audio_rel=f"audio/{r['id']}.wav",
                         duration=duration, src_lang="ko", transcript=r["text"].strip(),
                         speaker=str(r["speaker_id"]))
            for r, duration in zip(records, durations)]

    contract.write_spec(here, name=NAME, split=args.split, languages=["ko"],
                        primary_metric="cer", translations=[], group_rule="id",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
