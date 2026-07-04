// The Ferry's Last Crossing — play view client. Drives game.web (/api/game) and renders the story.
const $ = (id) => document.getElementById(id);
const S = { gid: null, roster: [], target: "__room", mode: "speak", busy: false, ended: false,
            voice: true, audio: null, playhead: 0, voiceQueue: Promise.resolve() };

// ---- voice: streaming PCM playback (starts at FIRST chunk, not full render) ----------------
async function speakEvent(slug, text) {
  if (!S.voice || !S.audio || !slug) return;
  try {
    const r = await fetch(`/api/game/${S.gid}/voice`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slug, text }),
    });
    if (!r.ok || !r.body) return;
    const rate = parseInt(r.headers.get("X-Sample-Rate") || "24000", 10);
    const reader = r.body.getReader();
    let carry = new Uint8Array(0);
    S.playhead = Math.max(S.playhead, S.audio.currentTime + 0.08);
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const buf = new Uint8Array(carry.length + value.length);
      buf.set(carry); buf.set(value, carry.length);
      const even = buf.length - (buf.length % 2);
      carry = buf.slice(even);
      if (!even) continue;
      const pcm = new Int16Array(buf.buffer.slice(0, even));
      const ab = S.audio.createBuffer(1, pcm.length, rate);
      const ch = ab.getChannelData(0);
      for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 32768;
      // underrun guard: if the network fell behind playback, move the playhead forward —
      // scheduling in the past plays IMMEDIATELY and chunks pile on top of each other
      if (S.playhead < S.audio.currentTime + 0.06) S.playhead = S.audio.currentTime + 0.06;
      const src = S.audio.createBufferSource();
      src.buffer = ab; src.connect(S.audio.destination);
      src.start(S.playhead);
      S.playhead += ab.duration;
    }
    // hold the queue until this clip has actually finished sounding
    const wait = (S.playhead - S.audio.currentTime) * 1000;
    if (wait > 0) await new Promise((res) => setTimeout(res, wait));
  } catch (e) { /* voice is an enhancement — the story never blocks on it */ }
}
function queueVoice(slug, text) {
  S.voiceQueue = S.voiceQueue.then(() => speakEvent(slug, text));
}

async function api(path, method = "POST", body) {
  const r = await fetch("/api/game" + path, {
    method, headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
const esc = (s) => (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const nameOf = (slug) => (S.roster.find((r) => r.slug === slug) || {}).name || slug;

// ---- rendering ----------------------------------------------------------
function add(cls, html) {
  const d = document.createElement("div");
  d.className = "ev " + cls;
  d.innerHTML = html;
  $("feed").appendChild(d);
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  return d;
}
function renderEvents(events, replay = false) {
  for (const e of events || []) {
    if (e.kind === "player" || e.kind === "player_action") {
      if (!replay) continue; // live: echoed optimistically. replay (resume): render them.
      const to = e.kind === "player_action" ? "" : e.to === "room" ? " → everyone" : e.to ? ` → ${nameOf(e.to)}` : "";
      add("you", `<span class="lbl">You${to}</span> ${esc(e.text)}`);
      continue;
    }
    if (e.kind === "role" || e.kind === "player_role") add("role", esc(e.text));
    else if (e.kind === "narration") add("narr", esc(e.text));
    else if (e.kind === "event") add("event", "⚡ " + esc(e.text));
    else if (e.kind === "reaction") add("react", `<b>${esc(e.who || "")}</b> ${esc(e.text)}`);
    else if (e.kind === "dialogue") {
      add("say", `<span class="who-name">${esc(e.who || "")}</span><span class="line">${esc(e.text)}</span>`);
      if (!replay) queueVoice(e.slug, e.text);   // the voice speaks the quotes; narration stays silent
    }
    else add("narr", esc(e.text));
  }
}
function echoYou(text) {
  const to = S.mode === "act" ? "" : S.target === "__room" ? " → everyone" : ` → ${nameOf(S.target)}`;
  const lbl = S.mode === "act" ? "You" : `<span class="lbl">You${to}</span>`;
  add("you", `${lbl} ${esc(text)}`);
}
let thinkingEl = null;
function thinking(on, label) {
  if (thinkingEl) { thinkingEl.remove(); thinkingEl = null; }
  if (on) thinkingEl = add("thinking", label || "…");
}

function renderView(v) {
  if (!v) return;
  $("beat").textContent = v.beat_title || "—";
  $("clock").textContent = `hour ${Math.round(v.clock)}`;
  S.roster = v.roster || S.roster;
  $("roster").innerHTML = S.roster.map((r) => `<span class="who">${esc(r.name)}</span>`).join("");
  renderTargets();
}
function renderTargets() {
  const chips = [{ slug: "__room", name: "🗣 Everyone" }].concat(S.roster);
  $("targets").innerHTML = chips.map((c) =>
    `<span class="chip ${c.slug === "__room" ? "everyone " : ""}${c.slug === S.target ? "sel" : ""}"
       data-slug="${c.slug}">${esc(c.name)}</span>`).join("");
  $("targets").style.opacity = S.mode === "act" ? ".4" : "1";
  $("targets").style.pointerEvents = S.mode === "act" ? "none" : "auto";
  [...$("targets").children].forEach((ch) => ch.onclick = () => { S.target = ch.dataset.slug; renderTargets(); });
}

// ---- actions ------------------------------------------------------------
function setBusy(on) {
  S.busy = on;
  $("sendBtn").disabled = on || S.ended;
  $("advanceBtn").disabled = on;
  $("input").disabled = on;
}
async function send() {
  const text = $("input").value.trim();
  if (!text || S.busy || S.ended) return;
  $("input").value = "";
  echoYou(text);
  setBusy(true);
  thinking(true, S.mode === "act" ? "…" : "…");
  try {
    let res;
    if (S.mode === "act") res = await api(`/${S.gid}/act`, "POST", { action: text });
    else if (S.target === "__room") res = await api(`/${S.gid}/say`, "POST", { line: text });
    else res = await api(`/${S.gid}/talk`, "POST", { target: S.target, line: text });
    thinking(false);
    renderEvents(res.events);
    renderView(res.view);
  } catch (e) { thinking(false); add("event", "⚠ " + esc(e.message)); }
  finally { setBusy(false); $("input").focus(); }
}
async function advance() {
  if (S.busy || S.ended) return;
  setBusy(true);
  thinking(true, "The night turns…");
  try {
    const res = await api(`/${S.gid}/advance`, "POST");
    thinking(false);
    renderEvents(res.events);
    renderView(res.view);
    if (res.ended) endNight();
  } catch (e) { thinking(false); add("event", "⚠ " + esc(e.message)); }
  finally { setBusy(false); }
}
function endNight() {
  S.ended = true;
  $("sendBtn").disabled = true; $("advanceBtn").disabled = true;
  add("narr", "— the crossing is here; the night is over —");
  const box = document.createElement("div");
  box.className = "ev";
  box.innerHTML = `<div class="targets"><input id="outcome" placeholder="one line: what became of them?"
      style="flex:1;min-width:220px;background:var(--bg2);border:1px solid var(--line);border-radius:9px;
      padding:8px 10px;color:var(--ink);font-family:ui-sans-serif,system-ui,sans-serif" />
    <button id="recordBtn" class="primary">Record the ending</button></div>`;
  $("feed").appendChild(box);
  $("recordBtn").onclick = async () => {
    $("recordBtn").disabled = true;
    try { const r = await api(`/${S.gid}/finish`, "POST", { outcome: $("outcome").value.trim() });
      localStorage.removeItem("ferry_gid");
      add("narr", `recorded · ${r.run_id}`); } catch (e) { add("event", "⚠ " + esc(e.message)); }
  };
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

const INTRO =
  "A word before you step in: this is a riverlands world of ferries and fords, peat fires and " +
  "oil lamps — an age of coin, crown soldiers, and market fairs, long before engines or " +
  "electricity. The folk here have never known anything else, so speak to them as a traveler " +
  "of their world. A storm has closed the river; everyone under this roof is stranded until " +
  "the dawn ferry. Talk to them, watch them, take their measure — the night will change them.";

async function begin() {
  $("beginBtn").disabled = true;
  $("startHint").textContent = "the storm closes in…";
  // audio must be born from a user gesture (mobile browsers) — the Begin click is ours
  try { S.audio = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { S.voice = false; }
  try {
    const res = await api("/new", "POST", { reply_model: $("replyModel").value });
    S.gid = res.game_id;
    localStorage.setItem("ferry_gid", S.gid);  // so a dropped connection can resume on reload
    $("title").textContent = res.title;
    $("start").style.display = "none";
    add("event", "⚑ " + INTRO);
    renderView(res.view);
    renderEvents(res.events);
    $("input").focus();
  } catch (e) { $("startHint").textContent = "couldn't start: " + e.message; $("beginBtn").disabled = false; }
}

// Resume an in-progress game after a reload / dropped mobile connection.
async function tryResume() {
  const gid = localStorage.getItem("ferry_gid");
  if (!gid) return;
  try {
    const res = await api(`/${gid}/state`, "GET");
    S.gid = gid;
    $("start").style.display = "none";
    renderView(res.view);
    renderEvents(res.history, true);  // replay full history, including your own past lines
    add("narr", "— resumed —");
    $("input").focus();
  } catch (e) { localStorage.removeItem("ferry_gid"); }  // game no longer on the server -> fresh start
}

// ---- wiring -------------------------------------------------------------
$("beginBtn").onclick = begin;
$("sendBtn").onclick = send;
$("voiceBtn").onclick = () => {
  S.voice = !S.voice;
  $("voiceBtn").textContent = S.voice ? "🔊 Voice on" : "🔇 Voice off";
  if (!S.audio && S.voice) {
    try { S.audio = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { S.voice = false; }
  }
};
$("advanceBtn").onclick = advance;
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
[...$("mode").children].forEach((b) => b.onclick = () => {
  S.mode = b.dataset.mode;
  [...$("mode").children].forEach((x) => x.classList.toggle("on", x === b));
  $("input").placeholder = S.mode === "act" ? "describe what you do…" : "say something…";
  renderTargets();
});

tryResume();  // if a game is already in progress on the server, pick it back up
