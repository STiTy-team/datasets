#!/usr/bin/env python3
"""Build a spliced-handoff multi-language conversation manifest from FLEURS.

FLEURS is an n-way parallel corpus (built from FLoRes sentences read aloud in
each language): the same sentence id shows up in every language's test.tsv as
a translation of the same source sentence. For each sentence id shared by
every language in --langs, this script builds ONE turn whose audio is a
single spliced clip: language 1's recording (often cut short mid-sentence),
immediately followed by language 2's recording, ... through the last
language in the rotation — one continuous audio stream that switches
language partway through, the way a real conversation handoff (or
interruption) sounds, instead of separate clips per language.

    turn 0 audio: [-ar,0.0-4.2s-][silence 0.8s][-ko,5.0-9.8s-][silence 1.1s][-en,10.9-15.3s-]
    turn 0 "segments": [{"lang": "ar", "text": "...", "start_sec": 0.0, "end_sec": 4.2,
                          "cut": true, "gap_after_sec": 0.8},
                         {"lang": "ko", "text": "...", "start_sec": 5.0, "end_sec": 9.8,
                          "cut": true, "gap_after_sec": 1.1},
                         {"lang": "en", "text": "...", "start_sec": 10.9, "end_sec": 15.3,
                          "cut": false, "gap_after_sec": 0.0}]

Each segment's own text is the FULL sentence in that language (FLEURS'
transcription) — `cut: true` means the audio for that segment stops before
finishing it (a real cutoff), `cut: false` means it played to completion
before handing off to the next language.

Whether a given segment is cut is controlled by --interrupt-frac (checked
independently per segment, including the last one — a spliced clip can end
mid-sentence too). When cut, --interrupt-keep-min/--interrupt-keep-max picks
how much of that segment's audio survives.

Between every segment (cut or not) except the last, a silent gap
(--gap-min-sec to --gap-max-sec, uniformly random) is inserted before the
next language starts — a real conversational pause, not an instant handoff.
This matters beyond realism: a commit mechanism that needs a quiet moment to
flush a result (VAD-based, or just an asyncio loop catching up) never gets
one when segments are spliced back-to-back with zero gap — every commit
ends up only arriving once the whole turn's audio finishes, which makes it
impossible to tell a fast commit trigger (like the <SEG> token) from a slow
one (like waiting for sentence-ending punctuation). --gap-min-sec 0
--gap-max-sec 0 restores the old zero-gap rapid-handoff behavior if you
specifically want that stress test instead.

Voice consistency: FLEURS' `test` split for ar_eg is 100% FEMALE (there is no
male Arabic reading), so its role is fixed to FEMALE. Other languages default
to whatever gender gives the largest shared sentence pool — override with
--genders. FLEURS only exposes gender, not a persistent per-speaker id, so
"the same voice for a language" really means "the same gender label," not
literally one individual reader.

Deterministic: given the same TSVs, --seed and --n-groups, this always
produces byte-identical spliced audio and the same manifest.

--no-splice restores the old behavior (one pure single-language turn per
language per group, no audio concatenation) if you need that shape instead.

Requires numpy + soundfile (`pip install numpy soundfile`) for the audio
concatenation.

Usage:

    python build_conversation_manifest.py \
        --fleurs-root . --langs ar_eg ko_kr en_us \
        --n-groups 100 --out conversations/ar_ko_en_test.jsonl
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import string
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLING_RATE = 16000

# FLEURS language directory name -> 2-letter code used in the output.
LANG_CODE = {
    "ar_eg": "ar", "en_us": "en", "de_de": "de", "ko_kr": "ko",
    "ja_jp": "ja", "cmn_hans_cn": "zh", "es_419": "es",
}


def read_tsv(path: Path) -> list[list[str]]:
    # QUOTE_NONE is required: FLEURS transcriptions contain literal quote
    # characters, and the default csv dialect reads those as the start of a
    # quoted (possibly multi-line) field, silently merging rows together.
    with open(path, "r", encoding="utf-8", newline="") as f:
        return [r for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
                 if len(r) >= 7]


def load_lang(root: Path, lang: str, split: str, gender: str) -> dict[str, dict]:
    """sentence id -> {filename, text, duration}, one recording per id.

    If a sentence has multiple recordings by the requested gender, the first
    one in file order is kept (deterministic, independent of --seed).
    """
    tsv_path = root / "data" / lang / f"{split}.tsv"
    if not tsv_path.exists():
        raise FileNotFoundError(
            f"missing {tsv_path}\n"
            f'  hf download google/fleurs --repo-type dataset --include "data/{lang}/*" '
            f"--local-dir {root}"
        )
    out: dict[str, dict] = {}
    for row in read_tsv(tsv_path):
        sent_id, filename, raw_text, _, _, num_samples, sent_gender = row[:7]
        if sent_gender != gender or sent_id in out:
            continue
        try:
            duration = int(num_samples) / SAMPLING_RATE
        except ValueError:
            continue
        out[sent_id] = {"filename": filename, "text": raw_text.strip(), "duration": duration}
    return out


def resolve_audio_dir(root: Path, lang: str, split: str) -> Path:
    audio_dir = root / "data" / lang / "audio" / split
    if not audio_dir.is_dir():
        raise FileNotFoundError(
            f"missing audio dir {audio_dir}\n"
            f'  hf download google/fleurs --repo-type dataset --include "data/{lang}/audio/{split}.tar.gz" '
            f"--local-dir {root}\n"
            f"  then: tar xzf {root}/data/{lang}/audio/{split}.tar.gz -C {root}/data/{lang}/audio/"
        )
    return audio_dir


def load_pcm_i16(wav_path: Path, duration: float) -> np.ndarray:
    frames = int(round(duration * SAMPLING_RATE))
    audio, sr = sf.read(str(wav_path), frames=frames, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    assert sr == SAMPLING_RATE, f"expected {SAMPLING_RATE}Hz, got {sr}Hz: {wav_path}"
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)


def pick_duration(rng: random.Random, full_duration: float, args: argparse.Namespace) -> tuple[float, bool]:
    if rng.random() < args.interrupt_frac:
        keep_frac = rng.uniform(args.interrupt_keep_min, args.interrupt_keep_max)
        return max(min(1.0, full_duration), round(full_duration * keep_frac, 3)), True
    return round(full_duration, 3), False


def resolve_common_ids(sents: list[dict], rng: random.Random, n_groups: int) -> list[str]:
    common_ids = set(sents[0])
    for s in sents[1:]:
        common_ids &= set(s)
    common_ids = sorted(common_ids, key=int)
    if not common_ids:
        print("[ERROR] no sentence id has a recording in every requested "
              "language/gender combination.", file=sys.stderr)
        sys.exit(2)
    rng.shuffle(common_ids)
    n_groups = n_groups if n_groups else len(common_ids)
    if n_groups > len(common_ids):
        print(f"[WARN] requested {n_groups} groups but only {len(common_ids)} "
              f"sentence ids qualify; using all of them.", file=sys.stderr)
        n_groups = len(common_ids)
    return common_ids[:n_groups]


def build_spliced(args: argparse.Namespace, root: Path, langs: list[str], codes: list[str],
                   genders: list[str], sents: list[dict], audio_dirs: list[Path]) -> int:
    rng = random.Random(args.seed)
    picked_ids = resolve_common_ids(sents, rng, args.n_groups)

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    audio_out_dir = out_path.parent / f"{out_path.stem}_audio"
    audio_out_dir.mkdir(parents=True, exist_ok=True)

    n = len(langs)
    n_cut_segments, n_segments = 0, 0
    total_sec = 0.0
    with open(out_path, "w", encoding="utf-8") as out:
        for group_index, sent_id in enumerate(picked_ids):
            pcm_parts: list[np.ndarray] = []
            segments: list[dict] = []
            cum_sec = 0.0
            for i in range(n):
                rec = sents[i][sent_id]
                wav_path = audio_dirs[i] / rec["filename"]
                duration, cut = pick_duration(rng, rec["duration"], args)
                pcm_parts.append(load_pcm_i16(wav_path, duration))
                cum_sec += duration
                is_last = i == n - 1
                gap_sec = 0.0 if is_last else round(rng.uniform(args.gap_min_sec, args.gap_max_sec), 3)
                segments.append({
                    "lang": codes[i], "text": rec["text"],
                    "start_sec": round(cum_sec - duration, 3), "end_sec": round(cum_sec, 3),
                    "full_duration": round(rec["duration"], 3), "cut": cut,
                    "gap_after_sec": gap_sec,
                })
                if gap_sec > 0:
                    pcm_parts.append(np.zeros(int(round(gap_sec * SAMPLING_RATE)), dtype=np.int16))
                    cum_sec += gap_sec
                n_segments += 1
                n_cut_segments += cut

            combined = np.concatenate(pcm_parts)
            wav_out = audio_out_dir / f"group{group_index:04d}_{sent_id}.wav"
            sf.write(str(wav_out), combined, SAMPLING_RATE, subtype="PCM_16")

            # Field names/shape match evaluation/ast/build_manifest_fleurs.py's
            # manifests (utt_id/wav/offset/duration/src_lang/tgt_lang/src_text/
            # tgt_text/speaker_id/talk_id) for the PRIMARY direction (first
            # language spoken -> the language right after the rotation wraps
            # around, i.e. what codes[0] would translate this into). `segments`
            # is additive and carries the actual per-language breakdown a flat
            # src/tgt pair can't represent.
            out.write(json.dumps({
                "utt_id": f"mixed_{sent_id}_{'_'.join(codes)}",
                "wav": str(wav_out),
                "offset": 0.0,
                "duration": round(cum_sec, 3),
                # Purely descriptive of the spliced audio's own span (which
                # language it opens/closes in) — NOT a translation instruction.
                # A real client picks its own single WebSocket targetLang;
                # see run_conversation_smoke_test.py's --target-lang.
                "src_lang": codes[0],
                "tgt_lang": codes[-1],
                "src_text": sents[0][sent_id]["text"],
                "tgt_text": sents[-1][sent_id]["text"],
                "speaker_id": "/".join(genders),
                "talk_id": sent_id,
                "turn_index": group_index,
                "pair_index": group_index,
                "speaker_role": "MIXED",
                "segments": segments,
            }, ensure_ascii=False) + "\n")
            total_sec += cum_sec

    print(f"manifest: {out_path}")
    print(f"  audio: {audio_out_dir}")
    print(f"  {len(picked_ids)} spliced turns, {' -> '.join(codes)} per turn, "
          f"{total_sec / 60:.1f} min total")
    print(f"  segments cut mid-sentence: {n_cut_segments}/{n_segments} "
          f"(keep {args.interrupt_keep_min:.0%}-{args.interrupt_keep_max:.0%} of full length when cut)")
    print(f"  seed={args.seed}  pool size={len(set(sents[0]).intersection(*[set(s) for s in sents[1:]]))}")
    return 0


def build_pure_rotation(args: argparse.Namespace, root: Path, langs: list[str], codes: list[str],
                         genders: list[str], sents: list[dict], audio_dirs: list[Path]) -> int:
    """--no-splice: one pure single-language turn per language per group (legacy shape)."""
    rng = random.Random(args.seed)
    picked_ids = resolve_common_ids(sents, rng, args.n_groups)

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = len(langs)
    turn_index, total_sec, missing_audio, n_interrupted = 0, 0.0, 0, 0
    with open(out_path, "w", encoding="utf-8") as out:
        for group_index, sent_id in enumerate(picked_ids):
            for i in range(n):
                lang, code, gender = langs[i], codes[i], genders[i]
                rec = sents[i][sent_id]
                nxt = (i + 1) % n
                tgt_code, tgt_text = codes[nxt], sents[nxt][sent_id]["text"]
                wav_path = audio_dirs[i] / rec["filename"]
                if not wav_path.exists():
                    missing_audio += 1
                    continue
                duration, interrupted = pick_duration(rng, rec["duration"], args)
                n_interrupted += interrupted
                out.write(json.dumps({
                    "utt_id": f"{lang}_{sent_id}_{Path(rec['filename']).stem[:8]}",
                    "wav": str(wav_path),
                    "offset": 0.0,
                    "duration": duration,
                    "src_lang": code,
                    "tgt_lang": tgt_code,
                    "src_text": rec["text"],
                    "tgt_text": tgt_text,
                    "speaker_id": gender,
                    "talk_id": sent_id,
                    "turn_index": turn_index,
                    "pair_index": group_index,
                    "speaker_role": string.ascii_uppercase[i],
                    "full_duration": round(rec["duration"], 3),
                    "interrupted": interrupted,
                }, ensure_ascii=False) + "\n")
                turn_index += 1
                total_sec += duration

    print(f"manifest: {out_path}")
    print(f"  {len(picked_ids)} sentence groups -> {turn_index} turns ({' -> '.join(codes)} -> ...)")
    print(f"  audio: {total_sec / 60:.1f} min (as streamed, post-cutoff), missing files: {missing_audio}")
    print(f"  interrupted: {n_interrupted}/{turn_index} turns cut mid-sentence")
    return 0


def build(args: argparse.Namespace) -> int:
    root = Path(args.fleurs_root).expanduser().resolve()
    langs = args.langs
    genders = args.genders
    if len(genders) != len(langs):
        print(f"[ERROR] --genders needs exactly one value per --langs "
              f"({len(langs)} langs, {len(genders)} genders given).", file=sys.stderr)
        return 2
    codes = [LANG_CODE.get(l, l.split("_")[0]) for l in langs]

    sents = [load_lang(root, lang, args.split, gender) for lang, gender in zip(langs, genders)]
    audio_dirs = [resolve_audio_dir(root, lang, args.split) for lang in langs]

    fn = build_spliced if args.splice else build_pure_rotation
    return fn(args, root, langs, codes, genders, sents, audio_dirs)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fleurs-root", default=str(Path(__file__).parent),
                   help="directory containing data/<lang>/test.tsv (default: this script's dir)")
    p.add_argument("--langs", nargs="+", default=["ar_eg", "ko_kr", "en_us"],
                   help="FLEURS language directories, in rotation order")
    p.add_argument("--genders", nargs="+", default=["FEMALE", "MALE", "FEMALE"],
                   choices=["MALE", "FEMALE"], metavar="{MALE,FEMALE}",
                   help="one gender per --langs entry, same order")
    p.add_argument("--split", default="test", choices=["test", "dev", "train"])
    p.add_argument("--n-groups", type=int, default=100,
                   help="number of sentence groups (spliced: = that many turns; "
                        "--no-splice: that many turns per language). 0 = every eligible sentence")
    p.add_argument("--seed", type=int, default=20260905,
                   help="shuffle seed; same seed + inputs always yields the same manifest")
    p.add_argument("--interrupt-frac", type=float, default=1.0,
                   help="probability any given segment/turn is cut short instead of run to completion. 0 = never")
    p.add_argument("--interrupt-keep-min", type=float, default=0.3,
                   help="minimum fraction of a segment's audio kept when cut")
    p.add_argument("--interrupt-keep-max", type=float, default=0.85,
                   help="maximum fraction of a segment's audio kept when cut")
    p.add_argument("--gap-min-sec", type=float, default=0.5,
                   help="minimum silence inserted between consecutive segments (a real "
                        "conversational pause). 0/0 restores the old zero-gap rapid-handoff behavior")
    p.add_argument("--gap-max-sec", type=float, default=1.5,
                   help="maximum silence inserted between consecutive segments")
    p.add_argument("--splice", action=argparse.BooleanOptionalAction, default=True,
                   help="one spliced multi-language clip per turn (default) vs. --no-splice "
                        "for one pure single-language turn per language per group")
    p.add_argument("--out", default=None,
                   help="default: conversations/<lang1>_<lang2>_..._test.jsonl")
    args = p.parse_args()
    if args.out is None:
        codes = [LANG_CODE.get(l, l.split("_")[0]) for l in args.langs]
        args.out = str(Path(__file__).parent / "conversations" / f"{'_'.join(codes)}_test.jsonl")
    sys.exit(build(args))


if __name__ == "__main__":
    main()
