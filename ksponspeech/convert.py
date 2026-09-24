#!/usr/bin/env python3
"""KsponSpeech -> the bench dataset contract. Spontaneous Korean conversation, ASR.

AI Hub ships the evaluation audio as headerless 16 kHz PCM16 (.pcm) and the
transcripts as scripts/<split>.trn, one "<relpath>.pcm :: <text>" per line. Every
clip is rewritten once into data/wav16k/. Clips are cut from unrelated
conversations, so every item is its own session.

The transcripts are annotated: noise tags (b/ l/ o/ n/ u/), fillers ("어/"),
repetitions ("전+"), uncertain speech ("*") and dual transcription
"(spelling)/(pronunciation)". normalize() keeps the words, picks one side of
each dual pair (spelling by default, as ESPnet and Lhotse do) and drops the rest.

    python ksponspeech/convert.py --split eval_clean
    python ksponspeech/convert.py --split eval_other --form phonetic
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _contract as contract

NAME = "ksponspeech"
SPLITS = ("eval_clean", "eval_other")
FORMS = ("spelling", "phonetic")


def normalize(text: str, form: str = "spelling") -> str:
    side = r"\1" if form == "spelling" else r"\2"
    text = re.sub(r"\b[blnou]/", " ", text)
    text = re.sub(r"\)\s*/\s*\(", ")/(", text)
    text = re.sub(r"\(([^)]*)\)/\(([^)]*)\)", side, text)
    text = re.sub(r"[/+*]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def read_trn(path: Path, form: str) -> list[tuple[str, str]]:
    """(pcm path relative to the corpus root, normalized text) per line."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rel, _, text = line.partition(" :: ")
        text = normalize(text, form)
        if text:
            out.append((rel.strip(), text))
    if not out:
        raise SystemExit(f"no usable lines in {path}")
    return out


def find_one(data: Path, pattern: str, hint: str) -> Path:
    found = sorted(data.rglob(pattern))
    if not found:
        raise SystemExit(f"no {pattern} under {data}\n{hint}")
    return found[0]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default="eval_clean", choices=SPLITS)
    p.add_argument("--form", default="spelling", choices=FORMS,
                   help="which side of a (spelling)/(pronunciation) pair to keep")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    data = contract.require_dir(here / "data", "Run ksponspeech/install.sh first.")
    hint = "Run ksponspeech/install.sh first."
    trn = find_one(data, f"{args.split}.trn", hint)
    root = find_one(data, "KsponSpeech_eval", hint).parent

    utterances = read_trn(trn, args.form)
    if args.limit:
        utterances = utterances[:args.limit]
    contract.report_lengths("ko", (text for _, text in utterances))
    missing = [rel for rel, _ in utterances if not (root / rel).is_file()]
    if missing:
        raise SystemExit(f"{len(missing)} pcm file(s) listed in {trn.name} are not under "
                         f"{root}: {missing[:3]}")

    out = here / "data" / "wav16k" / args.split
    print(f"transcoding {len(utterances)} clips -> {out} ...")
    durations = contract.transcode_all(
        [(root / rel, out / f"{Path(rel).stem}.wav") for rel, _ in utterances],
        raw_pcm=True)
    print(f"  {sum(durations) / 3600:.2f} h of audio")
    contract.link_audio(here, out)

    rows = [contract.row(item_id=Path(rel).stem, audio_rel=f"audio/{Path(rel).stem}.wav",
                         duration=duration, src_lang="ko", transcript=text)
            for (rel, text), duration in zip(utterances, durations)]

    contract.write_spec(here, name=NAME, split=args.split, languages=["ko"],
                        primary_metric="cer", translations=[], group_rule="id",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200},
                        extra={"transcript_form": args.form})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
