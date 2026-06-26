"use strict";

// ─────────────────────────────────────────────────────────────────────────────
// Real-Time AI Character Engine — browser client
//
// Two responsibilities:
//   1. Drive the voice loop over a WebSocket (send mic clips / text, receive
//      control JSON + streamed PCM audio).
//   2. Low-latency streaming playback: schedule each PCM frame on the Web Audio
//      clock as it arrives — NOT download-then-play.
//
// Audio wire format (must match the backend): raw PCM, signed 16-bit
// little-endian, mono, 24 kHz.
// ─────────────────────────────────────────────────────────────────────────────

const SAMPLE_RATE = 24000; // TTS playback
const STREAM_RATE = 16000; // mic -> AssemblyAI streaming
// Bump this whenever app.js changes so we can confirm the browser loaded it.
const APP_VERSION = "2026-06-25-el-default";
let isStreaming = false; // streaming STT available this session?
let livePartialEl = null; // live (interim) transcript bubble

// ---- DOM helpers ----
const $ = (id) => document.getElementById(id);
const connDot = $("conn-dot");

// ============================================================ tab switching
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    tab.classList.add("active");
    $("view-" + tab.dataset.view).classList.add("active");
  });
});

// ============================================================ audio playback
// A single, continuously-running AudioWorklet node plays streamed PCM. Because
// the node never stops, there's no per-response context warm-up (no clipped first
// word) and no per-buffer boundaries (no clicks). See web/pcm-player.js.
let audioCtx = null;
let pcmNode = null;
let pcmCarry = new Uint8Array(0); // holds a trailing odd byte across frames

async function ensureAudio() {
  if (!audioCtx) {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    try {
      audioCtx = new Ctor({ sampleRate: SAMPLE_RATE });
    } catch (e) {
      audioCtx = new Ctor(); // browser refused the explicit rate; we resample
    }
    await audioCtx.audioWorklet.addModule(
      "/pcm-player.js?v=" + (window.__BUILD__ || APP_VERSION),
    );
    pcmNode = new AudioWorkletNode(audioCtx, "pcm-player");
    pcmNode.connect(audioCtx.destination);
  }
  if (audioCtx.state === "suspended") await audioCtx.resume();
}

function resetPlaybackClock() {
  pcmCarry = new Uint8Array(0);
  if (!pcmNode) return;
  pcmNode.port.postMessage({ type: "reset" });
  // Prime the queue with a short silence so the first real samples are never at
  // the very edge of playback startup (defends the first word regardless of cause).
  const pad = new Float32Array(Math.round(SAMPLE_RATE * 0.08));
  pcmNode.port.postMessage(pad, [pad.buffer]);
}

function resampleLinear(input, fromRate, toRate) {
  if (fromRate === toRate) return input;
  const ratio = toRate / fromRate;
  const out = new Float32Array(Math.round(input.length * ratio));
  for (let i = 0; i < out.length; i++) {
    const pos = i / ratio;
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const frac = pos - i0;
    out[i] = input[i0] * (1 - frac) + input[i1] * frac;
  }
  return out;
}

function playPcmFrame(arrayBuffer) {
  if (!pcmNode) return;
  // Prepend any leftover odd byte from the previous frame.
  let bytes = new Uint8Array(arrayBuffer);
  if (pcmCarry.length) {
    const merged = new Uint8Array(pcmCarry.length + bytes.length);
    merged.set(pcmCarry, 0);
    merged.set(bytes, pcmCarry.length);
    bytes = merged;
    pcmCarry = new Uint8Array(0);
  }
  // Keep a trailing odd byte (a split 16-bit sample) for the next frame.
  if (bytes.length % 2 !== 0) {
    pcmCarry = bytes.slice(bytes.length - 1);
    bytes = bytes.slice(0, bytes.length - 1);
  }
  if (bytes.length === 0) return;

  const samples = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.length / 2);
  let f32 = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) f32[i] = samples[i] / 32768;
  if (audioCtx.sampleRate !== SAMPLE_RATE) {
    f32 = resampleLinear(f32, SAMPLE_RATE, audioCtx.sampleRate);
  }
  pcmNode.port.postMessage(f32, [f32.buffer]); // transfer ownership
}

// ============================================================ conversation log
const log = $("log");
let liveAssistantEl = null; // the assistant bubble currently being streamed into

function addMessage(who, text) {
  const el = document.createElement("div");
  el.className = "msg " + who;
  const label = document.createElement("div");
  label.className = "who";
  label.textContent = who === "user" ? "You" : currentCharacterName || "Character";
  const body = document.createElement("div");
  body.textContent = text;
  el.appendChild(label);
  el.appendChild(body);
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return body;
}

// Render assistant text with the model's [performance tags] shown as dim, italic stage
// directions — they're delivery notes the voice performs, not words it speaks aloud (the
// audio path strips/transforms them; see expressivity.render_tags). The optional trailing
// "]" in the pattern keeps a half-streamed "[clip..." from flashing as dialogue mid-token.
function renderPerfText(raw) {
  return escapeHtml(raw).replace(/\[[^\]]*\]?/g, (m) => `<span class="perf-tag">${m}</span>`);
}

// ============================================================ latency panel
function renderLatency(marks) {
  const panel = $("latency");
  panel.style.display = "block";
  const order = [
    ["transcript_ready", "STT → transcript"],
    ["llm_first_token", "LLM first token"],
    ["first_audio", "First audio out"],
    ["turn_complete", "Full reply spoken"],
  ];
  const max = Math.max(1, ...Object.values(marks));
  const firstAudio = marks.first_audio;
  $("lat-headline").textContent =
    firstAudio != null
      ? `⚡ First audio ${firstAudio} ms after you stopped talking`
      : "Latency budget (ms since you stopped talking)";

  const bars = $("lat-bars");
  bars.innerHTML = "";
  for (const [key, name] of order) {
    if (marks[key] == null) continue;
    const pct = Math.round((marks[key] / max) * 100);
    const bar = document.createElement("div");
    bar.className = "bar";
    bar.innerHTML =
      `<span class="name">${name}</span>` +
      `<span class="track"><span class="fill" style="width:${pct}%"></span></span>` +
      `<span class="val">${marks[key]} ms</span>`;
    bars.appendChild(bar);
  }
}

// ============================================================ websocket session
let ws = null;
let currentCharacterName = "";

function setConnected(isConnected) {
  connDot.classList.toggle("live", isConnected);
  $("connect").disabled = isConnected;
  $("disconnect").disabled = !isConnected;
  $("talk").disabled = !isConnected;
  $("text-input").disabled = !isConnected;
  $("send").disabled = !isConnected;
  $("character").disabled = isConnected;
  $("model").disabled = isConnected;
  $("profile").disabled = isConnected;
}

async function connect() {
  const slug = $("character").value;
  if (!slug) {
    setStatus("Pick a character first.");
    return;
  }
  // Clear any stale relevance panel from a previous session — it repopulates on the
  // first turn of the new one (long-term memory itself persists on disk regardless).
  document.getElementById("mem-debug")?.remove();
  memDebugExpanded.clear();
  memDebugLast = null;
  // Create the AudioContext + worklet from this user gesture so playback is allowed.
  try {
    await ensureAudio();
  } catch (e) {
    setStatus("Audio init failed: " + e);
    return;
  }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const model = $("model").value;
  const profile = $("profile").value;
  // A/B: full-loop LLM override from the page URL (?realtime_llm=openai/gpt-4o), forwarded
  // to the session so Bri/Corvin can be tested across models without a server restart.
  const rtLlm = new URLSearchParams(location.search).get("realtime_llm") || "";
  ws = new WebSocket(
    `${proto}://${location.host}/ws?character=${encodeURIComponent(slug)}` +
      `&model=${encodeURIComponent(model)}&profile=${encodeURIComponent(profile)}` +
      (rtLlm ? `&realtime_llm=${encodeURIComponent(rtLlm)}` : ``),
  );
  ws.binaryType = "arraybuffer";
  // Dev: expose the socket so you can drive the engine/game seam from the console, e.g.
  //   __ws.send(JSON.stringify({type:"remember", fact:"Bri owes the player a favor", importance:0.9}))
  //   __ws.send(JSON.stringify({type:"text", text:"hey", situation:{location:"the docks", present:["Marco"]}}))
  window.__ws = ws;

  ws.onopen = () => {
    setConnected(true);
    setStatus("Connected. Say hello.");
  };
  ws.onclose = () => {
    setConnected(false);
    setStatus("Disconnected.");
    ws = null;
  };
  ws.onerror = () => setStatus("Connection error.");

  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      playPcmFrame(event.data);
      return;
    }
    handleControl(JSON.parse(event.data));
  };
}

function handleControl(msg) {
  switch (msg.type) {
    case "ready":
      currentCharacterName = msg.character.name;
      isStreaming = !!msg.streaming;
      setTalkState("idle");
      if (msg.model) {
        setStatus(
          `Connected to ${currentCharacterName} · ${msg.model}` +
            (isStreaming ? " · live STT" : ""),
        );
      }
      break;
    case "partial_transcript":
      if (!livePartialEl) livePartialEl = addMessage("user", "");
      livePartialEl.textContent = msg.text;
      log.scrollTop = log.scrollHeight;
      break;
    case "transcript":
      if (livePartialEl) {
        livePartialEl.textContent = msg.text;
        livePartialEl = null;
      } else {
        addMessage("user", msg.text);
      }
      liveAssistantEl = null;
      break;
    case "mic_ended":
      stopStreamingMic();
      setTalkState("processing");
      break;
    case "assistant_start":
      liveAssistantEl = addMessage("assistant", "");
      liveAssistantEl._raw = "";
      break;
    case "assistant_delta":
      if (!liveAssistantEl) { liveAssistantEl = addMessage("assistant", ""); liveAssistantEl._raw = ""; }
      liveAssistantEl._raw += msg.text;
      liveAssistantEl.innerHTML = renderPerfText(liveAssistantEl._raw);
      log.scrollTop = log.scrollHeight;
      break;
    case "assistant_done":
      if (liveAssistantEl) liveAssistantEl.innerHTML = renderPerfText(msg.text);
      else { const b = addMessage("assistant", ""); b.innerHTML = renderPerfText(msg.text); }
      liveAssistantEl = null;
      if (isStreaming) setTalkState("idle"); // ready for the next turn
      break;
    case "audio_start":
      resetPlaybackClock();
      break;
    case "audio_end":
      break;
    case "memories":
      renderMemoryDebug(msg);
      break;
    case "remembered":
      setStatus(`Remembered: "${msg.fact}"`);
      break;
    case "latency":
      renderLatency(msg.marks);
      break;
    case "info":
      setStatus(msg.message);
      break;
    case "error":
      setStatus("⚠ " + msg.message);
      break;
  }
}

function disconnect() {
  if (ws) ws.close();
}

function setStatus(text) {
  $("conv-status").textContent = text;
}

// ---- dev: relevance-realization memory debug panel (server emits "memories") ----
function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

// Relevance-realization debug panel: two tabs (long-term scoring / short-term buffer),
// expandable rows, query-term bolding, and a minimize-to-pill toggle. Server emits a
// "memories" frame each turn with the scored long-term candidates + the short-term buffer.
const memDebugExpanded = new Set(); // expanded rows, keyed by tab+index
let memDebugTab = "long"; // "long" | "short"
let memDebugMin = false; // minimized to a pill?
let memDebugLast = null; // last payload, so UI toggles can re-render
let memDebugW = null; // persisted custom size (top-left resize grip)
let memDebugH = null;

const MEM_STOP = new Set(
  ("the a an and or but if then so to of in on at for with my your his her our their me you " +
    "he she it we they them him do does did is are was were be been have has had that this what " +
    "when how why who not no yes ok okay just like about").split(" "),
);
function memQueryTerms(q) {
  return ((q || "").toLowerCase().match(/[a-z0-9']{3,}/g) || []).filter((t) => !MEM_STOP.has(t));
}
function memBold(escaped, terms) {
  if (!terms.length) return escaped;
  const pat = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
  return escaped.replace(new RegExp("\\b(" + pat + ")\\b", "gi"), "<b style='color:#fff'>$1</b>");
}

function renderMemoryDebug(msg) {
  if (msg) memDebugLast = msg;
  msg = memDebugLast;
  if (!msg) return;

  let panel = document.getElementById("mem-debug");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "mem-debug";
    document.body.appendChild(panel);
  }
  panel.replaceChildren();
  panel.onclick = null;

  const el = (tag, css, txt) => {
    const n = document.createElement(tag);
    if (css) n.style.cssText = css;
    if (txt != null) n.textContent = txt;
    return n;
  };
  const pct = (x) => (Math.max(0, Math.min(1, x)) * 100).toFixed(0);
  const terms = memQueryTerms(msg.query);

  // expandable row shared by both tabs
  const addRow = (key, headText, headColor, fullText) => {
    const expanded = memDebugExpanded.has(key);
    const row = el("div", "border-top:1px solid #2a2a30;padding:4px 0");
    const head = el("div", `color:${headColor};cursor:pointer`);
    head.textContent = `${expanded ? "▾" : "▸"} ${headText}`;
    row.appendChild(head);
    const toggle = () => {
      if (memDebugExpanded.has(key)) memDebugExpanded.delete(key);
      else memDebugExpanded.add(key);
      renderMemoryDebug();
    };
    head.addEventListener("click", toggle);
    if (!expanded) {
      const oneLine = (fullText || "").replace(/\s+/g, " ");
      const shown = oneLine.length > 220 ? oneLine.slice(0, 220) + "…" : oneLine;
      const pv = el("div", "color:#bbb;margin-left:15px;cursor:pointer;word-break:break-word");
      pv.innerHTML = memBold(escapeHtml(shown), terms);
      pv.addEventListener("click", toggle);
      row.appendChild(pv);
    } else {
      const body = el(
        "div",
        "margin-left:15px;color:#e2e2e8;background:#23232a;padding:6px;border-radius:4px;" +
          "margin:2px 0;white-space:pre-wrap;word-break:break-word",
      );
      body.innerHTML = memBold(escapeHtml(fullText || ""), terms);
      body.addEventListener("click", (e) => e.stopPropagation());
      row.appendChild(body);
    }
    panel.appendChild(row);
    return row;
  };

  // --- minimized: a small pill that restores on click ---
  if (memDebugMin) {
    panel.style.cssText =
      "position:fixed;right:12px;bottom:12px;z-index:9999;cursor:pointer;" +
      "background:rgba(18,18,22,.97);color:#9be29b;font:13px ui-monospace,monospace;" +
      "border:1px solid #444;border-radius:20px;padding:6px 12px;box-shadow:0 4px 18px rgba(0,0,0,.45)";
    panel.textContent = "🧠 RR";
    panel.title = "Show relevance panel";
    panel.onclick = () => {
      memDebugMin = false;
      renderMemoryDebug();
    };
    return;
  }

  // Pinned bottom-right; grows up-left via the custom grip below (native resize handle
  // would sit against the screen corner, unusable). max-height auto-sizes until the user
  // resizes, then their explicit size persists across re-renders.
  panel.style.cssText =
    "position:fixed;right:12px;bottom:12px;width:480px;max-height:78vh;overflow:auto;" +
    "z-index:9999;background:rgba(18,18,22,.97);color:#ddd;font:11px/1.5 ui-monospace,monospace;" +
    "border:1px solid #444;border-radius:8px;padding:10px;box-shadow:0 4px 18px rgba(0,0,0,.45)";
  if (memDebugW) panel.style.width = memDebugW + "px";
  if (memDebugH) {
    panel.style.height = memDebugH + "px";
    panel.style.maxHeight = "none";
  }

  // --- header: resize grip (top-left) · title · embedder · minimize ---
  const header = el("div", "display:flex;align-items:center;gap:8px;margin-bottom:5px");
  const grip = el("div", "cursor:nwse-resize;color:#888;user-select:none;font-size:13px;padding:0 2px", "⤡");
  grip.title = "Drag to resize (bigger up-left, smaller down-right)";
  grip.addEventListener("mousedown", (e) => {
    e.preventDefault();
    const sx = e.clientX, sy = e.clientY, sw = panel.offsetWidth, sh = panel.offsetHeight;
    const move = (ev) => {
      memDebugW = Math.max(300, sw + (sx - ev.clientX));
      memDebugH = Math.max(140, sh + (sy - ev.clientY));
      panel.style.width = memDebugW + "px";
      panel.style.height = memDebugH + "px";
      panel.style.maxHeight = "none";
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
    };
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  });
  header.appendChild(grip);
  header.appendChild(el("div", "color:#fff;font-weight:bold;flex:1", "🧠 relevance realization"));
  header.appendChild(el("div", "color:#888", msg.embedder || ""));
  const minBtn = el(
    "div",
    "cursor:pointer;color:#ddd;background:#33333a;border:1px solid #555;border-radius:4px;padding:1px 9px;font-weight:bold",
    "—",
  );
  minBtn.title = "Minimize";
  minBtn.onclick = () => {
    memDebugMin = true;
    renderMemoryDebug();
  };
  header.appendChild(minBtn);
  panel.appendChild(header);

  panel.appendChild(
    el("div", "color:#9aa;margin-bottom:5px;word-break:break-word", "query: " + (msg.query || "")),
  );

  // --- tabs ---
  const longN = (msg.scored || []).length;
  const shortN = (msg.short_term || []).length;
  const tabs = el("div", "display:flex;gap:5px;margin-bottom:6px");
  const mkTab = (id, label) => {
    const active = memDebugTab === id;
    const t = el(
      "div",
      "cursor:pointer;padding:3px 10px;border-radius:5px;" +
        (active ? "background:#2f6b3a;color:#fff" : "background:#26262c;color:#aaa"),
      label,
    );
    t.onclick = () => {
      memDebugTab = id;
      renderMemoryDebug();
    };
    return t;
  };
  tabs.appendChild(mkTab("long", `Long-term (${longN})`));
  tabs.appendChild(mkTab("short", `Short-term (${shortN})`));
  panel.appendChild(tabs);

  if (memDebugTab === "long") {
    panel.appendChild(
      el("div", "color:#777;margin-bottom:4px",
        `★ injected into the prompt (budget ${(msg.selected || []).length}) · click a row for detail`),
    );
    (msg.scored || []).forEach((m, i) => {
      const tag = m.selected ? `★${m.rank}` : "·";
      const flag = m.kind === "world_event" ? " ⚑" : "";
      const headText =
        `${tag}  base ${m.base.toFixed(2)} · sim ${pct(m.similarity)} rec ${pct(m.recency)} imp ${pct(m.importance)}${flag}`;
      const row = addRow("L" + i, headText, m.selected ? "#9be29b" : "#8a8a92", m.text || "");
      if (memDebugExpanded.has("L" + i)) {
        const simRaw = m.similarity_raw != null ? ` (raw ${m.similarity_raw.toFixed(3)})` : "";
        const meta = el("div", "margin-left:15px;color:#9aa");
        meta.textContent =
          `kind ${m.kind || ""}${m.when ? " · when " + m.when : ""}  ·  ` +
          `base ${m.base.toFixed(3)} = sim ${m.similarity.toFixed(3)}${simRaw} · rec ${m.recency.toFixed(3)} · imp ${m.importance.toFixed(3)}`;
        row.appendChild(meta);
      }
    });
    if (!longN) panel.appendChild(el("div", "color:#888", "(no long-term memories stored yet)"));
  } else {
    panel.appendChild(
      el("div", "color:#777;margin-bottom:4px",
        "recent turns kept verbatim and injected every turn (not scored)"),
    );
    (msg.short_term || []).forEach((m, i) => {
      const who = m.role === "user" ? "Player" : "Character";
      const color = m.role === "user" ? "#7db4e6" : "#e6b07d";
      addRow("S" + i, who, color, m.content || "");
    });
    if (!shortN) panel.appendChild(el("div", "color:#888", "(short-term buffer empty)"));
  }
}

// ============================================================ mic capture
// Streaming (AssemblyAI) when available; otherwise batch (record a clip).
let isRecording = false;
let mediaRecorder = null;
let recordedChunks = [];

// Streaming capture state
let micStream = null;
let captureCtx = null;
let captureNode = null;
let capActive = false;
let capOutBuf = new Float32Array(0);

function setTalkState(state) {
  const btn = $("talk");
  if (state === "listening") {
    btn.classList.add("recording");
    btn.textContent = "■ Listening… (click to cancel)";
  } else if (state === "processing") {
    btn.classList.remove("recording");
    btn.textContent = "Thinking…";
  } else {
    btn.classList.remove("recording");
    btn.textContent = isStreaming ? "🎙 Click to talk" : "🎙 Hold to talk (click to start/stop)";
  }
}

async function toggleTalk() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  return isStreaming ? toggleStreamingMic() : toggleBatchRecord();
}

// --- Streaming: continuous 16 kHz PCM; the turn ends on AssemblyAI end-of-turn ---
async function toggleStreamingMic() {
  if (capActive) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "mic_stop" }));
    stopStreamingMic();
    setTalkState("idle");
    setStatus("Cancelled.");
    return;
  }
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (err) {
    setStatus("Microphone access denied.");
    return;
  }
  captureCtx = new (window.AudioContext || window.webkitAudioContext)();
  await captureCtx.audioWorklet.addModule("/mic-capture.js?v=" + (window.__BUILD__ || APP_VERSION));
  const src = captureCtx.createMediaStreamSource(micStream);
  captureNode = new AudioWorkletNode(captureCtx, "mic-capture");
  src.connect(captureNode);
  // Keep the graph running without audibly playing the mic back.
  const sink = captureCtx.createGain();
  sink.gain.value = 0;
  captureNode.connect(sink);
  sink.connect(captureCtx.destination);
  capOutBuf = new Float32Array(0);
  capActive = true;
  captureNode.port.onmessage = (e) => onMicChunk(e.data);
  ws.send(JSON.stringify({ type: "mic_start" }));
  setTalkState("listening");
  setStatus("Listening… speak, then pause.");
}

function onMicChunk(frame) {
  if (!capActive || !ws || ws.readyState !== WebSocket.OPEN) return;
  const down =
    captureCtx.sampleRate === STREAM_RATE
      ? frame
      : resampleLinear(frame, captureCtx.sampleRate, STREAM_RATE);
  const merged = new Float32Array(capOutBuf.length + down.length);
  merged.set(capOutBuf);
  merged.set(down, capOutBuf.length);
  capOutBuf = merged;
  const CH = 1600; // 100 ms @ 16 kHz
  while (capOutBuf.length >= CH) {
    const chunk = capOutBuf.subarray(0, CH);
    const i16 = new Int16Array(CH);
    for (let i = 0; i < CH; i++) {
      const v = Math.max(-1, Math.min(1, chunk[i]));
      i16[i] = v < 0 ? v * 32768 : v * 32767;
    }
    ws.send(i16.buffer);
    capOutBuf = capOutBuf.slice(CH);
  }
}

function stopStreamingMic() {
  capActive = false;
  if (micStream) micStream.getTracks().forEach((t) => t.stop());
  if (captureCtx) captureCtx.close().catch(() => {});
  captureCtx = null;
  captureNode = null;
  micStream = null;
  capOutBuf = new Float32Array(0);
}

// --- Batch: record a clip, send on stop (Whisper) ---
async function getRecorder() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  return new MediaRecorder(stream);
}

async function toggleBatchRecord() {
  if (!isRecording) {
    try {
      mediaRecorder = await getRecorder();
    } catch (err) {
      setStatus("Microphone access denied.");
      return;
    }
    recordedChunks = [];
    mediaRecorder.ondataavailable = (e) => e.data.size && recordedChunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const blob = new Blob(recordedChunks, { type: mediaRecorder.mimeType });
      const buf = await blob.arrayBuffer();
      if (ws && ws.readyState === WebSocket.OPEN && buf.byteLength) {
        ws.send(buf);
        setStatus("Thinking…");
      }
      mediaRecorder.stream.getTracks().forEach((t) => t.stop());
    };
    mediaRecorder.start();
    isRecording = true;
    $("talk").classList.add("recording");
    $("talk").textContent = "■ Stop & send";
    setStatus("Listening…");
  } else {
    mediaRecorder.stop();
    isRecording = false;
    $("talk").classList.remove("recording");
    $("talk").textContent = "🎙 Hold to talk (click to start/stop)";
  }
}

function sendText() {
  const input = $("text-input");
  const text = input.value.trim();
  if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: "text", text }));
  input.value = "";
  setStatus("Thinking…");
}

// ============================================================ character list
async function loadCharacters() {
  const res = await fetch("/api/characters");
  const chars = await res.json();
  const select = $("character");
  select.innerHTML = "";
  if (!chars.length) {
    const opt = document.createElement("option");
    opt.textContent = "No characters — create one →";
    opt.value = "";
    select.appendChild(opt);
  } else {
    for (const c of chars) {
      const opt = document.createElement("option");
      opt.value = c.slug;
      opt.textContent = c.name;
      select.appendChild(opt);
    }
  }
  renderCharRoster(chars);
}

// Manage existing characters (edit / delete) on the Create tab.
function renderCharRoster(chars) {
  const list = $("char-roster");
  if (!list) return;
  list.innerHTML = chars.length
    ? ""
    : '<div class="hint">No characters yet — fill the form below to create one.</div>';
  for (const c of chars) {
    const row = document.createElement("div");
    row.className = "row";
    row.style.cssText = "justify-content:space-between; align-items:center; margin-top:6px; gap:8px";
    const label = document.createElement("div");
    label.style.cssText = "flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap";
    label.innerHTML =
      `<span style="color:var(--text); font-size:14px">${escapeHtml(c.name)}</span>` +
      (c.concept ? ` <span class="hint">— ${escapeHtml(c.concept)}</span>` : "");
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "btn ghost";
    edit.textContent = "Edit";
    edit.style.flex = "0 0 auto";
    edit.addEventListener("click", () => editCharacter(c.slug));
    const dup = document.createElement("button");
    dup.type = "button";
    dup.className = "btn ghost";
    dup.textContent = "Duplicate";
    dup.style.flex = "0 0 auto";
    dup.addEventListener("click", () => duplicateCharacter(c.slug, c.name));
    const del = document.createElement("button");
    del.type = "button";
    del.className = "btn ghost";
    del.textContent = "Delete";
    del.style.flex = "0 0 auto";
    del.addEventListener("click", () => deleteCharacter(c.slug, c.name));
    row.append(label, edit, dup, del);
    list.appendChild(row);
  }
}

async function duplicateCharacter(slug, name) {
  try {
    const res = await fetch(`/api/characters/${slug}/duplicate`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      $("c-status").textContent = "⚠ " + (data.error || "Duplicate failed.");
      return;
    }
    $("c-status").textContent = `Duplicated "${name}" → "${data.name}". Edit it to rename or change its voice.`;
    await loadCharacters();
  } catch (err) {
    $("c-status").textContent = "⚠ " + err;
  }
}

async function deleteCharacter(slug, name) {
  if (!confirm(`Delete "${name}"? This removes the character. Past conversation memories are kept.`)) {
    return;
  }
  try {
    const res = await fetch("/api/characters/" + slug, { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      $("c-status").textContent = "⚠ " + (data.error || "Delete failed.");
      return;
    }
    if (editingSlug === slug) newCharacterForm(); // were editing it — reset the form
    $("c-status").textContent = `Deleted "${name}".`;
    await loadCharacters();
  } catch (err) {
    $("c-status").textContent = "⚠ " + err;
  }
}

// ============================================================ model list
async function loadModels() {
  const res = await fetch("/api/models");
  const data = await res.json();
  // Conversation model picker + the AI-draft model picker share the same list.
  for (const selId of ["model", "c-ai-model"]) {
    const select = $(selId);
    if (!select) continue;
    select.innerHTML = "";
    for (const m of data.models) {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.label;
      if (m.id === data.default) opt.selected = true;
      select.appendChild(opt);
    }
  }
}

// ============================================================ speaker profiles
async function loadProfiles() {
  const profs = await (await fetch("/api/profiles")).json();
  // Conversation dropdown
  const sel = $("profile");
  const cur = sel.value;
  sel.innerHTML = '<option value="">Default cadence</option>';
  for (const p of profs) {
    const o = document.createElement("option");
    o.value = p.slug;
    o.textContent = "🎚 " + p.name;
    sel.appendChild(o);
  }
  if (cur) sel.value = cur;
  // Train-tab list
  const list = $("train-list");
  list.innerHTML = profs.length ? "" : '<div class="hint">No profiles yet — record one above.</div>';
  for (const p of profs) {
    const row = document.createElement("div");
    row.className = "row";
    row.style.justifyContent = "space-between";
    row.style.marginTop = "6px";
    const label = document.createElement("span");
    label.textContent = `${p.name} — finishes after ${p.min_turn_silence}ms, waits up to ${p.max_turn_silence}ms`;
    label.style.fontSize = "13px";
    const del = document.createElement("button");
    del.className = "btn ghost";
    del.textContent = "Delete";
    del.onclick = async () => {
      await fetch("/api/profiles/" + p.slug, { method: "DELETE" });
      loadProfiles();
    };
    row.appendChild(label);
    row.appendChild(del);
    list.appendChild(row);
  }
}

// ============================================================ voice calibration
let calWs = null;
let calCtx = null;
let calNode = null;
let calStream = null;
let calActive = false;
let calBuf = new Float32Array(0);
let calResult = null;

// The wizard walks three kinds of speech so the profile sees the speaker's full
// pause range, not just their fluent baseline:
//   Part 1 — reading: smooth, well-formed cadence (the floor).
//   Part 2 — answering: spontaneous thinking-out-loud pauses.
//   Part 3 — drawled questions: the slow, dumbfounded "waaait… so… how do I…"
//            pattern. These long mid-question pauses are what gets people cut off
//            in a game, and nothing else here elicits them — so we direct the
//            speaker to really stretch them out. See orchestrator/cadence.py.
const TRAIN_PASSAGE =
  "The old road north hasn't been kind this winter. I left before dawn, when the frost " +
  "still held the ground, and walked until the light gave out. Somewhere past the second " +
  "bridge I lost the trail entirely — and, well, that's a story for another night. For now " +
  "I just need somewhere warm to sit and a moment to think about where I'm headed next.";

const TRAIN_STEPS = [
  { kind: "read", label: "Part 1 of 3 — read this aloud, naturally", prompt: TRAIN_PASSAGE },

  { kind: "answer", label: "Part 2 of 3 — answer out loud, take your time (1 of 4)",
    prompt: "To start — what did you do earlier today, before this?" },
  { kind: "answer", label: "Part 2 of 3 — answer out loud (2 of 4)",
    prompt: "Tell me about something you're looking forward to this week." },
  { kind: "answer", label: "Part 2 of 3 — answer out loud (3 of 4)",
    prompt: "Describe a place you really like. What's it like to be there?" },
  { kind: "answer", label: "Part 2 of 3 — answer out loud (4 of 4)",
    prompt: "Talk me through something you're trying to decide right now." },

  { kind: "drawl", label: "Part 3 of 3 — now ask these S-L-O-W-L-Y, like you're confused and thinking hard. Drag out every “…” (1 of 3)",
    prompt: "Waaait… so… how do I… actually get to the north pass from here?" },
  { kind: "drawl", label: "Part 3 of 3 — slow and unsure, really stretch the pauses (2 of 3)",
    prompt: "Hold on, let me think… what was… what did you say the price was again?" },
  { kind: "drawl", label: "Part 3 of 3 — slow and unsure, take long pauses between words (3 of 3)",
    prompt: "Umm… okay… so if I go left… no, wait… which way did you mean?" },
];

// trainStep: -1 idle | 0..N-1 index into TRAIN_STEPS
let trainStep = -1;
// Per-step voiced-time accounting for the "you've said enough" hint (questions
// only). Reset on every step; measured from the live mic level in onCalChunk.
let stepVoicedMs = 0;
let trainEnoughShown = false;
const ENOUGH_VOICED_MS = 5000; // ~5s of actual speech is plenty per question

function startCalibrationSession() {
  return new Promise((resolve, reject) => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    calWs = new WebSocket(`${proto}://${location.host}/ws/calibrate`);
    calWs.binaryType = "arraybuffer";
    calResult = null;
    calWs.onerror = () => reject(new Error("calibration socket error"));
    calWs.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer) return;
      const d = JSON.parse(e.data);
      if (d.type === "calibration_progress") {
        $("train-status").textContent = `🎙 Recording… (${d.samples} pauses measured)`;
      } else if (d.type === "calibration_result") {
        showCalibrationResult(d);
      } else if (d.type === "error") {
        $("train-status").textContent = "⚠ " + d.message;
        cancelTraining();
      }
    };
    calWs.onopen = async () => {
      try {
        calStream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
      } catch (err) {
        reject(new Error("Microphone access denied."));
        return;
      }
      calCtx = new (window.AudioContext || window.webkitAudioContext)();
      await calCtx.audioWorklet.addModule("/mic-capture.js?v=" + (window.__BUILD__ || APP_VERSION));
      const src = calCtx.createMediaStreamSource(calStream);
      calNode = new AudioWorkletNode(calCtx, "mic-capture");
      src.connect(calNode);
      const sink = calCtx.createGain();
      sink.gain.value = 0;
      calNode.connect(sink);
      sink.connect(calCtx.destination);
      calBuf = new Float32Array(0);
      calActive = true;
      calNode.port.onmessage = (e) => onCalChunk(e.data);
      calWs.send(JSON.stringify({ type: "mic_start" }));
      resolve();
    };
  });
}

// --- guided two-phase wizard: read a passage, then answer questions ---
async function beginTraining() {
  $("train-status").textContent = "Starting…";
  try {
    await startCalibrationSession();
  } catch (err) {
    $("train-status").textContent = "⚠ " + err.message;
    return;
  }
  trainStep = 0;
  $("train-idle").style.display = "none";
  $("train-result").style.display = "none";
  $("train-active").style.display = "block";
  renderTrainStep();
}

function renderTrainStep() {
  const step = TRAIN_STEPS[trainStep];
  if (!step) return;
  $("train-phase-label").textContent = step.label;
  $("train-prompt").textContent = step.prompt;
  $("train-next").textContent =
    trainStep >= TRAIN_STEPS.length - 1 ? "Finish & analyze" : "Next →";
  // Fresh "enough recorded" accounting for this step.
  stepVoicedMs = 0;
  trainEnoughShown = false;
  $("train-enough").style.display = "none";
}

function trainNext() {
  if (trainStep < 0) return;
  trainStep += 1;
  if (trainStep >= TRAIN_STEPS.length) finishTraining();
  else renderTrainStep();
}

function finishTraining() {
  trainStep = -1;
  $("train-active").style.display = "none";
  $("train-status").textContent = "Analyzing your cadence…";
  if (calWs && calWs.readyState === WebSocket.OPEN) {
    calWs.send(JSON.stringify({ type: "mic_stop" }));
  }
  stopCalibrationCapture(); // result arrives via onmessage
}

function cancelTraining() {
  trainStep = -1;
  if (calWs && calWs.readyState === WebSocket.OPEN) {
    calWs.send(JSON.stringify({ type: "mic_stop" }));
    calWs.close();
  }
  calWs = null;
  stopCalibrationCapture();
  $("train-active").style.display = "none";
  $("train-idle").style.display = "block";
  $("train-status").textContent = "Cancelled.";
}

function onCalChunk(frame) {
  if (!calActive || !calWs || calWs.readyState !== WebSocket.OPEN) return;

  // Live input meter + voice-activity timing, straight off the raw mic frame.
  let peak = 0;
  let sumSq = 0;
  for (let i = 0; i < frame.length; i++) {
    const s = frame[i];
    const a = s < 0 ? -s : s;
    if (a > peak) peak = a;
    sumSq += s * s;
  }
  const rms = Math.sqrt(sumSq / Math.max(1, frame.length));
  const fill = $("train-meter-fill");
  if (fill) fill.style.width = Math.min(100, Math.round(peak * 140)) + "%";

  // Count actual speech time on question steps so we can tell ramblers they're
  // done. VAD threshold sits above room noise but below normal speaking level.
  const step = TRAIN_STEPS[trainStep];
  if (step && step.kind === "answer" && !trainEnoughShown) {
    const frameMs = (frame.length / calCtx.sampleRate) * 1000;
    if (rms > 0.02) stepVoicedMs += frameMs;
    if (stepVoicedMs >= ENOUGH_VOICED_MS) {
      trainEnoughShown = true;
      $("train-enough").style.display = "block";
    }
  }

  const down =
    calCtx.sampleRate === STREAM_RATE
      ? frame
      : resampleLinear(frame, calCtx.sampleRate, STREAM_RATE);
  const merged = new Float32Array(calBuf.length + down.length);
  merged.set(calBuf);
  merged.set(down, calBuf.length);
  calBuf = merged;
  const CH = 1600;
  while (calBuf.length >= CH) {
    const chunk = calBuf.subarray(0, CH);
    const i16 = new Int16Array(CH);
    for (let i = 0; i < CH; i++) {
      const v = Math.max(-1, Math.min(1, chunk[i]));
      i16[i] = v < 0 ? v * 32768 : v * 32767;
    }
    calWs.send(i16.buffer);
    calBuf = calBuf.slice(CH);
  }
}

function stopCalibrationCapture() {
  calActive = false;
  if (calStream) calStream.getTracks().forEach((t) => t.stop());
  if (calCtx) calCtx.close().catch(() => {});
  calCtx = null;
  calNode = null;
  calStream = null;
  calBuf = new Float32Array(0);
  const fill = $("train-meter-fill");
  if (fill) fill.style.width = "0%";
}

function showCalibrationResult(d) {
  calResult = d;
  $("train-status").textContent = "Done — name it and save.";
  $("train-result").style.display = "block";
  $("train-result-info").innerHTML =
    `<div class="bar"><span class="name">Replies after you pause</span><span class="val">${d.min_turn_silence} ms</span></div>` +
    `<div class="bar"><span class="name">Waits through pauses up to</span><span class="val">${d.max_turn_silence} ms</span></div>` +
    `<div class="bar"><span class="name">Pauses measured / median gap</span><span class="val">${d.samples} / ${d.median_gap_ms} ms</span></div>`;
  if (calWs) {
    calWs.close();
    calWs = null;
  }
}

async function saveProfile() {
  const name = $("train-name").value.trim();
  if (!name || !calResult) {
    $("train-save-status").textContent = "Record + name it first.";
    return;
  }
  const res = await fetch("/api/profiles", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      name,
      min_turn_silence: calResult.min_turn_silence,
      max_turn_silence: calResult.max_turn_silence,
      stats: {
        samples: calResult.samples,
        median_gap_ms: calResult.median_gap_ms,
        p90_pause_ms: calResult.p90_pause_ms,
      },
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    $("train-save-status").textContent = "⚠ " + (data.error || "Failed.");
    return;
  }
  $("train-save-status").textContent = `✓ Saved "${data.name}". Pick it in Conversation.`;
  $("train-result").style.display = "none";
  $("train-idle").style.display = "block";
  await loadProfiles();
}

// ============================================================ voice design mode
let designedVoiceId = null;

// Voice sources differ by provider: Cartesia can't design from text, so it gets
// a browsable library + clone; Inworld keeps design + clone + preset-id.
const VOICE_MODES = {
  cartesia: [
    { value: "library", label: "Browse the Cartesia voice library" },
    { value: "clone", label: "Clone a voice — record a sample" },
  ],
  inworld: [
    { value: "design", label: "Design a voice — describe it in words" },
    { value: "clone", label: "Clone a voice — record a sample" },
    { value: "preset", label: "Preset voice id" },
  ],
  elevenlabs: [
    { value: "library", label: "Browse ElevenLabs voices" },
    { value: "design", label: "Design a voice — describe it in words" },
    { value: "clone", label: "Clone a voice — record a sample" },
    { value: "preset", label: "Paste an ElevenLabs voice id" },
  ],
};

let libraryVoiceId = null; // selected library voice (Cartesia or ElevenLabs)
let libLoaded = false; // whether the library list has been fetched this view
let libProvider = "cartesia"; // which provider the loaded list belongs to

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// Rebuild the voice-mode dropdown for the current provider, keeping the prior
// selection if it's still valid (else falling back to the provider's first mode).
function populateVoiceModes(preferred) {
  const provider = $("c-provider").value;
  const modes = VOICE_MODES[provider] || VOICE_MODES.inworld;
  const sel = $("c-voice-mode");
  const want = preferred || sel.value;
  sel.innerHTML = "";
  for (const m of modes) {
    const o = document.createElement("option");
    o.value = m.value;
    o.textContent = m.label;
    sel.appendChild(o);
  }
  sel.value = modes.some((m) => m.value === want) ? want : modes[0].value;
  switchVoiceMode();
}

function switchVoiceMode() {
  const mode = $("c-voice-mode").value;
  $("mode-design").style.display = mode === "design" ? "block" : "none";
  $("mode-clone").style.display = mode === "clone" ? "block" : "none";
  $("mode-preset").style.display = mode === "preset" ? "block" : "none";
  $("mode-library").style.display = mode === "library" ? "block" : "none";
  if (mode === "library" && !libLoaded) loadLibraryVoices();
}

async function loadLibraryVoices() {
  const list = $("lib-list");
  list.innerHTML = '<div class="hint" style="padding:10px">Loading voices…</div>';
  libLoaded = true;
  libProvider = $("c-provider").value;
  try {
    const params = new URLSearchParams({ provider: libProvider });
    const g = $("lib-gender").value;
    const q = $("lib-search").value.trim();
    if (g) params.set("gender", g);
    if (q) params.set("q", q);
    const res = await fetch("/api/voices?" + params.toString());
    const data = await res.json();
    if (!res.ok || data.error) {
      list.innerHTML = `<div class="hint" style="padding:10px">⚠ ${escapeHtml(data.error || "Failed to load.")}</div>`;
      return;
    }
    const voices = data.voices || [];
    if (!voices.length) {
      list.innerHTML = '<div class="hint" style="padding:10px">No voices match — widen the filter.</div>';
      return;
    }
    list.innerHTML = "";
    for (const v of voices) {
      const row = document.createElement("div");
      row.className = "lib-row";
      row.dataset.id = v.id;
      row.style.cssText =
        "display:flex; align-items:center; gap:10px; padding:9px 12px; border-bottom:1px solid var(--border); cursor:pointer";
      const play = document.createElement("button");
      play.type = "button";
      play.className = "btn ghost";
      play.textContent = "▶";
      play.title = "Preview";
      play.style.cssText = "flex:0 0 auto; padding:4px 11px; min-width:36px";
      play.addEventListener("click", (e) => {
        e.stopPropagation();
        previewLibraryVoice(v, play);
      });
      const meta = document.createElement("div");
      meta.style.cssText = "flex:1; min-width:0";
      meta.innerHTML =
        `<div style="color:var(--text); font-size:14px">${escapeHtml(v.name)}</div>` +
        `<div class="hint" style="margin:2px 0 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">${escapeHtml(v.description)}</div>`;
      const tag = document.createElement("span");
      tag.className = "status";
      tag.style.cssText = "margin:0; flex:0 0 auto; font-size:11px";
      tag.textContent = (v.gender || "").replace("gender_neutral", "neutral");
      row.append(play, meta, tag);
      row.addEventListener("click", () => selectLibraryVoice(v));
      list.appendChild(row);
    }
    highlightSelectedRow();
  } catch (err) {
    list.innerHTML = `<div class="hint" style="padding:10px">⚠ ${escapeHtml(err)}</div>`;
  }
}

function selectLibraryVoice(v) {
  libraryVoiceId = v.id;
  $("lib-selected").innerHTML = `✓ Selected: <strong style="color:var(--accent-2)">${escapeHtml(v.name)}</strong>`;
  highlightSelectedRow();
}

function highlightSelectedRow() {
  document.querySelectorAll("#lib-list .lib-row").forEach((r) => {
    r.style.background = r.dataset.id === libraryVoiceId ? "var(--panel-2)" : "";
  });
}

let previewBtn = null; // the play button whose audio is currently active

function resetPreviewBtn() {
  if (previewBtn) previewBtn.textContent = "▶";
  previewBtn = null;
}

function previewLibraryVoice(v, btn) {
  const a = $("lib-preview");
  // Clicking the active row again = toggle off.
  if (previewBtn === btn) {
    a.pause();
    resetPreviewBtn();
    return;
  }
  resetPreviewBtn(); // revert whatever was playing before
  previewBtn = btn;
  btn.textContent = "⏳"; // loading
  if (libProvider === "elevenlabs") {
    // ElevenLabs preview URLs are public — play them directly.
    if (!v.preview_url) {
      resetPreviewBtn();
      return;
    }
    a.src = v.preview_url;
  } else {
    // Cartesia: the raw preview URL is auth-gated, so go through our proxy (which
    // also synthesizes a sample when a voice has no stored preview).
    const params = new URLSearchParams({ voice_id: v.id });
    if (v.preview_url) params.set("url", v.preview_url);
    a.src = "/api/voices/preview?" + params.toString();
  }
  a.play().catch(() => {}); // AbortError on rapid switching is harmless
}

async function describeVoiceFromCharacter() {
  const card = buildCardFromForm();
  if (!card.name && !card.concept && !card.temperament) {
    $("c-describe-status").textContent = "Fill in (or AI-draft) the character first.";
    return;
  }
  $("c-describe-status").textContent = "Writing a voice description…";
  $("c-describe").disabled = true;
  try {
    const res = await fetch("/api/voice/describe", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ card, model: $("c-ai-model").value, provider: $("c-provider").value }),
    });
    const data = await res.json();
    if (!res.ok) {
      $("c-describe-status").textContent = "⚠ " + (data.error || "Failed.");
      return;
    }
    $("c-design-desc").value = data.description;
    designedVoiceId = null; // any prior preview no longer matches the new description
    $("c-design-playback").style.display = "none";
    $("c-describe-status").textContent = `✓ ${data.description.length} chars — tweak it, then Generate preview.`;
  } catch (err) {
    $("c-describe-status").textContent = "⚠ " + err;
  } finally {
    $("c-describe").disabled = false;
  }
}

async function generateDesignPreview() {
  const provider = $("c-provider").value;
  const desc = $("c-design-desc").value.trim();
  // Inworld caps the description at 30–250 chars; ElevenLabs is freer.
  if (provider === "inworld" && (desc.length < 30 || desc.length > 250)) {
    $("c-design-status").textContent = `Description must be 30–250 chars (now ${desc.length}).`;
    return;
  }
  if (desc.length < 15) {
    $("c-design-status").textContent = "Describe the voice in a bit more detail first.";
    return;
  }
  designedVoiceId = null;
  $("c-design-status").textContent = "Designing voice…";
  $("c-design-generate").disabled = true;
  try {
    const form = new FormData();
    form.append("description", desc);
    form.append("provider", provider);
    const res = await fetch("/api/voice/design", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) {
      $("c-design-status").textContent = "⚠ " + (data.error || "Design failed.");
      return;
    }
    designedVoiceId = data.voice_id;
    const pb = $("c-design-playback");
    pb.src = `data:${data.mime};base64,${data.audio_b64}`;
    pb.style.display = "block";
    pb.play().catch(() => {});
    $("c-design-status").textContent = "Preview ready — listen, then Create (or tweak & regenerate).";
  } catch (err) {
    $("c-design-status").textContent = "⚠ " + err;
  } finally {
    $("c-design-generate").disabled = false;
  }
}

// ============================================================ create character
let sampleRecorder = null;
let sampleChunks = [];
let sampleBlob = null;
let sampleRecording = false;
let meterCtx = null;
let meterRAF = null;
let meterTimer = null;
let recordStartMs = 0;

function stopMeter() {
  if (meterRAF) { cancelAnimationFrame(meterRAF); meterRAF = null; }
  if (meterTimer) { clearInterval(meterTimer); meterTimer = null; }
  if (meterCtx) { meterCtx.close().catch(() => {}); meterCtx = null; }
  $("c-meter").style.display = "none";
  $("c-meter-fill").style.width = "0%";
}

async function toggleSampleRecord() {
  if (!sampleRecording) {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      $("c-record-status").textContent = "Microphone access denied.";
      return;
    }

    // Live input-level meter so you can SEE the mic capturing.
    meterCtx = new (window.AudioContext || window.webkitAudioContext)();
    const src = meterCtx.createMediaStreamSource(stream);
    const analyser = meterCtx.createAnalyser();
    analyser.fftSize = 512;
    src.connect(analyser);
    const buf = new Uint8Array(analyser.fftSize);
    $("c-meter").style.display = "block";
    const draw = () => {
      analyser.getByteTimeDomainData(buf);
      let peak = 0;
      for (let i = 0; i < buf.length; i++) {
        const v = Math.abs(buf[i] - 128);
        if (v > peak) peak = v;
      }
      $("c-meter-fill").style.width = Math.min(100, Math.round((peak / 128) * 180)) + "%";
      meterRAF = requestAnimationFrame(draw);
    };
    draw();

    // Recorder
    sampleRecorder = new MediaRecorder(stream);
    sampleChunks = [];
    sampleRecorder.ondataavailable = (e) => e.data.size && sampleChunks.push(e.data);
    sampleRecorder.onstop = () => {
      sampleBlob = new Blob(sampleChunks, { type: sampleRecorder.mimeType });
      const secs = ((performance.now() - recordStartMs) / 1000).toFixed(1);
      $("c-record-status").textContent =
        `Sample recorded: ${secs}s, ${Math.round(sampleBlob.size / 1024)} KB. Play it back to check ↓`;
      const pb = $("c-playback");
      pb.src = URL.createObjectURL(sampleBlob);
      pb.style.display = "block";
      stream.getTracks().forEach((t) => t.stop());
      stopMeter();
    };
    sampleRecorder.start();
    sampleRecording = true;
    recordStartMs = performance.now();
    $("c-record").textContent = "■ Stop recording";
    $("c-playback").style.display = "none";
    meterTimer = setInterval(() => {
      const s = Math.floor((performance.now() - recordStartMs) / 1000);
      $("c-record-status").textContent = `● Recording… ${s}s (aim for 10–15s)`;
    }, 250);
  } else {
    sampleRecorder.stop();
    sampleRecording = false;
    $("c-record").textContent = "● Record ~12s sample";
  }
}

// --- repeaters for the two-field list sections (secrets, relationships) ---
function makeRepeaterRow(listId, fields) {
  const row = document.createElement("div");
  row.className = "rep-row";
  for (const f of fields) {
    const inp = document.createElement("input");
    inp.type = "text";
    inp.className = f.cls;
    inp.placeholder = f.placeholder;
    inp.style.flex = f.flex;
    inp.value = f.value || "";
    row.appendChild(inp);
  }
  const del = document.createElement("button");
  del.type = "button";
  del.className = "btn ghost";
  del.textContent = "✕";
  del.style.flex = "0 0 auto";
  del.addEventListener("click", () => row.remove());
  row.appendChild(del);
  $(listId).appendChild(row);
}

function addSecretRow(text = "", reveal = "") {
  makeRepeaterRow("secrets-list", [
    { cls: "sec-text", placeholder: "The secret they hold back", flex: "2", value: text },
    { cls: "sec-reveal", placeholder: "Reveal only when… (optional)", flex: "2", value: reveal },
  ]);
}

function addRelRow(who = "", how = "") {
  makeRepeaterRow("rel-list", [
    { cls: "rel-who", placeholder: "Who (e.g. the player, Bram)", flex: "1", value: who },
    { cls: "rel-how", placeholder: "How they regard them", flex: "2", value: how },
  ]);
}

function linesToList(id) {
  return $(id).value.split("\n").map((s) => s.trim()).filter(Boolean);
}

function gatherSecrets() {
  return [...document.querySelectorAll("#secrets-list .rep-row")]
    .map((r) => ({
      text: r.querySelector(".sec-text").value.trim(),
      reveal_when: r.querySelector(".sec-reveal").value.trim(),
    }))
    .filter((s) => s.text);
}

function gatherRelationships() {
  return [...document.querySelectorAll("#rel-list .rep-row")]
    .map((r) => ({
      who: r.querySelector(".rel-who").value.trim(),
      how: r.querySelector(".rel-how").value.trim(),
    }))
    .filter((r) => r.who && r.how);
}

// Collect every authored field into the structured card (no voice resolution).
function buildCardFromForm() {
  return {
    name: $("c-name").value.trim(),
    concept: $("c-concept").value.trim(),
    age: $("c-age").value.trim(),
    role: $("c-role").value.trim(),
    pronouns: $("c-pronouns").value.trim(),
    greeting: $("c-greeting").value.trim(),
    tts_provider: $("c-provider").value,
    temperament: $("c-temperament").value.trim(),
    speech_style: linesToList("c-speech"),
    backstory: $("c-backstory").value.trim(),
    knows: linesToList("c-knows"),
    doesnt_know: linesToList("c-doesnt"),
    goals: linesToList("c-goals"),
    secrets: gatherSecrets(),
    boundaries: linesToList("c-boundaries"),
    relationships: gatherRelationships(),
    disposition: $("c-disposition").value.trim(),
    sample_lines: linesToList("c-samples"),
    system_prompt: $("c-raw").value.trim(),
  };
}

// Populate the whole form from a card (used by both Edit and AI-draft).
function fillFormFromCard(c) {
  $("c-name").value = c.name || "";
  $("c-concept").value = c.concept || "";
  $("c-age").value = c.age || "";
  $("c-role").value = c.role || "";
  $("c-pronouns").value = c.pronouns || "";
  $("c-greeting").value = c.greeting || "";
  $("c-temperament").value = c.temperament || "";
  $("c-speech").value = (c.speech_style || []).join("\n");
  $("c-backstory").value = c.backstory || "";
  $("c-knows").value = (c.knows || []).join("\n");
  $("c-doesnt").value = (c.doesnt_know || []).join("\n");
  $("c-goals").value = (c.goals || []).join("\n");
  $("c-boundaries").value = (c.boundaries || []).join("\n");
  $("c-disposition").value = c.disposition || "";
  $("c-samples").value = (c.sample_lines || []).join("\n");
  $("c-raw").value = c.system_prompt || "";
  $("secrets-list").innerHTML = "";
  (c.secrets || []).forEach((s) => addSecretRow(s.text, s.reveal_when));
  $("rel-list").innerHTML = "";
  Object.entries(c.relationships || {}).forEach(([who, how]) => addRelRow(who, how));
}

async function draftCharacter() {
  const concept = $("c-ai-concept").value.trim();
  if (!concept) {
    $("c-ai-status").textContent = "Type a one-line concept first.";
    return;
  }
  $("c-ai-status").textContent = "Drafting a full character… this can take 20–30s.";
  $("c-ai-draft").disabled = true;
  try {
    const res = await fetch("/api/characters/draft", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ concept, model: $("c-ai-model").value }),
    });
    const data = await res.json();
    if (!res.ok) {
      $("c-ai-status").textContent = "⚠ " + (data.error || "Draft failed.");
      return;
    }
    fillFormFromCard(data.card);
    $("c-ai-status").textContent = "✓ Drafted — review every field, then Preview or Create. Pick a voice above.";
  } catch (err) {
    $("c-ai-status").textContent = "⚠ " + err;
  } finally {
    $("c-ai-draft").disabled = false;
  }
}

async function previewPrompt() {
  const pre = $("prompt-preview");
  pre.style.display = "block";
  pre.textContent = "Compiling…";
  try {
    const form = new FormData();
    form.append("card", JSON.stringify(buildCardFromForm()));
    const res = await fetch("/api/characters/preview-prompt", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) {
      pre.textContent = "⚠ " + (data.error || "Failed.");
      return;
    }
    pre.textContent =
      data.prompt && data.prompt.trim()
        ? data.prompt
        : "(empty — fill in some fields above, or add a raw override)";
  } catch (err) {
    pre.textContent = "⚠ " + err;
  }
}

async function createCharacter() {
  const name = $("c-name").value.trim();
  if (!name) {
    $("c-status").textContent = "Name is required.";
    return;
  }
  const card = buildCardFromForm();

  // Resolve the voice source (clone uploads a file; the rest ride in the card).
  let sampleFile = null;
  const mode = $("c-voice-mode").value;
  if (mode === "design") {
    if (!designedVoiceId) {
      $("c-status").textContent = "Generate a voice preview first.";
      return;
    }
    card.design_voice_id = designedVoiceId;
    card.design_description = $("c-design-desc").value.trim(); // ElevenLabs create needs it
  } else if (mode === "clone") {
    if (!sampleBlob) {
      $("c-status").textContent = "Record a voice sample first.";
      return;
    }
    sampleFile = sampleBlob;
  } else if (mode === "library") {
    if (!libraryVoiceId) {
      $("c-status").textContent = "Pick a voice from the library first.";
      return;
    }
    card.voice_id = libraryVoiceId;
  } else {
    const presetVoice = $("c-voice-id").value.trim();
    if (!presetVoice) {
      $("c-status").textContent = "Enter a preset voice_id.";
      return;
    }
    card.voice_id = presetVoice;
  }

  const form = new FormData();
  form.append("card", JSON.stringify(card));
  if (sampleFile) form.append("sample", sampleFile, "sample.webm");

  const url = editingSlug ? `/api/characters/${editingSlug}` : "/api/characters";
  $("c-status").textContent = editingSlug ? "Saving…" : "Creating (cloning if needed)…";
  $("c-create").disabled = true;
  try {
    const res = await fetch(url, { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) {
      $("c-status").textContent = "⚠ " + (data.error || "Failed.");
    } else if (editingSlug) {
      $("c-status").textContent = `✓ Saved "${data.name}". Reconnect in Conversation to hear changes.`;
      await loadCharacters();
    } else {
      $("c-status").textContent = `✓ Created "${data.name}". Switch to Conversation and refresh.`;
      await loadCharacters();
    }
  } catch (err) {
    $("c-status").textContent = "⚠ " + err;
  } finally {
    $("c-create").disabled = false;
  }
}

// ============================================================ edit / new
let editingSlug = null;

async function editCharacter(slug) {
  if (!slug) {
    setStatus("Pick a character to edit.");
    return;
  }
  const res = await fetch(`/api/characters/${slug}/full`);
  if (!res.ok) {
    setStatus("Couldn't load that character to edit.");
    return;
  }
  const c = await res.json();
  editingSlug = slug;
  fillFormFromCard(c);
  $("c-provider").value = c.tts_provider || "cartesia";
  // Pre-load the current voice so saving keeps it unless you pick/record a new
  // one. Cartesia → library mode (current id retained + highlighted); Inworld →
  // preset mode showing the id.
  libLoaded = false;
  if ($("c-provider").value === "cartesia") {
    libraryVoiceId = c.voice_id;
    populateVoiceModes("library");
    $("lib-selected").innerHTML =
      `Current voice: <strong>${escapeHtml(c.voice_id)}</strong> — pick another below to change it.`;
  } else {
    $("c-voice-id").value = c.voice_id;
    populateVoiceModes("preset");
  }
  $("c-create").textContent = "Save changes";
  $("c-mode-label").textContent = `Editing "${c.name}"`;
  $("c-new").style.display = "inline-block";
  $("c-status").textContent = "";
  document.querySelector('.tab[data-view="create"]').click();
}

function newCharacterForm() {
  editingSlug = null;
  [
    "c-name", "c-concept", "c-age", "c-role", "c-pronouns", "c-greeting",
    "c-temperament", "c-speech", "c-backstory", "c-knows", "c-doesnt",
    "c-goals", "c-boundaries", "c-disposition", "c-samples", "c-raw",
    "c-voice-id", "c-ai-concept",
  ].forEach((id) => $(id) && ($(id).value = ""));
  $("prompt-preview").style.display = "none";
  $("secrets-list").innerHTML = "";
  $("rel-list").innerHTML = "";
  designedVoiceId = null;
  libraryVoiceId = null;
  $("lib-selected").textContent = "";
  highlightSelectedRow(); // clear any leftover row highlight
  $("c-design-playback").style.display = "none";
  populateVoiceModes(); // back to the current provider's default mode
  $("c-create").textContent = "Create character";
  $("c-mode-label").textContent = "Creating a new character";
  $("c-new").style.display = "none";
  $("c-status").textContent = "";
}

// ============================================================ wire up events
$("connect").addEventListener("click", connect);
$("disconnect").addEventListener("click", disconnect);
$("refresh").addEventListener("click", loadCharacters);
$("talk").addEventListener("click", toggleTalk);
$("send").addEventListener("click", sendText);
$("text-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendText();
});
$("c-record").addEventListener("click", toggleSampleRecord);
$("c-create").addEventListener("click", createCharacter);
$("c-voice-mode").addEventListener("change", switchVoiceMode);
$("c-provider").addEventListener("change", () => {
  libLoaded = false; // re-fetch the library on next entry to library mode
  // Voice ids aren't portable across providers — clear the current pick so you
  // can't accidentally save a Cartesia voice on an ElevenLabs character.
  libraryVoiceId = null;
  $("c-voice-id").value = "";
  $("lib-selected").textContent = "";
  highlightSelectedRow();
  populateVoiceModes();
});
$("lib-load").addEventListener("click", loadLibraryVoices);
$("lib-gender").addEventListener("change", loadLibraryVoices);
$("lib-search").addEventListener("keydown", (e) => {
  if (e.key === "Enter") loadLibraryVoices();
});
const _libPreview = $("lib-preview");
_libPreview.addEventListener("playing", () => {
  if (previewBtn) previewBtn.textContent = "⏸";
});
_libPreview.addEventListener("ended", resetPreviewBtn);
_libPreview.addEventListener("error", resetPreviewBtn);
$("c-design-generate").addEventListener("click", generateDesignPreview);
$("c-describe").addEventListener("click", describeVoiceFromCharacter);
$("add-secret").addEventListener("click", () => addSecretRow());
$("add-rel").addEventListener("click", () => addRelRow());
$("c-preview").addEventListener("click", previewPrompt);
$("c-ai-draft").addEventListener("click", draftCharacter);
$("c-ai-concept").addEventListener("keydown", (e) => {
  if (e.key === "Enter") draftCharacter();
});
$("edit-char").addEventListener("click", () => editCharacter($("character").value));
$("c-new").addEventListener("click", newCharacterForm);
$("train-begin").addEventListener("click", beginTraining);
$("train-next").addEventListener("click", trainNext);
$("train-cancel").addEventListener("click", cancelTraining);
$("train-save").addEventListener("click", saveProfile);
$("c-design-desc").addEventListener("input", () => {
  designedVoiceId = null;
  $("c-design-playback").style.display = "none";
});

const buildEl = $("build");
if (buildEl) {
  buildEl.textContent =
    "js " + APP_VERSION + (window.__BUILD__ ? " · srv " + window.__BUILD__ : "");
}
console.log("[AI Character Engine] app.js", APP_VERSION, "| server build", window.__BUILD__);

populateVoiceModes();
loadCharacters();
loadModels();
loadProfiles();
