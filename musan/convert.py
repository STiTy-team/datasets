#!/usr/bin/env python3
"""An existing bench dataset + MUSAN -> the same dataset under additive noise.

MUSAN has no transcripts; it is noise, music and babble to mix into speech. Every
wav the source manifest points at is rewritten with MUSAN audio of one kind laid
under it at a fixed SNR, and the manifest, alignment and spec are carried over
unchanged -- the words, their times and the item windows do not move. The result
is a new dataset beside this script:

    python musan/convert.py --source fleurs/en_us --kind noise --snr 5
        # -> musan/fleurs_en_us.noise-snr5/

The noise under each wav is MUSAN files of that kind strung end to end from a
random start, chosen by a seed and the wav's path, so rebuilding gives the same
mix. SNR is measured against the speech's active level (contract.active_power),
so the silence around a short clip or between turns of a meeting does not
dilute it. When the mix would clip, speech and noise are scaled down together,
which keeps the SNR.
"""
import argparse
import json
import random
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import soundfile as sf
import yaml

import _contract as contract

NAME = "musan"
KINDS = ("noise", "music", "speech")
SPEC_KEYS = {"name", "split", "languages", "audio", "provides", "primary_metric",
             "group_rule", "bench_defaults"}


def noise_track(files: list[Path], length: int, rng: random.Random) -> np.ndarray:
    """MUSAN files strung end to end from a random point until length is covered."""
    pieces, have = [], 0
    first = True
    while have < length:
        audio, sr = sf.read(str(rng.choice(files)), dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)
        if sr != contract.SAMPLE_RATE:
            import soxr
            audio = soxr.resample(audio, sr, contract.SAMPLE_RATE)
        if first and len(audio) > 1:
            audio = audio[rng.randrange(len(audio)):]
            first = False
        pieces.append(audio)
        have += len(audio)
    return np.concatenate(pieces)[:length]


def mix(job: tuple) -> None:
    source, dest, key, files, snr, seed = job
    if dest.is_file() and contract.audio_problem(dest) is None:
        return
    speech, _ = sf.read(str(source), dtype="float32")
    noise = noise_track(files, len(speech), random.Random(f"{seed}:{key}"))
    gain = np.sqrt(contract.active_power(speech) / (max(float(np.mean(noise ** 2)), 1e-12)
                                           * 10 ** (snr / 10)))
    mixed = speech + gain * noise
    peak = float(np.abs(mixed).max())
    if peak > 0.99:
        mixed *= 0.99 / peak
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    sf.write(str(partial), mixed, contract.SAMPLE_RATE, format="WAV", subtype="PCM_16")
    partial.replace(dest)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", required=True,
                   help="dataset directory under the repo root, e.g. fleurs/en_us")
    p.add_argument("--kind", default="noise", choices=KINDS)
    p.add_argument("--snr", type=float, required=True, help="dB")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)

    here = contract.here(__file__)
    source = contract.require_dir(here.parent / args.source,
                                  f"Build {args.source} first (its install.sh).")
    if not (source / "manifest.jsonl").is_file():
        raise SystemExit(f"no manifest.jsonl in {source} -- build it first.")
    files = sorted((here / "data" / "musan" / args.kind).rglob("*.wav"))
    if not files:
        raise SystemExit(f"no MUSAN {args.kind} wavs under {here}/data/musan\n"
                         f"Run KINDS={args.kind} musan/install.sh first.")

    label = f"{args.source.strip('/').replace('/', '_')}.{args.kind}-snr{args.snr:g}"
    if args.seed:
        label += f"-seed{args.seed}"
    dataset_dir = here / label
    audio_out = here / "data" / "mixed" / label
    with open(source / "manifest.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    wavs = sorted({r["audio"] for r in rows})
    if not all(w.startswith("audio/") for w in wavs):
        raise SystemExit(f"{args.source}: audio paths must start with audio/")

    print(f"mixing {len(wavs)} wavs with MUSAN {args.kind} ({len(files)} files) "
          f"at {args.snr:g} dB -> {audio_out} ...")
    jobs = [(source / w, audio_out / w.removeprefix("audio/"), w, files, args.snr, args.seed)
            for w in wavs]
    with ProcessPoolExecutor() as pool:
        for n, _ in enumerate(pool.map(mix, jobs, chunksize=8), start=1):
            if n % 200 == 0:
                print(f"  {n}/{len(jobs)}", flush=True)
    dataset_dir.mkdir(exist_ok=True)
    contract.link_audio(dataset_dir, audio_out)

    spec = yaml.safe_load((source / "dataset.yml").read_text(encoding="utf-8"))
    extra = {k: v for k, v in spec.items() if k not in SPEC_KEYS}
    extra["musan"] = {"source": spec["name"], "kind": args.kind, "snr_db": args.snr,
                      "seed": args.seed}
    contract.write_spec(dataset_dir, name=f"{NAME}/{label}", split=spec["split"],
                        languages=spec["languages"], primary_metric=spec["primary_metric"],
                        translations=spec["provides"].get("translations") or [],
                        transcript=spec["provides"].get("transcript", True),
                        group_rule=spec["group_rule"], bench_defaults=spec["bench_defaults"],
                        extra=extra)
    contract.write_manifest(dataset_dir, rows)
    # Same words at the same times: the source's alignment still holds.
    if (source / contract.ALIGNMENT_NAME).is_file():
        shutil.copyfile(source / contract.ALIGNMENT_NAME, dataset_dir / contract.ALIGNMENT_NAME)
    contract.align(dataset_dir)
    return contract.verify(dataset_dir)


if __name__ == "__main__":
    raise SystemExit(main())
