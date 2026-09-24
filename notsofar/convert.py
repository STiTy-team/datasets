#!/usr/bin/env python3
"""NOTSOFAR-1 -> the bench dataset contract. Real office meetings, English ASR.

Every meeting was recorded at once by close-talk mics and several far-field
devices, all sample-aligned. One far-field channel per meeting is used as the
meeting wav (--device, a single-channel device by default), and each utterance
of gt_transcription.json becomes an item pointing into it with offset/duration
-- nothing is cut. group is the meeting and items run in start order, so
utterances of different speakers overlap, which is the point of this corpus.

The per-meeting Hashtags (#DebateOverlaps, #TransientNoise=high, #Music, ...)
are the corpus's overlap and noise metadata; dataset.yml keeps them per meeting.

    python notsofar/convert.py --version eval_full --device sc_meetup_0
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _contract as contract

NAME = "notsofar"
VERSIONS = {
    "eval_full": "eval_set/240825.1_eval_full_with_GT",
    "eval_small": "eval_set/240629.1_eval_small_with_GT",
    "dev": "dev_set/240825.1_dev1",
}


def meetings_dir(here: Path, version: str) -> Path:
    return here / "data" / "benchmark-datasets" / VERSIONS[version] / "MTG"


def pick_wav(meeting: Path, device: str) -> tuple[str, str]:
    """(device, wav path relative to the meeting) -- the asked-for device when the
    meeting has it, else its first single-channel far-field device.

    Devices are named by their folder (sc_rockfall_0, mc_rockfall_0): device_name
    in devices.json is the same for an array and the single mic beside it."""
    wavs = {}
    for d in json.loads((meeting / "devices.json").read_text(encoding="utf-8")):
        if d["is_close_talk"]:
            continue
        first = d["wav_file_names"].split(",")[0].strip()
        wavs[first.split("/")[0]] = first
    if device not in wavs:
        fallback = sorted(n for n in wavs if n.startswith("sc_"))
        if not fallback:
            raise SystemExit(f"{meeting.name}: no {device} and no single-channel device")
        device = fallback[0]
    return device, wavs[device]


def clean(text: str) -> str:
    """Drop the transcription tags (<ST/>, <FILL/>, <UNKNOWN/>, ...), keeping what
    <PName>...</PName> wraps, and reattach punctuation left floating."""
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r" ([,.?!])", r"\1", text)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", default="eval_full", choices=VERSIONS)
    p.add_argument("--device", default="sc_meetup_0",
                   help="device whose first channel is the meeting audio")
    p.add_argument("--list-wavs", action="store_true",
                   help="print each meeting's wav path in the HF repo and exit "
                        "(install.sh uses this)")
    args = p.parse_args(argv)

    here = contract.here(__file__)
    root = contract.require_dir(meetings_dir(here, args.version),
                                "Run notsofar/install.sh first.")
    meetings = sorted(m for m in root.iterdir() if (m / "devices.json").is_file())
    if not meetings:
        raise SystemExit(f"no meetings under {root}\nRun notsofar/install.sh first.")

    if args.list_wavs:
        for meeting in meetings:
            _, wav = pick_wav(meeting, args.device)
            print(f"benchmark-datasets/{VERSIONS[args.version]}/MTG/{meeting.name}/{wav}")
        return 0

    rows, info = [], {}
    for meeting in meetings:
        device, wav = pick_wav(meeting, args.device)
        if not (meeting / wav).is_file():
            raise SystemExit(f"missing {meeting / wav}\nRun notsofar/install.sh first.")
        metadata = json.loads((meeting / "gt_meeting_metadata.json").read_text(encoding="utf-8"))
        length = float(metadata["MeetingDurationSec"])
        utterances = json.loads((meeting / "gt_transcription.json").read_text(encoding="utf-8"))
        utterances = sorted(utterances, key=lambda u: (u["start_time"], u["end_time"]))
        info[meeting.name] = {
            "device": device,
            "hashtags": [t.strip() for t in metadata.get("Hashtags", "").split(",") if t.strip()],
        }
        for n, u in enumerate(utterances):
            text = clean(u["text"])
            start, end = float(u["start_time"]), min(float(u["end_time"]), length)
            if not text or end <= start:
                continue
            rows.append(contract.row(item_id=f"{meeting.name}_{n:04d}",
                                     audio_rel=f"audio/{meeting.name}/{wav}",
                                     offset=start, duration=end - start, src_lang="en",
                                     transcript=text, group=meeting.name,
                                     speaker=f"{meeting.name}_{u['speaker_id']}"))
    contract.report_lengths("en", (r["reference"]["transcript"] for r in rows))
    fallbacks = sum(m["device"] != args.device for m in info.values())
    print(f"  {len(meetings)} meetings, {len(rows)} utterances"
          + (f", {fallbacks} meeting(s) without {args.device} use another device"
             if fallbacks else ""))

    contract.link_audio(here, root)
    contract.write_spec(here, name=NAME, split=args.version, languages=["en"],
                        primary_metric="wer", translations=[], group_rule="meeting",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200},
                        extra={"device": args.device, "meetings": info})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
