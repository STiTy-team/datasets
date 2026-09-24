#!/usr/bin/env python3
"""Fetch the Earnings-22 segment table: call, start, end, text -- no audio.

distil-whisper/earnings22 (config "chunked") cuts every call into segments of up
to 20 s and stores each with its audio. Only the text and time columns are read,
so 24 GB of parquet costs a few MB over HTTP. Written to data/segments.jsonl,
sorted by call and start time.

    python earnings22/fetch_segments.py
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem

REPO = "datasets/distil-whisper/earnings22"
COLUMNS = ["file_id", "segment_id", "transcription", "start_ts", "end_ts"]


def main() -> int:
    out = Path(__file__).resolve().parent / "data" / "segments.jsonl"
    out.parent.mkdir(exist_ok=True)
    fs = HfFileSystem()
    shards = sorted(fs.glob(f"{REPO}/chunked/test-*.parquet"))
    if not shards:
        raise SystemExit(f"no chunked/test-*.parquet in {REPO}")

    def read(shard: str) -> list[dict]:
        with fs.open(shard) as f:
            return pq.ParquetFile(f).read(columns=COLUMNS).to_pylist()

    rows = []
    with ThreadPoolExecutor(8) as pool:
        for n, part in enumerate(pool.map(read, shards), start=1):
            rows += part
            print(f"  {n}/{len(shards)} shards", flush=True)
    rows.sort(key=lambda r: (r["file_id"], r["start_ts"]))
    partial = out.with_name(out.name + ".part")
    with open(partial, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    partial.replace(out)
    print(f"  {len(rows)} segments -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
