#!/usr/bin/env python3
"""BSTC dev -> the bench dataset contract. Chinese talks, zh -> en, long-form.

One item is one whole talk, as in mcif/: the dev release carries no sentence
timestamps. The Chinese transcript is stored as a streaming simulation -- each
sentence written out one growing prefix per line -- so the finished sentences
are the lines the next line does not extend. They are checked one-to-one against
the English reference lines before anything is written.

The test set was never released; the literature reports on dev.

    python bstc/convert.py
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _contract as contract

NAME = "bstc"


def nonempty_lines(path: Path) -> list[str]:
    return [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def finished_sentences(prefixes: list[str]) -> list[str]:
    """Keep each prefix line that the following line does not grow."""
    return [p for p, nxt in zip(prefixes, prefixes[1:] + [""]) if not nxt.startswith(p)]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.parse_args(argv)

    here = contract.here(__file__)
    text = contract.require_dir(here / "data" / "bstc_transcription_translation" / "dev",
                                "Run bstc/install.sh first.")
    audio_dir = contract.require_dir(here / "data" / "devdata",
                                     "Run bstc/install.sh first.")
    contract.link_audio(here, audio_dir)

    rows = []
    zh_all, en_all = [], []
    for ref in sorted((text / "ref_text").glob("*.txt")):
        talk = ref.stem
        zh = finished_sentences(nonempty_lines(text / "streaming_transcription" / ref.name))
        en = nonempty_lines(ref)
        if len(zh) != len(en):
            raise SystemExit(f"talk {talk}: {len(zh)} Chinese sentences but {len(en)} "
                             f"English lines -- the prefix parsing no longer matches.")
        wav = audio_dir / f"{talk}.wav"
        if not wav.is_file():
            raise SystemExit(f"missing audio for talk {talk}: {wav}")
        zh_all += zh
        en_all += en
        rows.append(contract.row(
            item_id=talk, audio_rel=f"audio/{wav.name}",
            duration=contract.probe_duration(wav), src_lang="zh",
            transcript="".join(zh), group=talk, speaker=talk,
            translations={"en": "\n".join(en)}))
    # Per sentence, not per talk: a whole talk is far past the sanity limit.
    contract.report_lengths("zh (chars)", (" ".join(s) for s in zh_all))
    contract.report_lengths("en", en_all)
    print(f"  {len(rows)} talks, {sum(r['duration'] for r in rows) / 3600:.2f} h")

    contract.write_spec(here, name=NAME, split="dev", languages=["zh"],
                        primary_metric="cer", translations=["en"], group_rule="talk",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
