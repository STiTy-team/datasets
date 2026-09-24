#!/usr/bin/env python3
"""ACL 60/60 from HuggingFace -> the bench dataset contract. No manual download.

    python acl6060/hf_download.py --split eval --tgt de

The mirror is `ymoslem/acl-6060` (CC-BY-4.0): one parquet per split holding the
gold sentence wav and its text in English plus ten target languages. A token is
used when one is configured (HF_TOKEN, or `hf auth login`), and not needed --
the repo is public.

What this path does NOT have is the talk each sentence came from. The mirror
carries no talk id, and the release's full talk wavs -- which is what
`convert.py` byte-matches to recover both the talk and the order within it --
are not in it. So every item is its own session here, and a run over this
dataset never exercises a handler that lives across sentences. Use `convert.py`
with the official release when that is the thing being measured.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _contract as contract

NAME = "acl6060"
REPO = "ymoslem/acl-6060"
TEXT_COLUMN = "text_{lang}"
SOURCE_LANG = "en"
LANGS = ["ar", "de", "fa", "fr", "ja", "nl", "pt", "ru", "tr", "zh"]


def parquet_for(split: str) -> Path:
    from huggingface_hub import HfApi, hf_hub_download

    files = [f for f in HfApi().list_repo_files(REPO, repo_type="dataset")
             if f.startswith(f"data/{split}-") and f.endswith(".parquet")]
    if not files:
        raise SystemExit(f"{REPO} has no parquet for split {split!r}")
    if len(files) > 1:
        raise SystemExit(
            f"{REPO} now ships {len(files)} shards for {split!r} ({files}). "
            f"Reading only the first would silently drop most of the split.")
    print(f"[download] {REPO}:{files[0]}")
    return Path(hf_hub_download(REPO, files[0], repo_type="dataset"))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default="eval", choices=["dev", "eval"])
    p.add_argument("--tgt", nargs="+", default=["de"], help=f"targets ({LANGS})")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)

    unknown = sorted(set(args.tgt) - set(LANGS))
    if unknown:
        raise SystemExit(f"{REPO} has no text for {unknown} (it has {LANGS})")

    import pyarrow.parquet as pq

    here = contract.here(__file__)
    audio_dir = here / "data" / args.split
    audio_dir.mkdir(parents=True, exist_ok=True)

    columns = ["index", "audio", TEXT_COLUMN.format(lang=SOURCE_LANG)]
    columns += [TEXT_COLUMN.format(lang=lang) for lang in args.tgt]
    table = pq.read_table(parquet_for(args.split), columns=columns)
    rows_in = table.to_pylist()
    print(f"[convert] {len(rows_in)} sentences, targets {sorted(args.tgt)}")

    contract.report_lengths(
        SOURCE_LANG, [r[TEXT_COLUMN.format(lang=SOURCE_LANG)] for r in rows_in])
    for lang in sorted(args.tgt):
        contract.report_lengths(
            lang, [r[TEXT_COLUMN.format(lang=lang)] for r in rows_in])

    kept, empty = [], 0
    for raw in rows_in:
        transcript = (raw[TEXT_COLUMN.format(lang=SOURCE_LANG)] or "").strip()
        translations = {lang: (raw[TEXT_COLUMN.format(lang=lang)] or "").strip()
                        for lang in args.tgt}
        if not transcript or any(not t for t in translations.values()):
            empty += 1
            continue

        name = f"sent_{int(raw['index']) + 1:04d}.wav"
        kept.append((name, raw["audio"]["bytes"], transcript, translations))
        if args.limit and len(kept) >= args.limit:
            break

    if empty:
        print(f"warning: {empty} sentence(s) were empty in some language, skipped")

    # The mirror's wavs are not guaranteed to be the contract's 16 kHz mono PCM16,
    # so each one is rewritten once from its bytes.
    print(f"transcoding {len(kept)} clips -> {audio_dir} ...")
    durations = contract.transcode_all([(audio, audio_dir / name)
                                        for name, audio, _, _ in kept])
    contract.link_audio(here, audio_dir)

    rows = [contract.row(
        item_id=f"{args.split}_{name.removesuffix('.wav')}",
        audio_rel=f"audio/{name}",
        duration=duration,
        src_lang=SOURCE_LANG,
        transcript=transcript,
        translations=translations)
        for (name, _, transcript, translations), duration in zip(kept, durations)]

    contract.write_spec(here, name=NAME, split=f"{args.split}-hf",
                        languages=[SOURCE_LANG],
                        primary_metric="wer", translations=sorted(args.tgt),
                        group_rule="id (the mirror carries no talk id)",
                        bench_defaults={})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
