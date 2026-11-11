#!/usr/bin/env python3
"""_src/ downloads -> noise/<place>/*.wav and room/<place>/*.wav at 16 kHz mono.

    python augment/convert.py
"""
import argparse
import io
import re
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

SAMPLE_RATE = 16000
SCAFE_CHANNELS = ("01", "06", "11", "16")
RECEIVERS = ("A105", "A306", "A406", "A506")
RIR_CAPSULE = 0
RIR_PEAK = 0.9
RIR_SECONDS = 2.0
MIT_RESTAURANT = re.compile(r"Audio/h\d{3}_(?:FastFood)?Restaurant_\w*\.wav")


def resample(audio: np.ndarray, sr: int) -> np.ndarray:
    return audio if sr == SAMPLE_RATE else soxr.resample(audio, sr, SAMPLE_RATE)


def write(dest: Path, audio: np.ndarray, subtype: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    sf.write(str(partial), audio, SAMPLE_RATE, format="WAV", subtype=subtype)
    partial.replace(dest)
    print(f"  {dest.relative_to(dest.parents[2])}")


def noise_cafe(src: Path, out: Path) -> None:
    with zipfile.ZipFile(src / "SCAFE_48k.zip") as z:
        for ch in SCAFE_CHANNELS:
            dest = out / "noise" / "cafe" / f"demand_scafe_ch{ch}.wav"
            if dest.is_file():
                continue
            audio, sr = sf.read(io.BytesIO(z.read(f"SCAFE/ch{ch}.wav")), dtype="float32")
            write(dest, resample(audio, sr), "PCM_16")


def room_hall(src: Path, out: Path) -> None:
    for receiver in RECEIVERS:
        dest = out / "room" / "hall" / f"arvedi_S0_{receiver}_cap{RIR_CAPSULE + 1}.wav"
        if dest.is_file():
            continue
        audio, sr = sf.read(str(src / f"rir-S0-{receiver}.wav"), dtype="float32", always_2d=True)
        rir = resample(audio[:, RIR_CAPSULE], sr)[: int(RIR_SECONDS * SAMPLE_RATE)]
        write(dest, rir * (RIR_PEAK / float(np.abs(rir).max())), "FLOAT")


def room_restaurant(src: Path, out: Path) -> None:
    with zipfile.ZipFile(src / "MIT_IR_Survey.zip") as z:
        for name in sorted(n for n in z.namelist() if MIT_RESTAURANT.fullmatch(n)):
            dest = out / "room" / "restaurant" / f"mit_{Path(name).stem.split('_')[0]}.wav"
            if dest.is_file():
                continue
            audio, sr = sf.read(io.BytesIO(z.read(name)), dtype="float32")
            rir = resample(audio, sr)[: int(RIR_SECONDS * SAMPLE_RATE)]
            write(dest, rir * (RIR_PEAK / float(np.abs(rir).max())), "FLOAT")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    args = p.parse_args(argv)

    src = Path(__file__).resolve().parent / "_src"
    if not (src / "SCAFE_48k.zip").is_file():
        raise SystemExit(f"no {src}/SCAFE_48k.zip -- run augment/install.sh first.")
    noise_cafe(src, args.out)
    room_hall(src, args.out)
    room_restaurant(src, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
