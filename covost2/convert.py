#!/usr/bin/env python3
"""CoVoST 2 -> the bench dataset contract. Common Voice clips with translations.

Read from the fixie-ai/covost2 parquet mirror, which embeds each Common Voice
mp3 next to its transcript and translation. Every clip is decoded once into
data/wav16k/. One item is one clip read by one volunteer, unrelated to the next,
so every item is its own session. One direction is one dataset, written to
covost2/<pair>/ -- de_en and en_de have different source audio.

    python covost2/convert.py --pair de_en --split test      # -> covost2/de_en/
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyarrow.parquet as pq

import _contract as contract

NAME = "covost2"
SPLITS = ("test", "validation")
# Scored by characters rather than words: no spaces between words.
CER_LANGS = {"zh", "ja"}


def bench_lang(covost_code: str) -> str:
    """CoVoST language code -> the code bench uses. zh-CN -> zh, sv-SE -> sv."""
    return covost_code.split("-")[0].lower()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pair", default="de_en",
                   help="<source>_<target> config of fixie-ai/covost2 (de_en, en_de, ...)")
    p.add_argument("--split", default="test", choices=SPLITS)
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    dataset_dir = here / args.pair
    src, tgt = (bench_lang(code) for code in args.pair.split("_", 1))
    shards = sorted((here / "data" / args.pair).glob(f"{args.split}-*.parquet"))
    if not shards:
        raise SystemExit(f"no {args.pair}/{args.split}-*.parquet under {here}/data\n"
                         f"Run covost2/install.sh first.")

    records = [r for shard in shards for r in pq.read_table(shard).to_pylist()]
    records.sort(key=lambda r: r["id"])
    if args.limit:
        records = records[:args.limit]
    contract.report_lengths(src, (r["sentence"] for r in records))
    contract.report_lengths(tgt, (r["translation"] for r in records))

    out = here / "data" / "wav16k" / args.pair / args.split
    print(f"transcoding {len(records)} clips -> {out} ...")
    durations = contract.transcode_all(
        [(r["audio"]["bytes"], out / f"{r['id']}.wav") for r in records])
    dataset_dir.mkdir(exist_ok=True)
    contract.link_audio(dataset_dir, out)

    rows = [contract.row(item_id=r["id"], audio_rel=f"audio/{r['id']}.wav",
                         duration=duration, src_lang=src, transcript=r["sentence"],
                         translations={tgt: r["translation"]})
            for r, duration in zip(records, durations)]

    contract.write_spec(dataset_dir, name=f"{NAME}/{args.pair}", split=args.split,
                        languages=[src],
                        primary_metric="cer" if src in CER_LANGS else "wer",
                        translations=[tgt], group_rule="id",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200})
    contract.write_manifest(dataset_dir, rows)
    contract.align(dataset_dir)
    return contract.verify(dataset_dir)


if __name__ == "__main__":
    raise SystemExit(main())
