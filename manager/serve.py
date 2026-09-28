#!/usr/bin/env python3
"""A manager for the datasets in this repo, served in the browser.

Two tabs over the same datasets:

  살펴보기  what is in a dataset -- its spec, its shape (lengths, languages,
            sessions, reference coverage, which fields rows carry, alignment),
            every row as bench reads it, its audio and its word timings, and
            the contract's verify() on demand.
  녹음      new items recorded straight into it.

`manifest.jsonl` is the live thing here: it is read and rewritten in place.
A `convert.py` re-run regenerates it and discards edits made here, which is
fine for the converted datasets and moot for a hand-recorded one.

Recording captures float samples off the browser's audio graph at 16 kHz and
posts them as s16le, so what lands on disk is already the contract's format --
no MediaRecorder, no webm/opus, no ffmpeg, no lossy generation.

A browser will not open a microphone from a file:// page, so the page has to be
served over http://localhost regardless; once a process exists to serve it,
having that process write the files is less machinery than a web framework.

    python manager/serve.py                 # http://127.0.0.1:8765
    python manager/serve.py --port 9000
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import mimetypes
import os
import re
import statistics
import sys
import wave
import webbrowser
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import _contract as contract  # noqa: E402

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
CHANNELS = 1

# Under this and it was a misfire -- a double-tapped space bar, a click on the
# wrong button. Keeping them means hand-deleting them later.
MIN_DURATION_SEC = 0.25

# One take held in memory before it is written. 16 kHz mono s16le is about
# 1.9 MB a minute, so this is roughly nine hours: a ceiling against a runaway
# client, not against any real session.
MAX_TAKE_BYTES = 1 << 30

PAGE = 100
SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SAFE_DATASET = re.compile(r"^[A-Za-z0-9_-]{1,64}(/[A-Za-z0-9_.+-]{1,128})?$")
SAFE_LANG = re.compile(r"^[A-Za-z0-9_-]{1,16}$")
MARKERS = ("dataset.yml", "manifest.jsonl")
DURATION_BINS = (1, 2, 5, 10, 20, 30, 60, 180, 600)

# Every dataset directory in this repo carries a README. A new one made from the
# manager starts with a stub rather than nothing to explain itself.
README_STUB = """# {name}

데이터셋 매니저에서 만든 데이터셋. 받아오는 코퍼스가 아니라 직접 녹음해서 채운다.

```bash
make manager                           # 목록에서 {name} 을 고르고 녹음 탭으로 간다
```

`dataset.yml` 과 `manifest.jsonl` 은 매니저가 읽고 쓴다. 형식과 녹음하는 법은
[`manager/README.md`](../manager/README.md) 에 있다.
"""
STATIC = Path(__file__).resolve().parent / "static"
SKIP = {"manager", "data", "audio", "__pycache__"}


class HttpError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _plain_dirs(path: Path) -> list[Path]:
    return sorted(d for d in path.iterdir() if d.is_dir()
                  and not d.name.startswith(".") and d.name not in SKIP)


def _is_dataset(path: Path) -> bool:
    return any((path / m).is_file() for m in MARKERS)


def datasets(root: Path) -> dict[str, Path]:
    """Every dataset under the repo root, keyed by its bench name.

    A multilingual corpus keeps one dataset per source language in a
    subdirectory (`fleurs/en_us`), so one level down counts too. A top-level
    directory is listed itself when it holds a dataset or holds none below it:
    requiring a dataset.yml would hide a directory you just made to record
    into, which is the one case where you most want to see it listed.
    """
    out = {}
    for top in _plain_dirs(root):
        nested = [d for d in _plain_dirs(top) if _is_dataset(d)]
        if _is_dataset(top) or not nested:
            out[top.name] = top
        for sub in nested:
            out[f"{top.name}/{sub.name}"] = sub
    return out


def read_spec(dataset: Path) -> dict:
    path = dataset / "dataset.yml"
    if not path.is_file():
        return {}
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_spec_raw(dataset: Path, spec: dict) -> None:
    """Rewrite dataset.yml from a loaded spec, keeping the contract's key order."""
    import yaml
    (dataset / "dataset.yml").write_text(
        yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")


def parse_langs(raw: str) -> list[str]:
    """"ko, en de" -> ["ko", "en", "de"], order kept, duplicates dropped."""
    out = []
    for lang in re.split(r"[,\s]+", raw.strip()):
        if not lang:
            continue
        if not SAFE_LANG.match(lang):
            raise HttpError(400, f"언어 코드가 잘못됐다: {lang}")
        if lang not in out:
            out.append(lang)
    return out


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def read_manifest(dataset: Path) -> list[dict]:
    return read_jsonl(dataset / "manifest.jsonl")


def write_manifest(dataset: Path, rows: list[dict]) -> None:
    """Rewrite manifest.jsonl. Unlike the contract's writer, an empty dataset is
    allowed: deleting the last item is a legitimate thing to do from here."""
    (dataset / "manifest.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")


def audio_path(dataset: Path, item: dict) -> Path | None:
    """The item's audio file, or None if the row points outside the dataset.

    Checked lexically, not on the resolved path: `audio` is normally a symlink
    to the corpus somewhere else on disk, which is inside the dataset as far as
    the row is concerned.
    """
    rel = str(item.get("audio") or "")
    if not rel or Path(rel).is_absolute():
        return None
    path = Path(os.path.normpath(dataset / rel))
    if not path.is_relative_to(dataset):
        return None
    return path


def text_units(text: str, lang: str) -> int:
    if lang in contract.UNSPACED_LANGUAGES:
        return len(re.sub(r"\s", "", text))
    return len(text.split())


def spread(values: list[float]) -> dict | None:
    if not values:
        return None
    values = sorted(values)
    return {"min": values[0], "p50": statistics.median(values),
            "p90": values[int(0.9 * (len(values) - 1))], "max": values[-1],
            "mean": sum(values) / len(values)}


def histogram(durations: list[float]) -> list[dict]:
    edges = [0, *DURATION_BINS, float("inf")]
    counts = [0] * (len(edges) - 1)
    for d in durations:
        for i in range(len(counts)):
            if edges[i] <= d < edges[i + 1]:
                counts[i] += 1
                break
    return [{"lo": edges[i], "hi": None if edges[i + 1] == float("inf") else edges[i + 1],
             "count": c} for i, c in enumerate(counts)]


def fields(rows: list[dict]) -> list[dict]:
    """Which keys the rows carry, how often, and as what JSON type."""
    seen: dict[str, Counter] = {}

    def note(key: str, value) -> None:
        seen.setdefault(key, Counter())[type(value).__name__] += 1

    for row in rows:
        for key, value in row.items():
            note(key, value)
            if key == "reference" and isinstance(value, dict):
                for sub, inner in value.items():
                    note(f"reference.{sub}", inner)
                    if sub == "translations" and isinstance(inner, dict):
                        for lang, text in inner.items():
                            note(f"reference.translations.{lang}", text)
    return [{"key": k, "count": sum(c.values()), "types": dict(c)}
            for k, c in seen.items()]


def shape(dataset: Path) -> dict:
    rows = read_manifest(dataset)
    spec = read_spec(dataset)
    manifest = dataset / "manifest.jsonl"
    aligned = contract._read_alignment(dataset / contract.ALIGNMENT_NAME)

    durations = [float(r.get("duration") or 0) for r in rows]
    files = {audio_path(dataset, r) for r in rows}
    missing = sum(1 for f in files if not f or not f.is_file())

    units = [text_units(t, r.get("src_lang", "")) for r in rows
             if (t := (r.get("reference") or {}).get("transcript") or "").strip()]
    translation_langs = Counter(
        lang for r in rows
        for lang, text in ((r.get("reference") or {}).get("translations") or {}).items()
        if (text or "").strip())

    transcripts = {r.get("id"): (r.get("reference") or {}).get("transcript") or ""
                   for r in rows}
    orphan = sum(1 for i in aligned if i not in transcripts)
    stale = sum(1 for i, a in aligned.items()
                if i in transcripts and a.get("transcript") != transcripts[i])

    groups = [r.get("group", r.get("id")) for r in rows]
    return {
        "spec": spec,
        "files": {
            "manifest": manifest.is_file(),
            "manifest_bytes": manifest.stat().st_size if manifest.is_file() else 0,
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()
            if manifest.is_file() else None,
            "alignment": (dataset / contract.ALIGNMENT_NAME).is_file(),
            "readme": (dataset / "README.md").is_file(),
            "convert": (dataset / "convert.py").is_file(),
        },
        "items": len(rows),
        "duration": {"total": sum(durations), **(spread(durations) or {})},
        "histogram": histogram(durations),
        "sessions": len(dict.fromkeys(groups)),
        "sessions_contiguous": len(dict.fromkeys(groups)) == len(
            [g for i, g in enumerate(groups) if i == 0 or groups[i - 1] != g]),
        "speakers": len({r.get("speaker") for r in rows if r.get("speaker")}),
        "src_lang": dict(Counter(r.get("src_lang", "") for r in rows).most_common()),
        "audio_files": len(files),
        "audio_missing": missing,
        "offset_items": sum(1 for r in rows if r.get("offset") is not None),
        "partial_items": sum(1 for r in rows if r.get("partial")),
        "transcript": {"filled": len(units), "units": spread(units)},
        "translations": dict(translation_langs.most_common()),
        "fields": fields(rows),
        "alignment": {
            "items": len(aligned) - orphan,
            "stale": stale,
            "orphan": orphan,
            "aligners": dict(Counter(a.get("aligner", "") for a in aligned.values())),
        },
    }


def matches(row: dict, needle: str) -> bool:
    ref = row.get("reference") or {}
    haystack = [row.get("id", ""), row.get("speaker", ""), row.get("group", ""),
                ref.get("transcript") or "", *(ref.get("translations") or {}).values()]
    return any(needle in str(h).lower() for h in haystack)


class Manager(BaseHTTPRequestHandler):
    server_version = "dataset-manager"
    protocol_version = "HTTP/1.1"

    # ---- plumbing ----

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self.dispatch("GET")

    def do_POST(self):
        self.dispatch("POST")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def dispatch(self, method: str):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        self.query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            self.route(method, parts)
        except HttpError as err:
            self.send_json({"error": err.message}, err.code)
        except Exception as err:  # noqa: BLE001 -- a local tool, not a service
            self.send_json({"error": f"{type(err).__name__}: {err}"}, 500)

    def route(self, method: str, parts: list[str]):
        if method == "GET" and not parts:
            return self.send_file(STATIC / "index.html")
        if method == "GET" and parts[0] == "static" and len(parts) == 2:
            path = (STATIC / parts[1]).resolve()
            if path.parent != STATIC.resolve() or not path.is_file():
                raise HttpError(404, "not found")
            return self.send_file(path)

        if parts[:1] != ["api"] or len(parts) != 2:
            raise HttpError(404, "not found")
        action = parts[1]
        if method == "GET" and action == "datasets":
            return self.send_json(self.list_datasets())
        if method == "POST" and action == "datasets":
            return self.send_json(self.create_dataset(), 201)

        dataset = self.pick()
        endpoints = {
            ("GET", "shape"): lambda: self.send_json(
                {"name": self.query["ds"], "path": str(dataset), **shape(dataset)}),
            ("GET", "items"): lambda: self.send_json(self.items(dataset)),
            ("GET", "item"): lambda: self.send_json(self.item(dataset)),
            ("GET", "audio"): lambda: self.send_audio(dataset),
            ("GET", "verify"): lambda: self.send_json(self.verify(dataset)),
            ("DELETE", "audio"): lambda: self.send_json(self.drop_audio(dataset)),
            ("DELETE", "item"): lambda: self.send_json(self.drop_item(dataset)),
            ("POST", "record"): lambda: self.send_json(self.record(dataset)),
        }
        handler = endpoints.get((method, action))
        if not handler:
            raise HttpError(404, "not found")
        return handler()

    def send_json(self, payload: dict, code: int = 200):
        self.send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8", code)

    def send_file(self, path: Path):
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_bytes(path.read_bytes(), ctype)

    def send_bytes(self, data: bytes, ctype: str, code: int = 200):
        """Send a body, honouring a single Range so <audio> can seek."""
        size = len(data)
        start, end = 0, size - 1

        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
        if code == 200 and m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), end) if m.group(2) else end
            else:
                start = max(0, size - int(m.group(2)))
            if start > end or start >= size:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            code = HTTPStatus.PARTIAL_CONTENT

        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        self.wfile.write(data[start:end + 1])

    def body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_TAKE_BYTES:
            raise HttpError(413, "take 가 너무 크다")
        return self.rfile.read(length)

    # ---- dataset access ----

    def pick(self) -> Path:
        name = self.query.get("ds", "")
        if not SAFE_DATASET.match(name):
            raise HttpError(400, "데이터셋 이름이 잘못됐다")
        dataset = datasets(self.server.root).get(name)
        if not dataset:
            raise HttpError(404, f"그런 데이터셋이 없다: {name}")
        return dataset

    def find(self, dataset: Path) -> tuple[list[dict], int]:
        item_id = self.query.get("id", "")
        rows = read_manifest(dataset)
        for i, row in enumerate(rows):
            if row.get("id") == item_id:
                return rows, i
        raise HttpError(404, f"그런 항목이 없다: {item_id}")

    # ---- endpoints ----

    def list_datasets(self) -> dict:
        root = self.server.root
        out = []
        for name, dataset in datasets(root).items():
            rows = read_manifest(dataset)
            out.append({
                "name": name,
                "items": len(rows),
                "duration": round(sum(float(r.get("duration") or 0) for r in rows), 1),
                "converted": (dataset / "manifest.jsonl").is_file(),
            })
        return {"root": str(root), "datasets": out}

    def create_dataset(self) -> dict:
        """Make a new dataset directory at the repo root.

        The spec is written now rather than left to the first take, so the
        dataset has a declared src_lang from the moment it exists.
        """
        root = self.server.root
        name = (self.query.get("name") or "").strip()
        if not SAFE_NAME.match(name):
            raise HttpError(400, "이름은 영문·숫자·_·- 만, 64자 이내")
        if name in SKIP:
            raise HttpError(400, f"예약된 이름이다: {name}")
        dataset = root / name
        if dataset.exists():
            raise HttpError(409, f"이미 있다: {name}")

        languages = parse_langs(self.query.get("languages", "")) or ["en"]
        dataset.mkdir()
        contract.write_spec(
            dataset, name=name, split="record", languages=languages,
            primary_metric="wer", translations=[], transcript=False,
            group_rule="id", bench_defaults={})
        (dataset / "README.md").write_text(README_STUB.format(name=name),
                                           encoding="utf-8")
        return {"name": name, "path": str(dataset), "languages": languages}

    def items(self, dataset: Path) -> dict:
        offset = max(0, int(self.query.get("offset") or 0))
        needle = (self.query.get("q") or "").strip().lower()
        rows = read_manifest(dataset)
        indexed = [(i, r) for i, r in enumerate(rows) if not needle or matches(r, needle)]
        if self.query.get("order") == "recent":
            indexed.reverse()
        page = []
        for i, row in indexed[offset:offset + PAGE]:
            audio = audio_path(dataset, row)
            page.append({**row, "line": i + 1,
                         "has_audio": bool(audio and audio.is_file())})
        return {"total": len(rows), "matched": len(indexed), "offset": offset,
                "items": page}

    def item(self, dataset: Path) -> dict:
        rows, i = self.find(dataset)
        row = rows[i]
        path = audio_path(dataset, row)
        audio = None
        if path and path.is_file():
            import soundfile as sf
            info = sf.info(str(path))
            audio = {
                "file": str(Path(row["audio"])),
                "resolved": str(path),
                "bytes": path.stat().st_size,
                "format": info.format, "subtype": info.subtype,
                "sample_rate": info.samplerate, "channels": info.channels,
                "file_duration": info.frames / info.samplerate,
                "problem": contract.audio_problem(path),
            }
        aligned = contract._read_alignment(dataset / contract.ALIGNMENT_NAME).get(row["id"])
        if aligned:
            aligned = {**aligned, "stale": aligned.get("transcript") !=
                       (row.get("reference") or {}).get("transcript")}
        return {"line": i + 1, "row": row, "audio": audio, "alignment": aligned}

    def send_audio(self, dataset: Path):
        """The item's audio. An item cut from a longer file by `offset` gets only
        its window, so playback and word timings line up with what bench reads."""
        rows, i = self.find(dataset)
        row = rows[i]
        path = audio_path(dataset, row)
        if not path or not path.is_file():
            raise HttpError(404, "오디오가 없다")
        if row.get("offset") is None:
            return self.send_file(path)
        import soundfile as sf
        with sf.SoundFile(str(path)) as f:
            f.seek(int(round(float(row["offset"]) * f.samplerate)))
            frames = f.read(int(round(float(row["duration"]) * f.samplerate)),
                            dtype="int16")
            rate = f.samplerate
        buf = io.BytesIO()
        sf.write(buf, frames, rate, format="WAV", subtype="PCM_16")
        self.send_bytes(buf.getvalue(), "audio/wav")

    def verify(self, dataset: Path) -> dict:
        if not all((dataset / m).is_file() for m in MARKERS):
            raise HttpError(409, "dataset.yml 과 manifest.jsonl 이 둘 다 있어야 검증한다")
        out = io.StringIO()
        with redirect_stdout(out):
            code = contract.verify(dataset)
        return {"ok": code == 0, "report": out.getvalue().strip()}

    def drop_audio(self, dataset: Path) -> dict:
        """Unlink the file, keep the row. verify() will then flag it as missing,
        which is the honest state: the item exists and its audio does not.
        Items sharing one file by offset lose it together, so that is refused."""
        rows, i = self.find(dataset)
        path = audio_path(dataset, rows[i])
        if path and sum(audio_path(dataset, r) == path for r in rows) > 1:
            raise HttpError(409, "다른 항목도 이 파일을 쓴다")
        if path:
            path.unlink(missing_ok=True)
        return {"deleted_audio": self.query.get("id", "")}

    def drop_item(self, dataset: Path) -> dict:
        rows, i = self.find(dataset)
        path = audio_path(dataset, rows[i])
        shared = path and sum(audio_path(dataset, r) == path for r in rows) > 1
        if path and not shared:
            path.unlink(missing_ok=True)
        del rows[i]
        write_manifest(dataset, rows)
        return {"deleted": self.query.get("id", "")}

    def record(self, dataset: Path) -> dict:
        """Raw s16le in the body, the take's details in the query string.

        The page is the only client, so there is no reason to wrap one blob of
        bytes in a multipart envelope and pull in a parser to unwrap it.
        """
        pcm = self.body()
        duration = len(pcm) / SAMPLE_WIDTH / SAMPLE_RATE
        if duration < MIN_DURATION_SEC:
            return {"discarded": True, "duration": round(duration, 3)}

        spec = read_spec(dataset)
        declared = list(spec.get("languages") or [])
        src_lang = (self.query.get("src_lang") or "").strip() or \
            (declared[0] if declared else "en")
        if not SAFE_LANG.match(src_lang):
            raise HttpError(400, f"언어 코드가 잘못됐다: {src_lang}")

        sessions = dataset / "data" / "sessions"
        sessions.mkdir(parents=True, exist_ok=True)

        prefix = re.sub(r"[^A-Za-z0-9_-]", "", self.query.get("prefix", "")) or "rec"
        base = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        taken = {r.get("id") for r in read_manifest(dataset)}
        item_id, n = base, 2
        while item_id in taken or (sessions / f"{item_id}.wav").exists():
            item_id, n = f"{base}_{n}", n + 1

        with wave.open(str(sessions / f"{item_id}.wav"), "wb") as w:
            w.setnchannels(CHANNELS)
            w.setsampwidth(SAMPLE_WIDTH)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm)

        if not spec:
            # A hand-recorded dataset has no converter to write its spec, so the
            # first take bootstraps one.
            contract.write_spec(
                dataset, name=dataset.relative_to(self.server.root).as_posix(),
                split="record", languages=[src_lang], primary_metric="wer",
                translations=[], transcript=False, group_rule="id",
                bench_defaults={})
        elif src_lang not in declared:
            # A dataset can hold more than one source language. Recording one the
            # spec has not declared widens the spec rather than contradicting it.
            spec["languages"] = declared + [src_lang]
            write_spec_raw(dataset, spec)

        row = contract.row(item_id=item_id, audio_rel=f"data/sessions/{item_id}.wav",
                           duration=duration, src_lang=src_lang, transcript="",
                           speaker=self.query.get("speaker", ""))
        # Not a contract field. It is the whole point of an overlap take, and it
        # is knowable only while recording, so it rides along.
        speakers = int(self.query.get("speakers") or 0)
        if speakers:
            row["speakers"] = speakers

        rows = read_manifest(dataset)
        rows.append(row)
        write_manifest(dataset, rows)
        return row


def serve(root: Path, host: str, port: int) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Manager)
    httpd.root = root
    return httpd


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=str(ROOT), help="repo root holding the datasets")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9280)
    p.add_argument("--open", action="store_true", help="open a browser tab on start")
    args = p.parse_args(argv)

    root = Path(args.root).resolve()
    url = f"http://{args.host}:{args.port}"
    print(f"datasets in {root}: {', '.join(datasets(root)) or 'none'}")
    print(f"open {url}")
    if args.open:
        webbrowser.open(url)

    httpd = serve(root, args.host, args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
