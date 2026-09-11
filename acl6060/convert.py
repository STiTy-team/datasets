#!/usr/bin/env python3
"""ACL 60/60 -> the bench dataset contract. Conference talks, en -> many.

One item is one *gold sentence* from segmented_wavs/gold/sent_N.wav, with group
set to the talk it came from. That is the mapping the contract wants: one handler
lives for one talk, so sentences inside a talk keep their context and unrelated
talks never share one.

Streaming a whole 10-minute talk as a single item is the other option, and it is
not used here. The pieces a streaming system emits do not line up with reference
sentence boundaries, so scoring needs mwerSegmenter to realign them first, and
bench has no resegmentation stage. Sentence-level items are scorable directly.

    python acl6060/convert.py --split eval --tgt de
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _contract as contract

NAME = "acl6060"

# our language code -> the code in the release's XML filenames
XML_LANG = {"de": "de", "ja": "ja", "zh": "zh", "ar": "ar", "fa": "fa",
            "fr": "fr", "nl": "nl", "pt": "pt", "ru": "ru", "tr": "tr"}


def parse_segs(xml_path: Path) -> dict[int, str]:
    """seg id -> text. XML entities unescaped, whitespace collapsed."""
    if not xml_path.is_file():
        raise SystemExit(f"missing XML: {xml_path}")
    raw = xml_path.read_text(encoding="utf-8")
    out: dict[int, str] = {}
    for _docid, body in re.findall(r'<doc docid="([^"]+)"[^>]*>(.*?)</doc>', raw, re.S):
        for sid, text in re.findall(r'<seg id="(\d+)">(.*?)</seg>', body, re.S):
            out[int(sid)] = re.sub(r"\s+", " ", html.unescape(text)).strip()
    if not out:
        raise SystemExit(f"no <seg> entries parsed from {xml_path}")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default="eval", choices=["dev", "eval"])
    p.add_argument("--tgt", nargs="+", default=["de"],
                   help=f"target languages ({sorted(XML_LANG)})")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    split_dir = contract.require_dir(
        here / "acl_6060" / args.split,
        "Obtain the ACL 60/60 release and extract it into acl6060/ so that\n"
        "  acl6060/acl_6060/<split>/{text,full_wavs,segmented_wavs}\n"
        "exists. See acl6060/README.md.")

    timings_path = here / f"timings_{args.split}.json"
    if not timings_path.is_file():
        raise SystemExit(
            f"missing {timings_path}.\n"
            f"The release ships no timestamps. Recover them first (from a STiTy "
            f"checkout):\n  python evaluation/ast/recover_acl6060_timings.py "
            f"--split {args.split} --acl-root {here}")
    timings = json.loads(timings_path.read_text(encoding="utf-8"))
    by_seg = {int(s["seg_id"]): s for s in timings["segments"]}

    xml_dir = split_dir / "text" / "xml"
    print("reading XML ...")
    source = parse_segs(xml_dir / f"ACL.6060.{args.split}.en-xx.en.xml")
    contract.report_lengths("en", source.values())

    targets: dict[str, dict[int, str]] = {}
    for lang in args.tgt:
        if lang not in XML_LANG:
            raise SystemExit(f"unknown target {lang!r} (known: {sorted(XML_LANG)})")
        table = parse_segs(xml_dir / f"ACL.6060.{args.split}.en-xx.{XML_LANG[lang]}.xml")
        contract.report_lengths(lang, table.values())
        # Sentence-by-sentence pairing only holds if the id sets match exactly.
        if set(table) != set(source):
            only_src = len(set(source) - set(table))
            only_tgt = len(set(table) - set(source))
            raise SystemExit(
                f"seg id mismatch for {lang}: {only_src} only in en, {only_tgt} only "
                f"in {lang}. Sentence alignment would be wrong.")
        targets[lang] = table

    gold_dir = contract.require_dir(split_dir / "segmented_wavs" / "gold",
                                    "The release should contain it.")
    contract.link_audio(here, gold_dir)

    # Ordered by (talk, time within talk). Time, not seg id: gold boundaries
    # overlap in a few places, so speaking order and id order disagree. bench
    # preserves manifest order inside a group, so this ordering is what streams.
    ordered = sorted(
        (sid for sid in source if sid in by_seg),
        key=lambda sid: (str(by_seg[sid]["talk_id"]),
                         float(by_seg[sid].get("offset") or 0.0)))
    untimed = len(set(source) - set(by_seg))
    if untimed:
        print(f"warning: {untimed} sentence(s) have no timing entry and were skipped "
              f"(cannot be assigned to a talk)")

    rows = []
    missing_audio = empty = 0
    for sid in ordered:
        wav = gold_dir / f"sent_{sid}.wav"
        if not wav.is_file():
            missing_audio += 1
            continue
        text = source[sid]
        translations = {lang: table[sid] for lang, table in targets.items()}
        if not text or any(not t for t in translations.values()):
            empty += 1
            continue
        talk_id = str(by_seg[sid]["talk_id"])
        rows.append(contract.row(
            item_id=f"{args.split}_sent_{sid}",
            audio_rel=f"audio/sent_{sid}.wav",
            duration=contract.probe_duration(wav, "wav"),
            src_lang="en",
            transcript=text,
            group=talk_id,
            speaker=talk_id,
            translations=translations))
        if args.limit and len(rows) >= args.limit:
            break

    if missing_audio:
        print(f"warning: {missing_audio} sentence(s) had no gold wav and were skipped")
    if empty:
        print(f"warning: {empty} sentence(s) were empty in some language and were skipped")

    contract.write_spec(here, name=NAME, split=args.split, languages=["en"],
                        audio_format="wav", primary_metric="wer",
                        translations=sorted(targets), group_rule="talk_id",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200})
    contract.write_manifest(here, rows)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
