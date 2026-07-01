// Embodied play view — drives game.arena.web (/api/embodied) and renders the grounded world.
const $ = (id) => document.getElementById(id);
const S = { gid: null, target: null, busy: false };
const PAL = ["#2b3a52", "#3a2f4d", "#274536", "#4a3a24", "#233f4a", "#42283a", "#2f3a24"];
const ENTCOL = { you: "#7fd1a8" };
const ecol = (ref, i) => (ref === "you" ? "#7fd1a8" : ["#f0b86e", "#6ea8fe", "#c79bf0", "#e0697a", "#5ec98a"][i % 5]);
// marker letter: skip a leading article so handles ("The ferrywoman") don't all become "T"
const markOf = (e) => e.you ? "@" : ((e.ref.replace(/^(the|a|an)\s+/i, "").trim()[0] || "?").toUpperCase());

async function api(path, method = "POST", body) {
  const r = await fetch("/api/embodied" + path, {
    method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
const esc = (s) => (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// ---- rendering ----------------------------------------------------------
function drawGrid(g) {
  const map = $("map");
  map.style.gridTemplateColumns = `repeat(${g.w}, 26px)`;
  // which region each cell belongs to
  const regionAt = (x, y) => g.regions.findIndex((r) => x >= r.rect[0] && y >= r.rect[1] && x <= r.rect[2] && y <= r.rect[3]);
  const entAt = {};
  // you (@) always win a cell, so your marker can never be hidden under an NPC's
  g.entities.forEach((e, i) => { const k = `${e.x},${e.y}`; if (!entAt[k] || e.you) entAt[k] = { ...e, i }; });
  let html = "";
  for (let y = 0; y < g.h; y++) for (let x = 0; x < g.w; x++) {
    const ri = regionAt(x, y);
    const tint = ri >= 0 ? PAL[ri % PAL.length] : "#0e131b";
    const e = entAt[`${x},${y}`];
    const you = e && e.you ? " you-here" : "";
    const mark = e ? `<span class="ent" style="color:${ecol(e.ref, e.i)}" title="${esc(e.ref)}">${esc(markOf(e))}</span>` : "";
    html += `<div class="cell${you}" style="background:${tint}">${mark}</div>`;
  }
  map.innerHTML = html;
  $("legend").innerHTML = g.entities.map((e, i) =>
    `<div><b style="color:${ecol(e.ref, i)}">${esc(markOf(e))}</b> = ${esc(e.ref)} — ${esc(e.stance || "")}</div>`).join("")
    + `<div style="margin-top:6px">${g.regions.map((r, i) => `<span class="dot" style="background:${PAL[i % PAL.length]}"></span>${esc(r.name)}`).join("  ")}</div>`;
}

function renderView(v) {
  if (!v) return;
  $("clock").textContent = `hour ${Math.round(v.clock)}`;
  $("where").textContent = v.where || "—";
  $("scene").textContent = v.scene || "";
  drawGrid(v.grid);
  // talk chips
  S.present = v.present;
  if (!S.target && v.present.length) S.target = v.present[0].slug;
  $("talkChips").innerHTML = v.present.map((p) =>
    `<button class="chip${p.slug === S.target ? " sel" : ""}" data-slug="${p.slug}">${esc(p.ref)}</button>`).join("");
  [...$("talkChips").children].forEach((b) => b.onclick = () => { S.target = b.dataset.slug; renderView(v); });
  // action buttons
  const acts = v.actions || [];
  const moves = acts.filter((a) => a.startsWith("cross to") || a.startsWith("move nearer"));
  const dos = acts.filter((a) => !moves.includes(a));
  $("moveBtns").innerHTML = moves.map((a) => `<button data-act="${esc(a)}">${esc(a.replace("cross to ", "→ ").replace("move nearer to ", "→ "))}</button>`).join("");
  $("doBtns").innerHTML = dos.map((a) => `<button data-act="${esc(a)}">${esc(a)}</button>`).join("");
  [...$("moveBtns").children, ...$("doBtns").children].forEach((b) => b.onclick = () => doAct(b.dataset.act));
}

function feed(events) {
  const f = $("feed"); let n = 0;
  for (const e of events || []) {
    if (e.kind === "scene") continue; // shown live in the scene panel
    let cls = "", html = "";
    if (e.kind === "time") { cls = "time"; html = esc(e.text); }
    else if (e.kind === "player") { cls = "you"; html = `<b>You:</b> ${esc(e.text)}`; }
    else if (e.kind === "player_move" || e.kind === "player_act") { cls = "you"; html = esc(e.text); }
    else if (e.kind === "dialogue") { cls = "say"; html = `<span class="who">${esc(e.who || "")}:</span> ${esc(e.text)}`; }
    else if (e.kind === "npc_act") { cls = "act"; html = `${esc(e.who || "")} — ${esc(e.text)}${e.reason ? ` · “${esc(e.reason)}”` : ""}`; }
    else html = esc(e.text);
    const d = document.createElement("div"); d.className = "ev " + cls; d.innerHTML = html; f.appendChild(d); n++;
  }
  if (n) window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }); // only when something happened
}

// ---- actions ------------------------------------------------------------
function busy(on) { S.busy = on; [...document.querySelectorAll("footer button, input")].forEach((el) => el.disabled = on); }
async function run(fn) { if (S.busy) return; busy(true); try { const res = await fn(); feed(res.events); renderView(res.view); } catch (e) { feed([{ kind: "time", text: "⚠ " + e.message }]); } finally { busy(false); } }
function doAct(label) { run(() => api(`/${S.gid}/act`, "POST", { label })); }
async function say() {
  const line = $("line").value.trim(); if (!line || !S.target) return;
  $("line").value = ""; feed([{ kind: "player", text: line }]);
  await run(() => api(`/${S.gid}/talk`, "POST", { target: S.target, line }));
}

async function begin() {
  $("beginBtn").disabled = true; $("startHint").textContent = "the storm closes in…";
  try {
    const res = await api("/new", "POST", { reply_model: $("replyModel").value });
    S.gid = res.game_id; $("title").textContent = res.title; $("start").style.display = "none";
    renderView(res.view); feed(res.events);
  } catch (e) { $("startHint").textContent = "couldn't start: " + e.message; $("beginBtn").disabled = false; }
}

$("beginBtn").onclick = begin;
$("sayBtn").onclick = say;
$("line").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); say(); } });
$("advanceBtn").onclick = () => run(() => api(`/${S.gid}/advance`, "POST", { hours: 2 }));
