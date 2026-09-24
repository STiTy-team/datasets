#!/usr/bin/env python3
"""kosp2e -> the bench dataset contract. Korean speech, English translations.

Four source corpora (Zeroth, KSS, StyleKQC, Covid-ED) share one split list per
corpus: split/<corpus>_<part>.xlsx with columns [index, id, translation], where id
is the wav basename. One item is one utterance and its own session.

There is no Korean transcript: the authors hand it out only on request, so the
spec declares provides.transcript: false.

    python kosp2e/convert.py --part test
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import openpyxl

import _contract as contract

NAME = "kosp2e"
CORPORA = ("zeroth", "kss", "stylekqc", "covid")
PARTS = ("test", "dev")


def read_split(path: Path) -> list[tuple[str, str]]:
    """(wav basename, English translation) per row."""
    if not path.is_file():
        raise SystemExit(f"missing {path}\nRun kosp2e/install.sh first.")
    sheet = openpyxl.load_workbook(path, read_only=True).active
    rows = list(sheet.iter_rows(values_only=True))
    if [str(c) for c in rows[0][1:3]] != ["id", "translation"]:
        raise SystemExit(f"{path}: unexpected header {rows[0]}")
    return [(str(uid).strip(), str(text).strip()) for _, uid, text, *_ in rows[1:]
            if uid is not None and text]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--part", default="test", choices=PARTS)
    p.add_argument("--corpora", nargs="+", default=list(CORPORA), choices=CORPORA)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    data = here / "data"
    contract.link_audio(here, data)

    rows = []
    missing = 0
    for corpus in args.corpora:
        for uid, translation in read_split(data / f"{corpus}_{args.part}.xlsx"):
            wav = data / corpus / f"{uid}.wav"
            if not wav.is_file():
                missing += 1
                continue
            rows.append(contract.row(
                item_id=f"{corpus}_{uid}", audio_rel=f"audio/{corpus}/{uid}.wav",
                duration=contract.probe_duration(wav), src_lang="ko",
                speaker=corpus, translations={"en": translation}))
    if missing:
        raise SystemExit(f"{missing} wav(s) listed in the split files are not on disk "
                         f"-- re-run kosp2e/install.sh to fetch the rest.")
    contract.report_lengths("en", (r["reference"]["translations"]["en"] for r in rows))

    contract.write_spec(here, name=NAME, split=args.part, languages=["ko"],
                        primary_metric="cer", translations=["en"], group_rule="id",
                        transcript=False,
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
