"""The MIND SERVER seam for a foreign world (#35/#38): Unity (or any client that owns a world)
drives the UNCHANGED engine over plain JSON. The client composes each NPC's first-person percept
(line of sight, gaze, proximity — earned from real space) into `situation`; the engine never
learns what a raycast is. Game policy (react thresholds, magnitudes, name/acquaintance rules)
lives in game/policy.py, shared with the grid arena so the treatment arms can't drift.

ONE live session per process — every session shares the per-character memory namespaces and a
new session resets them (same rule as the grid arena; run-scoped namespaces are #37). All DTOs
are flat/array-shaped so Unity's built-in JsonUtility can produce and parse them."""
from __future__ import annotations

import asyncio
import base64
import glob
import logging
import os
from pathlib import Path
from uuid import uuid4

import yaml
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from orchestrator.adapters.llm_anthropic import AnthropicLLM
from orchestrator.character_store import load_character
from orchestrator.config import ALLOWED_MODEL_IDS, EngineCaps, get_settings
from orchestrator.context import RespondRequest, Situation
from orchestrator.engine import Engine
from orchestrator.memory.long_term import LongTermMemory

from .. import casting, experiment_log, policy

# TTS provider is a game-level knob (GAME_TTS=inworld|elevenlabs|hume|fish|chatterbox).
# Inworld is the default — the CURRENT Track V setup; the seam means the client never
# knows which engine spoke. The bake-off candidates swap in with an env change + restart.
def _tts_provider() -> str:
    import os
    return (os.environ.get("GAME_TTS") or "inworld").strip().lower()


def _tts():
    provider = _tts_provider()
    if provider == "elevenlabs":
        from orchestrator.adapters.tts_elevenlabs import ElevenLabsTTS
        return ElevenLabsTTS()
    if provider == "hume":
        from orchestrator.adapters.tts_hume import HumeTTS
        return HumeTTS()
    if provider == "fish":
        from orchestrator.adapters.tts_fish import FishTTS
        return FishTTS()
    if provider == "chatterbox":
        from orchestrator.adapters.tts_chatterbox import ChatterboxTTS
        return ChatterboxTTS()
    from orchestrator.adapters.tts_inworld import InworldTTS
    return InworldTTS()

def _stt():
    from orchestrator.adapters.stt_assemblyai import AssemblyAISTT
    return AssemblyAISTT()

router = APIRouter(prefix="/api/mind")

_GAME_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO = "ferry_crossing.yaml"


class MindSession:
    """The engines for one cast + the run bookkeeping — a world-less ArenaGame."""

    def __init__(self, scenario_path: Path, reply_model: str | None):
        self.scenario = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
        self.cast = [c["slug"] for c in self.scenario["cast"]]
        self.handles = {c["slug"]: (c.get("handle") or "someone").strip() for c in self.scenario["cast"]}
        self.here_because = {c["slug"]: (c.get("here_because") or "").strip() for c in self.scenario["cast"]}
        self.player_handle = (self.scenario.get("player_handle") or "a newcomer").strip()
        over = dict(relationship_state=True, reflection_enabled=True, intent_state=True,
                    background_reflection=True)
        window = (self.scenario.get("clock") or {}).get("recent_happenings_window")
        if window:
            over["recent_happenings_window"] = float(window)
        caps = EngineCaps.from_settings(get_settings(), **over)
        mem_dir = Path(get_settings().memory_dir)
        for slug in self.cast:  # fresh minds per run (shared namespaces; one live session)
            ns = load_character(slug).memory_namespace
            for f in glob.glob(str(mem_dir / f"{ns}.*")):
                os.remove(f)
            LongTermMemory.invalidate(ns)
        by_slug = {c["slug"]: c for c in self.scenario["cast"]}
        self.engines = {slug: Engine(casting.situate(load_character(slug), self.scenario, by_slug.get(slug)),
                                     AnthropicLLM(model=reply_model), caps=caps)
                        for slug in self.cast}
        # voice casting, per provider: the profile's own voice_id wins when its tts_provider
        # matches the active engine; else the scenario's authored voice for that provider
        # (voice_inworld: <id> / voice: <ElevenLabs name>) — game data end to end
        self.voice_names = {c["slug"]: (c.get("voice") or "").strip() for c in self.scenario["cast"]}
        self.voice_inworld = {c["slug"]: (c.get("voice_inworld") or "").strip() for c in self.scenario["cast"]}
        self.voice_ids: dict = {}
        st = get_settings()
        self.voice_ready = bool(st.inworld_api_key if _tts_provider() == "inworld"
                                else st.elevenlabs_api_key)
        book = get_settings().salience_model
        self.run_id = experiment_log.start_run(
            condition="TREAT-EMBODIED-3D", scenario=self.scenario["id"], characters=self.cast,
            models=f"reply={reply_model or 'default'} book={book}")

    def engine(self, slug: str) -> Engine:
        eng = self.engines.get(slug)
        if eng is None:
            raise HTTPException(status_code=404, detail=f"no such character in this session: {slug}")
        return eng

    def situation(self, slug: str, sit: "SituationDTO | None") -> Situation | None:
        d = {"location": sit.location, "present": sit.present, "clock": sit.clock} if sit else {}
        d["extra"] = {"Performance": sit.performance if sit and sit.performance
                      else policy.PERFORMANCE_RULES}
        if sit and sit.ambient:
            d["extra"]["Around you, right now"] = sit.ambient
        frame = (self.scenario.get("world_frame") or "").strip()
        if frame:  # the scenario's world overrides a reused sheet's old life (no Marco here)
            d["extra"]["The world you live in"] = frame
        if self.here_because.get(slug):
            d["extra"]["Why you're here tonight"] = self.here_because[slug]
        return Situation.from_dict(d)

    async def voice_for(self, slug: str) -> str | None:
        if not self.voice_ready:
            return None
        if slug in self.voice_ids:
            return self.voice_ids[slug]
        provider = _tts_provider()
        char = self.engine(slug).character
        vid = (char.voice_id or "").strip() if getattr(char, "tts_provider", "") == provider else ""
        if not vid and provider == "inworld":
            vid = self.voice_inworld.get(slug, "")
        if not vid and provider == "elevenlabs":
            try:  # ElevenLabs voices are cast by NAME against the account library
                voices = await _tts().list_voices()
                want = self.voice_names.get(slug, "").lower()
                match = next((v for v in voices if want and want in (v["name"] or "").lower()), None)
                vid = (match or (voices[0] if voices else {})).get("id") or ""
            except Exception:
                vid = ""
        self.voice_ids[slug] = vid or None
        return self.voice_ids[slug]

    async def finish(self, outcome: str) -> None:
        for eng in self.engines.values():
            await eng.flush_reflection()
        experiment_log.finalize_run(self.run_id, outcome or "(unity session)")


_sessions: dict[str, MindSession] = {}
_locks: dict[str, asyncio.Lock] = {}


def _s(sid: str) -> MindSession:
    s = _sessions.get(sid)
    if s is None:
        raise HTTPException(status_code=404, detail="no such session — create one")
    return s


def _lock(sid: str) -> asyncio.Lock:
    return _locks.setdefault(sid, asyncio.Lock())


# ---- DTOs (JsonUtility-friendly: flat fields + arrays, no dicts) --------------------------------

class NewSession(BaseModel):
    scenario: str = DEFAULT_SCENARIO
    reply_model: str | None = None


class SituationDTO(BaseModel):
    location: str = ""
    present: list[str] = Field(default_factory=list)  # client-composed first-person strings
    clock: float | None = None
    performance: str = ""  # optional override of the default performance rules
    ambient: str = ""      # what the world is DOING around them (the storm's arc, perceived)


class Respond(BaseModel):
    line: str = ""    # a spoken player line (framed as address by the engine)
    event: str = ""   # OR a non-spoken trigger ("you just watched the stranger bar the door")
    situation: SituationDTO | None = None


class Choose(BaseModel):
    situation: str = ""            # the rendered first-person scene text
    options: list[str] = Field(default_factory=list)


class ObservedItem(BaseModel):
    slug: str
    observed: str  # first-person, composed by the client ("the newcomer (close by) bars the door")


class Observe(BaseModel):
    clock: float | None = None
    magnitude: float = Field(default=0.1, ge=0, le=1)
    items: list[ObservedItem] = Field(default_factory=list)


class Acted(BaseModel):
    action: str
    reason: str = ""
    clock: float | None = None


class Finish(BaseModel):
    outcome: str = ""


# ---- endpoints -----------------------------------------------------------------------------------

@router.post("/session")
async def new_session(body: NewSession):
    if body.reply_model and body.reply_model not in ALLOWED_MODEL_IDS:
        raise HTTPException(status_code=422, detail=f"unknown reply_model {body.reply_model!r}")
    path = _GAME_DIR / "scenarios" / Path(body.scenario or DEFAULT_SCENARIO).name
    if path.suffix != ".yaml" or not path.is_file():
        raise HTTPException(status_code=400, detail=f"unknown scenario '{body.scenario}'")
    for sid, old in list(_sessions.items()):  # one live session per process (shared namespaces)
        async with _lock(sid):
            try:
                await old.finish("(superseded by a new session)")
            except Exception:
                pass
            _sessions.pop(sid, None)
            _locks.pop(sid, None)
    s = MindSession(path, body.reply_model)
    sid = uuid4().hex[:8]
    _sessions[sid] = s
    return {"session_id": sid, "title": s.scenario["title"], "player_handle": s.player_handle,
            "voice": s.voice_ready,
            "react_at": policy.REACT_SALIENCE, "speak_at": policy.SPEAK_SALIENCE,
            "cast": [{"slug": c, "handle": s.handles[c], "here_because": s.here_because[c]}
                     for c in s.cast]}


@router.post("/{sid}/{slug}/respond")
async def respond(sid: str, slug: str, body: Respond):
    s = _s(sid)
    eng = s.engine(slug)
    if not (body.line.strip() or body.event.strip()):
        raise HTTPException(status_code=400, detail="need line or event")
    async with _lock(sid):
        reply = await eng.respond(RespondRequest(
            player_input=body.line.strip() or None, event=body.event.strip() or None,
            situation=s.situation(slug, body.situation)))
    return {"reply": reply, "name_spoken": policy.spoken_name(eng.character.name, reply) or "",
            "face_marks": policy.parse_face_marks(eng.last_postscript)}


@router.post("/{sid}/{slug}/choose")
async def choose(sid: str, slug: str, body: Choose):
    s = _s(sid)
    eng = s.engine(slug)
    if not body.options:
        raise HTTPException(status_code=400, detail="need options (the afforded actions)")
    sit = body.situation
    frame = (s.scenario.get("world_frame") or "").strip()
    if frame:  # choices ground on the scenario's world too, not a reused sheet's old life
        sit = f"(The world you live in: {frame})\n{sit}"
    async with _lock(sid):
        out = await eng.choose_action(sit, body.options)
    return {"action": out.get("action") or "", "reason": out.get("reason") or "",
            "expression": out.get("expression") or "", "face": out.get("face") or "neutral"}


@router.post("/{sid}/observe")
async def observe(sid: str, body: Observe):
    """The react recipe's server half: each witness remembers its own first-person observation
    (appraised salience, #25 magnitude hint) and shared policy maps salience -> ''|'act'|'speak'.
    The CLIENT decided who witnessed (line of sight / earshot — free from the scene) and, for
    reactors, follows up with /choose or /respond."""
    s = _s(sid)
    async with _lock(sid):
        async def appraise(item: ObservedItem):
            sal = await s.engine(item.slug).remember(
                item.observed, kind="player_event", t=body.clock, magnitude=body.magnitude)
            return {"slug": item.slug, "salience": sal or 0.0,
                    "react": policy.react_verdict(sal or 0.0),
                    "flinch": policy.flinch(sal or 0.0)}
        return {"results": await asyncio.gather(*(appraise(i) for i in body.items))}


@router.post("/{sid}/{slug}/acted")
async def acted(sid: str, slug: str, body: Acted):
    """The game ENACTED a chosen action — write it into the character's memory as their OWN act.
    Without this the body moves but the mind never learns it did ('why did you come over?' →
    confabulation — the sandbox continuity bug, rediscovered live on the Unity arm). The stored
    form + pinned salience put it in the #30 working-memory foreground for the next few beats."""
    s = _s(sid)
    eng = s.engine(slug)
    text = f"(chose, of their own will) {body.action}" + (f" — {body.reason}" if body.reason else "")
    async with _lock(sid):
        await eng.remember(text, kind="decision", importance=0.65, t=body.clock)
    return {"ok": True}


class Speak(BaseModel):
    text: str


@router.post("/{sid}/{slug}/speak")
async def speak(sid: str, slug: str, body: Speak):
    """The character's line as AUDIO in their own voice — raw PCM s16le mono (rate in header),
    played by the client at the speaker's position. Stateless: no session lock held."""
    s = _s(sid)
    vid = await s.voice_for(slug)
    if not vid or not body.text.strip():
        raise HTTPException(status_code=404, detail="no voice available")
    from orchestrator.config import AUDIO_SAMPLE_RATE
    # narration is stage business, never voiced — but Hume ACTS it: its adapter takes the
    # full reply and turns the stage directions into per-utterance acting instructions
    text = body.text if _tts_provider() == "hume" else policy.spoken_text(body.text)
    chunks = []
    async for chunk in _tts().stream_speech(text, vid):
        chunks.append(chunk)
    if not chunks:
        raise HTTPException(status_code=404, detail="nothing speakable")
    return Response(content=b"".join(chunks), media_type="application/octet-stream",
                    headers={"X-Sample-Rate": str(AUDIO_SAMPLE_RATE)})


class EmotionMark(BaseModel):
    t: float | None = None     # seconds into the clip — the performance can TURN mid-sentence
    frac: float | None = None  # OR a fraction of the clip (0-1); resolved to seconds after TTS
    face: str = ""
    strength: float = Field(default=0.9, ge=0, le=1)


class SpeakAnim(BaseModel):
    text: str
    face: str = ""          # engine face tag (happy/sad/...) — colors the facial performance
    intensity: float = 0.9  # how strongly the tag overrides audio-inferred emotion
    emotions: list[EmotionMark] = Field(default_factory=list)  # timeline; supersedes `face`


@router.post("/{sid}/{slug}/speak_anim")
async def speak_anim(sid: str, slug: str, body: SpeakAnim):
    """Voice + face in one call: TTS PCM plus a timestamped ARKit blendshape track solved by
    the face-anim adapter. The ENGINE's chosen face tag rides along as the preferred emotion —
    which face a character makes stays a mind decision, the audio only times the mouth.
    Face animation is an enhancement: if the solver is unreachable, voice still ships (anim=null)."""
    s = _s(sid)
    vid = await s.voice_for(slug)
    if not vid or not body.text.strip():
        raise HTTPException(status_code=404, detail="no voice available")
    from orchestrator.config import AUDIO_SAMPLE_RATE
    # same rule as /speak: Hume receives the full reply (stage business -> direction)
    text = body.text if _tts_provider() == "hume" else policy.spoken_text(body.text)
    chunks = []
    async for chunk in _tts().stream_speech(text, vid):
        chunks.append(chunk)
    if not chunks:
        raise HTTPException(status_code=404, detail="nothing speakable")
    pcm = b"".join(chunks)
    anim = None
    if os.environ.get("GAME_NVIDIA_API_KEY"):
        try:
            from orchestrator.adapters.faceanim_a2f import A2FFaceAnim
            clip_secs = len(pcm) / 2 / AUDIO_SAMPLE_RATE
            timeline = ([(m.t if m.t is not None else (m.frac or 0.0) * clip_secs,
                          m.face, m.strength) for m in body.emotions if m.face.strip()]
                        if body.emotions else None)
            result = await A2FFaceAnim().animate(
                pcm, AUDIO_SAMPLE_RATE,
                emotion=body.face.strip() or None,
                emotion_strength=body.intensity,
                emotion_timeline=timeline)
            anim = result.to_dict()
        except Exception as exc:  # never let lip-sync failure silence the voice
            logging.getLogger("mind_api").warning("face anim skipped: %s", exc)
    return {"rate": AUDIO_SAMPLE_RATE, "pcm_b64": base64.b64encode(pcm).decode("ascii"),
            "anim": anim}


def _adapter_named(provider: str):
    if provider == "elevenlabs":
        from orchestrator.adapters.tts_elevenlabs import ElevenLabsTTS
        return ElevenLabsTTS()
    if provider == "hume":
        from orchestrator.adapters.tts_hume import HumeTTS
        return HumeTTS()
    if provider == "fish":
        from orchestrator.adapters.tts_fish import FishTTS
        return FishTTS()
    if provider == "chatterbox":
        from orchestrator.adapters.tts_chatterbox import ChatterboxTTS
        return ChatterboxTTS()
    from orchestrator.adapters.tts_inworld import InworldTTS
    return InworldTTS()


async def _bakeoff_voice(s: "MindSession", slug: str, provider: str) -> str:
    """Bake-off casting: env override BAKEOFF_<PROVIDER>_VOICE, else a sensible default —
    the comparison is about PERFORMANCE; final casting comes after a winner is picked."""
    env = os.environ.get(f"BAKEOFF_{provider.upper()}_VOICE")
    if env:
        return env
    if provider == "chatterbox":
        ref = _GAME_DIR.parent / "tts_voices" / "bri_inworld_ref.wav"
        return str(ref) if ref.exists() else ""
    if provider == "hume":
        return "Ava Song"   # young-female library voice; BAKEOFF_HUME_VOICE overrides
    if provider == "fish":
        return ""  # provider default voice
    return await s.voice_for(slug) or ""


class SpeakMulti(BaseModel):
    text: str
    providers: list[str] = Field(default_factory=lambda: ["inworld"])


@router.post("/{sid}/{slug}/speak_multi")
async def speak_multi(sid: str, slug: str, body: SpeakMulti):
    """The bake-off seam: ONE reply, every requested voice. Returns per-provider WAV
    (base64) + first-audio/total latency so ears and numbers line up on identical text."""
    import time as _time
    import wave as _wave
    import io as _io
    s = _s(sid)
    from orchestrator.config import AUDIO_SAMPLE_RATE
    spoken = policy.spoken_text(body.text)   # narration is stage business, never voiced

    async def one(provider: str) -> dict:
        try:
            tts = _adapter_named(provider)
            voice = await _bakeoff_voice(s, slug, provider)
            # Hume gets the full reply: its adapter ACTS the stage directions
            text = body.text if provider == "hume" else spoken
            t0 = _time.perf_counter()
            first = None
            chunks: list[bytes] = []
            async for chunk in tts.stream_speech(text, voice):
                if first is None:
                    first = _time.perf_counter() - t0
                chunks.append(chunk)
            total = _time.perf_counter() - t0
            pcm = b"".join(chunks)
            if not pcm:
                return {"provider": provider, "error": "no audio"}
            buf = _io.BytesIO()
            with _wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(AUDIO_SAMPLE_RATE)
                w.writeframes(pcm)
            return {"provider": provider, "wav_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
                    "first_audio_s": round(first, 2), "total_s": round(total, 2),
                    "clip_s": round(len(pcm) / 2 / AUDIO_SAMPLE_RATE, 1), "voice": voice}
        except Exception as exc:
            return {"provider": provider, "error": str(exc)[:200]}

    results = await asyncio.gather(*(one(p.strip().lower()) for p in body.providers if p.strip()))
    return {"results": list(results)}


@router.get("/bakeoff")
async def bakeoff_page():
    """The conversational bake-off: talk to a mind once, hear the reply in every candidate
    voice side by side. Dev instrument — ears first, numbers alongside."""
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_BAKEOFF_HTML, headers={"Cache-Control": "no-store"})


_BAKEOFF_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>TTS bake-off — talk to Bri</title>
<style>
 body{font-family:Segoe UI,system-ui,sans-serif;background:#14100d;color:#e8dcc8;max-width:860px;margin:2rem auto;padding:0 1rem}
 h1{font-size:1.2rem;color:#d8a24a} .muted{color:#8d7f6a;font-size:.85rem}
 #log{border:1px solid #3a2f24;border-radius:8px;padding:1rem;min-height:120px;margin:1rem 0;background:#1b1611}
 .turn{margin:.6rem 0} .you{color:#9fb7d8} .her{color:#e8dcc8} .marks{color:#d8a24a;font-size:.8rem}
 .voices{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.6rem;margin:.4rem 0 1rem}
 .voice{border:1px solid #3a2f24;border-radius:8px;padding:.6rem;background:#201a13}
 .voice b{color:#d8a24a} .voice .num{color:#8d7f6a;font-size:.8rem} .err{color:#c96a5a;font-size:.8rem}
 input[type=text]{width:70%;padding:.55rem;background:#241d15;border:1px solid #3a2f24;color:#e8dcc8;border-radius:6px}
 button{padding:.55rem 1rem;background:#d8a24a;border:none;border-radius:6px;font-weight:600;cursor:pointer}
 label{margin-right:.9rem;font-size:.9rem}
</style></head><body>
<h1>TTS bake-off — a conversation with Bri, every voice at once</h1>
<div class="muted">One mind, one reply, N voices. Latency shown per provider. Session resets on reload.</div>
<div id="provs">
 <label><input type="checkbox" value="inworld" checked>inworld (current)</label>
 <label><input type="checkbox" value="hume" checked>hume</label>
 <label><input type="checkbox" value="fish" checked>fish s2-pro</label>
 <label><input type="checkbox" value="chatterbox" checked>chatterbox (local)</label>
 <label><input type="checkbox" value="elevenlabs">elevenlabs</label>
</div>
<div id="log"></div>
<form id="f"><input type="text" id="line" placeholder="Say something to Bri..." autocomplete="off">
<button>Send</button></form>
<script>
const SLUG='brielle-bri-castellano'; let SID=null;
const log=document.getElementById('log');
async function init(){
  const r=await fetch('/api/mind/session',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({scenario:'ferry_crossing.yaml'})});
  SID=(await r.json()).session_id;
}
function el(h){const d=document.createElement('div');d.innerHTML=h;return d.firstChild}
document.getElementById('f').onsubmit=async e=>{
  e.preventDefault();
  const line=document.getElementById('line').value.trim(); if(!line||!SID)return;
  document.getElementById('line').value='';
  log.appendChild(el(`<div class="turn you">You: ${line}</div>`));
  const think=el(`<div class="turn muted">Bri is thinking...</div>`); log.appendChild(think);
  const rr=await fetch(`/api/mind/${SID}/${SLUG}/respond`,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({line,situation:{location:'the bar, in the taproom',
      present:['the traveler stands right in front of you, speaking to you'],
      ambient:'rain drums on the roof; the storm has the ferry grounded'}})});
  const rd=await rr.json(); think.remove();
  const marks=(rd.face_marks||[]).map(m=>`${m.face}@${m.frac}`).join(' ')||'neutral';
  log.appendChild(el(`<div class="turn her">Bri: ${rd.reply} <span class="marks">[face: ${marks}]</span></div>`));
  const provs=[...document.querySelectorAll('#provs input:checked')].map(c=>c.value);
  const grid=el(`<div class="voices"></div>`); log.appendChild(grid);
  for(const p of provs) grid.appendChild(el(`<div class="voice" id="v-${p}"><b>${p}</b><div class="num">synthesizing...</div></div>`));
  window.scrollTo(0,document.body.scrollHeight);
  const sr=await fetch(`/api/mind/${SID}/${SLUG}/speak_multi`,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({text:rd.reply,providers:provs})});
  for(const res of (await sr.json()).results){
    const box=document.getElementById(`v-${res.provider}`); if(!box)continue;
    box.innerHTML=res.error
      ? `<b>${res.provider}</b><div class="err">${res.error}</div>`
      : `<b>${res.provider}</b><div class="num">first audio ${res.first_audio_s}s · total ${res.total_s}s · clip ${res.clip_s}s</div>
         <audio controls src="data:audio/wav;base64,${res.wav_b64}" style="width:100%"></audio>`;
  }
  window.scrollTo(0,document.body.scrollHeight);
};
init();
</script></body></html>"""


@router.post("/{sid}/stt")
async def stt(sid: str, request: Request):
    """Push-to-talk: a WAV clip in, the player's words out (AssemblyAI batch — short clips
    resolve in a few seconds)."""
    _s(sid)
    audio = await request.body()
    if not audio or len(audio) < 1000:
        raise HTTPException(status_code=400, detail="empty clip")
    text = await _stt().transcribe(audio)
    return {"text": (text or "").strip()}


@router.post("/{sid}/finish")
async def finish(sid: str, body: Finish):
    s = _s(sid)
    async with _lock(sid):
        await s.finish(body.outcome)
    _sessions.pop(sid, None)
    _locks.pop(sid, None)
    return {"ok": True, "run_id": s.run_id}
