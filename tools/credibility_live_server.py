"""Browser free-hand chat against the persisted, scarred Corvin — the demo's LOOK, but YOU drive it.

Serves one page + a tiny JSON API. Every message you type runs through the SAME Engine and the SAME
capability flags as `--live` (relationship_state, arena_query, salience, reflection, intent), against
the SAME mind the scripted arc left on .memory/. Because respond(debug=True) reflects INLINE, trust /
scars / recall / beliefs update live as you talk — the right panel is the real 🧠 state, not a replay.

    python -m tools.credibility_live_server                              # http://127.0.0.1:8799
    python -m tools.credibility_live_server --talk-model sonnet --engine-model haiku
    python -m tools.credibility_live_server --port 8800 --slug brielle-bri-castellano-inworld

Model knobs mirror the CLI (haiku|sonnet|opus or a full id). Voice is Hume (toggle in the page);
mute it with --mute-default or just leave the toggle off. 'Reset' restores the pre-web snapshot.
Bills the LLM per turn (and Hume per spoken reply).
"""
# NB: intentionally NO `from __future__ import annotations` — it stringifies annotations (PEP 563),
# which breaks FastAPI's body-model resolution for types defined inside build_app().

import argparse
import asyncio
import io
import wave

from tools import credibility_demo as demo   # runs bootstrap() + set_flags(all caps ON) at import
from tools._harness import make_engine

from orchestrator.character_store import load_character
from orchestrator.config import AUDIO_SAMPLE_RATE
from orchestrator.context import RespondRequest, Situation

# ── runtime state (single-user demo; one engine, one lock) ────────────────────────────────────
STATE: dict = {"eng": None, "clock": 41.0, "tts": None, "turns": 0}
_LOCK = asyncio.Lock()
CFG: dict = {"talk_model": demo.MODEL, "engine_model": None, "mute_default": False,
             "voice": demo.CORVIN_VOICE}


def _engine():
    return STATE["eng"]


def _name() -> str:
    return load_character(demo.SLUG).name.split(" (")[0].split()[0]


def _rebuild_engine() -> None:
    STATE["eng"] = make_engine(demo.SLUG, model=CFG["talk_model"], max_tokens=220)


def _state_dict(*, reply: str | None = None, dbg: dict | None = None) -> dict:
    eng = _engine()
    ch = load_character(demo.SLUG)
    d: dict = {
        "name": ch.name.split(" (")[0],
        "role": getattr(ch, "role", "") or "",
        "location": demo.DOCK,
        "talk_model": CFG["talk_model"],
        "engine_model": CFG["engine_model"] or "default (claude-sonnet-4-6)",
        "relationship": demo.rel_snap(eng),
        "scar_lines": demo.scar_lines(eng),
        "beliefs": list(eng.long_term.beliefs()),
        "intent": (eng.intent.get().intent or ""),
        "turns": STATE["turns"],
        "mute_default": CFG["mute_default"],
    }
    if reply is not None:
        d["reply"] = reply
        d["scored"] = demo.scored_rows(dbg or {})
        d["recalled"] = [s["text"] for s in (dbg or {}).get("scored", []) if s.get("selected")]
    return d


def _pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(AUDIO_SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


def build_app():
    from fastapi import FastAPI, Response
    from fastapi.responses import HTMLResponse, JSONResponse
    from pydantic import BaseModel

    class TextIn(BaseModel):
        text: str = ""

    app = FastAPI(title="Credibility — free-hand")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return PAGE

    @app.get("/api/state")
    async def state() -> JSONResponse:
        return JSONResponse(_state_dict())

    @app.post("/api/say")
    async def say(body: TextIn) -> JSONResponse:
        text = (body.text or "").strip()
        if not text:
            return JSONResponse({"error": "empty"}, status_code=400)
        async with _LOCK:
            eng = _engine()
            sit = Situation(location=demo.DOCK, clock=STATE["clock"], present=[_name()])
            reply, dbg = await eng.respond(
                RespondRequest(player_input=text, situation=sit), debug=True)
            STATE["clock"] += 0.02
            STATE["turns"] += 1
            return JSONResponse(_state_dict(reply=reply, dbg=dbg))

    @app.post("/api/speak")
    async def speak(body: TextIn):
        text = (body.text or "").strip()
        if not text:
            return Response(status_code=204)
        if STATE["tts"] is None:
            STATE["tts"] = __import__("orchestrator.main", fromlist=["make_tts"]).make_tts("hume")
        pcm = b""
        async for chunk in STATE["tts"].stream_speech(text, CFG["voice"]):
            pcm += chunk
        return Response(content=_pcm_to_wav(pcm), media_type="audio/wav")

    @app.post("/api/reset")
    async def reset() -> JSONResponse:
        async with _LOCK:
            demo.restore("pre-web")
            _rebuild_engine()
            STATE["clock"] = 41.0
            STATE["turns"] = 0
            return JSONResponse(_state_dict())

    return app


# ── the page (matches docs/credibility-demo/overlay.html palette + components) ─────────────────
PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Credibility — free-hand</title>
<style>
:root{
  --bg:#0a0c10; --panel:#11151b; --panel2:#0d1116; --edge:#222c37; --edge2:#2f3d4b;
  --ink:#e9eef4; --muted:#8b97a5; --dim:#5c6773;
  --aff:#f2b45c; --trust:#3fd0c9; --resp:#a98cff; --scar:#ff5d6c;
  --sel:#7cffb2; --gold:#ffd166; --player:#6fb2ff;
  --mono:"SF Mono",ui-monospace,"Cascadia Code",Consolas,monospace;
  --sans:"Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
}
*{box-sizing:border-box}
html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);overflow:hidden;-webkit-font-smoothing:antialiased}
#stage{display:grid;grid-template-rows:auto 1fr;height:100vh}
header{display:flex;align-items:center;gap:16px;padding:14px 26px;border-bottom:1px solid var(--edge)}
.who .name{font-size:21px;font-weight:700}
.who .role{color:var(--muted);font-size:12px}
.badge{margin-left:auto;display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted);
  border:1px solid var(--edge2);border-radius:999px;padding:6px 12px}
.badge b{color:var(--sel);font-weight:600}
.dot{width:7px;height:7px;border-radius:50%;background:var(--sel);box-shadow:0 0 10px var(--sel)}
.model{font-family:var(--mono);font-size:11px;color:var(--dim)}
main{display:grid;grid-template-columns:1.05fr .95fr;min-height:0}
.left{display:flex;flex-direction:column;min-height:0;border-right:1px solid var(--edge)}
.right{padding:16px 20px;display:flex;flex-direction:column;gap:12px;min-height:0;overflow:auto;
  background:linear-gradient(180deg,var(--panel2),var(--bg))}
.scene{font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:.3px;padding:14px 30px 0}
.convo{flex:1;display:flex;flex-direction:column;gap:18px;min-height:0;overflow:auto;padding:18px 30px}
.line .tag{font-family:var(--mono);font-size:11px;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:6px}
.player .tag{color:var(--player)} .npc .tag{color:var(--aff)}
.player .text{color:#cfe0f5;font-size:18px;line-height:1.5;font-style:italic;border-left:2px solid var(--player);padding-left:14px}
.npc .text{color:var(--ink);font-size:20px;line-height:1.5;white-space:pre-wrap;border-left:2px solid var(--aff);padding-left:14px}
.npc .text .stage{color:var(--dim);font-style:italic}
.recalled{font-family:var(--mono);font-size:10.5px;color:var(--dim);margin-top:8px;padding-left:14px}
.dockbar{border-top:1px solid var(--edge);padding:12px 18px;display:flex;gap:10px;align-items:center}
#msg{flex:1;background:#0b0f14;border:1px solid var(--edge2);border-radius:10px;color:var(--ink);
  font-family:var(--sans);font-size:15px;padding:11px 14px;resize:none;height:44px;line-height:1.3}
#msg:focus{outline:none;border-color:var(--trust)}
button{font-family:var(--sans);font-size:13px;border-radius:9px;border:1px solid var(--edge2);
  background:#141a22;color:var(--ink);padding:10px 15px;cursor:pointer}
button:hover{border-color:var(--trust)} button:disabled{opacity:.5;cursor:default}
#send{background:linear-gradient(180deg,#1f6f6b,#155a4a);border-color:#2c5a44;color:#eafff6;font-weight:600}
.toggle{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);user-select:none}
.card{background:var(--panel);border:1px solid var(--edge);border-radius:12px;padding:12px 15px}
.card h3{margin:0 0 9px;font-size:10.5px;letter-spacing:1.6px;text-transform:uppercase;color:var(--muted);font-weight:600}
.meter{margin:7px 0}
.meter .row{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:5px}
.meter .lbl{font-size:12px;font-weight:600} .meter .val{font-family:var(--mono);font-size:12px}
.track{position:relative;height:11px;border-radius:7px;background:#0b0f14;border:1px solid var(--edge);overflow:hidden}
.fill{position:absolute;left:0;top:0;bottom:0;border-radius:7px;transition:width 1s cubic-bezier(.2,.8,.2,1),background .6s}
.scarzone{position:absolute;top:0;bottom:0;right:0;width:0;border-left:2px solid var(--scar);transition:width 1s cubic-bezier(.2,.8,.2,1);
  background:repeating-linear-gradient(-45deg,rgba(255,93,108,.32),rgba(255,93,108,.32) 5px,transparent 5px,transparent 10px)}
.a .fill{background:linear-gradient(90deg,#a97a2e,var(--aff))}
.t .fill{background:linear-gradient(90deg,#1f6f6b,var(--trust))}
.r .fill{background:linear-gradient(90deg,#5b4aa3,var(--resp))}
.mood{margin-top:8px;font-size:12px;color:var(--muted)} .mood b{color:var(--ink);font-style:italic}
.scarnote{margin-top:6px;font-size:11px;line-height:1.35;color:var(--scar);opacity:.9}
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:11.5px}
th{color:var(--dim);font-weight:500;text-align:right;padding:4px 7px;font-size:9.5px;letter-spacing:.5px;
  text-transform:uppercase;border-bottom:1px solid var(--edge)}
th:last-child{text-align:left}
td{padding:4px 7px;text-align:right;color:var(--muted);border-bottom:1px solid #171d25}
td.mem{text-align:left;color:var(--dim);max-width:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
tr.sel td{color:var(--ink)} tr.sel td.mem{color:var(--sel)}
tr.sel td.star{color:var(--sel)} tr.dim td{opacity:.5}
.win{color:var(--sel)} .imp{color:var(--gold)}
.beliefs li{font-size:12.5px;line-height:1.45;color:var(--ink);margin:4px 0;list-style:none;padding-left:14px;position:relative}
.beliefs li:before{content:"•";color:var(--scar);position:absolute;left:0}
.intent{font-size:12px;color:var(--muted);font-style:italic}
.empty{color:var(--dim);font-size:12px;font-style:italic}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--edge2);border-top-color:var(--trust);
  border-radius:50%;animation:sp .7s linear infinite;vertical-align:middle}
@keyframes sp{to{transform:rotate(360deg)}}
</style></head>
<body><div id="stage">
  <header>
    <div class="who"><div class="name" id="hName">…</div><div class="role" id="hRole"></div></div>
    <div class="model" id="hModel"></div>
    <div class="badge"><span class="dot"></span>loaded from <b>.memory/</b> · <span id="hTurns">0</span> turns</div>
  </header>
  <main>
    <div class="left">
      <div class="scene" id="scene">the fish-dock · unscripted · nothing past this point is written</div>
      <div class="convo" id="convo"></div>
      <div class="dockbar">
        <textarea id="msg" placeholder="Say something to him…  (Enter to send · Shift+Enter for newline)"></textarea>
        <label class="toggle"><input type="checkbox" id="voice"> 🔊 voice</label>
        <button id="send">Send</button>
        <button id="reset" title="restore the pre-web snapshot">Reset</button>
      </div>
    </div>
    <div class="right">
      <div class="card">
        <h3>Relationship <span id="moodInline" class="mood" style="margin:0"></span></h3>
        <div class="meter a"><div class="row"><span class="lbl" style="color:var(--aff)">affection</span><span class="val" id="vAff">—</span></div>
          <div class="track"><div class="fill" id="fAff"></div><div class="scarzone" id="sAff"></div></div></div>
        <div class="meter t"><div class="row"><span class="lbl" style="color:var(--trust)">trust</span><span class="val" id="vTru">—</span></div>
          <div class="track"><div class="fill" id="fTru"></div><div class="scarzone" id="sTru"></div></div></div>
        <div class="meter r"><div class="row"><span class="lbl" style="color:var(--resp)">respect</span><span class="val" id="vRes">—</span></div>
          <div class="track"><div class="fill" id="fRes"></div><div class="scarzone" id="sRes"></div></div></div>
        <div id="scarNotes"></div>
      </div>
      <div class="card" style="flex:1;min-height:150px;display:flex;flex-direction:column">
        <h3>🧠 Memory relevance <span class="model" style="text-transform:none;letter-spacing:0">— what he recalled to answer</span></h3>
        <div style="flex:1;overflow:auto"><table id="brain"><thead><tr>
          <th class="star"></th><th>sim_raw</th><th>import</th><th>recency</th><th>score</th><th style="text-align:left">memory</th>
        </tr></thead><tbody id="brainBody"><tr><td colspan="6" class="empty" style="text-align:center">— talk to him and this fills with the real scores —</td></tr></tbody></table></div>
      </div>
      <div class="card">
        <h3>Consolidated beliefs</h3>
        <ul class="beliefs" id="beliefs"></ul>
        <div class="intent" id="intent"></div>
      </div>
    </div>
  </main>
</div>
<script>
const $=id=>document.getElementById(id);
const clamp=v=>Math.max(0,Math.min(1,v));
function esc(s){return (s||"").replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function stageify(s){return esc(s).replace(/\*([^*]+)\*/g,'<span class="stage">$1</span>');}

function paintState(d){
  $("hName").textContent=d.name; $("hRole").textContent=d.role?("· "+d.role):"";
  $("hModel").textContent="voice "+d.talk_model+"  ·  engine "+d.engine_model;
  $("hTurns").textContent=d.turns;
  const r=d.relationship;
  const set=(fill,scar,val,v,sc)=>{ $(fill).style.width=(clamp(v)*100)+"%";
    $(scar).style.width=(clamp(sc)*100)+"%"; $(val).textContent=v.toFixed(2)+(sc>0?("  ⌈"+(1-sc).toFixed(2)+"⌉"):""); };
  set("fAff","sAff","vAff",r.affection,r.scar_affection);
  set("fTru","sTru","vTru",r.trust,r.scar_trust);
  set("fRes","sRes","vRes",r.respect,r.scar_respect);
  $("moodInline").innerHTML=r.mood?("· <b>"+esc(r.mood)+"</b>"):"";
  $("scarNotes").innerHTML=(d.scar_lines||[]).map(s=>'<div class="scarnote">✕ '+esc(s)+'</div>').join("");
  const bl=$("beliefs"); bl.innerHTML=(d.beliefs&&d.beliefs.length)?d.beliefs.map(b=>"<li>"+esc(b)+"</li>").join(""):'<li class="empty" style="color:var(--dim)">none consolidated yet</li>';
  $("intent").textContent=d.intent?("current intent: "+d.intent):"";
  if(d.scored) paintBrain(d.scored);
}
function paintBrain(rows){
  const b=$("brainBody");
  if(!rows.length){ b.innerHTML='<tr><td colspan="6" class="empty" style="text-align:center">(no long-term memories scored yet)</td></tr>'; return; }
  rows=rows.slice().sort((a,c)=>c.base-a.base);
  b.innerHTML=rows.map(s=>{
    const impWin=s.selected&&s.importance>s.similarity_raw+0.05;
    const sup=!s.selected&&s.similarity_raw>0.55;
    return '<tr class="'+(s.selected?'sel':(sup?'dim':''))+'">'+
      '<td class="star">'+(s.selected?'★':'')+'</td>'+
      '<td>'+s.similarity_raw.toFixed(2)+'</td>'+
      '<td class="'+(impWin?'imp':'')+'">'+s.importance.toFixed(2)+'</td>'+
      '<td>'+s.recency.toFixed(2)+'</td>'+
      '<td class="'+(s.selected?'win':'')+'">'+s.base.toFixed(2)+'</td>'+
      '<td class="mem" title="'+esc(s.text)+'">'+esc(s.text)+'</td></tr>';
  }).join("");
}
function addLine(cls,tag,html,recalled){
  const c=$("convo");
  const div=document.createElement("div"); div.className="line "+cls;
  div.innerHTML='<div class="tag">'+tag+'</div><div class="text">'+html+'</div>'+
    (recalled&&recalled.length?'<div class="recalled">recalled: '+recalled.map(t=>esc(t.slice(0,44))).join("  |  ")+'</div>':'');
  c.appendChild(div); c.scrollTop=c.scrollHeight; return div;
}
let busy=false;
async function send(){
  const t=$("msg").value.trim(); if(!t||busy) return;
  busy=true; $("send").disabled=true; $("msg").value="";
  addLine("player","you",esc(t));
  const npc=addLine("npc",$("hName").textContent,'<span class="spin"></span>');
  try{
    const res=await fetch("/api/say",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:t})});
    const d=await res.json();
    if(d.error){ npc.querySelector(".text").innerHTML='<span class="empty">('+d.error+')</span>'; }
    else{
      npc.querySelector(".text").innerHTML=stageify(d.reply);
      if(d.recalled&&d.recalled.length){ const rc=document.createElement("div"); rc.className="recalled";
        rc.innerHTML='recalled: '+d.recalled.map(x=>esc(x.slice(0,44))).join("  |  "); npc.appendChild(rc); }
      paintState(d);
      if($("voice").checked) speak(d.reply);
    }
  }catch(e){ npc.querySelector(".text").innerHTML='<span class="empty">(network error)</span>'; }
  busy=false; $("send").disabled=false; $("msg").focus();
}
async function speak(text){
  try{
    const res=await fetch("/api/speak",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
    if(!res.ok) return; const buf=await res.arrayBuffer();
    const url=URL.createObjectURL(new Blob([buf],{type:"audio/wav"}));
    const a=new Audio(url); a.onended=()=>URL.revokeObjectURL(url); a.play();
  }catch(e){}
}
async function reset(){
  if(!confirm("Restore the pre-web snapshot? This wipes the current conversation's changes to his mind.")) return;
  const d=await (await fetch("/api/reset",{method:"POST"})).json();
  $("convo").innerHTML=""; paintState(d);
}
$("send").onclick=send; $("reset").onclick=reset;
$("msg").addEventListener("keydown",e=>{ if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();} });
(async()=>{ const d=await (await fetch("/api/state")).json(); paintState(d);
  if(d.mute_default===false) {} $("msg").focus(); })();
</script>
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Browser free-hand chat vs the persisted scarred mind.")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--slug", default=demo.SLUG, help="character slug (default: Corvin)")
    ap.add_argument("--talk-model", help="conversational model: haiku|sonnet|opus or a full id")
    ap.add_argument("--engine-model", help="engine-process model: haiku|sonnet|opus or a full id")
    ap.add_argument("--voice", default=demo.CORVIN_VOICE, help="Hume voice ref (HUME_AI:<id>)")
    ap.add_argument("--mute-default", action="store_true", help="start with the voice toggle off")
    args = ap.parse_args()

    demo.SLUG = args.slug
    CFG["voice"] = args.voice
    CFG["mute_default"] = args.mute_default
    if args.talk_model:
        CFG["talk_model"] = demo.resolve_model(args.talk_model)
    if args.engine_model:
        CFG["engine_model"] = demo.resolve_model(args.engine_model)
    demo.apply_engine_model(CFG["engine_model"])

    demo.snapshot("pre-web")          # reset point for the session
    _rebuild_engine()
    print(f"   ⚙ {_name()}  ·  voice={CFG['talk_model']}  engine={CFG['engine_model'] or 'default (claude-sonnet-4-6)'}")
    print(f"   ▶ open  http://{args.host}:{args.port}/   (free-hand; Reset restores 'pre-web')")

    import uvicorn
    uvicorn.run(build_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
