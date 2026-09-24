#!/usr/bin/env python3
"""MCIF -> the bench dataset contract. ACL 2023 talks, en -> de/it/zh, long-form.

One item is one whole talk and group is that talk. This is the one place the
repo streams a talk as a single item, and it is forced: the release has no
sentence timestamps at all. The English transcript is one paragraph per talk
and the translations are sentence-per-line with no link back to the audio, so
there is nothing to cut on. Both references go in whole; see README.md for what
that means for scoring.

Only the talks that carry a translation reference (task="TRANS", 21 talks) are
kept. The other MCIF talks exist for QA and summarisation.

    python mcif/convert.py --tgt de zh
"""
import argparse
import gzip
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _contract as contract

NAME = "mcif"
TARGETS = ("de", "it", "zh")


def read_refs(path: Path, task: str) -> dict[str, str]:
    """audio filename -> reference text, for one task of one language file."""
    if not path.is_file():
        raise SystemExit(f"missing {path}\nRun mcif/install.sh first.")
    root = ET.fromstring(gzip.decompress(path.read_bytes()))
    out = {s.findtext("audio_path"): (s.findtext("reference") or "").strip()
           for s in root.iter("sample") if s.get("task") == task}
    if not out:
        raise SystemExit(f"no task={task} samples in {path}")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tgt", nargs="+", default=["de", "zh"], choices=TARGETS)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    data = here / "data"
    transcripts = read_refs(data / "MCIF.long.en.ref.xml.gz", "ASR")
    targets = {lang: read_refs(data / f"MCIF.long.{lang}.ref.xml.gz", "TRANS")
               for lang in args.tgt}
    for lang, table in targets.items():
        if set(table) != set(transcripts):
            raise SystemExit(f"{lang} TRANS talks differ from the en ASR talks; the "
                             f"release layout changed -- inspect before converting.")

    audio_dir = contract.require_dir(data / "MCIF_DATA" / "LONG_AUDIOS",
                                     "Run mcif/install.sh first.")
    contract.link_audio(here, audio_dir)

    rows = []
    for wav, transcript in sorted(transcripts.items()):
        talk = Path(wav).stem
        rows.append(contract.row(
            item_id=talk, audio_rel=f"audio/{wav}",
            duration=contract.probe_duration(audio_dir / wav),
            src_lang="en", transcript=transcript, group=talk, speaker=talk,
            translations={lang: table[wav] for lang, table in targets.items()}))
    hours = sum(r["duration"] for r in rows) / 3600
    print(f"  {len(rows)} talks, {hours:.2f} h")

    contract.write_spec(here, name=NAME, split="test-long", languages=["en"],
                        primary_metric="wer", translations=sorted(targets),
                        group_rule="talk",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
