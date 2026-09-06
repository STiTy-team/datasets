# FLEURS datasets

Raw [google/fleurs](https://huggingface.co/datasets/google/fleurs) downloads plus
scripts that turn them into test datasets for STiTy.

FLEURS is **fully public on Hugging Face** (`gated: false`, `private: false`) —
downloading it does **not** require a Hugging Face account, token, or `hf auth login`.
If a download ever 401s, that's a different (private/gated) dataset, not this one.

## Layout

```
data/<lang>/test.tsv            # id, filename, raw_transcription, transcription, phonemes, num_samples, gender
data/<lang>/audio/test/*.wav    # 16kHz mono
conversations/*.jsonl           # generated — see "Conversation datasets" below
```

`test.tsv` has **no header row** and is **tab-separated with literal quote
characters in the text** — always parse it with `csv.QUOTE_NONE`, otherwise a
quote character gets read as the start of a quoted field and merges rows
together.

## Installing

```bash
pip install -r requirements.txt

./install.sh                     # downloads + extracts the default language set below
./install.sh ar_eg ko_kr en_us   # or only specific languages
```

Idempotent — safe to re-run, it skips whatever's already downloaded and
extracted. `install.sh` needs the `hf` CLI (part of `requirements.txt`); no
Hugging Face account, token, or `hf auth login` needed (see above).

Default language set: `en_us de_de ko_kr ja_jp cmn_hans_cn(zh) es_419 ar_eg`.
FLEURS covers 102 languages total — see the [dataset card](https://huggingface.co/datasets/google/fleurs)
for the full code list if you need one outside this set; `install.sh` takes
any FLEURS language code as an argument.

### Manually downloading one language

`install.sh` just wraps this per language — useful if you only need one, or
want text without audio (drop the `audio/test.tar.gz` include, much smaller):

```bash
hf download google/fleurs --repo-type dataset \
  --include "data/<lang>/test.tsv" "data/<lang>/audio/test.tar.gz" \
  --local-dir .

# extract the audio (hf download leaves it as a tarball)
tar xzf data/<lang>/audio/test.tar.gz -C data/<lang>/audio/
```

## Conversation datasets

FLEURS is **n-way parallel**: it's built from FLoRes sentences read aloud in
each language, so the same sentence `id` is a verified translation across every
language's `test.tsv`. `build_conversation_manifest.py` uses that to build
**spliced multi-language conversations**: for each shared sentence id, it
concatenates that sentence's recording in language 1, then language 2, ...
through the last language in `--langs`, into ONE physical audio clip that
switches language mid-stream — the way a real conversation handoff (or
interruption) sounds, not separate clips per language.

```bash
python build_conversation_manifest.py \
    --langs ar_eg ko_kr en_us \
    --genders FEMALE MALE FEMALE \
    --n-groups 100 --seed 20260905 \
    --out conversations/ar_ko_en_test.jsonl
```

Deterministic: the same TSVs + `--seed` + `--n-groups` always produce
byte-identical spliced audio and the same manifest.

**Gender defaults exist to make each language's speaker sound like a
consistent, distinct person, not just a different language.** They're not
arbitrary: FLEURS' `ar_eg` test split has **no male recordings at all**
(428/428 rows are FEMALE), so it's pinned to FEMALE — other languages default
to whatever gender gives the largest shared sentence pool. Override with
`--genders` if a different combination suits your language set better. Note
FLEURS only exposes gender, not a persistent per-speaker id, so "the same
voice for a language" really means "the same gender label," not literally one
individual reader.

By default, every segment has a chance (`--interrupt-frac`, default `1.0` —
always) of being cut short instead of played to completion before handing off
to the next language, keeping a random `--interrupt-keep-min`–
`--interrupt-keep-max` fraction of its audio (default 30%–85%). Set
`--interrupt-frac 0` for clean, uninterrupted handoffs instead.

Each line of the output JSONL is one turn. Field names/shape match STiTy's own
`evaluation/ast/build_manifest_fleurs.py` manifests (`utt_id`/`wav`/`offset`/
`duration`/`src_lang`/`tgt_lang`/`src_text`/`tgt_text`/`speaker_id`/`talk_id`)
so existing tooling can read the top level of this file too — `src_lang`/
`tgt_lang` describe which language the spliced audio opens/closes in (not a
translation instruction; a real client only has one WebSocket `targetLang`
per session, see below). `segments` is additive and carries the real
per-language breakdown a flat src/tgt pair can't represent:

```jsonc
{"utt_id": "mixed_1959_ar_ko_en",
 "wav": "/abs/path/to/conversations/ar_ko_en_test_audio/group0000_1959.wav",
 "offset": 0.0, "duration": 13.4,
 "src_lang": "ar", "tgt_lang": "en", "src_text": "...", "tgt_text": "...",
 "speaker_id": "FEMALE/MALE/FEMALE", "talk_id": "1959",
 "turn_index": 0, "pair_index": 0, "speaker_role": "MIXED",
 "segments": [
   {"lang": "ar", "text": "...", "start_sec": 0.0, "end_sec": 4.2, "full_duration": 8.8, "cut": true},
   {"lang": "ko", "text": "...", "start_sec": 4.2, "end_sec": 9.0, "full_duration": 13.3, "cut": true},
   {"lang": "en", "text": "...", "start_sec": 9.0, "end_sec": 13.4, "full_duration": 7.8, "cut": false}
 ]}
```

`--no-splice` restores the older shape instead — one pure single-language
turn per language per group (no audio concatenation), rotating through
`--langs` with each turn's `tgt_lang`/`tgt_text` pointing at the next
language in rotation.

Run `python build_conversation_manifest.py --help` for all options.

## Smoke-testing against a live STiTy server

`run_conversation_smoke_test.py` streams a generated conversation manifest
turn-by-turn into a running STiTy WebSocket server and reports, per turn:

- **timing** — time to first/last `final`, whether commits arrived
  incrementally mid-stream or only after `finish`, and a realtime factor
  (wall time ÷ audio length; >1 means it's falling behind a live conversation)
- **accuracy, scored per SEGMENT** — every `final` is matched to the manifest
  segment whose language it claims; a segment split into several `final`
  commits gets its pieces concatenated and scored ONCE (not once per commit,
  which would silently over-weight segments that happen to get chunked more)
  against that segment's own FLEURS text: WER/CER for the ASR transcript
  (`jiwer`), BLEU/chrF for the translation (`sacrebleu`)
- which segments got **no output at all**, broken down **by language** — the
  single most useful reliability signal here. In testing, one model dropped
  the middle language of a 3-way splice in 7/8 turns while never mislabeling
  anything it did produce; a pooled "38% dropped" number hides that it's
  almost entirely one language failing, not a general problem

This is a smoke test for catching real problems during development, not a
publishable benchmark — scores are per-utterance and small-sample (see
STiTy's own `evaluation/ast/` for corpus-level BLEU/proper LAAL). A cut
segment's reference is still the full sentence (there's no word-level
alignment to know exactly which words the truncated audio covers), so its
scores will look far worse than an uncut segment's even when the model is
working correctly — cut vs. uncut are always reported separately, never
averaged together.

**Coverage bias — read this before comparing two runs.** Excluding dropped
segments from WER/BLEU rewards a model for giving up on hard cases: it just
shrinks its own denominator to the easier ones it attempted. A model that
drops nothing and correctly produces partial output for a brutally-cut
segment will look *worse* on the plain, unadjusted numbers than one that
silently skips it entirely. The **penalized** accuracy (every dropped
segment scored as a complete miss — wer/cer=1.0, bleu/chrf=0 — instead of
excluded) is the fair number for that comparison; the plain per-language/
per-cut numbers are for understanding one run in isolation.

```bash
pip install -r requirements.txt
python run_conversation_smoke_test.py --n-turns 16 \
    --log-file run.jsonl --summary-file run.summary.json   # 0 turns = every turn in the manifest
```

Two different output files, two different jobs:

- **`--log-file`** — one JSON record per turn: full timing, the expected
  reference text/segments, per-segment scores, every raw `final`, and any
  correlated server log lines (see below). Detailed, but you have to dig
  through it.
- **`--summary-file`** — one JSON object for the WHOLE run: timing,
  accuracy/drop-rate broken down **by language** and by cut-vs-uncut, the
  penalized (coverage-adjusted) accuracy, and the actual **worst-scoring
  segments** (with their expected vs. actual text right there, so you don't
  have to go hunting in the full log for what to inspect). The at-a-glance
  report — run this once per model/config you're testing (same manifest,
  same `--n-turns`) and each summary file stands on its own for judging that
  run, or for comparing against another run's summary file yourself.

There's also `--server-log-file` (off by default) for correlating STiTy's
own server-side log with each turn — the WebSocket protocol only ever sends
the cleaned, final committed text, so for a **dropped** segment (no `final`
at all) or the raw `<SEG>`-tagged in-progress transcription, the server's
own log is the only place that information exists at all. Best-effort and
not portable: the log format/path is specific to whichever STiTy server
build is running, correlation is by append-order rather than connection id
(only reliable with one client talking to that server at a time), and the
server has to actually be writing its output to a file in the first place —
by default it just prints to its own terminal, so this needs something like
`tmux pipe-pane -o 'cat >> server.log'` pointed at wherever it's running
before it'll have anything to read. Run `--help` for the full caveats.

Requires a STiTy server already running and reachable (default
`ws://localhost:8765`) — this script is only a client, it doesn't start one.
