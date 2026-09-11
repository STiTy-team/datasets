#!/usr/bin/env python3
"""FLEURS -> the bench dataset contract. Source audio plus n-way parallel references.

FLEURS reads the same FLoRes sentences in every language and the sentence id is
shared, so one source-language audio set plus any number of target-language TSVs
gives speech-translation pairs. Target references land in
reference.translations keyed by language, so a single manifest serves en->ko,
en->de and en->ja at once -- adding a target costs one TSV, not another audio
download.

    python fleurs/convert.py --src en_us --tgt ko_kr de_de
"""
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _contract as contract

NAME = "fleurs"

# FLEURS locale -> the language code bench uses.
LOCALES = {
    "en_us": "en", "ko_kr": "ko", "ja_jp": "ja", "cmn_hans_cn": "zh",
    "de_de": "de", "es_419": "es", "fr_fr": "fr", "it_it": "it",
    "pt_br": "pt", "ru_ru": "ru", "nl_nl": "nl", "pl_pl": "pl",
    "tr_tr": "tr", "vi_vn": "vi", "th_th": "th", "id_id": "id",
    "ar_eg": "ar", "hi_in": "hi",
}


def read_tsv(path: Path) -> dict[str, dict]:
    """sentence id -> row.

    QUOTE_NONE is not optional. test.tsv has no header and carries literal quote
    characters inside the text; letting csv treat one as the start of a quoted
    field merges rows together, and the merged monster then looks like a single
    very long sentence.
    """
    if not path.is_file():
        raise SystemExit(f"missing TSV: {path}\nRun fleurs/install.sh first.")
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8", newline="") as f:
        for fields in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(fields) < 4:
                continue
            sentence_id, filename, raw_transcription, transcription = fields[:4]
            gender = fields[6] if len(fields) > 6 else ""
            text = (transcription or raw_transcription or "").strip()
            if not sentence_id or not text:
                continue
            # Several recordings share one sentence id; first wins so the source
            # and target sides join deterministically.
            out.setdefault(sentence_id, {"filename": filename.strip(), "text": text,
                                         "speaker": gender.strip()})
    if not out:
        raise SystemExit(f"no usable rows in {path}")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", default="en_us", help="source locale (audio comes from here)")
    p.add_argument("--tgt", nargs="+", default=["ko_kr", "de_de"],
                   help="target locales (references only, no audio needed)")
    p.add_argument("--split", default="test")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    if args.src not in LOCALES:
        raise SystemExit(f"unknown source locale {args.src} (known: {sorted(LOCALES)})")
    src_lang = LOCALES[args.src]

    print("reading TSVs ...")
    source = read_tsv(here / "data" / args.src / f"{args.split}.tsv")
    contract.report_lengths(args.src, (r["text"] for r in source.values()))

    targets: dict[str, dict[str, dict]] = {}
    for locale in args.tgt:
        if locale not in LOCALES:
            raise SystemExit(f"unknown target locale {locale} (known: {sorted(LOCALES)})")
        rows = read_tsv(here / "data" / locale / f"{args.split}.tsv")
        contract.report_lengths(locale, (r["text"] for r in rows.values()))
        targets[LOCALES[locale]] = rows

    audio_dir = contract.require_dir(
        here / "data" / args.src / "audio" / args.split,
        f"Extract it:\n  tar xzf {here}/data/{args.src}/audio/{args.split}.tar.gz "
        f"-C {here}/data/{args.src}/audio/")
    contract.link_audio(here, audio_dir)

    rows = []
    skipped_audio = skipped_ref = 0
    for sentence_id in sorted(source, key=lambda s: (len(s), s)):
        entry = source[sentence_id]
        wav = audio_dir / entry["filename"]
        if not wav.is_file():
            skipped_audio += 1
            continue
        translations = {lang: table[sentence_id]["text"]
                        for lang, table in targets.items() if sentence_id in table}
        if len(translations) != len(targets):
            skipped_ref += 1
            continue
        rows.append(contract.row(
            item_id=f"{src_lang}_{sentence_id}",
            audio_rel=f"audio/{entry['filename']}",
            duration=contract.probe_duration(wav, "wav"),
            src_lang=src_lang,
            transcript=entry["text"],
            # Unrelated single sentences: one session each, so no context carries
            # from one utterance into the next.
            group=f"{src_lang}_{sentence_id}",
            speaker=entry["speaker"],
            translations=translations))
        if args.limit and len(rows) >= args.limit:
            break

    if skipped_audio:
        print(f"warning: {skipped_audio} sentence(s) had no audio file and were skipped")
    if skipped_ref:
        print(f"warning: {skipped_ref} sentence(s) lacked a reference in some target "
              f"language and were skipped")

    contract.write_spec(here, name=NAME, split=f"{args.split}-{args.src}",
                        languages=[src_lang], audio_format="wav",
                        primary_metric="wer", translations=sorted(targets),
                        group_rule="id",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200})
    contract.write_manifest(here, rows)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
