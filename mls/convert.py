#!/usr/bin/env python3
"""Multilingual LibriSpeech -> the bench dataset contract. Read audiobooks, ASR only.

The Hugging Face release ships each split as parquet with the audio embedded as
opus bytes. Every clip is decoded once into data/wav16k/, which is what the
manifest points at. One item is one clip, and clips are unrelated to each other,
so every item is its own session.

    python mls/convert.py --language german --split test
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyarrow.parquet as pq

import _contract as contract

NAME = "mls"

# MLS config name -> the language code bench uses.
LANGUAGES = {"german": "de", "dutch": "nl", "french": "fr", "spanish": "es",
             "italian": "it", "portuguese": "pt", "polish": "pl"}
SPLITS = ("test", "dev")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--language", default="german", choices=sorted(LANGUAGES))
    p.add_argument("--split", default="test", choices=SPLITS)
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    lang = LANGUAGES[args.language]
    shards = sorted((here / "data" / args.language).glob(f"{args.split}-*.parquet"))
    if not shards:
        raise SystemExit(f"no {args.language}/{args.split}-*.parquet under {here}/data\n"
                         f"Run mls/install.sh first.")

    records = [r for shard in shards for r in pq.read_table(shard).to_pylist()]
    records.sort(key=lambda r: r["id"])
    if args.limit:
        records = records[:args.limit]
    contract.report_lengths(lang, (r["transcript"] for r in records))

    out = here / "data" / "wav16k" / args.language / args.split
    print(f"transcoding {len(records)} clips -> {out} ...")
    durations = contract.transcode_all(
        [(r["audio"]["bytes"], out / f"{r['id']}.wav") for r in records])
    contract.link_audio(here, out)

    rows = [contract.row(item_id=r["id"], audio_rel=f"audio/{r['id']}.wav",
                         duration=duration, src_lang=lang, transcript=r["transcript"],
                         speaker=str(r["speaker_id"]))
            for r, duration in zip(records, durations)]

    contract.write_spec(here, name=NAME, split=f"{args.split}-{args.language}",
                        languages=[lang], primary_metric="wer", translations=[],
                        group_rule="id",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
