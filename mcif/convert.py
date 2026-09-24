#!/usr/bin/env python3
"""MCIF -> the bench dataset contract. ACL 2023 talks, en -> de/it/zh, long-form.

One item is one sentence and group is the talk it belongs to, as in acl6060/.
The long-form release has no sentence timestamps, but its short-form release
carries, for every talk, the English transcript sentence per line -- one line per
translation line -- so the sentences are known. Where each is spoken is found by
forced-aligning the whole talk (contract.locate_sentences), and each row then
points into the talk wav with offset/duration; nothing is cut. bench streams the
sentences in order inside one session, or the whole talk at once with
`longform: true`, which is what LongYAAL needs.

Only the talks that carry a translation reference (task="TRANS", 21 talks) are
kept. The other MCIF talks exist for QA and summarisation.

    python mcif/convert.py --tgt de zh
"""
import argparse
import gzip
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _contract as contract

NAME = "mcif"
TARGETS = ("de", "it", "zh")


def samples(path: Path, task: str) -> dict[str, ET.Element]:
    """iid suffix (the talk number) -> <sample>, for one task of one file."""
    if not path.is_file():
        raise SystemExit(f"missing {path}\nRun mcif/install.sh first.")
    root = ET.fromstring(gzip.decompress(path.read_bytes()))
    out = {s.get("iid").split("_")[-1]: s for s in root.iter("sample") if s.get("task") == task}
    if not out:
        raise SystemExit(f"no task={task} samples in {path}")
    return out


def lines(text: str | None) -> list[str]:
    return [l.strip() for l in (text or "").strip().splitlines() if l.strip()]


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tgt", nargs="+", default=["de", "zh"], choices=TARGETS)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    data = here / "data"
    long_asr = samples(data / "MCIF.long.en.ref.xml.gz", "ASR")
    long_trans = {lang: samples(data / f"MCIF.long.{lang}.ref.xml.gz", "TRANS")
                  for lang in args.tgt}
    short_trans = {lang: samples(data / f"MCIF.short.{lang}.ref.xml.gz", "TRANS")
                   for lang in args.tgt}
    talks = set(long_asr)
    for lang in args.tgt:
        if set(long_trans[lang]) != talks or set(short_trans[lang]) != talks:
            raise SystemExit(f"{lang}: TRANS talks differ from the en ASR talks; the "
                             f"release layout changed -- inspect before converting.")

    audio_dir = contract.require_dir(data / "MCIF_DATA" / "LONG_AUDIOS",
                                     "Run mcif/install.sh first.")
    contract.link_audio(here, audio_dir)

    rows = []
    n_talks = 0
    for n in sorted(talks, key=int):
        wav = long_asr[n].findtext("audio_path")
        talk = Path(wav).stem
        paragraph = squash(long_asr[n].findtext("reference") or "")
        # The short-form file of each target carries the English sentence per line.
        # They agree except for the odd "[INAUDIBLE]" mark, so take the copy that
        # matches the long-form paragraph word for word.
        candidates = {lang: lines(short_trans[lang][n].findtext("metadata/transcript"))
                      for lang in args.tgt}
        sentences = next((c for c in candidates.values() if squash(" ".join(c)) == paragraph),
                         None)
        if sentences is None:
            raise SystemExit(f"talk {talk}: no short-form transcript matches the long-form "
                             f"paragraph -- inspect before converting.")
        refs = {}
        for lang in args.tgt:
            ref = lines(short_trans[lang][n].findtext("reference"))
            if len(ref) != len(sentences):
                raise SystemExit(f"talk {talk}: {len(sentences)} English sentences but "
                                 f"{len(ref)} {lang} lines")
            if lines(long_trans[lang][n].findtext("reference")) != ref:
                raise SystemExit(f"talk {talk}: the {lang} short-form and long-form "
                                 f"references differ")
            refs[lang] = ref

        print(f"  {talk}: locating {len(sentences)} sentences ...", flush=True)
        spans = contract.locate_sentences(audio_dir / wav, sentences, "en")
        for idx, ((offset, duration), sentence) in enumerate(zip(spans, sentences)):
            rows.append(contract.row(
                item_id=f"{talk}_{idx:03d}", audio_rel=f"audio/{wav}",
                offset=offset, duration=duration, src_lang="en",
                transcript=sentence, group=talk, speaker=talk,
                translations={lang: refs[lang][idx] for lang in args.tgt}))
        n_talks += 1

    contract.report_lengths("en", (r["reference"]["transcript"] for r in rows))
    hours = sum(contract.probe_duration(audio_dir / w) for w in
                {long_asr[n].findtext("audio_path") for n in talks}) / 3600
    print(f"  {n_talks} talks, {len(rows)} sentences, {hours:.2f} h")

    contract.write_spec(here, name=NAME, split="test-long", languages=["en"],
                        primary_metric="wer", translations=sorted(args.tgt),
                        group_rule="talk",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
