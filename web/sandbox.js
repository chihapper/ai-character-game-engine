// Director's Sandbox — drive an NPC's world by hand to validate metamorphosis.
// Talks to /api/sandbox/* (see orchestrator/sandbox.py).
const $ = (id) => document.getElementById(id);
const state = { slug: null, clock: 0, steps: [], busy: false };

async function api(path, method = "GET", body) {
  const r = await fetch("/api/sandbox" + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
}

const esc = (s) => (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

function setBusy(b) {
  state.busy = b;
  document.querySelectorAll("button").forEach((x) => (x.disabled = b));
}

function setClock(v) {
  state.clock = v;
  $("clock").textContent = v;
  $("delClock").textContent = v;
}

function recordStep(step) {
  state.steps.push(step);
  $("stepCount").textContent = state.steps.length;
}

// ---- feed ---------------------------------------------------------------
let feedStarted = false;
function feed(cls, inner) {
  if (!feedStarted) { $("feed").innerHTML = ""; feedStarted = true; }
  const el = document.createElement("div");
  el.className = "ev " + cls;
  el.innerHTML = inner;
  const box = $("feed");
  box.insertBefore(el, box.firstChild);      // newest at the very top (full reverse-chronological)
  box.scrollTop = 0;                          // keep the newest line in view
  return el;
}
const dayTag = (t) => `<span class="meta">day ${t}</span>`;

function feedDecision(dec, clock) {
  if (!dec) { feed("deliberate", `${dayTag(clock)}<span class="empty">deliberation failed (no decision)</span>`); return; }
  let html = `${dayTag(clock)}<b>Deliberation</b>`;
  html += dec.changed ? ` <span class="tag changed">CHANGED</span>` : ` <span class="tag">no change</span>`;
  if (dec.reflection) html += `<div class="refl">“${esc(dec.reflection)}”</div>`;
  if (dec.internal) html += `<div class="internal">↳ toward you: ${esc(dec.internal)}</div>`;
  if (dec.new_goals && dec.new_goals.length)
    html += `<div class="goals">↳ new goals: ${dec.new_goals.map(esc).join(" · ")}</div>`;
  if (dec.world_action) html += `<div class="world">↳ acts: ${esc(dec.world_action)}</div>`;
  feed("deliberate", html);
}

// ---- state panel --------------------------------------------------------
function bar(label, val, scar) {
  const pct = Math.round((val || 0) * 100);
  const sc = Math.round((scar || 0) * 100);
  return `<div class="bar"><div class="lab"><span>${label}</span>
    <span>${(val || 0).toFixed(2)}${scar ? ` <span style="color:var(--bad)">(scar ${scar.toFixed(2)})</span>` : ""}</span></div>
    <div class="track"><div class="fill" style="width:${pct}%"></div>
      ${sc ? `<div class="scar" style="width:${sc}%"></div>` : ""}</div></div>`;
}
function renderState(s) {
  if (!s) return;
  const r = s.relationship || {};
  $("bars").innerHTML =
    bar("trust", r.trust, r.scar_trust) +
    bar("affection", r.affection, r.scar_affection) +
    bar("respect", r.respect, r.scar_respect);
  $("mood").textContent = r.mood || "—";
  $("goals").innerHTML = (s.goals && s.goals.length)
    ? s.goals.map((g) => `<li>${esc(g)}</li>`).join("")
    : `<li class="empty">—</li>`;
  $("intent").textContent = s.intent || "—";
  $("mems").innerHTML = (s.recent_memories && s.recent_memories.length)
    ? s.recent_memories.slice().reverse().map((m) =>
        `<div class="mem"><b>${m.t != null ? `d${m.t} · ` : ""}</b>${esc(m.text)}
         <span style="float:right">${m.importance}</span></div>`).join("")
    : `<span class="empty">—</span>`;
}

// ---- actions ------------------------------------------------------------
async function refresh() {
  if (!state.slug) return;
  try { renderState(await api(`/${state.slug}/state`)); } catch (e) { console.error(e); }
}

async function doSay() {
  const text = $("sayText").value.trim();
  if (!text || !state.slug) return;
  $("sayText").value = "";
  feed("say", `${dayTag(state.clock)}<b>You:</b> ${esc(text)}`);
  setBusy(true);
  try {
    const res = await api(`/${state.slug}/say`, "POST", { text, clock: state.clock });
    feed("reply", `${dayTag(state.clock)}<b>${esc(charName())}:</b> ${esc(res.reply)}`);
    renderState(res.state);
    recordStep({ type: "say", text });
  } catch (e) { feed("reply", `<span class="empty">error: ${esc(e.message)}</span>`); }
  finally { setBusy(false); }
}

async function doEvent() {
  const text = $("evText").value.trim();
  if (!text || !state.slug) return;
  const roleSel = $("evRole").value;
  const slider = parseFloat($("evImp").value);
  const appraise = $("evAppraise").checked;
  const react = $("evReact").checked;
  // #25: appraise on -> NPC realizes salience (slider is just a coarse objective hint);
  //       off -> the slider IS the stored importance (manual override).
  const body = appraise
    ? { text, importance: null, magnitude: slider, react, clock: state.clock }
    : { text, importance: slider, react, clock: state.clock };
  if (roleSel === "__self") body.actor = "self";
  else if (roleSel) body.player_role = roleSel;
  $("evText").value = "";
  const tag = roleSel === "__self" ? "self-change" : roleSel ? `player ${roleSel}` : "world";
  const salTag = appraise ? `<span class="tag">appraised · hint ${slider.toFixed(2)}</span>` : "";
  const reactTag = react ? `<span class="tag">react now</span>` : "";
  feed("event", `${dayTag(state.clock)}⚡ <b>Event</b> <span class="tag">${tag}</span>${salTag}${reactTag} ${esc(text)}`);
  setBusy(true);
  try {
    const res = await api(`/${state.slug}/event`, "POST", body);
    renderState(res.state);
    // 2a: if it landed hard enough, they reacted in the moment — show the deliberation right here.
    if (res.decision) feedDecision(res.decision, state.clock);
    else if (react && res.reacted === false)
      feed("advance", `${dayTag(state.clock)}<span class="empty">${esc(charName())} registered it, but at salience ${res.salience ?? "—"} it didn't rise to an in-the-moment reaction.</span>`);
    recordStep({ type: "event", text, importance: body.importance, magnitude: body.magnitude || null,
      player_role: body.player_role || null, actor: body.actor || "player", react });
  } catch (e) { feed("event", `<span class="empty">error: ${esc(e.message)}</span>`); }
  finally { setBusy(false); }
}

async function doDeliberate() {
  if (!state.slug) return;
  const mode = $("delMode").value;
  setBusy(true);
  try {
    const res = await api(`/${state.slug}/deliberate`, "POST", { clock: state.clock, mode });
    feedDecision(res.decision, state.clock);
    renderState(res.state);
    recordStep({ type: "deliberate", mode });
  } catch (e) { feed("deliberate", `<span class="empty">error: ${esc(e.message)}</span>`); }
  finally { setBusy(false); }
}

function advance(days) {
  setClock(state.clock + days);
  feed("advance", `⏩ time advances ${days} day${days === 1 ? "" : "s"} → day ${state.clock}`);
  recordStep({ type: "advance", days });
}

async function doReset() {
  if (!state.slug || !confirm("Wipe this character's memory and start fresh?")) return;
  setBusy(true);
  try {
    const res = await api(`/${state.slug}/reset`, "POST", {});
    setClock(0); state.steps = []; $("stepCount").textContent = 0;
    $("feed").innerHTML = `<span class="empty">Fresh slate.</span>`; feedStarted = true;
    renderState(res.state);
  } catch (e) { alert("reset failed: " + e.message); }
  finally { setBusy(false); }
}

// ---- scenarios ----------------------------------------------------------
async function loadScenarioList() {
  try {
    const list = await api("/scenarios");
    $("scenList").innerHTML = `<option value="">— load scenario —</option>` +
      list.map((s, i) => `<option value="${i}">${esc(s.name)} (${(s.steps || []).length})</option>`).join("");
    $("scenList")._data = list;
  } catch (e) { console.error(e); }
}
async function saveScenario() {
  const name = $("scenName").value.trim();
  if (!name) return alert("name the scenario first");
  if (!state.steps.length) return alert("no steps recorded yet");
  await api("/scenarios", "POST", { name, slug: state.slug, steps: state.steps });
  $("scenName").value = "";
  await loadScenarioList();
  alert(`saved "${name}" (${state.steps.length} steps)`);
}
async function replayScenario() {
  const idx = $("scenList").value;
  if (idx === "" || !state.slug) return alert("pick a scenario");
  const scen = $("scenList")._data[idx];
  if (!confirm(`Replay "${scen.name}" on ${charName()}? This resets their memory first.`)) return;
  setBusy(true);
  setClock(0); $("feed").innerHTML = ""; feedStarted = true;
  feed("advance", `▶ replaying scenario "${esc(scen.name)}" (${scen.steps.length} steps)…`);
  try {
    const res = await api(`/${state.slug}/replay`, "POST", { name: scen.name, steps: scen.steps });
    for (const t of res.transcript) {
      if (t.type === "advance") setClock(t.clock), feed("advance", `⏩ → day ${t.clock}`);
      else if (t.type === "say") {
        feed("say", `${dayTag(t.clock)}<b>You:</b> ${esc(t.text)}`);
        feed("reply", `${dayTag(t.clock)}<b>${esc(charName())}:</b> ${esc(t.reply)}`);
      } else if (t.type === "event") feed("event", `${dayTag(t.clock)}⚡ <b>Event</b> ${esc(t.text)}`);
      else if (t.type === "deliberate") feedDecision(t.decision, t.clock);
    }
    state.steps = scen.steps.slice(); $("stepCount").textContent = state.steps.length;
    renderState(res.state);
  } catch (e) { feed("advance", `<span class="empty">replay error: ${esc(e.message)}</span>`); }
  finally { setBusy(false); }
}

// ---- save / load game (state snapshot of ALL characters) ----------------
async function loadSavesList() {
  try {
    const saves = await api("/saves");
    $("savesList").innerHTML = `<option value="">— load game —</option>` +
      saves.map((s) => `<option value="${esc(s.name)}">${esc(s.name)} · ${esc((s.created || "").replace("T", " "))}</option>`).join("");
  } catch (e) { console.error(e); }
}
async function saveGame() {
  const name = $("saveName").value.trim();
  if (!name) return alert("name the save first");
  setBusy(true);
  try {
    const res = await api("/save", "POST", { name, clock: state.clock });
    $("saveName").value = "";
    await loadSavesList();
    feed("advance", `💾 saved game "${esc(res.name)}" — ${(res.characters || []).length} character(s), at day ${state.clock}`);
  } catch (e) { alert("save failed: " + e.message); }
  finally { setBusy(false); }
}
async function loadGame() {
  const name = $("savesList").value;
  if (!name) return alert("pick a save to load");
  if (!confirm(`Load game "${name}"? This restores ALL characters' state (current state is auto-backed-up first).`)) return;
  setBusy(true);
  try {
    const res = await api("/load", "POST", { name });
    const m = res.manifest || {};
    if (m.clock != null) setClock(m.clock);
    $("feed").innerHTML = ""; feedStarted = true;
    feed("advance", `📂 loaded game "${esc(name)}" — ${(m.characters || []).length} character(s) restored, resuming at day ${state.clock}`);
    await refresh();
  } catch (e) { alert("load failed: " + e.message); }
  finally { setBusy(false); }
}
async function downloadTranscript() {
  if (!state.slug) return;
  try {
    const { turns } = await api(`/${state.slug}/transcript`);
    if (!turns || !turns.length) return alert("no transcript recorded for this character yet");
    const lines = [`# Transcript — ${charName()}`, ""];
    for (const t of turns) {
      lines.push(`[day ${t.clock}] You: ${t.user}`);
      lines.push(`[day ${t.clock}] ${charName()}: ${t.reply}`, "");
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${state.slug}-transcript.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) { alert("transcript failed: " + e.message); }
}

// ---- per-role model selector --------------------------------------------
const MODEL_LABELS = {
  "claude-sonnet-4-6": "Sonnet 4.6 ($3/$15)",
  "claude-haiku-4-5": "Haiku 4.5 ($1/$5)",
  "claude-opus-4-8": "Opus 4.8 ($5/$25)",
};
const MODEL_SELECTS = [["mdlReply", "reply"], ["mdlDelib", "deliberation"], ["mdlBook", "bookkeeping"]];
async function loadModels() {
  try {
    const { choice, options } = await api("/models");
    const opts = options.map((o) => `<option value="${o}">${MODEL_LABELS[o] || o}</option>`).join("");
    for (const [id, key] of MODEL_SELECTS) {
      $(id).innerHTML = opts;
      $(id).value = choice[key];
      $(id).onchange = setModels;
    }
  } catch (e) { console.error(e); }
}
async function setModels() {
  const body = { reply: $("mdlReply").value, deliberation: $("mdlDelib").value, bookkeeping: $("mdlBook").value };
  try {
    await api("/models", "POST", body);
    feed("advance", `⚙ models — reply: ${MODEL_LABELS[body.reply]} · delib: ${MODEL_LABELS[body.deliberation]} · book: ${MODEL_LABELS[body.bookkeeping]}`);
  } catch (e) { alert("model switch failed: " + e.message); }
}

// ---- boot ---------------------------------------------------------------
function charName() {
  const o = $("char").selectedOptions[0];
  return o ? o.textContent : state.slug;
}
async function selectChar(slug) {
  state.slug = slug;
  setClock(0); state.steps = []; $("stepCount").textContent = 0;
  $("feed").innerHTML = `<span class="empty">Talk, jump time, inject events, deliberate — watch them change.</span>`;
  feedStarted = true;
  await refresh();
}
async function boot() {
  // characters come from the main API (not the sandbox prefix)
  let chars = [];
  try { chars = await (await fetch("/api/characters")).json(); } catch (e) { console.error(e); }
  $("char").innerHTML = chars.map((c) =>
    `<option value="${c.slug}">${esc(c.name || c.slug)}</option>`).join("");
  $("char").onchange = () => selectChar($("char").value);

  $("sayBtn").onclick = doSay;
  $("sayText").addEventListener("keydown", (e) => { if (e.key === "Enter") doSay(); });
  $("evBtn").onclick = doEvent;
  $("evImp").oninput = () => ($("evImpV").textContent = parseFloat($("evImp").value).toFixed(2));
  const syncEvLab = () => ($("evImpLab").innerHTML = $("evAppraise").checked
    ? 'magnitude <span class="hint">(world hint)</span>'
    : 'importance <span class="hint">(manual)</span>');
  $("evAppraise").onchange = syncEvLab; syncEvLab();
  $("delBtn").onclick = doDeliberate;
  $("resetBtn").onclick = doReset;
  document.querySelectorAll("[data-adv]").forEach((b) =>
    (b.onclick = () => advance(parseInt(b.dataset.adv, 10))));
  $("saveScen").onclick = saveScenario;
  $("replayBtn").onclick = replayScenario;
  $("saveGameBtn").onclick = saveGame;
  $("loadGameBtn").onclick = loadGame;
  $("transcriptBtn").onclick = downloadTranscript;

  await loadModels();
  await loadScenarioList();
  await loadSavesList();
  if (chars.length) { $("char").value = chars[0].slug; await selectChar(chars[0].slug); }
}
boot();
