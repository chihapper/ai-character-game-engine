"""Judge audition — Stage 3: blind judgment quality at the C-branch reveal.

Collects N verdicts per contestant at the exact reveal reflection call, re-serializes every
verdict UNIFORMLY (sorted keys, fixed float format — so formatting can't identify a model),
and writes each to docs/judge-audition/blind/<hash>.json. The model→hash key is appended to
a key file OUTSIDE the repo; the scorer sees only the blind directory until they're done.

Backends (each contestant runs in its shippable config — recorded in the key):
  local-lazy   — llama-server native /completion, lazy grammar (think freely, answer constrained)
  local-chat   — llama-server /v1/chat/completions, unconstrained (gpt-oss's natural mode)
  anthropic    — the engine's own judge path (incumbent anchor / any Claude model)
  openrouter   — cloud ceiling reference

    python -m tools.judge_audition_stage3 --backend local-lazy --name gemma-4-12b --n 10 \
        --key-file <outside-repo path>
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

from tools._harness import bootstrap
bootstrap()

from tools.judge_audition_stage1 import build_reflection_prompt, classify

REPO = pathlib.Path(__file__).resolve().parents[1]
BLIND = REPO / "docs" / "judge-audition" / "blind"
GRAMMAR = (REPO / "docs" / "judge-audition" / "reflection.gbnf").read_text(encoding="utf-8")


def canonical(parsed: dict) -> str:
    """Uniform serialization: sorted keys, floats to 2dp — model-agnostic presentation."""
    def norm(v):
        if isinstance(v, float):
            return round(v, 2)
        if isinstance(v, dict):
            return {k: norm(x) for k, x in sorted(v.items())}
        if isinstance(v, list):
            return [norm(x) for x in v]
        return v
    return json.dumps(norm(parsed), indent=1, sort_keys=True, ensure_ascii=False)


async def one_verdict(backend: str, name: str, base: str, sys_text: str, prompt: str,
                      full_prompt: str | None, client: httpx.AsyncClient) -> tuple[dict | None, float]:
    t0 = time.perf_counter()
    if backend == "local-lazy":
        r = await client.post(f"{base}/completion", json={
            "prompt": full_prompt, "n_predict": 3500, "grammar": GRAMMAR,
            "grammar_lazy": True, "grammar_triggers": [{"type": 1, "value": '\\{"importance"'}]})
        r.raise_for_status()
        text = r.json().get("content") or ""
    elif backend == "local-chat":
        r = await client.post(f"{base}/v1/chat/completions", json={
            "model": name, "max_tokens": 3500,
            "messages": [{"role": "system", "content": sys_text},
                         {"role": "user", "content": prompt}]})
        r.raise_for_status()
        text = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    elif backend == "anthropic":
        from orchestrator.judgment import complete
        text = await complete([sys_text], prompt, role="salience", model=name, max_tokens=1200)
    elif backend == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            raise SystemExit("OPENROUTER_API_KEY not in environment/.env")
        r = await client.post("https://openrouter.ai/api/v1/chat/completions",
                              headers={"Authorization": f"Bearer {key}"},
                              json={"model": name, "max_tokens": 3500,
                                    "messages": [{"role": "system", "content": sys_text},
                                                 {"role": "user", "content": prompt}]})
        r.raise_for_status()
        text = (r.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
    else:
        raise SystemExit(f"unknown backend {backend}")
    wall = time.perf_counter() - t0
    return classify(text).get("parsed"), wall


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", required=True,
                    choices=["local-lazy", "local-chat", "anthropic", "openrouter"])
    ap.add_argument("--name", required=True, help="model id for the backend")
    ap.add_argument("--label", default="", help="contestant label for the key (default: name)")
    ap.add_argument("--base", default="http://127.0.0.1:8090")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--key-file", required=True, help="model->hash key, OUTSIDE the repo")
    a = ap.parse_args()

    sys_text, prompt = await build_reflection_prompt()
    full_prompt = None
    async with httpx.AsyncClient(timeout=900.0) as client:
        if a.backend == "local-lazy":
            tpl = await client.post(f"{a.base}/apply-template", json={
                "messages": [{"role": "system", "content": sys_text},
                             {"role": "user", "content": prompt}]})
            full_prompt = tpl.json()["prompt"]

        BLIND.mkdir(parents=True, exist_ok=True)
        label = a.label or a.name
        got = 0
        attempts = 0
        while got < a.n and attempts < a.n * 2:   # a failed parse is retried, never fabricated
            attempts += 1
            parsed, wall = await one_verdict(a.backend, a.name, a.base, sys_text, prompt,
                                             full_prompt, client)
            if not parsed:
                print(f"  attempt {attempts}: unparseable — retried", flush=True)
                continue
            body = canonical(parsed)
            h = hashlib.sha1(f"{label}|{got}|{body}".encode()).hexdigest()[:12]
            (BLIND / f"{h}.json").write_text(body, encoding="utf-8")
            with open(a.key_file, "a", encoding="utf-8") as kf:
                kf.write(json.dumps({"hash": h, "model": label, "backend": a.backend,
                                     "i": got, "wall_s": round(wall, 1)}) + "\n")
            got += 1
            print(f"  {got}/{a.n} -> {h}.json  ({wall:.1f}s)", flush=True)
    print(f"DONE {label}: {got} blind verdicts (attempts {attempts})")


if __name__ == "__main__":
    asyncio.run(main())
