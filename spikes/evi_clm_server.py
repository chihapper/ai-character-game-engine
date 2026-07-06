"""EVI + Custom Language Model (CLM) spike — ISOLATED, does not touch the demo.

Goal: answer two questions before we'd ever consider EVI for the voice loop —
  Q1  Does EVI's Octave delivery hold up when OUR engine (Claude) is the brain,
      GIVEN that a CLM returns plain text and can't pass Octave the per-utterance
      acting `description` / trailing_silence we author in the modular pipeline?
  Q2  Is the CLM round-trip latency (EVI -> our engine -> back) acceptable?

Shape: EVI's Custom Language Model opens a socket to a POST /chat/completions
endpoint and expects an OpenAI-compatible **SSE** stream back (per Hume's CLM
guide). This server exposes exactly that, backed by a real character Engine, and
**logs every incoming request verbatim** to spikes/evi_clm_requests.jsonl so a
single live call reveals HOW EVI delivers the user's prosody/emotional context
(the whole point of the exercise) — we build the parsing off real payloads, not
guesses.

This is a SPIKE: minimal caps, one character, its own port. It imports nothing
from game/server*, so the live demo on :8001 is untouched.

Run:  .venv/Scripts/python.exe -m spikes.evi_clm_server        # binds :8010
Then tunnel :8010 and point a Hume EVI config's Custom LLM URL at
  https://<tunnel>/chat/completions   (see spikes/EVI_CLM_RUNBOOK.md)
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import uuid

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402

from game.policy import spoken_text  # noqa: E402  (strip stage business -> only what the mouth says)
from orchestrator.adapters.llm_anthropic import AnthropicLLM  # noqa: E402
from orchestrator.character_store import load_character  # noqa: E402
from orchestrator.context import RespondRequest, Situation  # noqa: E402
from orchestrator.engine import Engine  # noqa: E402

SLUG = os.environ.get("EVI_SPIKE_SLUG", "brielle-bri-castellano")
MODEL = os.environ.get("EVI_SPIKE_MODEL", "claude-haiku-4-5")   # low latency for the Q2 test
PORT = int(os.environ.get("EVI_SPIKE_PORT", "8010"))
REQLOG = pathlib.Path(__file__).with_name("evi_clm_requests.jsonl")

# Lever 2 (words carry the performance): the only delivery channel through EVI's text-only CLM is
# the SPOKEN words themselves. Octave is a speech-LANGUAGE model, so a laugh written INTO the quoted
# speech ("Ha—", "haha") is voiced as an audible laugh; a stage direction ("*she laughs*") is stripped
# by spoken_text() and never reaches the voice. So we direct the mind to put its vocal reactions in
# the words. ([pause] is Octave's only supported inline marker; [laughs]-style tags are NOT.)
_VOICE_PERF = {"Voice performance": (
    "Your reply is SPOKEN ALOUD by a voice engine that voices only your quoted words. Put your laughs "
    "and vocal reactions INTO the quoted speech, spelled out — 'Ha—', 'haha', a breathy 'mmm', 'pfft' "
    "— never as third-person stage directions (those are silent). Speak expressively and musically, "
    "with interjections, em-dashes and ellipses for real rhythm; use '[pause]' for a beat. Never flat.")}

app = FastAPI()
_eng: Engine | None = None


def engine() -> Engine:
    global _eng
    if _eng is None:
        _eng = Engine(load_character(SLUG), AnthropicLLM(model=MODEL, max_tokens=200))
    return _eng


def _log(kind: str, payload) -> None:
    """Append a verbatim record — this is how we learn EVI's real emotional-context format."""
    try:
        with open(REQLOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "kind": kind, "payload": payload},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass


def _latest_user_text(messages: list[dict]) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):  # OpenAI content-parts form
                return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    return ""


def _sse_chunk(cid: str, created: int, delta: dict, finish=None) -> str:
    body = {"id": cid, "object": "chat.completion.chunk", "created": created,
            "model": f"engine:{SLUG}",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


@app.get("/health")
async def health():
    return {"ok": True, "slug": SLUG, "model": MODEL}


@app.post("/chat/completions")
async def chat_completions(request: Request):
    raw = await request.json()
    _log("request", raw)                       # <-- verbatim: shows how EVI ships emotion/prosody
    messages = raw.get("messages", [])
    user_text = _latest_user_text(messages)
    t0 = time.time()
    full = await engine().respond(RespondRequest(
        player_input=user_text,
        situation=Situation(location="a rain-locked ferry inn", game_time="evening",
                            clock=0.0, present=[], extra=_VOICE_PERF)))
    reply = spoken_text(full).replace("*", "")   # quoted speech only; drop markdown emphasis (Octave
    #                                              guide says avoid markup — EVI may voice the asterisks)
    gen_ms = round((time.time() - t0) * 1000)
    _log("reply", {"user_text": user_text, "full": full, "spoken": reply, "engine_ms": gen_ms})

    cid, created = f"chatcmpl-{uuid.uuid4().hex[:24]}", int(t0)

    if not raw.get("stream", True):            # non-streaming fallback
        return JSONResponse({
            "id": cid, "object": "chat.completion", "created": created, "model": f"engine:{SLUG}",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": reply},
                         "finish_reason": "stop"}]})

    async def gen():
        # sentence-chunk the reply so EVI/Octave can begin speaking sooner (approximates the
        # streaming our pipeline does); a spike-grade split is fine here.
        import re
        parts = [p for p in re.split(r"(?<=[.!?…])\s+", reply.strip()) if p]
        yield _sse_chunk(cid, created, {"role": "assistant"})
        for p in parts:
            yield _sse_chunk(cid, created, {"content": p + " "})
        yield _sse_chunk(cid, created, {}, finish="stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    print(f"[evi-clm-spike] character={SLUG} model={MODEL}  ->  POST http://0.0.0.0:{PORT}/chat/completions")
    print(f"[evi-clm-spike] logging every EVI payload to {REQLOG}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
