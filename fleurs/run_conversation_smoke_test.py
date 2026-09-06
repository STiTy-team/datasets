#!/usr/bin/env python3
"""Drive a generated FLEURS conversation manifest through a live STiTy
streaming WebSocket server, turn by turn, and report what came back —
timing AND accuracy, so slow/hanging/dropped/wrong output is all visible,
not just "it produced some text".

This is a smoke test, not a benchmark: it exists to catch real problems
during development, not to produce publishable numbers (see STiTy's own
evaluation/ast/ for that — corpus-level BLEU, proper LAAL, etc.). Scores here
are per-utterance and small-sample; don't read a handful of turns as "the"
accuracy of the model.

Handles both manifest shapes build_conversation_manifest.py can produce:
  - spliced (default): one turn is ONE physical clip switching language
    mid-stream (a `segments` list says which language is speaking when, and
    whether that segment was cut short). `lang` is sent as "auto" — the
    server has to detect the switch itself, not be told about it in advance.
    The single WebSocket `targetLang` for the whole clip comes from
    --target-lang (a real session only has one target; there's no way to ask
    for "translate the ar part to ko and the en part to ar" over one stream).
  - --no-splice (legacy): one turn is one pure single-language sentence.
    `lang`/`targetLang` come straight from the turn's own src_lang/tgt_lang.

Protocol (matches Qwen3-ASR/examples/streaming_websocket_server.py):
    connect -> server "hello"
    client "start" {lang, targetLang} -> server "ready"
    client sends raw PCM s16le 16kHz mono binary frames
    server sends "final" {original, translation, language, commitReason} as
        segments commit
    client "finish" flushes whatever's left, then the same connection can
        take a new "start" for the next turn

TIMING captured per turn (all wall-clock, from the first audio chunk sent):
  - time_to_first_final_sec / time_to_last_final_sec
  - each final's elapsed_sec (since stream start) and since_finish_sec
    (since the client said "finish" — negative means a real incremental
    commit arrived mid-stream, not something produced only after the fact)
  - realtime_factor = total wall time for the turn / audio duration.
    >1 means the pipeline is falling behind a live conversation.
  - commit_lag_first_sec / commit_lag_last_sec per segment: commit arrival
    time MINUS that segment's own audio end time (not the whole turn's).
    This is the actual test of whether a `seg`-triggered commit (the model's
    own <SEG> token, meant to fire as soon as a complete thought is
    recognized) arrives sooner than a `dot`-triggered one (waiting for
    literal sentence-ending punctuation) — build_conversation_manifest.py's
    --gap-min-sec/--gap-max-sec inserts a real silence gap between segments
    specifically so there's a "quiet moment" for an early commit to be
    distinguishable from one that's just waiting on more audio to arrive.
    **With zero gap between segments (the old default), this can't be
    measured at all** — every commit ends up arriving at essentially the
    same time regardless of commitReason, because there's never a pause for
    an early flush to happen before more audio keeps the connection busy.
    Aggregated by commit reason in --summary-file's `commit_lag_by_reason`.

ACCURACY is scored per SEGMENT, not per final. A manifest segment can yield
multiple `final` commits (e.g. two `seg` commits for one longer sentence);
those get concatenated into one hypothesis and scored ONCE, so a segment
that happens to get split into 3 pieces doesn't count 3x toward the
aggregate the way naive per-final averaging would. Each `final` is matched
to the manifest segment whose language it claims (greedy, order-preserving —
see match_finals_to_segments), then scored against that segment's own FLEURS
text:
  - wer / cer: word/char error rate of the concatenated ASR transcript vs.
    that segment's full sentence (jiwer)
  - bleu / chrf: translation quality vs. the turn's target-language segment,
    if the target language is one of the turn's spoken languages (sacrebleu)
  - dropped segments (got NO final at all) are the single most important
    reliability signal this script produces, and they're tracked
    per-language — in testing, the middle language of a 3-way ar->ko->en
    splice was dropped far more often than the other two with one model,
    and that's invisible if you only look at a pooled drop rate.

**Coverage bias, and why there are two versions of every accuracy number**:
excluding dropped segments from WER/BLEU (the "matched-only" view) rewards a
model for giving up on hard cases — it just shrinks its own denominator to
the easier ones it attempted. The "penalized" view scores every dropped
segment as a complete miss (wer/cer=1.0, bleu/chrf=0) instead of excluding
it, which is the fairer number for comparing two models/configs where drop
rates differ. Trust "penalized" over "matched-only" for that comparison.

**Cut-segment caveat**: a cut/interrupted segment's reference is still the
FULL sentence (there's no word-level alignment to know exactly which words
the truncated audio covers), so its wer/cer/bleu/chrf will look far worse
than an uncut segment's EVEN WHEN the ASR/translation is working perfectly —
that's expected incompleteness, not a model error. cut vs. uncut are always
broken out separately, never averaged together. WER/CER also assume
whitespace-delimited words (fine for ar/ko/en; if you extend this to ja/zh,
lean on CER, not WER — same caveat STiTy's own evaluation/ast/README.md
notes for BLEU tokenization).

A turn that raises a connection/timeout error is logged and skipped rather
than aborting the whole run, so one bad turn doesn't hide the rest.

Pass --log-file to write one JSON record per turn (all of the above, the
expected reference text/segments, and the raw `final` messages) for later
analysis — this is what makes accuracy reconstructable after the fact
instead of only visible in the terminal while the run happens.

Pass --summary-file to ALSO write one flat JSON object summarizing the whole
run at a glance: timing, per-language accuracy/drop-rate, cut-vs-uncut
accuracy, penalized (coverage-adjusted) accuracy, and the worst-scoring
segments to go inspect. Run this script once per model server (same
manifest, same --n-turns) with a different --summary-file each time to build
up one such report per experiment.

Pass --server-log-file to also try to surface what the ASR model actually
produced internally — including for DROPPED segments, where the WebSocket
protocol gives you nothing at all, since no `final` was ever sent. The
protocol only ever sends the cleaned, committed text; the server's own log
is the only place the raw in-progress transcription (SEG token included)
exists. Best effort — see that flag's --help for the caveats.

Usage:
    python run_conversation_smoke_test.py \
        --manifest conversations/ar_ko_en_test.jsonl --n-turns 8 \
        --host localhost --port 8765 \
        --log-file run.jsonl --summary-file run.summary.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

import jiwer
import numpy as np
import sacrebleu
import soundfile as sf
import websockets

SAMPLING_RATE = 16000


def load_pcm_i16(wav_path: str, offset: float, duration: float) -> np.ndarray:
    """Read only [offset, offset+duration) — a --no-splice turn marked
    `interrupted` has a `duration` shorter than the sentence's full length,
    and that's exactly what should get streamed to sound like a real cutoff.
    A spliced turn's `wav` is already exactly `duration` long."""
    info = sf.info(wav_path)
    start = int(round(offset * info.samplerate))
    frames = int(round(duration * info.samplerate))
    audio, sr = sf.read(wav_path, start=start, frames=frames, dtype="float32",
                        always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    assert sr == SAMPLING_RATE, f"expected {SAMPLING_RATE}Hz, got {sr}Hz: {wav_path}"
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)


async def recv_type(ws, expected, timeout=25.0):
    deadline = time.perf_counter() + timeout
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"timed out waiting for {expected!r}")
        msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
        if not isinstance(msg, str):
            continue
        data = json.loads(msg)
        if data.get("type") == expected:
            return data


async def run_turn(ws, turn: dict, *, lang: str, target_lang: str, chunk_ms: int,
                    drain_grace_sec: float) -> dict:
    """Stream one turn's audio and collect `final`s + timing.

    Returns a dict: {finals, audio_sec, finish_sent_elapsed_sec, error}.
    Never raises for protocol-level issues (timeouts/empty results) — those
    show up as empty `finals`/non-None `error` instead, so the caller can
    keep going to the next turn.
    """
    result: dict = {"finals": [], "audio_sec": 0.0, "finish_sent_elapsed_sec": None, "error": None}
    try:
        await ws.send(json.dumps({"type": "start", "lang": lang, "targetLang": target_lang}))
        await recv_type(ws, "ready")

        pcm = load_pcm_i16(turn["wav"], turn.get("offset", 0.0), turn["duration"])
        result["audio_sec"] = len(pcm) / SAMPLING_RATE
        chunk_size = int(chunk_ms / 1000.0 * SAMPLING_RATE)
        stream_origin = time.perf_counter()
        for i in range(0, len(pcm), chunk_size):
            chunk = pcm[i:i + chunk_size]
            target_at = stream_origin + (i + len(chunk)) / SAMPLING_RATE
            await asyncio.sleep(max(0.0, target_at - time.perf_counter()))
            await ws.send(chunk.tobytes())

        finish_sent_at = time.perf_counter()
        result["finish_sent_elapsed_sec"] = round(finish_sent_at - stream_origin, 3)
        await ws.send(json.dumps({"type": "finish"}))

        idle_deadline = time.perf_counter() + drain_grace_sec
        while time.perf_counter() < idle_deadline:
            remaining = idle_deadline - time.perf_counter()
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if not isinstance(msg, str):
                continue
            data = json.loads(msg)
            if data.get("type") == "final":
                recv_at = time.perf_counter()
                data["_elapsed_sec"] = round(recv_at - stream_origin, 3)
                data["_since_finish_sec"] = round(recv_at - finish_sent_at, 3)
                result["finals"].append(data)
                idle_deadline = time.perf_counter() + drain_grace_sec  # more may follow
    except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError, OSError) as e:
        result["error"] = f"{type(e).__name__}: {e}"
    return result


# ── expected content + matching ─────────────────────────────────────────────

def get_segments(turn: dict) -> list[dict]:
    """Normalize both manifest shapes to a list of {lang, text, cut, end_sec}.
    `end_sec` is when that segment's own audio finishes within the turn — the
    reference point for commit_lag (see score_turn_segments): how long after
    the audio itself ended did the commit actually arrive."""
    segs = turn.get("segments")
    if segs:
        return [{"lang": s["lang"], "text": s["text"], "cut": s["cut"],
                  "end_sec": s["end_sec"]} for s in segs]
    return [{"lang": turn["src_lang"], "text": turn["src_text"],
              "cut": turn.get("interrupted", False), "end_sec": turn["duration"]}]


def get_target_ref_text(turn: dict, segments: list[dict], target_lang: str) -> str | None:
    """The reference translation for scoring `translation` fields — only
    computable if the requested target language is actually one of the
    turn's own spoken languages (we only have FLEURS text per spoken
    language, not a translation into an arbitrary unrelated target)."""
    for seg in segments:
        if seg["lang"] == target_lang:
            return seg["text"]
    if turn.get("tgt_lang") == target_lang:
        return turn.get("tgt_text")
    return None


def match_finals_to_segments(segments: list[dict], finals: list[dict]) -> list[int | None]:
    """Order-preserving match. A final reporting the same language as the
    currently-open segment continues claiming that SAME segment — one spoken
    segment commonly yields multiple `final` commits (e.g. two `seg` commits
    for one longer sentence), and that's not a new/duplicate segment. When
    the language changes, claims the next not-yet-claimed segment with that
    language. Returns one segment index (or None — an unmatched/
    hallucinated-language final) per final, same order as `finals`."""
    claimed = [False] * len(segments)
    matches: list[int | None] = []
    current: int | None = None
    for f in finals:
        lang = f.get("language")
        if current is not None and segments[current]["lang"] == lang:
            matches.append(current)
            continue
        match = None
        for i, seg in enumerate(segments):
            if not claimed[i] and seg["lang"] == lang:
                match = i
                claimed[i] = True
                break
        current = match
        matches.append(match)
    return matches


def safe_wer_cer(reference: str, hypothesis: str) -> tuple[float | None, float | None]:
    if not reference.strip() or not hypothesis.strip():
        return None, None
    return jiwer.wer(reference, hypothesis), jiwer.cer(reference, hypothesis)


def safe_bleu_chrf(reference: str | None, hypothesis: str) -> tuple[float | None, float | None]:
    if not reference or not reference.strip() or not hypothesis.strip():
        return None, None
    bleu = sacrebleu.sentence_bleu(hypothesis, [reference]).score
    chrf = sacrebleu.sentence_chrf(hypothesis, [reference]).score
    return bleu, chrf


def score_turn_segments(segments: list[dict], finals: list[dict], target_ref_text: str | None,
                         turn_index: int, pair_index: int) -> tuple[list[dict], list[dict]]:
    """One record per manifest segment (dropped or not — never per final).
    Returns (segment_records, unmatched_finals)."""
    matches = match_finals_to_segments(segments, finals)
    by_seg: dict[int, list[dict]] = defaultdict(list)
    unmatched_finals = []
    for f, seg_idx in zip(finals, matches):
        if seg_idx is None:
            unmatched_finals.append(f)
        else:
            by_seg[seg_idx].append(f)

    records = []
    for i, seg in enumerate(segments):
        fins = by_seg.get(i, [])
        rec = {"turn_index": turn_index, "pair_index": pair_index,
               "lang": seg["lang"], "cut": seg["cut"], "expected_text": seg["text"],
               "dropped": not fins, "n_finals": len(fins)}
        if fins:
            original = " ".join(f.get("original", "").strip() for f in fins).strip()
            translation = " ".join(f.get("translation", "").strip() for f in fins).strip()
            wer, cer = safe_wer_cer(seg["text"], original)
            bleu, chrf = safe_bleu_chrf(target_ref_text, translation)
            # commit_lag: elapsed time (since stream start) MINUS this segment's
            # own audio end time. First = time to first partial result for this
            # segment (perceived responsiveness); last = time until it's fully
            # committed. Needs --gap-min-sec/--gap-max-sec > 0 in the manifest to
            # be meaningful — with zero gap between segments, a commit for an
            # earlier segment can't be distinguished from one that's just
            # waiting on later audio to finish streaming.
            commit_lag_first = round(fins[0]["_elapsed_sec"] - seg["end_sec"], 3)
            commit_lag_last = round(fins[-1]["_elapsed_sec"] - seg["end_sec"], 3)
            commit_reasons = sorted({f.get("commitReason") for f in fins if f.get("commitReason")})
            rec.update(original=original, translation=translation, wer=wer, cer=cer, bleu=bleu, chrf=chrf,
                       commit_lag_first_sec=commit_lag_first, commit_lag_last_sec=commit_lag_last,
                       commit_reasons=commit_reasons)
        else:
            rec.update(original="", translation="", wer=None, cer=None, bleu=None, chrf=None,
                       commit_lag_first_sec=None, commit_lag_last_sec=None, commit_reasons=[])
        records.append(rec)
    return records, unmatched_finals


def _fmt(x: float | None, pct: bool = False) -> str:
    if x is None:
        return "n/a"
    return f"{x:.0%}" if pct else f"{x:.1f}"


def _pctl(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    idx = min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))
    return s[idx]


def _stats(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"mean": round(statistics.mean(values), 4), "p50": round(statistics.median(values), 4),
            "p90": round(_pctl(values, 90), 4), "max": round(max(values), 4), "n": len(values)}


def _print_score_group(label: str, values: list[float], pct: bool = False) -> None:
    if not values:
        return
    scale = 100 if pct else 1
    print(f"  {label}: mean={statistics.mean(values) * scale:.1f}{'%' if pct else ''} "
          f"p50={statistics.median(values) * scale:.1f}{'%' if pct else ''} "
          f"n={len(values)}")


def open_server_log_tail(path: str | None):
    """Best-effort only — see --server-log-file help. Seeks to the current
    end of the file so only lines written FROM HERE ON are ever read; each
    call to read_new_server_log_lines() then picks up whatever's new since
    the last call, which lines up with "what happened during this turn" as
    long as no other client is talking to the same server at the same time."""
    if not path:
        return None
    f = open(path, "r", encoding="utf-8", errors="replace")
    f.seek(0, 2)
    return f


def read_new_server_log_lines(log_tail) -> list[str]:
    if log_tail is None:
        return []
    return [line.rstrip("\n") for line in log_tail.readlines()]


def print_expected(turn: dict) -> None:
    segments = turn.get("segments")
    if segments:
        for seg in segments:
            cut_note = f"  [CUT at {seg['end_sec'] - seg['start_sec']:.1f}s / {seg['full_duration']:.1f}s]" \
                if seg["cut"] else ""
            print(f"  [{seg['start_sec']:5.1f}-{seg['end_sec']:5.1f}s] ({seg['lang']}){cut_note} {seg['text']}")
    else:
        cut_note = ""
        if turn.get("interrupted"):
            cut_note = (f"  [CUT at {turn['duration']:.1f}s / "
                        f"{turn.get('full_duration', turn['duration']):.1f}s]")
        print(f"  expected src ({turn['src_lang']}){cut_note}: {turn['src_text']}")
        print(f"  expected ref ({turn['tgt_lang']}): {turn['tgt_text']}")


# ── run-level aggregation ────────────────────────────────────────────────────

def build_summary(args: argparse.Namespace, model_path: str | None, n_turns: int, ok: int,
                   empty: int, errors: int, first_final_secs: list[float], last_final_secs: list[float],
                   realtime_factors: list[float], commit_reasons: Counter,
                   segment_records: list[dict], total_finals: int, unmatched_finals_total: int,
                   worst_n: int = 10) -> dict:
    """One flat, schema-stable JSON object per run — the whole point is that
    two of these (e.g. from two different --model server runs) can be
    tabulated/diffed directly, which raw per-turn logs can't be without
    re-deriving these same aggregates by hand each time.

    Scored per SEGMENT (see score_turn_segments), not per final, so a
    segment split into several `final` commits doesn't over-weight the mean.
    """
    matched = [r for r in segment_records if not r["dropped"]]
    dropped = [r for r in segment_records if r["dropped"]]

    def metric_stats(records: list[dict], key: str) -> dict | None:
        return _stats([r[key] for r in records if r.get(key) is not None])

    by_lang = {}
    for lang in sorted({r["lang"] for r in segment_records}):
        lang_all = [r for r in segment_records if r["lang"] == lang]
        lang_matched = [r for r in lang_all if not r["dropped"]]
        lang_dropped = [r for r in lang_all if r["dropped"]]
        by_lang[lang] = {
            "segments_total": len(lang_all), "segments_dropped": len(lang_dropped),
            "segments_dropped_rate": round(len(lang_dropped) / len(lang_all), 4) if lang_all else None,
            "wer": metric_stats(lang_matched, "wer"), "cer": metric_stats(lang_matched, "cer"),
            "bleu": metric_stats(lang_matched, "bleu"), "chrf": metric_stats(lang_matched, "chrf"),
        }

    by_cut = {}
    for cut_flag, label in ((True, "cut"), (False, "uncut")):
        recs = [r for r in matched if r["cut"] == cut_flag]
        by_cut[label] = {"n": len(recs), "wer": metric_stats(recs, "wer"), "cer": metric_stats(recs, "cer"),
                          "bleu": metric_stats(recs, "bleu"), "chrf": metric_stats(recs, "chrf")}

    # Penalized = coverage-adjusted: a dropped segment counts as a complete
    # miss (wer/cer=1.0, bleu/chrf=0) instead of being excluded. This is the
    # fair number for comparing two runs with different drop rates — see
    # module docstring "Coverage bias" section.
    penalized = {
        "wer": _stats([r["wer"] for r in matched if r["wer"] is not None] + [1.0] * len(dropped)),
        "cer": _stats([r["cer"] for r in matched if r["cer"] is not None] + [1.0] * len(dropped)),
        "bleu": _stats([r["bleu"] for r in matched if r["bleu"] is not None] + [0.0] * len(dropped)),
        "chrf": _stats([r["chrf"] for r in matched if r["chrf"] is not None] + [0.0] * len(dropped)),
    }

    # commit_lag: does a `seg`-triggered commit actually arrive sooner after its
    # own segment's audio ends than a `dot`-triggered one? Only meaningful if
    # the manifest has real gaps between segments (--gap-min-sec > 0) — with
    # zero gap, an earlier segment's commit can't be distinguished from one
    # that's simply waiting on later audio to finish streaming.
    lag_by_reason: dict[str, list[float]] = defaultdict(list)
    lag_by_lang: dict[str, list[float]] = defaultdict(list)
    for r in matched:
        if r.get("commit_lag_last_sec") is None:
            continue
        lag_by_lang[r["lang"]].append(r["commit_lag_last_sec"])
        for reason in r.get("commit_reasons") or ["?"]:
            lag_by_reason[reason].append(r["commit_lag_last_sec"])
    commit_lag_by_reason = {reason: _stats(v) for reason, v in sorted(lag_by_reason.items())}
    commit_lag_by_language = {lang: _stats(v) for lang, v in sorted(lag_by_lang.items())}

    worst = sorted((r for r in matched if r["wer"] is not None), key=lambda r: -r["wer"])[:worst_n]
    worst_view = [{"turn_index": r["turn_index"], "lang": r["lang"], "cut": r["cut"], "wer": r["wer"],
                   "expected_text": r["expected_text"], "original": r["original"]} for r in worst]
    dropped_view = [{"turn_index": r["turn_index"], "lang": r["lang"], "cut": r["cut"],
                      "expected_text": r["expected_text"]} for r in dropped]

    return {
        "run": {
            "wall_time": datetime.now(timezone.utc).isoformat(), "model_path": model_path,
            "host": args.host, "port": args.port, "manifest": args.manifest,
            "n_turns_requested": args.n_turns, "n_turns_run": n_turns,
            "src_lang": args.src_lang, "target_lang": args.target_lang,
            "chunk_ms": args.chunk_ms, "drain_grace_sec": args.drain_grace_sec,
        },
        "outcome": {"ok": ok, "empty": empty, "errors": errors, "total": n_turns},
        "timing": {
            "time_to_first_final_sec": _stats(first_final_secs),
            "time_to_last_final_sec": _stats(last_final_secs),
            "realtime_factor": _stats(realtime_factors),
        },
        "reliability": {
            "language_detection_accuracy": round((total_finals - unmatched_finals_total) / total_finals, 4)
                if total_finals else None,
            "segments_total": len(segment_records), "segments_dropped": len(dropped),
            "segments_dropped_rate": round(len(dropped) / len(segment_records), 4) if segment_records else None,
            "unmatched_finals": unmatched_finals_total,
            "commit_reasons": dict(commit_reasons),
        },
        "accuracy_by_language": by_lang,
        "accuracy_by_cut": by_cut,
        "accuracy_penalized_for_drops": penalized,
        "commit_lag_by_reason": commit_lag_by_reason,
        "commit_lag_by_language": commit_lag_by_language,
        "worst_segments": worst_view,
        "dropped_segments": dropped_view,
    }


async def main_async(args: argparse.Namespace) -> int:
    with open(args.manifest, encoding="utf-8") as f:
        turns = [json.loads(line) for line in f]
    if args.n_turns:
        turns = turns[:args.n_turns]

    log_f = open(args.log_file, "w", encoding="utf-8") if args.log_file else None
    server_log_tail = open_server_log_tail(args.server_log_file)
    uri = f"ws://{args.host}:{args.port}"
    print(f"connecting to {uri} ...")
    ok, empty, errors = 0, 0, 0
    first_final_secs, last_final_secs, realtime_factors = [], [], []
    commit_reasons: Counter[str] = Counter()
    all_segment_records: list[dict] = []
    total_finals = unmatched_finals_total = 0
    model_path = None

    try:
        # ping_interval=None: this script's turns can run 40s+ of audio through a
        # single busy asyncio server loop, well past the `websockets` library's
        # default 20s ping/pong keepalive timeout — that killed every long-running
        # experiment with "keepalive ping timeout" past turn ~14 before this was
        # disabled. STiTy's own eval client hits the same issue (test_ast.py sets
        # --ws-ping-timeout, default 60s); we go further and turn it off entirely
        # since a single manifest can have turns over a minute long.
        async with websockets.connect(uri, max_size=None, ping_interval=None) as ws:
            hello = await recv_type(ws, "hello")
            model_path = hello.get("modelPath")
            print(f"server: {hello.get('message')}  model={model_path}\n")

            for turn in turns:
                is_mixed = bool(turn.get("segments"))
                lang = args.src_lang if is_mixed else turn["src_lang"]
                target_lang = args.target_lang if is_mixed else turn["tgt_lang"]
                segments = get_segments(turn)
                target_ref_text = get_target_ref_text(turn, segments, target_lang)

                print(f"--- turn {turn['turn_index']} (pair {turn['pair_index']}, "
                      f"role {turn['speaker_role']}, lang={lang!r} target={target_lang!r}) ---")
                print_expected(turn)

                wall_start = datetime.now(timezone.utc).isoformat()
                t0 = time.perf_counter()
                result = await run_turn(ws, turn, lang=lang, target_lang=target_lang,
                                         chunk_ms=args.chunk_ms, drain_grace_sec=args.drain_grace_sec)
                turn_wall_sec = round(time.perf_counter() - t0, 3)
                finals = result["finals"]
                server_log_lines = read_new_server_log_lines(server_log_tail)
                if server_log_lines:
                    seg_lines = [l for l in server_log_lines if "<SEG>" in l]
                    print(f"  server log: {len(server_log_lines)} new lines from {args.server_log_file} "
                          f"(best-effort — see --server-log-file help)"
                          + (f", {len(seg_lines)} with <SEG>:" if seg_lines else ""))
                    for line in seg_lines:
                        print(f"    {line}")

                seg_records: list[dict] = []
                if result["error"]:
                    print(f"  [!] error: {result['error']}")
                    errors += 1
                elif not finals:
                    print("  [!] no `final` messages received")
                    empty += 1
                else:
                    for f in finals:
                        commit_reasons[f.get("commitReason") or "?"] += 1
                        print(f"  final @ {f['_elapsed_sec']:.2f}s (since finish: {f['_since_finish_sec']:+.2f}s) "
                              f"lang={f.get('language')!r} commit={f.get('commitReason')}")
                        print(f"    original:    {f.get('original', '').strip()!r}")
                        print(f"    translation: {f.get('translation', '').strip()!r}")
                    total_finals += len(finals)

                    seg_records, unmatched = score_turn_segments(segments, finals, target_ref_text,
                                                                   turn["turn_index"], turn["pair_index"])
                    unmatched_finals_total += len(unmatched)
                    all_segment_records.extend(seg_records)

                    print("  segments:")
                    for rec in seg_records:
                        if rec["dropped"]:
                            print(f"    {rec['lang']}{'(cut)' if rec['cut'] else ''}: "
                                  f"[!] NO OUTPUT AT ALL")
                        else:
                            print(f"    {rec['lang']}{'(cut)' if rec['cut'] else ''} "
                                  f"({rec['n_finals']} commit{'s' if rec['n_finals'] != 1 else ''}, "
                                  f"{'/'.join(rec['commit_reasons'])}): "
                                  f"wer={_fmt(rec['wer'], pct=True)} cer={_fmt(rec['cer'], pct=True)} "
                                  f"bleu={_fmt(rec['bleu'])} chrf={_fmt(rec['chrf'])}  "
                                  f"commit_lag_first={rec['commit_lag_first_sec']:+.2f}s "
                                  f"commit_lag_last={rec['commit_lag_last_sec']:+.2f}s")
                    if unmatched:
                        print(f"  [!] {len(unmatched)} final(s) matched no expected segment "
                              f"(wrong/hallucinated language): "
                              f"{[u.get('language') for u in unmatched]}")

                    original = " ".join(f.get("original", "").strip() for f in finals).strip()
                    translation = " ".join(f.get("translation", "").strip() for f in finals).strip()
                    if original or translation:
                        ok += 1
                    else:
                        empty += 1

                audio_sec = result["audio_sec"]
                t_first = finals[0]["_elapsed_sec"] if finals else None
                t_last = finals[-1]["_elapsed_sec"] if finals else None
                realtime_factor = round(turn_wall_sec / audio_sec, 2) if audio_sec else None
                if t_first is not None:
                    first_final_secs.append(t_first)
                    last_final_secs.append(t_last)
                if realtime_factor is not None:
                    realtime_factors.append(realtime_factor)

                print(f"  timing: audio={audio_sec:.2f}s  finish_sent_at={result['finish_sent_elapsed_sec']}s  "
                      f"first_final={t_first}s  last_final={t_last}s  "
                      f"turn_wall={turn_wall_sec}s  realtime_factor={realtime_factor}")
                print()

                if log_f:
                    log_f.write(json.dumps({
                        "wall_start": wall_start,
                        "turn_index": turn["turn_index"], "pair_index": turn["pair_index"],
                        "speaker_role": turn["speaker_role"], "lang": lang, "target_lang": target_lang,
                        "expected_segments": segments, "target_ref_text": target_ref_text,
                        "audio_sec": round(audio_sec, 3), "turn_wall_sec": turn_wall_sec,
                        "finish_sent_elapsed_sec": result["finish_sent_elapsed_sec"],
                        "time_to_first_final_sec": t_first, "time_to_last_final_sec": t_last,
                        "realtime_factor": realtime_factor, "n_finals": len(finals),
                        "error": result["error"], "finals": finals, "segment_scores": seg_records,
                        "server_log_lines": server_log_lines,
                    }, ensure_ascii=False) + "\n")
                    log_f.flush()  # a crash mid-run shouldn't lose everything logged so far
    finally:
        if log_f:
            log_f.close()
        if server_log_tail:
            server_log_tail.close()

    n = len(turns)
    print(f"done: {ok}/{n} produced output, {empty}/{n} empty, {errors}/{n} errored")
    if first_final_secs:
        print(f"  time_to_first_final_sec: mean={statistics.mean(first_final_secs):.2f} "
              f"p50={statistics.median(first_final_secs):.2f} p90={_pctl(first_final_secs, 90):.2f} "
              f"max={max(first_final_secs):.2f}")
        print(f"  time_to_last_final_sec:  mean={statistics.mean(last_final_secs):.2f} "
              f"p50={statistics.median(last_final_secs):.2f} p90={_pctl(last_final_secs, 90):.2f} "
              f"max={max(last_final_secs):.2f}")
    if realtime_factors:
        print(f"  realtime_factor:         mean={statistics.mean(realtime_factors):.2f} "
              f"p90={_pctl(realtime_factors, 90):.2f} max={max(realtime_factors):.2f}  "
              f"(>1 = falling behind a live conversation)")
    if total_finals:
        acc = (total_finals - unmatched_finals_total) / total_finals
        print(f"  language detection accuracy: {acc:.0%} ({total_finals - unmatched_finals_total}/{total_finals} "
              f"finals matched an expected language)")
    if all_segment_records:
        n_dropped = sum(r["dropped"] for r in all_segment_records)
        print(f"  segments with NO output at all: {n_dropped}/{len(all_segment_records)} "
              f"({n_dropped / len(all_segment_records):.0%})")
        by_lang_drop = Counter()
        by_lang_total = Counter()
        for r in all_segment_records:
            by_lang_total[r["lang"]] += 1
            by_lang_drop[r["lang"]] += r["dropped"]
        print(f"    by language: " + ", ".join(
            f"{lang}={by_lang_drop[lang]}/{by_lang_total[lang]}" for lang in sorted(by_lang_total)))
    if commit_reasons:
        print(f"  commit reasons: {dict(commit_reasons)}")

    matched_records = [r for r in all_segment_records if not r["dropped"]]
    lag_by_reason: dict[str, list[float]] = defaultdict(list)
    for r in matched_records:
        if r.get("commit_lag_last_sec") is not None:
            for reason in r.get("commit_reasons") or ["?"]:
                lag_by_reason[reason].append(r["commit_lag_last_sec"])
    if lag_by_reason:
        print("  commit_lag (commit arrival minus that segment's own audio end — needs "
              "--gap-min-sec > 0 in the manifest to be meaningful):")
        for reason, values in sorted(lag_by_reason.items()):
            print(f"    {reason}: mean={statistics.mean(values):+.2f}s p50={statistics.median(values):+.2f}s "
                  f"n={len(values)}")


    dropped_records = [r for r in all_segment_records if r["dropped"]]
    for label, key, pct in (("WER", "wer", True), ("CER", "cer", True), ("BLEU", "bleu", False),
                             ("chrF", "chrf", False)):
        for cut_flag, cut_label in ((False, "uncut"), (True, "CUT — expected worse, scored vs. FULL sentence")):
            values = [r[key] for r in matched_records if r["cut"] == cut_flag and r[key] is not None]
            _print_score_group(f"{label} ({cut_label} segments)", values, pct=pct)
    print("  penalized (dropped segments counted as a complete miss, not excluded):")
    for label, key, pct, miss_value in (("WER", "wer", True, 1.0), ("CER", "cer", True, 1.0),
                                          ("BLEU", "bleu", False, 0.0), ("chrF", "chrf", False, 0.0)):
        values = [r[key] for r in matched_records if r[key] is not None] + [miss_value] * len(dropped_records)
        _print_score_group(f"  {label}", values, pct=pct)

    if args.log_file:
        print(f"  full per-turn log: {args.log_file}")

    if args.summary_file:
        summary = build_summary(args, model_path, n, ok, empty, errors, first_final_secs,
                                 last_final_secs, realtime_factors, commit_reasons,
                                 all_segment_records, total_finals, unmatched_finals_total)
        with open(args.summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"  run summary: {args.summary_file}")

    return 0 if empty == 0 and errors == 0 else 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", default="conversations/ar_ko_en_test.jsonl")
    p.add_argument("--n-turns", type=int, default=8, help="0 = run every turn in the manifest")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--src-lang", default="auto",
                   help="`lang` sent for spliced (mixed) turns — 'auto' makes the server detect "
                        "the mid-stream language switch itself. Ignored for --no-splice manifests, "
                        "which carry their own single src_lang per turn.")
    p.add_argument("--target-lang", default="en",
                   help="`targetLang` sent for spliced (mixed) turns — a session only has one "
                        "target, so this picks it for the whole clip regardless of which language "
                        "is speaking. Ignored for --no-splice manifests.")
    p.add_argument("--chunk-ms", type=int, default=200, help="audio chunk size sent per frame")
    p.add_argument("--drain-grace-sec", type=float, default=5.0,
                   help="how long to keep listening for `final` messages after `finish`")
    p.add_argument("--log-file", default=None,
                   help="write one JSON record per turn here (timing + per-segment accuracy + raw "
                        "finals + any correlated server log lines) for later analysis")
    p.add_argument("--summary-file", default=None,
                   help="write one JSON object here summarizing the WHOLE run at a glance: timing, "
                        "per-language accuracy/drop-rate, cut-vs-uncut accuracy, penalized "
                        "(coverage-adjusted) accuracy, and the worst-scoring segments")
    p.add_argument("--server-log-file", default=None,
                   help="path to the STiTy server's own log file (e.g. logs/asr_server.log in its repo). "
                        "BEST EFFORT ONLY: tails whatever's newly appended during each turn — this is the "
                        "only way to see what the model produced internally for a DROPPED segment (no "
                        "`final` means the WebSocket protocol gives you nothing at all for it), and the "
                        "only way to see the raw <SEG> token, which the protocol always strips before "
                        "sending anything to a client. Correlation is by append-order, not connection id, "
                        "so it's only reliable if this is the only client talking to that server during "
                        "the run. Not portable — the log format/path is specific to whichever STiTy server "
                        "build you're running, not a stable API, and that server has to actually be "
                        "writing its output to a file in the first place (by default it just prints to "
                        "its own terminal).")
    sys.exit(asyncio.run(main_async(p.parse_args())))


if __name__ == "__main__":
    main()
