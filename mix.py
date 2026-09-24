#!/usr/bin/env python3
"""Several languages of one dataset -> one mixed-language dataset of synthetic conversations.

A multilingual corpus here is one dataset per source language, in subdirectories
of the corpus (fleurs/ko_kr/, fleurs/en_us/; mls/german/, mls/french/). This
strings their items into conversations and writes the result as a new
subdirectory beside them:

    python mix.py fleurs --src ko_kr en_us                       # -> fleurs/ko_kr+en_us/
    python mix.py fleurs --src ko_kr en_us --switch 0.9 --gap 0 0.5 --cut 0.3
                                        # -> fleurs/ko_kr+en_us.switch0.9-gap0-0.5-cut0.3/
    python mix.py fleurs --src ko_kr en_us --level -26          # -> fleurs/ko_kr+en_us.level-26/

A conversation is one wav of turns, and a turn is one item of a source dataset
read by one speaker. When the sources are parallel -- items of different
languages share a sentence key, the item id without its "<lang>_" prefix, as in
FLEURS -- turns use different sentences: a sentence is spoken at most once across
the whole mix, so no turn's reference translation is something that was just
said out loud, and a translator that reads previous turns as context cannot copy
its answer from them. Sources that share no sentence are drawn independently.

Four knobs set how hard the mix is:

  --switch P     chance that the next turn is in a different language. 1 alternates
                 every turn (ko, en, ko, ...); lower values leave runs of one language.
  --gap MIN MAX  silence between turns, in seconds. 0 means the next speaker starts
                 right away, so there is no pause for the VAD to commit on.
  --cut P        chance that a turn is cut off partway, at a word boundary, and the
                 next speaker takes over -- the rest of the sentence is never said.
  --level DB     bring every turn to this active speech level (dBFS) first. Each
                 source was recorded at its own level; left alone, a quiet language
                 next to a loud one hands the loudness jump to the VAD and language
                 ID as a cue. Off by default.

A cut turn's transcript is the words that were said; its translations still belong
to the whole sentence, since half a sentence has no reference translation. It is
marked `partial`, and bench keeps it out of translation metrics while still using
it for WER and language detection. Cutting needs word timings, so each source
dataset has to have been aligned (alignment.jsonl).

Every turn is an item cut from the conversation wav by `offset`, and the
conversation is its `group`. A run reads turns one by one; `longform: true` streams
each conversation whole, which is what exercises switching language mid-stream.

With parallel sources every turn carries references in every language of the mix,
its own included (the text of the same sentence, taken from another source's
references): the contract asks for each declared translation on every item, and a
same-language "translation" is the text itself. bench leaves same-language items out
of translation metrics, so these never score anything. --tgt adds more reference
languages; a sentence missing one of them is not used.

The output directory is named after the knobs that differ from the defaults, and
dataset.yml records all of them under `mix`.
"""
import argparse
import json
import random
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

import _contract as contract

DEFAULTS = {"turns": 6, "switch": 1.0, "gap": [0.5, 1.5], "cut": 0.0, "seed": 0,
            "level": None}
CUT_TAIL_SEC = 0.05
PEAK = 0.99


def dataset_name(sources: list[str], knobs: dict) -> str:
    changed = []
    for key, value in knobs.items():
        if value == DEFAULTS[key]:
            continue
        shown = "-".join(f"{v:g}" for v in value) if isinstance(value, list) else f"{value:g}"
        changed.append(f"{key}{shown}")
    return "+".join(sources) + ("." + "-".join(changed) if changed else "")


def word_ends(transcript: str, aligned: list[dict]) -> list[float] | None:
    """End time of each transcript word, from aligned pieces that may split words
    (Korean) -- matched by counting letters and digits. None when they disagree."""
    timed = [(c, piece["end"]) for piece in aligned
             for c in piece["word"].lower() if c.isalnum()]
    ends, seen = [], 0
    for word in transcript.split():
        seen += sum(c.isalnum() for c in word.lower())
        if seen == 0 or seen > len(timed):
            return None
        ends.append(timed[seen - 1][1])
    return ends if seen == len(timed) else None


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def sentence_key(item: dict) -> str:
    """The item id without its "<lang>_" prefix: FLEURS writes en_1660 and ko_1660
    for the same sentence."""
    prefix = f"{item['src_lang']}_"
    return item["id"].removeprefix(prefix)


def references_of(item: dict, languages: list[str]) -> dict[str, str] | None:
    """The item's own references in the given languages; None when one is missing."""
    known = item["reference"]["translations"]
    if any(not (known.get(lang) or "").strip() for lang in languages):
        return None
    return {lang: known[lang] for lang in languages}


def languages_of(rng: random.Random, sources: list[str], turns: int, switch: float) -> list[str]:
    order = [rng.choice(sources)]
    while len(order) < turns:
        others = [s for s in sources if s != order[-1]]
        order.append(rng.choice(others) if rng.random() < switch else order[-1])
    return order


def read_turn(source_dir: Path, item: dict) -> np.ndarray:
    path = source_dir / item["audio"]
    if item.get("offset") is None:
        audio, rate = sf.read(path, dtype="float32")
    else:
        audio, rate = sf.read(path, dtype="float32",
                              start=round(item["offset"] * contract.SAMPLE_RATE),
                              frames=round(item["duration"] * contract.SAMPLE_RATE))
    if rate != contract.SAMPLE_RATE:
        raise SystemExit(f"{path} is {rate} Hz, not {contract.SAMPLE_RATE}; rebuild "
                         f"{source_dir.name}")
    return audio


def level_to(audio: np.ndarray, level_db: float) -> tuple[np.ndarray, bool]:
    """audio at level_db dBFS of active speech (contract.active_power), and whether
    the gain had to be held back so the peak stays under PEAK."""
    power = contract.active_power(audio)
    if power <= 0:
        return audio, False
    gain = 10 ** ((level_db - 10 * np.log10(power)) / 20)
    peak = float(np.abs(audio).max()) * gain
    if peak > PEAK:
        return audio * (gain * PEAK / peak), True
    return audio * gain, False


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("dataset", help="corpus directory holding one dataset per language, "
                                   "e.g. fleurs")
    p.add_argument("--src", nargs="+", required=True,
                   help="source datasets (subdirectories of the corpus, built first)")
    p.add_argument("--tgt", nargs="*", default=[],
                   help="extra reference languages every turn must carry (e.g. de)")
    p.add_argument("--turns", type=int, default=DEFAULTS["turns"], help="turns per conversation")
    p.add_argument("--switch", type=float, default=DEFAULTS["switch"],
                   help="chance the next turn changes language, 0..1")
    p.add_argument("--gap", nargs=2, type=float, default=DEFAULTS["gap"], metavar=("MIN", "MAX"),
                   help="silence between turns, seconds (0 = no pause)")
    p.add_argument("--cut", type=float, default=DEFAULTS["cut"],
                   help="chance a turn is cut off partway at a word boundary, 0..1")
    p.add_argument("--level", type=float, default=DEFAULTS["level"], metavar="DB",
                   help="bring every turn to this active speech level, dBFS (e.g. -26)")
    p.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    p.add_argument("--limit", type=int, default=None, help="number of conversations")
    args = p.parse_args(argv)

    if len(args.src) < 2:
        raise SystemExit("a mix needs at least two source datasets")
    if args.turns < 2:
        raise SystemExit("--turns must be at least 2")
    if not (0 <= args.switch <= 1 and 0 <= args.cut <= 1):
        raise SystemExit("--switch and --cut are probabilities, 0..1")
    if not 0 <= args.gap[0] <= args.gap[1]:
        raise SystemExit("--gap needs 0 <= MIN <= MAX")
    if args.level is not None and args.level >= 0:
        raise SystemExit("--level is in dBFS, below 0 (e.g. -26)")

    knobs = {"turns": args.turns, "switch": args.switch, "gap": list(args.gap),
             "cut": args.cut, "seed": args.seed}
    if args.level is not None:
        knobs["level"] = args.level
    corpus = contract.require_dir(contract.here(__file__) / args.dataset,
                                  f"no dataset directory {args.dataset}")
    dataset_dir = corpus / dataset_name(args.src, knobs)

    source_dirs, specs, items, alignments = {}, {}, {}, {}
    for source in args.src:
        source_dir = corpus / source
        spec_path = source_dir / "dataset.yml"
        if not spec_path.is_file():
            raise SystemExit(f"{args.dataset}/{source} is not built -- run its install.sh")
        source_dirs[source] = source_dir
        specs[source] = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        rows = [r for r in read_jsonl(source_dir / "manifest.jsonl") if not r.get("partial")]
        if not rows:
            raise SystemExit(f"{args.dataset}/{source}: empty manifest")
        items[source] = {}
        for row in rows:
            items[source].setdefault(sentence_key(row), row)
        alignments[source] = {r["id"]: r for r in
                              read_jsonl(source_dir / contract.ALIGNMENT_NAME)}
    if args.cut and not all(alignments.values()):
        missing = [s for s in args.src if not alignments[s]]
        raise SystemExit(f"--cut needs word timings; {args.dataset}/{missing[0]}/"
                         f"{contract.ALIGNMENT_NAME} is missing. Rebuild it with its "
                         f"convert.py (it aligns at the end).")
    splits = {spec["split"] for spec in specs.values()}
    if len(splits) != 1:
        raise SystemExit(f"the sources are different splits: {sorted(splits)}")
    split = splits.pop()

    languages = list(dict.fromkeys(lang for s in args.src for lang in specs[s]["languages"]))
    shared = set.intersection(*(set(items[s]) for s in args.src))
    parallel = bool(shared)
    wanted = list(dict.fromkeys((languages if parallel else []) + args.tgt))

    def references(key: str) -> dict[str, str] | None:
        """Every wanted language's text for a sentence, from the references its
        items carry in every source; None when one is missing."""
        known = {}
        for source in args.src:
            if key in items[source]:
                for lang, text in items[source][key]["reference"]["translations"].items():
                    if text and text.strip():
                        known.setdefault(lang, text)
        if any(lang not in known for lang in wanted):
            return None
        return {lang: known[lang] for lang in wanted}

    rng = random.Random(args.seed)
    if parallel:
        keys = sorted(shared, key=lambda s: (len(s), s))
        refs = {k: references(k) for k in keys}
        keys = [k for k in keys if refs[k] is not None]
        if not keys:
            lacking = [lang for lang in wanted
                       if not any(lang in items[s][k]["reference"]["translations"]
                                  for s in args.src for k in shared)]
            raise SystemExit(f"no shared sentence has references in {lacking or wanted}; "
                             f"build each source with the others as targets")
        rng.shuffle(keys)
        pools = {source: keys[i::len(args.src)] for i, source in enumerate(args.src)}
    else:
        refs, pools = {}, {}
        for source in args.src:
            keys = sorted(items[source], key=lambda s: (len(s), s))
            refs.update({(source, k): references_of(items[source][k], args.tgt)
                         for k in keys})
            keys = [k for k in keys if refs[(source, k)] is not None]
            if not keys:
                raise SystemExit(f"no item of {args.dataset}/{source} has references "
                                 f"in {args.tgt}")
            rng.shuffle(keys)
            pools[source] = keys
    taken = {source: 0 for source in args.src}

    out = corpus / "data" / "mixed" / dataset_dir.name / split
    out.mkdir(parents=True, exist_ok=True)
    rows, groups, cut_turns, held_back = [], 0, 0, 0
    while args.limit is None or groups < args.limit:
        order = languages_of(rng, args.src, args.turns, args.switch)
        if any(taken[s] + order.count(s) > len(pools[s]) for s in args.src):
            break
        group = f"conv{groups:04d}"
        groups += 1
        pieces, cursor = [], 0.0
        for turn, source in enumerate(order):
            key = pools[source][taken[source]]
            taken[source] += 1
            item = items[source][key]
            audio = read_turn(source_dirs[source], item)
            if args.level is not None:
                audio, limited = level_to(audio, args.level)
                held_back += limited
            transcript, partial = item["reference"]["transcript"], False
            if turn < args.turns - 1 and rng.random() < args.cut:
                aligned = alignments[source].get(item["id"])
                words = transcript.split()
                ends = (word_ends(transcript, aligned["words"])
                        if aligned and aligned["transcript"] == transcript else None)
                if ends and len(words) >= 2:
                    kept = rng.randint(1, len(words) - 1)
                    stop = min(len(audio), int((ends[kept - 1] + CUT_TAIL_SEC)
                                               * contract.SAMPLE_RATE))
                    audio, transcript, partial = audio[:stop], " ".join(words[:kept]), True
                    cut_turns += 1
            duration = len(audio) / contract.SAMPLE_RATE
            rows.append(contract.row(
                item_id=f"{group}_{turn:02d}_{item['id']}",
                audio_rel=f"audio/{group}.wav",
                duration=duration,
                offset=cursor,
                src_lang=item["src_lang"],
                transcript=transcript,
                group=group,
                speaker=f"{source}:{item['speaker']}",
                translations=refs[key] if parallel else refs[(source, key)],
                partial=partial))
            pieces.append(audio)
            cursor += duration
            if turn < args.turns - 1:
                gap = np.zeros(int(rng.uniform(*args.gap) * contract.SAMPLE_RATE),
                               dtype="float32")
                pieces.append(gap)
                cursor += len(gap) / contract.SAMPLE_RATE
        sf.write(out / f"{group}.wav", np.concatenate(pieces), contract.SAMPLE_RATE,
                 subtype="PCM_16")

    if not rows:
        raise SystemExit(f"not enough sentences for one conversation of {args.turns} turns")
    print(f"mixed {groups} conversations, {len(rows)} turns ({cut_turns} cut) -> {out}")
    if held_back:
        print(f"  {held_back} turn(s) could not reach {args.level:g} dBFS without clipping "
              f"and were left quieter")

    metrics = {spec["primary_metric"] for spec in specs.values()}
    mix = {"sources": list(args.src), **knobs, "cut_turns": cut_turns}
    if args.level is not None:
        mix["level_held_back_turns"] = held_back
    dataset_dir.mkdir(exist_ok=True)
    contract.link_audio(dataset_dir, out)
    contract.write_spec(dataset_dir, name=f"{args.dataset}/{dataset_dir.name}", split=split,
                        languages=languages,
                        # Characters are the one unit every language's text shares.
                        primary_metric=metrics.pop() if len(metrics) == 1 else "cer",
                        translations=sorted(wanted),
                        group_rule=f"conversation of {args.turns} turns ({', '.join(languages)})",
                        bench_defaults=specs[args.src[0]]["bench_defaults"],
                        extra={"mix": mix})
    contract.write_manifest(dataset_dir, rows)
    contract.align(dataset_dir)
    return contract.verify(dataset_dir)


if __name__ == "__main__":
    raise SystemExit(main())
