"""The bench dataset contract, in one place.

Deliberately self-contained: this repo does not import STiTy. Two checkouts
sitting side by side is an assumption that breaks the first time someone clones
only one of them, and a dataset repo that cannot run on its own is not really a
separate concern.

This is where a dataset is judged valid. bench reads what comes out of here and
assumes it is well formed, so a converter has to fail at the end of conversion
rather than leave the problem for a benchmark run to find.

There is exactly one audio format bench reads: 16 kHz mono PCM16 wav. A corpus
that ships anything else (mp3, opus, NIST sph, headerless pcm, bytes inside
parquet) goes through transcode() once, at conversion time. Declaring a format
per dataset used to let a headerless .pcm pass verify() and then fail inside
bench, whose loader never looks at the declaration.
"""
from __future__ import annotations

import functools
import io
import json
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import accumulate
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

AUDIO_FORMAT = "wav"
SAMPLE_RATE = 16000
CHANNELS = 1
_SF_FORMAT = "WAV"
_SF_SUBTYPE = "PCM_16"

PRIMARY_METRICS = {"wer", "cer"}
DURATION_TOLERANCE_SEC = 0.05

# A sentence longer than this is almost always a parsing failure rather than a
# real utterance. Checked before conversion because a small smoke test will not
# surface it: a merged-row fragment of 2,916 words once reached a live run,
# blew the model's token limit, and cost real money.
MAX_REASONABLE_WORDS = 200


def probe_duration(path: Path) -> float:
    info = sf.info(str(path))
    return float(info.frames) / float(info.samplerate)


def audio_problem(path: Path) -> str | None:
    """Why this file is not the one format bench reads, or None if it is."""
    try:
        info = sf.info(str(path))
    except RuntimeError as e:
        return f"unreadable ({e})"
    got = (info.format, info.subtype, info.samplerate, info.channels)
    want = (_SF_FORMAT, _SF_SUBTYPE, SAMPLE_RATE, CHANNELS)
    if got != want:
        return (f"is {info.format}/{info.subtype} {info.samplerate} Hz "
                f"{info.channels}ch, want {_SF_FORMAT}/{_SF_SUBTYPE} "
                f"{SAMPLE_RATE} Hz {CHANNELS}ch")
    return None


def transcode(source: Path | bytes, dest: Path, *, raw_pcm: bool = False) -> float:
    """Decode source into dest as 16 kHz mono PCM16 wav. Returns the duration.

    source is a path or the encoded bytes themselves (audio embedded in parquet).
    Anything libsndfile decodes works: wav, flac, mp3, ogg/opus, NIST sph.
    raw_pcm=True reads headerless little-endian s16le at 16 kHz mono, which has
    no header to detect. A dest that already conforms is left alone, so re-running
    a converter costs a header read per file rather than a decode.
    """
    if dest.is_file() and audio_problem(dest) is None:
        return probe_duration(dest)
    src = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else str(source)
    raw = ({"format": "RAW", "samplerate": SAMPLE_RATE, "channels": 1,
            "subtype": "PCM_16", "endian": "LITTLE"} if raw_pcm else {})
    audio, sr = sf.read(src, dtype="float32", always_2d=True, **raw)
    audio = audio.mean(axis=1)
    if sr != SAMPLE_RATE:
        import soxr
        audio = soxr.resample(audio, sr, SAMPLE_RATE)
    # Resampling overshoots on near-full-scale input; unclipped, the int16 cast
    # wraps those samples around to the opposite sign.
    audio = np.clip(audio, -1.0, 1.0)
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    sf.write(str(partial), audio, SAMPLE_RATE, format=_SF_FORMAT, subtype=_SF_SUBTYPE)
    partial.replace(dest)
    return len(audio) / SAMPLE_RATE


def _transcode_job(job: tuple) -> float:
    source, dest, raw_pcm = job
    return transcode(source, dest, raw_pcm=raw_pcm)


def transcode_all(jobs: list[tuple[Path | bytes, Path]], *,
                  raw_pcm: bool = False) -> list[float]:
    """transcode() over (source, dest) pairs on every core. Durations, in order."""
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor() as pool:
        return list(pool.map(_transcode_job, [(s, d, raw_pcm) for s, d in jobs],
                             chunksize=16))


def link_audio(dataset_dir: Path, source: Path) -> Path:
    """Symlink <dataset>/audio -> source. Never copies; corpora are huge."""
    link = dataset_dir / "audio"
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        raise SystemExit(f"{link} exists and is not a symlink; remove it first")
    if not source.is_dir():
        raise SystemExit(f"audio source is not a directory: {source}")
    link.symlink_to(source)
    return link


def row(*, item_id: str, audio_rel: str, duration: float, src_lang: str,
        transcript: str = "", group: str | None = None, speaker: str = "",
        offset: float | None = None, translations: dict | None = None) -> dict:
    out = {
        "id": item_id,
        "audio": audio_rel,
        "duration": round(float(duration), 3),
        "group": group or item_id,
        "speaker": speaker,
        "src_lang": src_lang,
        "reference": {"transcript": transcript,
                      "translations": dict(translations or {})},
    }
    if offset is not None:
        out["offset"] = round(float(offset), 3)
    return out


def write_spec(dataset_dir: Path, *, name: str, split: str, languages: list[str],
               primary_metric: str, translations: list[str], group_rule: str,
               bench_defaults: dict, transcript: bool = True) -> Path:
    """transcript=False for a corpus with no source-side text (ST-only
    references, or raw recordings); verify() then stops demanding one."""
    if primary_metric not in PRIMARY_METRICS:
        raise SystemExit(f"primary_metric must be one of {sorted(PRIMARY_METRICS)}")
    dataset_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "name": name,
        "split": split,
        "languages": list(languages),
        "audio": {"format": AUDIO_FORMAT, "sample_rate": SAMPLE_RATE},
        "provides": {"transcript": bool(transcript),
                     "translations": list(translations)},
        "primary_metric": primary_metric,
        "group_rule": group_rule,
        "bench_defaults": dict(bench_defaults),
    }
    path = dataset_dir / "dataset.yml"
    path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return path


def write_manifest(dataset_dir: Path, rows: list[dict]) -> Path:
    if not rows:
        raise SystemExit("no items to write -- check the source paths and filters")
    path = dataset_dir / "manifest.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for item in rows:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return path


def report_lengths(label: str, texts) -> None:
    """Print the word-count distribution and refuse absurd rows."""
    counts = [len(t.split()) for t in texts if t and t.strip()]
    if not counts:
        raise SystemExit(f"{label}: every sentence was empty")
    print(f"  {label}: {len(counts)} sentences, words min {min(counts)} "
          f"median {int(statistics.median(counts))} max {max(counts)}")
    if max(counts) > MAX_REASONABLE_WORDS:
        raise SystemExit(
            f"{label}: longest sentence is {max(counts)} words, past the "
            f"{MAX_REASONABLE_WORDS}-word sanity limit. That is the signature of a "
            f"parsing problem, not a real sentence -- inspect before converting."
        )


def verify(dataset_dir: Path) -> int:
    """Re-read what was written and check it. Returns a process exit code."""
    spec = yaml.safe_load((dataset_dir / "dataset.yml").read_text(encoding="utf-8"))
    want_transcript = bool(spec["provides"].get("transcript", True))
    want_translations = list(spec["provides"].get("translations") or [])

    problems: list[str] = []
    declared = (spec["audio"].get("format"), int(spec["audio"].get("sample_rate", 0)))
    if declared != (AUDIO_FORMAT, SAMPLE_RATE):
        problems.append(f"dataset.yml declares audio {declared}, the only format is "
                        f"{(AUDIO_FORMAT, SAMPLE_RATE)}")
    # Items cut from one long file by offset share it; probe each file once.
    probed: dict[Path, tuple[str | None, float]] = {}
    seen: set[str] = set()
    groups: list[str] = []
    n = 0

    with open(dataset_dir / "manifest.jsonl", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            n += 1
            item_id = item["id"]
            if item_id in seen:
                problems.append(f"{item_id}: duplicate id (line {lineno})")
            seen.add(item_id)
            if item["group"] not in groups:
                groups.append(item["group"])
            if Path(item["audio"]).is_absolute():
                problems.append(f"{item_id}: audio path is absolute")
                continue
            audio = dataset_dir / item["audio"]
            if not audio.is_file():
                problems.append(f"{item_id}: audio missing at {item['audio']}")
                continue
            if audio not in probed:
                bad = audio_problem(audio)
                probed[audio] = (bad, 0.0 if bad else probe_duration(audio))
            bad, actual = probed[audio]
            if bad:
                problems.append(f"{item_id}: {item['audio']} {bad}")
                continue
            if want_transcript and not (item["reference"].get("transcript") or "").strip():
                problems.append(f"{item_id}: empty transcript")
            for lang in want_translations:
                if not (item["reference"]["translations"].get(lang) or "").strip():
                    problems.append(f"{item_id}: missing {lang} reference translation")
            duration = float(item["duration"])
            offset = item.get("offset")
            if offset is None:
                if abs(actual - duration) > DURATION_TOLERANCE_SEC:
                    problems.append(
                        f"{item_id}: duration {duration:.3f}s but the file is "
                        f"{actual:.3f}s")
            elif offset < 0 or offset + duration > actual + DURATION_TOLERANCE_SEC:
                problems.append(
                    f"{item_id}: window [{offset:.3f}, {offset + duration:.3f}]s "
                    f"runs outside the {actual:.3f}s file")

    alignment = dataset_dir / ALIGNMENT_NAME
    n_aligned = 0
    if alignment.is_file():
        transcripts = {}
        with open(dataset_dir / "manifest.jsonl", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    transcripts[item["id"]] = item["reference"].get("transcript") or ""
        with open(alignment, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                aligned = json.loads(line)
                n_aligned += 1
                if aligned["id"] not in transcripts:
                    problems.append(f"{aligned['id']}: in alignment.jsonl but not "
                                    f"in the manifest -- re-run convert.py")
                elif aligned["transcript"] != transcripts[aligned["id"]]:
                    problems.append(f"{aligned['id']}: aligned against an old "
                                    f"transcript -- re-run convert.py")

    # Sessions must be contiguous: bench keeps one handler alive per group, and a
    # group that reappears later would silently get a second, stateless one.
    if len(groups) != len(set(groups)):
        problems.append("group values are not contiguous -- sort items by group")

    print()
    print(f"{spec['name']}: {n} items, {len(set(groups))} sessions, "
          f"languages {spec['languages']}, references "
          f"{['transcript'] * want_transcript + want_translations}"
          + (f", {n_aligned} aligned" if n_aligned else ""))
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for line in problems[:20]:
            print(f"  - {line}")
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more")
        return 1
    print(f"OK -> {dataset_dir}")
    return 0


ALIGNER = "Qwen/Qwen3-ForcedAligner-0.6B"
ALIGNMENT_NAME = "alignment.jsonl"
# The aligner guesses every word's time in one pass, and its guesses drift near the
# end of long audio: 5-minute talks came back with their last 30-120 words stacked on
# one instant. Qwen's own pipeline never hands it more than 180 s (qwen_asr's
# MAX_FORCE_ALIGN_INPUT_SECONDS), so longer items are cut into pieces of that size.
ALIGN_PIECE_SEC = 180.0
# Memory follows total audio in a batch, not item count: eight 5-minute talks ran a
# 6 GB GPU out of memory, while one 299 s item peaks at 3.9 GiB.
ALIGN_BATCH_SEC = 300.0
ALIGN_BATCH_SIZE = 8
# Only used to find which part of a long transcript each piece holds.
ASR = "Qwen/Qwen3-ASR-0.6B"
ALIGNER_LANGUAGES = {
    "de": "German", "en": "English", "es": "Spanish", "fr": "French",
    "it": "Italian", "ja": "Japanese", "ko": "Korean", "pt": "Portuguese",
    "ru": "Russian", "yue": "Cantonese", "zh": "Chinese",
}
UNSPACED_LANGUAGES = {"ja", "yue", "zh"}


@dataclass(frozen=True)
class _Piece:
    """A stretch of one item's audio and the part of its transcript spoken there."""
    item: dict
    start: float
    duration: float
    text: str


def align(dataset_dir: Path) -> Path | None:
    """When each word of each reference transcript is spoken, into alignment.jsonl.

    One line per item: {"id", "transcript", "aligner", "words": [{"word",
    "start", "end"}]}, times in seconds from the start of the item's audio (after
    `offset`). Chinese and Japanese get one entry per character; the aligner
    splits Korean words into smaller pieces. Items over ALIGN_PIECE_SEC are
    aligned piece by piece (see _pieces). Items already aligned against the same
    transcript by the same method are skipped, so re-converting only aligns what
    changed and the models are not even loaded when nothing did.
    """
    with open(dataset_dir / "manifest.jsonl", encoding="utf-8") as f:
        items = [json.loads(line) for line in f if line.strip()]
    path = dataset_dir / ALIGNMENT_NAME
    done = _read_alignment(path)
    todo = [i for i in items if _needs_alignment(i, done)]
    print(f"  align: {len(items)} items, {len(todo)} to align")

    if todo:
        pieces = _pieces(dataset_dir, todo)
        pieces_left = Counter(p.item["id"] for p in pieces)
        words: dict[str, list[dict]] = {}
        aligner = _aligner()
        with open(path, "a", encoding="utf-8") as out:
            finished = 0
            for batch in _batches(pieces):
                results = aligner.align(
                    audio=[_piece_audio(dataset_dir, p) for p in batch],
                    text=[p.text for p in batch],
                    language=[ALIGNER_LANGUAGES[p.item["src_lang"]] for p in batch],
                )
                for piece, result in zip(batch, results):
                    item = piece.item
                    words.setdefault(item["id"], []).extend(
                        {"word": w.text, "start": round(piece.start + w.start_time, 3),
                         "end": round(piece.start + w.end_time, 3)} for w in result)
                    pieces_left[item["id"]] -= 1
                    if pieces_left[item["id"]] == 0:
                        out.write(json.dumps({
                            "id": item["id"],
                            "transcript": item["reference"]["transcript"],
                            "aligner": _method(item),
                            "words": words.pop(item["id"]),
                        }, ensure_ascii=False) + "\n")
                        finished += 1
                out.flush()
                print(f"  align: {finished}/{len(todo)}", flush=True)

    done = _read_alignment(path)
    kept = [done[i["id"]] for i in items if i["id"] in done
            and done[i["id"]]["transcript"] == i["reference"].get("transcript")]
    if not kept:
        path.unlink(missing_ok=True)
        return None
    partial = path.with_name(path.name + ".part")
    with open(partial, "w", encoding="utf-8") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    partial.replace(path)
    return path


def _method(item: dict) -> str:
    if item["duration"] > ALIGN_PIECE_SEC:
        return f"{ALIGNER} in {ALIGN_PIECE_SEC:.0f}s pieces"
    return ALIGNER


def _pieces(dataset_dir: Path, items: list[dict]) -> list[_Piece]:
    """Short items whole; long ones cut at their quietest moments.

    A long item's audio is cut into pieces of at most ALIGN_PIECE_SEC with
    qwen_asr's own cutter, and each piece is transcribed. Those transcriptions
    only locate the cuts in the reference transcript (_split_reference); the
    words that get aligned are always the reference's.
    """
    long_items = [i for i in items if i["duration"] > ALIGN_PIECE_SEC]
    cuts = _cut_and_transcribe(dataset_dir, long_items) if long_items else {}
    pieces = []
    for item in items:
        transcript = item["reference"]["transcript"]
        if item["id"] not in cuts:
            pieces.append(_Piece(item, 0.0, item["duration"], transcript))
            continue
        spans = cuts[item["id"]]
        texts = _split_reference(transcript, [heard for _, _, heard in spans],
                                 item["src_lang"])
        pieces += [_Piece(item, start, duration, text)
                   for (start, duration, _), text in zip(spans, texts) if text]
    return pieces


def _cut_and_transcribe(dataset_dir: Path, items: list[dict]
                        ) -> dict[str, list[tuple[float, float, str]]]:
    """Per item, its pieces as (start, duration, what the ASR heard there)."""
    import torch
    from qwen_asr import Qwen3ASRModel
    from qwen_asr.inference.utils import split_audio_into_chunks

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    # The default of 512 output tokens ends a fast speaker's 180 s piece early,
    # which pushes the missing words into the next piece.
    asr = Qwen3ASRModel.from_pretrained(ASR, device_map=device, dtype=torch.bfloat16,
                                        max_new_tokens=4096)
    cuts = {}
    for n, item in enumerate(items, start=1):
        audio, sr = _item_audio(dataset_dir, item)
        language = ALIGNER_LANGUAGES[item["src_lang"]]
        cuts[item["id"]] = [
            (start, len(chunk) / sr, asr.transcribe(audio=(chunk, sr), language=language)[0].text)
            for chunk, start in split_audio_into_chunks(audio, sr, ALIGN_PIECE_SEC)]
        print(f"  align: cut {n}/{len(items)} long items", flush=True)
    del asr
    torch.cuda.empty_cache()
    return cuts


def _split_reference(transcript: str, heard: list[str], lang: str) -> list[str]:
    """The reference transcript cut into one part per piece.

    Matches the reference against the pieces' transcriptions word by word
    (character by character for unspaced scripts). A piece's part ends at the
    last reference word matched inside it; words between two pieces' matches go
    to the later piece.
    """
    reference = _units(transcript, lang)
    recognized, piece_of = [], []
    for index, text in enumerate(heard):
        units = _units(text, lang)
        recognized += units
        piece_of += [index] * len(units)

    ends = [0] * len(heard)
    matcher = SequenceMatcher(None, [_match_key(u) for u in reference],
                              [_match_key(u) for u in recognized], autojunk=False)
    for a, b, size in matcher.get_matching_blocks():
        for k in range(size):
            piece = piece_of[b + k]
            ends[piece] = max(ends[piece], a + k + 1)
    ends = list(accumulate(ends, max))
    ends[-1] = len(reference)

    joiner = "" if lang in UNSPACED_LANGUAGES else " "
    return [joiner.join(reference[start:end]) for start, end in zip([0, *ends[:-1]], ends)]


def _units(text: str, lang: str) -> list[str]:
    if lang in UNSPACED_LANGUAGES:
        return [c for c in text if not c.isspace()]
    return text.split()


def _match_key(unit: str) -> str:
    return "".join(c for c in unit.lower() if c.isalnum()) or unit


def _batches(pieces: list[_Piece]):
    """Up to ALIGN_BATCH_SIZE pieces and ALIGN_BATCH_SEC of audio per batch."""
    batch: list[_Piece] = []
    seconds = 0.0
    for piece in pieces:
        if batch and (len(batch) == ALIGN_BATCH_SIZE
                      or seconds + piece.duration > ALIGN_BATCH_SEC):
            yield batch
            batch, seconds = [], 0.0
        batch.append(piece)
        seconds += piece.duration
    if batch:
        yield batch


def _read_alignment(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return {row["id"]: row for row in (json.loads(line) for line in f if line.strip())}


def _needs_alignment(item: dict, done: dict[str, dict]) -> bool:
    transcript = item["reference"].get("transcript") or ""
    if not transcript.strip():
        return False
    row = done.get(item["id"], {})
    if row.get("transcript") == transcript and row.get("aligner") == _method(item):
        return False
    if item["src_lang"] not in ALIGNER_LANGUAGES:
        print(f"  align: skip {item['id']}, the aligner has no {item['src_lang']!r}")
        return False
    return True


def _piece_audio(dataset_dir: Path, piece: _Piece) -> tuple[np.ndarray, int]:
    audio, sr = _item_audio(dataset_dir, piece.item)
    start = int(round(piece.start * sr))
    return audio[start:start + int(round(piece.duration * sr))], sr


def _item_audio(dataset_dir: Path, item: dict) -> tuple[np.ndarray, int]:
    path = str(dataset_dir / item["audio"])
    if item.get("offset") is None:
        audio, _ = sf.read(path, dtype="float32")
    else:
        audio, _ = sf.read(path, start=int(round(item["offset"] * SAMPLE_RATE)),
                           frames=int(round(item["duration"] * SAMPLE_RATE)),
                           dtype="float32")
    return audio, SAMPLE_RATE


@functools.cache
def _aligner():
    import torch
    from qwen_asr import Qwen3ForcedAligner

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    return Qwen3ForcedAligner.from_pretrained(ALIGNER, device_map=device,
                                              dtype=torch.bfloat16)


def here(script_file: str) -> Path:
    """The dataset directory a converter writes into: its own directory."""
    return Path(script_file).resolve().parent


def require_dir(path: Path, hint: str) -> Path:
    if not path.is_dir():
        print(f"missing directory: {path}\n{hint}", file=sys.stderr)
        raise SystemExit(2)
    return path
