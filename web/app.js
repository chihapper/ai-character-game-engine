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
const APP_VERSION = "2026-06-24-train2-6";
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
  ws = new WebSocket(
    `${proto}://${location.host}/ws?character=${encodeURIComponent(slug)}` +
      `&model=${encodeURIComponent(model)}&profile=${encodeURIComponent(profile)}`,
  );
  ws.binaryType = "arraybuffer";

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
      break;
    case "assistant_delta":
      if (!liveAssistantEl) liveAssistantEl = addMessage("assistant", "");
      liveAssistantEl.textContent += msg.text;
      log.scrollTop = log.scrollHeight;
      break;
    case "assistant_done":
      if (liveAssistantEl) liveAssistantEl.textContent = msg.text;
      else addMessage("assistant", msg.text);
      liveAssistantEl = null;
      if (isStreaming) setTalkState("idle"); // ready for the next turn
      break;
    case "audio_start":
      resetPlaybackClock();
      break;
    case "audio_end":
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
    return;
  }
  for (const c of chars) {
    const opt = document.createElement("option");
    opt.value = c.slug;
    opt.textContent = c.name;
    select.appendChild(opt);
  }
}

// ============================================================ model list
async function loadModels() {
  const res = await fetch("/api/models");
  const data = await res.json();
  const select = $("model");
  select.innerHTML = "";
  for (const m of data.models) {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.label;
    if (m.id === data.default) opt.selected = true;
    select.appendChild(opt);
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

const TRAIN_PASSAGE =
  "The old road north hasn't been kind this winter. I left before dawn, when the frost " +
  "still held the ground, and walked until the light gave out. Somewhere past the second " +
  "bridge I lost the trail entirely — and, well, that's a story for another night. For now " +
  "I just need somewhere warm to sit and a moment to think about where I'm headed next.";

const TRAIN_QUESTIONS = [
  "To start — what did you do earlier today, before this?",
  "Tell me about something you're looking forward to this week.",
  "Describe a place you really like. What's it like to be there?",
  "If you had a free afternoon tomorrow, how would you spend it?",
  "Last one — talk me through something you're trying to decide right now.",
];

// trainStep: -1 idle | 0 reading | 1..N answering question N
let trainStep = -1;

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
  if (trainStep === 0) {
    $("train-phase-label").textContent = "Part 1 of 2 — read this aloud, naturally";
    $("train-prompt").textContent = TRAIN_PASSAGE;
    $("train-next").textContent = "Done reading — start questions →";
  } else {
    const n = trainStep;
    $("train-phase-label").textContent =
      `Part 2 of 2 — question ${n} of ${TRAIN_QUESTIONS.length} (answer out loud, take your time)`;
    $("train-prompt").textContent = TRAIN_QUESTIONS[n - 1];
    $("train-next").textContent =
      n >= TRAIN_QUESTIONS.length ? "Finish & analyze" : "Next question →";
  }
}

function trainNext() {
  if (trainStep < 0) return;
  trainStep += 1;
  if (trainStep > TRAIN_QUESTIONS.length) finishTraining();
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
        p85_pause_ms: calResult.p85_pause_ms,
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

function switchVoiceMode() {
  const mode = $("c-voice-mode").value;
  $("mode-design").style.display = mode === "design" ? "block" : "none";
  $("mode-clone").style.display = mode === "clone" ? "block" : "none";
  $("mode-preset").style.display = mode === "preset" ? "block" : "none";
}

async function generateDesignPreview() {
  const desc = $("c-design-desc").value.trim();
  if (desc.length < 30 || desc.length > 250) {
    $("c-design-status").textContent = `Description must be 30–250 chars (now ${desc.length}).`;
    return;
  }
  designedVoiceId = null;
  $("c-design-status").textContent = "Designing voice…";
  $("c-design-generate").disabled = true;
  try {
    const form = new FormData();
    form.append("description", desc);
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

async function createCharacter() {
  const name = $("c-name").value.trim();
  const prompt = $("c-prompt").value.trim();
  if (!name || !prompt) {
    $("c-status").textContent = "Name and personality are required.";
    return;
  }
  const form = new FormData();
  form.append("name", name);
  form.append("system_prompt", prompt);
  form.append("greeting", $("c-greeting").value.trim());
  form.append("tts_provider", $("c-provider").value);
  const mode = $("c-voice-mode").value;
  if (mode === "design") {
    if (!designedVoiceId) {
      $("c-status").textContent = "Generate a voice preview first.";
      return;
    }
    form.append("design_voice_id", designedVoiceId);
  } else if (mode === "clone") {
    if (!sampleBlob) {
      $("c-status").textContent = "Record a voice sample first.";
      return;
    }
    form.append("sample", sampleBlob, "sample.webm");
  } else {
    const presetVoice = $("c-voice-id").value.trim();
    if (!presetVoice) {
      $("c-status").textContent = "Enter a preset voice_id.";
      return;
    }
    form.append("voice_id", presetVoice);
  }

  const url = editingSlug ? `/api/characters/${editingSlug}` : "/api/characters";
  $("c-status").textContent = editingSlug ? "Saving…" : "Creating (cloning/designing if needed)…";
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
  $("c-name").value = c.name;
  $("c-prompt").value = c.system_prompt;
  $("c-greeting").value = c.greeting;
  $("c-provider").value = c.tts_provider || "inworld";
  // Default to Preset mode showing the current voice id, so saving keeps the
  // existing voice unless you switch to Design/Clone to replace it.
  $("c-voice-mode").value = "preset";
  $("c-voice-id").value = c.voice_id;
  switchVoiceMode();
  $("c-create").textContent = "Save changes";
  $("c-mode-label").textContent = `Editing "${c.name}"`;
  $("c-new").style.display = "inline-block";
  $("c-status").textContent = "";
  document.querySelector('.tab[data-view="create"]').click();
}

function newCharacterForm() {
  editingSlug = null;
  ["c-name", "c-prompt", "c-greeting", "c-voice-id"].forEach((id) => ($(id).value = ""));
  designedVoiceId = null;
  $("c-design-playback").style.display = "none";
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
$("c-design-generate").addEventListener("click", generateDesignPreview);
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

switchVoiceMode();
loadCharacters();
loadModels();
loadProfiles();
