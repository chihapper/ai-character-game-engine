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

const SAMPLE_RATE = 24000;
const PLAYBACK_PRIME = 0.12; // seconds of jitter cushion before playback starts

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
// A single AudioContext, with a running "next start time" so frames play
// gaplessly back-to-back as they stream in.
let audioCtx = null;
let nextStartTime = 0;
let pcmCarry = new Uint8Array(0); // holds a trailing odd byte across frames

function ensureAudio() {
  if (!audioCtx) {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    try {
      // Match the stream's sample rate so each frame plays natively. A context
      // running at a different rate (commonly 48 kHz) resamples every buffer
      // independently, producing a click at each ~0.5 s buffer boundary.
      audioCtx = new Ctor({ sampleRate: SAMPLE_RATE });
    } catch (e) {
      audioCtx = new Ctor(); // browser refused the explicit rate; fall back
    }
  }
  if (audioCtx.state === "suspended") audioCtx.resume();
}

function resetPlaybackClock() {
  pcmCarry = new Uint8Array(0);
  if (!audioCtx) {
    nextStartTime = 0;
    return;
  }
  const start = audioCtx.currentTime + 0.04;
  // Prepend a short silent pad. After sitting idle between responses the
  // AudioContext drops its first few output samples when it restarts; letting it
  // eat this silence (instead of the first word) fixes the clipped-first-word.
  const padSamples = Math.round(SAMPLE_RATE * 0.12);
  const pad = audioCtx.createBuffer(1, padSamples, SAMPLE_RATE);
  const src = audioCtx.createBufferSource();
  src.buffer = pad;
  src.connect(audioCtx.destination);
  src.start(start);
  nextStartTime = start + pad.duration;
}

function playPcmFrame(arrayBuffer) {
  ensureAudio();
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
  const f32 = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) f32[i] = samples[i] / 32768;

  const buf = audioCtx.createBuffer(1, f32.length, SAMPLE_RATE);
  buf.getChannelData(0).set(f32);
  const src = audioCtx.createBufferSource();
  src.buffer = buf;
  src.connect(audioCtx.destination);

  const now = audioCtx.currentTime;
  if (nextStartTime < now) nextStartTime = now + PLAYBACK_PRIME; // underran — re-cushion
  src.start(nextStartTime);
  nextStartTime += buf.duration;
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
}

function connect() {
  const slug = $("character").value;
  if (!slug) {
    setStatus("Pick a character first.");
    return;
  }
  ensureAudio(); // create the AudioContext from a user gesture so playback is allowed
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const model = $("model").value;
  ws = new WebSocket(
    `${proto}://${location.host}/ws?character=${encodeURIComponent(slug)}&model=${encodeURIComponent(model)}`,
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
      if (msg.model) setStatus(`Connected to ${currentCharacterName} · ${msg.model}`);
      break;
    case "transcript":
      addMessage("user", msg.text);
      liveAssistantEl = null;
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
// Click-to-talk: click to start recording, click again to stop and send.
let mediaRecorder = null;
let recordedChunks = [];
let isRecording = false;

async function getRecorder() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  return new MediaRecorder(stream);
}

async function toggleTalk() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
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
        ws.send(buf); // binary frame = recorded utterance
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
    $("talk").textContent = "🎙 Hold to talk (or click to start/stop)";
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

  $("c-status").textContent = "Creating (cloning voice if needed)…";
  $("c-create").disabled = true;
  try {
    const res = await fetch("/api/characters", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) {
      $("c-status").textContent = "⚠ " + (data.error || "Failed to create.");
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
$("c-design-desc").addEventListener("input", () => {
  designedVoiceId = null;
  $("c-design-playback").style.display = "none";
});

switchVoiceMode();
loadCharacters();
loadModels();
