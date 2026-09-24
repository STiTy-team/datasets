const RATE = 16000;
const RECENT = 20;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const state = { ctx: null, node: null, chunks: [], frames: 0, recording: false,
                dataset: null, tab: "browse", offset: 0, query: "", langs: [] };

function remember(key, value) {
  try { localStorage.setItem(key, value); } catch {}
}
function recall(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function api(action, params = {}, init = {}) {
  const q = new URLSearchParams({ ds: state.dataset, ...params });
  return fetch(`/api/${action}?${q}`, init);
}

function setStatus(kind, text) {
  $("status").dataset.state = kind;
  $("status-text").textContent = text;
}

function mmss(seconds) {
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

const num = (n, d = 1) => (n === undefined || n === null ? "–"
  : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }));
const pct = (a, b) => (b ? `${Math.round((100 * a) / b)}%` : "–");

/* ---------- tabs ---------- */

function applyTab(tab) {
  state.tab = tab;
  remember("manager-tab", tab);
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("off", v.id !== tab));
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
}

function showTab(tab) {
  applyTab(tab);
  loadTab();
}

document.querySelectorAll(".tab").forEach((b) =>
  b.addEventListener("click", () => showTab(b.dataset.tab)));

function loadTab() {
  if (!state.dataset) return;
  loadHeader();
  if (state.tab === "browse") {
    loadShape();
    state.offset = 0;
    loadItems();
  } else {
    loadRecent();
  }
}

/* ---------- microphone ---------- */

async function arm() {
  setStatus("idle", "마이크 여는 중…");

  // The DSP stays off. A noise suppressor is trained to treat the overlapping
  // second voice as noise and delete it, and that voice is the whole dataset.
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: false, noiseSuppression: false,
             autoGainControl: false, channelCount: 1 },
  });

  state.ctx = new AudioContext({ sampleRate: RATE });
  if (Math.round(state.ctx.sampleRate) !== RATE) {
    throw new Error(`브라우저가 16 kHz 를 거부했다 (${state.ctx.sampleRate} Hz)`);
  }
  await state.ctx.audioWorklet.addModule("/static/recorder-worklet.js");

  state.node = new AudioWorkletNode(state.ctx, "capture", { channelCount: 1 });
  state.node.port.onmessage = (e) => {
    state.chunks.push(e.data);
    state.frames += e.data.length;
    $("clock").textContent = mmss(state.frames / RATE);
  };

  // A muted sink keeps the graph pulling without routing the mic back to the
  // speakers, which in a room with two people talking is a feedback loop.
  const sink = state.ctx.createGain();
  sink.gain.value = 0;
  state.ctx.createMediaStreamSource(stream).connect(state.node);
  state.node.connect(sink).connect(state.ctx.destination);

  setStatus("armed", "대기 · 16 kHz");
  $("record-btn").textContent = "녹음 시작";
}

/* ---------- recording ---------- */

function toPCM(chunks) {
  const pcm = new Int16Array(chunks.reduce((n, c) => n + c.length, 0));
  let i = 0;
  for (const chunk of chunks) {
    for (const s of chunk) {
      const v = Math.max(-1, Math.min(1, s));
      pcm[i++] = v < 0 ? v * 0x8000 : v * 0x7fff;
    }
  }
  return pcm;
}

function start() {
  state.chunks = [];
  state.frames = 0;
  state.recording = true;
  state.node.port.postMessage({ recording: true });
  $("clock").textContent = "0:00";
  $("clock").classList.add("live");
  $("record-btn").textContent = "정지";
  $("record-btn").classList.add("live");
  $("dataset").disabled = true;
  setStatus("live", `녹음 중 · ${state.dataset}`);
}

async function stop() {
  state.recording = false;
  state.node.port.postMessage({ recording: false });
  $("clock").classList.remove("live");
  $("record-btn").textContent = "녹음 시작";
  $("record-btn").classList.remove("live");
  $("record-btn").disabled = true;
  $("dataset").disabled = false;
  setStatus("armed", "저장 중…");

  const pcm = toPCM(state.chunks);
  state.chunks = [];

  const res = await api("record", {
    prefix: $("prefix").value,
    speakers: String(Number($("speakers").value) || 0),
    src_lang: $("src-lang").value,
    speaker: $("speaker").value,
  }, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: pcm,
  });
  const saved = await res.json();
  $("record-btn").disabled = false;
  if (!res.ok) {
    setStatus("error", saved.error || `저장 실패 (${res.status})`);
    return;
  }
  setStatus("armed", saved.discarded
    ? `너무 짧아 버렸다 (${saved.duration}초)`
    : `저장됨 · ${saved.id}`);
  refreshDatasets(state.dataset);
}

async function toggle() {
  try {
    if (!state.node) await arm();
    else if (state.recording) await stop();
    else start();
  } catch (err) {
    setStatus("error", err.message || String(err));
    $("record-btn").disabled = false;
    $("record-btn").textContent = "다시 시도";
  }
}

$("record-btn").addEventListener("click", toggle);

document.addEventListener("keydown", (event) => {
  if (state.tab !== "record") return;
  if (event.code !== "Space" || event.target.matches("input, select, button")) return;
  event.preventDefault();
  toggle();
});

/* ---------- header ---------- */

function loadHeader() {
  const { datasets } = state.list;
  const d = datasets.find((x) => x.name === state.dataset);
  $("total-count").textContent = d ? num(d.items, 0) : "0";
  $("total-dur").textContent = d ? mmss(d.duration) : "0:00";
}

/* ---------- shape ---------- */

function stat(label, value, note = "", flag = false) {
  return `<div class="stat${flag ? " flag" : ""}"><span>${esc(label)}</span>
    <b>${value}</b>${note ? `<i>${note}</i>` : ""}</div>`;
}

function bars(entries, total) {
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return `<div class="bars">${entries.map(([k, v]) => `
    <div class="bar"><span>${esc(k)}</span>
      <div><i style="width:${(100 * v) / max}%"></i></div>
      <b>${num(v, 0)}</b><em>${pct(v, total)}</em></div>`).join("")}</div>`;
}

function binLabel(b) {
  return b.hi === null ? `${b.lo}s+` : `${b.lo}–${b.hi}s`;
}

async function loadShape() {
  const res = await api("shape");
  const s = await res.json();
  if (!res.ok) {
    $("shape").innerHTML = `<p class="flag">${esc(s.error)}</p>`;
    return;
  }
  $("path").textContent = s.path;
  $("verify-out").classList.add("hidden");

  const spec = s.spec || {};
  const provides = spec.provides || {};
  const declared = provides.translations || [];
  const d = s.duration;
  const t = s.transcript;

  const translations = [...new Set([...declared, ...Object.keys(s.translations)])]
    .map((lang) => [lang, s.translations[lang] || 0]);
  const shortTranslations = translations.some(([lang, n]) =>
    declared.includes(lang) && n < s.items);

  const files = Object.entries({
    "dataset.yml": Object.keys(spec).length > 0,
    "manifest.jsonl": s.files.manifest,
    "alignment.jsonl": s.files.alignment,
    "README.md": s.files.readme,
    "convert.py": s.files.convert,
  }).map(([k, v]) => `<span class="${v ? "" : "off"}">${k}</span>`).join("");

  $("shape").innerHTML = `
    <div class="files">${files}</div>
    <div class="stats">
      ${stat("항목", num(s.items, 0))}
      ${stat("총 길이", mmss(d.total || 0))}
      ${stat("세션 (group)", num(s.sessions, 0),
        s.sessions_contiguous ? "" : "연속이 아니다", !s.sessions_contiguous)}
      ${stat("화자", num(s.speakers, 0))}
      ${stat("오디오 파일", num(s.audio_files, 0),
        s.audio_missing ? `${s.audio_missing} 개 없음` : "", s.audio_missing > 0)}
      ${stat("offset 항목", num(s.offset_items, 0))}
      ${stat("partial 항목", num(s.partial_items, 0))}
      ${stat("primary_metric", esc(spec.primary_metric || "–"))}
    </div>

    <h3>길이 <span class="dim">초</span></h3>
    ${s.items ? `<div class="spread">
      <span>min <b>${num(d.min, 2)}</b></span><span>p50 <b>${num(d.p50, 2)}</b></span>
      <span>mean <b>${num(d.mean, 2)}</b></span><span>p90 <b>${num(d.p90, 2)}</b></span>
      <span>max <b>${num(d.max, 2)}</b></span></div>
      ${bars(s.histogram.filter((b) => b.count).map((b) => [binLabel(b), b.count]), s.items)}`
      : '<p class="dim">항목 없음</p>'}

    <h3>src_lang</h3>
    ${bars(Object.entries(s.src_lang), s.items)}

    <h3>참조 ${shortTranslations ? '<span class="flag">선언한 번역이 빠진 항목이 있다</span>' : ""}</h3>
    ${bars([[`transcript${provides.transcript === false ? " (선언 안 함)" : ""}`, t.filled],
            ...translations.map(([lang, n]) =>
              [`→ ${lang}${declared.includes(lang) ? "" : " (선언 안 함)"}`, n])], s.items)}
    ${t.units ? `<p class="dim small">전사 길이 (단어, 중·일은 글자): min ${t.units.min} ·
      p50 ${num(t.units.p50, 0)} · p90 ${t.units.p90} · max ${t.units.max}</p>` : ""}

    <h3>정렬 ${s.alignment.stale ? `<span class="flag">${s.alignment.stale} 개가 옛 전사 기준</span>` : ""}
      ${s.alignment.orphan ? `<span class="flag">${s.alignment.orphan} 개는 manifest 에 없다</span>` : ""}</h3>
    ${s.files.alignment
      ? `${bars([["aligned", s.alignment.items]], t.filled || s.items)}
         <p class="dim small">${Object.entries(s.alignment.aligners)
           .map(([k, v]) => `${esc(k)} × ${v}`).join(" · ")}</p>`
      : '<p class="dim small">alignment.jsonl 없음</p>'}

    <h3>행의 필드</h3>
    <table class="fields-table">
      ${s.fields.map((f) => `<tr>
        <td class="${f.key.includes(".") ? "sub" : ""}">${esc(f.key)}</td>
        <td>${Object.keys(f.types).map(esc).join(" | ")}</td>
        <td class="${f.count < s.items && !f.key.startsWith("reference.translations.") ? "partial" : ""}">
          ${num(f.count, 0)}</td></tr>`).join("")}
    </table>

    ${s.files.manifest_sha256 ? `<p class="dim small sha">manifest sha256
      <code>${s.files.manifest_sha256}</code> · ${num(s.files.manifest_bytes / 1024, 0)} KB</p>` : ""}`;

  $("spec").textContent = Object.keys(spec).length
    ? JSON.stringify(spec, null, 2) : "dataset.yml 없음";
  state.langs = spec.languages || [];
  syncLangs();
}

$("verify").addEventListener("click", async () => {
  const out = $("verify-out");
  out.classList.remove("hidden", "ok", "bad");
  out.textContent = "검증 중… (오디오 헤더를 전부 읽는다)";
  const res = await api("verify");
  const body = await res.json();
  out.textContent = body.report || body.error;
  out.classList.add(res.ok && body.ok ? "ok" : "bad");
});

/* ---------- items ---------- */

function confirmingButton(label, onConfirm) {
  const b = document.createElement("button");
  b.className = "ghost del";
  b.textContent = label;
  b.addEventListener("click", async (event) => {
    event.stopPropagation();
    if (b.dataset.armed !== "1") {
      b.dataset.armed = "1";
      b.textContent = "정말?";
      setTimeout(() => { b.dataset.armed = "0"; b.textContent = label; }, 3000);
      return;
    }
    const res = await onConfirm();
    if (!res.ok) {
      b.textContent = (await res.json()).error || "실패";
      return;
    }
    refreshDatasets(state.dataset);
  });
  return b;
}

function row(item) {
  const el = document.createElement("div");
  el.className = "take";

  const facts = [
    `<b>${mmss(item.duration || 0)}</b>`,
    item.src_lang && `<span>${esc(item.src_lang)}</span>`,
    item.speaker && `<span>${esc(item.speaker)}</span>`,
    item.speakers && `<span>화자 ${item.speakers}</span>`,
    item.group !== item.id && `<span>group ${esc(item.group)}</span>`,
    item.offset !== undefined && `<span>+${item.offset}s</span>`,
    item.partial && `<span class="flag">partial</span>`,
    !item.has_audio && `<span class="flag">오디오 없음</span>`,
  ].filter(Boolean);

  const text = item.reference?.transcript || "";
  const langs = Object.keys(item.reference?.translations || {});

  el.innerHTML = `
    <div class="line">#${item.line}</div>
    <div class="id">${esc(item.id)}</div>
    <div class="facts">${facts.join("")}</div>
    <div class="note">${text ? esc(text) : "<i>전사 없음</i>"}${langs.length
      ? ` <span class="dim">· 번역 ${esc(langs.join(", "))}</span>` : ""}</div>`;

  el.addEventListener("click", (event) => {
    if (event.target.closest(".detail")) return;
    const open = el.querySelector(".detail");
    if (open) {
      open.remove();
      el.classList.remove("open");
    } else {
      el.classList.add("open");
      el.append(detail(item));
    }
  });
  return el;
}

function detail(item) {
  const box = document.createElement("div");
  box.className = "detail";
  box.textContent = "읽는 중…";
  const id = item.id;

  api("item", { id }).then(async (res) => {
    const d = await res.json();
    if (!res.ok) {
      box.textContent = d.error;
      return;
    }
    box.textContent = "";

    const tools = document.createElement("div");
    tools.className = "tools";
    let player = null;
    if (d.audio) {
      player = document.createElement("audio");
      player.controls = true;
      player.preload = "metadata";
      player.src = `/api/audio?${new URLSearchParams({ ds: state.dataset, id })}`;
      tools.append(player);
      tools.append(confirmingButton("오디오 삭제",
        () => api("audio", { id }, { method: "DELETE" })));
    }
    tools.append(confirmingButton("항목 삭제",
      () => api("item", { id }, { method: "DELETE" })));
    box.append(tools);

    const ref = d.row.reference || {};
    const texts = [
      ["transcript", ref.transcript],
      ...Object.entries(ref.translations || {}).map(([k, v]) => [`→ ${k}`, v]),
    ].filter(([, v]) => v);
    if (texts.length) {
      const t = document.createElement("dl");
      t.className = "texts";
      t.innerHTML = texts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");
      box.append(t);
    }

    if (d.audio) {
      const a = d.audio;
      const info = document.createElement("p");
      info.className = `audio-info${a.problem ? " flag" : ""}`;
      info.textContent = `${a.file} · ${a.format}/${a.subtype} ${a.sample_rate} Hz `
        + `${a.channels}ch · 파일 ${a.file_duration.toFixed(3)}s · `
        + `${Math.round(a.bytes / 1024)} KB${a.problem ? ` · ${a.problem}` : ""}`;
      box.append(info);
    }

    if (d.alignment) {
      const al = document.createElement("div");
      al.className = "words";
      const head = document.createElement("p");
      head.className = `dim small${d.alignment.stale ? " flag" : ""}`;
      head.textContent = `정렬 · ${d.alignment.aligner} · ${d.alignment.words.length} 단어`
        + (d.alignment.stale ? " · 옛 전사 기준" : "") + " · 누르면 그 자리부터 재생";
      al.append(head);
      for (const w of d.alignment.words) {
        const chip = document.createElement("button");
        chip.className = "word";
        chip.title = `${w.start.toFixed(2)} – ${w.end.toFixed(2)}s`;
        chip.textContent = w.word;
        chip.addEventListener("click", () => {
          if (!player) return;
          player.currentTime = w.start;
          player.play();
        });
        al.append(chip);
      }
      box.append(al);
      if (player) {
        const chips = [...al.querySelectorAll(".word")];
        player.addEventListener("timeupdate", () => {
          const now = player.currentTime;
          d.alignment.words.forEach((w, i) =>
            chips[i].classList.toggle("now", w.start <= now && now < w.end));
        });
      }
    }

    const raw = document.createElement("pre");
    raw.className = "code";
    raw.textContent = `manifest.jsonl:${d.line}\n${JSON.stringify(d.row, null, 2)}`;
    box.append(raw);
  });
  return box;
}

async function loadItems() {
  const res = await api("items", { offset: state.offset, q: state.query });
  const data = await res.json();
  if (!res.ok) return;

  const rows = data.items.map(row);
  if (state.offset === 0) $("list").replaceChildren(...rows);
  else $("list").append(...rows);

  const shown = state.offset + data.items.length;
  $("range").textContent = !data.total ? ""
    : state.query ? `${shown} / ${data.matched} 일치 (전체 ${data.total})`
    : `${shown} / ${data.total}`;
  $("empty").classList.toggle("hidden", data.total > 0);
  $("more").classList.toggle("hidden", shown >= data.matched);
  state.offset = shown;
}

$("more").addEventListener("click", loadItems);

let searchTimer = null;
$("search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.query = $("search").value.trim();
    state.offset = 0;
    loadItems();
  }, 250);
});

async function loadRecent() {
  const res = await api("items", { order: "recent" });
  const data = await res.json();
  if (!res.ok) return;
  $("recent").replaceChildren(...data.items.slice(0, RECENT).map(row));
  $("recent-range").textContent = data.total ? `전체 ${data.total} 중 마지막 ${Math.min(RECENT, data.total)}` : "";
  if (!state.langs.length) {
    const shape = await (await api("shape")).json();
    state.langs = shape.spec?.languages || [];
    $("path").textContent = shape.path;
  }
  syncLangs();
}

function syncLangs() {
  $("lang-options").replaceChildren(...state.langs.map((l) => {
    const o = document.createElement("option");
    o.value = l;
    return o;
  }));
  if (!state.langs.includes($("src-lang").value)) {
    $("src-lang").value = state.langs[0] || "";
  }
}

$("dataset").addEventListener("change", () => {
  state.dataset = $("dataset").value;
  state.langs = [];
  state.query = "";
  $("search").value = "";
  remember("manager-dataset", state.dataset);
  loadTab();
});

/* ---------- new dataset ---------- */

function showPanel(open) {
  $("new-panel").classList.toggle("hidden", !open);
  $("new-error").textContent = "";
  if (open) $("new-name").focus();
  else { $("new-name").value = ""; $("new-langs").value = ""; }
}

$("new").addEventListener("click", () => {
  showPanel($("new-panel").classList.contains("hidden"));
});
$("new-cancel").addEventListener("click", () => showPanel(false));

async function createDataset() {
  const name = $("new-name").value.trim();
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(name)) {
    $("new-error").textContent = "이름은 영문·숫자·_·- 만 쓴다";
    return;
  }
  const q = new URLSearchParams({ name, languages: $("new-langs").value });
  const res = await fetch(`/api/datasets?${q}`, { method: "POST" });
  const body = await res.json();
  if (!res.ok) {
    $("new-error").textContent = body.error || `실패 (${res.status})`;
    return;
  }
  showPanel(false);
  state.langs = [];
  applyTab("record");
  await refreshDatasets(body.name);
}

$("new-create").addEventListener("click", createDataset);
$("new-panel").addEventListener("keydown", (event) => {
  if (event.key === "Enter") createDataset();
  if (event.key === "Escape") showPanel(false);
});

/* ---------- boot ---------- */

async function refreshDatasets(select) {
  state.list = await (await fetch("/api/datasets")).json();
  const { datasets } = state.list;
  $("dataset").replaceChildren(...datasets.map((d) => {
    const o = document.createElement("option");
    o.value = d.name;
    o.textContent = `${d.name} · ${d.items} items`;
    return o;
  }));
  const saved = select || recall("manager-dataset");
  state.dataset = datasets.some((d) => d.name === saved) ? saved : datasets[0]?.name;
  if (!state.dataset) return setStatus("error", "데이터셋이 없다. + 로 하나 만든다");
  $("dataset").value = state.dataset;
  remember("manager-dataset", state.dataset);
  return loadTab();
}

applyTab(recall("manager-tab") === "record" ? "record" : "browse");
refreshDatasets();
