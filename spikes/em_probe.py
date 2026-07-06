"""EM de-risk probe (throwaway): is Hume's STANDALONE Expression Measurement streaming API
still live, and what does it return? The docs now 302 to /intro, so we confirm empirically.

Sends a WAV to wss://api.hume.ai/v0/stream/models with the prosody + burst models enabled,
prints the raw response shape + the top emotions per model. If prosody returns a 48-dim
emotion vector, the API is live and we have the wire format; if the burst model fires on a
laugh clip, vocal-burst detection works.

    .venv/Scripts/python.exe -m spikes.em_probe <path-to.wav>
"""
import asyncio
import base64
import json
import os
import ssl
import sys

from dotenv import load_dotenv

load_dotenv(".env")
import certifi  # noqa: E402  (same CA bundle our working httpx/Octave calls use)
import websockets  # noqa: E402

KEY = (os.environ.get("HUME_API_KEY") or "").strip()
URL = "wss://api.hume.ai/v0/stream/models"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())


async def probe(path: str) -> None:
    audio = open(path, "rb").read()
    b64 = base64.b64encode(audio).decode()
    msg = {"models": {"prosody": {}, "burst": {}}, "data": b64}
    print(f"[probe] {path} ({len(audio)} bytes) -> {URL.split('?')[0]}  models=prosody,burst")
    async with websockets.connect(URL, ssl=SSL_CTX, additional_headers={"X-Hume-Api-Key": KEY},
                                  max_size=None, open_timeout=20) as ws:
        await ws.send(json.dumps(msg))
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=45)
        except asyncio.TimeoutError:
            print("[probe] TIMEOUT waiting for a response"); return
        d = json.loads(resp)
        print("[probe] response top-level keys:", list(d.keys()))
        # error surface (Hume returns {"error":...} or a job/warning envelope)
        if "error" in d or (len(d) == 1 and "code" in d):
            print("[probe] ERROR:", json.dumps(d)[:600]); return
        for model in ("prosody", "burst"):
            block = d.get(model)
            if block is None:
                print(f"[probe] {model}: (absent)"); continue
            if "error" in block:
                print(f"[probe] {model}: ERROR ->", str(block["error"])[:200]); continue
            preds = (block.get("predictions") or []) if isinstance(block, dict) else []
            print(f"[probe] {model}: {len(preds)} prediction(s)")
            for i, p in enumerate(preds[:3]):
                emo = sorted(p.get("emotions", []), key=lambda e: -e.get("score", 0))[:6]
                t = p.get("time") or {}
                print(f"    #{i} t={t}  top:", ", ".join(f"{e['name']}={e['score']:.2f}" for e in emo))
        # dump a trimmed raw sample so we capture the exact wire shape
        print("[probe] raw[:700]:", json.dumps(d)[:700])


if __name__ == "__main__":
    if not KEY:
        print("HUME_API_KEY missing from .env"); sys.exit(1)
    path = sys.argv[1] if len(sys.argv) > 1 else "ab_out/brielle-bri-castellano-inworld__anthropic-claude-haiku-4-5.wav"
    asyncio.run(probe(path))
