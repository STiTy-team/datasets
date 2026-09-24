#!/usr/bin/env python3
"""AMI Meeting Corpus -> the bench dataset contract. English meetings, ASR.

One meeting is one wav (the headset mix, or the first microphone of array 1),
and the NXT manual annotations give each speaker's segments on that meeting's
timeline: segments/<meeting>.<agent>.segments.xml points at a run of
words/<meeting>.<agent>.words.xml. Each segment becomes an item pointing into
the meeting wav with offset/duration -- nothing is cut. Segments longer than
MAX_PIECE_WORDS are cut at sentence ends (see pack_sentences). group is the
meeting and items run in start order, so segments of different speakers overlap.

Meetings follow the full-corpus-asr partition (Kaldi, Lhotse, ESPnet).

    python ami/convert.py --split test --mic ihm-mix
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _contract as contract

NAME = "ami"
NITE = "{http://nite.sourceforge.net/}"
MEETINGS = {
    "test": ["EN2002a", "EN2002b", "EN2002c", "EN2002d", "ES2004a", "ES2004b",
             "ES2004c", "ES2004d", "IS1009a", "IS1009b", "IS1009c", "IS1009d",
             "TS3003a", "TS3003b", "TS3003c", "TS3003d"],
    "dev": ["ES2011a", "ES2011b", "ES2011c", "ES2011d", "IB4001", "IB4002", "IB4003",
            "IB4004", "IB4010", "IB4011", "IS1008a", "IS1008b", "IS1008c", "IS1008d",
            "TS3004a", "TS3004b", "TS3004c", "TS3004d"],
}
STREAMS = {"ihm-mix": "Mix-Headset", "sdm": "Array1-01"}
HREF = re.compile(r"#id\(([^)]+)\)(?:\.\.id\(([^)]+)\))?")
SENTENCE_ENDS = {".", "?", "!"}
MAX_PIECE_WORDS = 60


def speakers(annotations: Path, meeting: str) -> dict[str, str]:
    """NXT agent letter -> global speaker id, for one meeting."""
    root = ET.parse(annotations / "corpusResources" / "meetings.xml").getroot()
    for node in root.iter("meeting"):
        if node.get("observation") == meeting:
            return {s.get("nxt_agent"): s.get("global_name") for s in node.iter("speaker")}
    raise SystemExit(f"{meeting} is not in meetings.xml")


def read_words(path: Path) -> tuple[list[ET.Element], dict[str, int]]:
    elements = list(ET.parse(path).getroot())
    return elements, {e.get(f"{NITE}id"): i for i, e in enumerate(elements)}


def join_words(words: list[ET.Element]) -> str:
    """Words joined by spaces, punctuation attached to the word before it."""
    text = ""
    for w in words:
        word = w.text.strip()
        text += word if w.get("punc") == "true" or not text else " " + word
    return text


def pack_sentences(words: list[ET.Element]) -> list[list[ET.Element]]:
    """Consecutive sentences packed into pieces of at most MAX_PIECE_WORDS words.

    A speaker's segment can run for minutes without a pause the transcribers
    marked, and word times leave no gaps to cut at, so a long segment is cut at
    its sentence ends instead. A single sentence longer than the limit stays whole.
    """
    sentences, current = [], []
    for w in words:
        current.append(w)
        if w.get("punc") == "true" and w.text.strip() in SENTENCE_ENDS:
            sentences.append(current)
            current = []
    if current:
        sentences.append(current)
    pieces, piece = [], []
    for sentence in sentences:
        if piece and spoken(piece) + spoken(sentence) > MAX_PIECE_WORDS:
            pieces.append(piece)
            piece = []
        piece += sentence
    return pieces + [piece] if piece else pieces


def spoken(words: list[ET.Element]) -> int:
    return sum(w.get("punc") != "true" for w in words)


def read_segments(annotations: Path, meeting: str, agent: str) -> list[dict]:
    words_path = annotations / "words" / f"{meeting}.{agent}.words.xml"
    segments_path = annotations / "segments" / f"{meeting}.{agent}.segments.xml"
    if not segments_path.is_file():
        return []
    elements, index = read_words(words_path)
    out = []
    for segment in ET.parse(segments_path).getroot().iter("segment"):
        child = segment.find(f"{NITE}child")
        if child is None:
            continue
        first, last = HREF.search(child.get("href")).groups()
        words = [e for e in elements[index[first]:index[last or first] + 1]
                 if e.tag == "w" and (e.text or "").strip()]
        if not spoken(words):
            continue
        pieces = pack_sentences(words)
        segment_id = segment.get(f"{NITE}id").split(".", 1)[1]
        for n, piece in enumerate(pieces):
            times = [float(w.get(k)) for w in piece for k in ("starttime", "endtime")
                     if w.get(k)]
            if n == 0:
                times.append(float(segment.get("transcriber_start")))
            if n == len(pieces) - 1:
                times.append(float(segment.get("transcriber_end")))
            start, end = min(times), max(times)
            if end > start:
                out.append({"id": segment_id if len(pieces) == 1 else f"{segment_id}.{n}",
                            "start": start, "end": end, "text": join_words(piece)})
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--split", default="test", choices=MEETINGS)
    p.add_argument("--mic", default="ihm-mix", choices=STREAMS)
    p.add_argument("--list", action="store_true",
                   help="print the split's meeting ids and exit (install.sh uses this)")
    args = p.parse_args(argv)

    if args.list:
        print("\n".join(MEETINGS[args.split]))
        return 0

    here = contract.here(__file__)
    annotations = contract.require_dir(here / "data" / "annotations",
                                       "Run ami/install.sh first.")
    audio_dir = contract.require_dir(here / "data" / "audio", "Run ami/install.sh first.")
    stream = STREAMS[args.mic]

    rows = []
    for meeting in MEETINGS[args.split]:
        wav = f"{meeting}.{stream}.wav"
        if not (audio_dir / wav).is_file():
            raise SystemExit(f"missing {audio_dir / wav}\nRun MIC={args.mic} ami/install.sh.")
        segments = []
        for agent, speaker in speakers(annotations, meeting).items():
            segments += [dict(s, agent=agent, speaker=speaker)
                         for s in read_segments(annotations, meeting, agent)]
        segments.sort(key=lambda s: (s["start"], s["agent"]))
        rows += [contract.row(item_id=f"{meeting}_{s['agent']}_{s['id']}",
                              audio_rel=f"audio/{wav}", offset=s["start"],
                              duration=s["end"] - s["start"], src_lang="en",
                              transcript=s["text"], group=meeting, speaker=s["speaker"])
                 for s in segments]
    contract.report_lengths("en", (r["reference"]["transcript"] for r in rows))
    print(f"  {len(MEETINGS[args.split])} meetings, {len(rows)} segments")

    contract.link_audio(here, audio_dir)
    contract.write_spec(here, name=NAME, split=f"{args.split}-{args.mic}", languages=["en"],
                        primary_metric="wer", translations=[], group_rule="meeting",
                        bench_defaults={"trailing_silence_ms": 4000,
                                        "chunk_size_ms": 200, "send_interval_ms": 200},
                        extra={"mic": args.mic})
    contract.write_manifest(here, rows)
    contract.align(here)
    return contract.verify(here)


if __name__ == "__main__":
    raise SystemExit(main())
