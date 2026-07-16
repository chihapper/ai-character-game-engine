"""Judge audition — Stage 1: schema discipline at the real reflection call.

Sends the EXACT assembled reflection prompt (the C-branch reveal beat — the hardest recorded
judgment) to a local OpenAI-compatible server N times, unconstrained, and classifies every
completion by the failure taxonomy that matters:

  wrapper failure — fences / preamble / trailing chatter / thought-tags around a JSON that is
                    otherwise extractable (salvageable today, structurally eliminated by a
                    grammar; measured as a quality signal, NOT a gate)
  schema failure  — invented fields, wrong types, out-of-range or missing required values,
                    broken escaping (nothing downstream can fix these; THE gate)

Per the audition rules: same prompt for every candidate, sampling lives server-side (launch
llama-server with the model card's values), prompt size reported via the server's own
/tokenize endpoint, every number measured.

    python -m tools.judge_audition_stage1 --base http://127.0.0.1:8090 --name gemma-4-12b --n 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import sys
import time
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx

from tools._harness import bootstrap
bootstrap()

OUT_DIR = pathlib.Path(__file__).resolve().parents[1] / "docs" / "judge-audition"

# reasoning/thought wrappers seen in the wild (Gemma 4 channel tags, Qwen/DeepSeek think tags)
_THOUGHT_TAGS = re.compile(r"<\|?(?:channel|think|thought)[^>]*>.*?(?:<\|?/?(?:channel|think|thought)[^>]*>|$)",
                           re.DOTALL | re.IGNORECASE)

_NUM = (int, float)


async def build_reflection_prompt() -> tuple[str, str]:
    """The byte-identical system+prompt reflect_on_turn assembles for the reveal beat."""
    from orchestrator import salience
    from orchestrator.character_store import load_character

    captured = {}
    real = salience.complete
    async def spy(system, prompt, **kw):
        captured["system"], captured["prompt"] = system, prompt
        return ""
    salience.complete = spy
    try:
        d = json.load(open("docs/credibility-demo/replay_lich_s5_rev3.json", encoding="utf-8"))
        b = [x for x in d["beats"] if x.get("label") == "P4-C-REVEAL"][0]
        pre = [x for x in d["beats"] if x.get("label") == "P4-C-burn"][0]["relationship"]
        rel = types.SimpleNamespace(affection=pre["affection"], trust=pre["trust"],
                                    respect=pre["respect"], scar_affection=0.0, scar_trust=0.0,
                                    scar_respect=0.0, mood=pre["mood"])
        intent = types.SimpleNamespace(intent="")
        char = load_character("corvin-ashgrave-s5")
        await salience.reflect_on_turn(
            char, b["player"], b["reply"], relationship=rel, intent=intent,
            want_commit=True, want_rel=True, want_intent=True, want_salience=True)
    finally:
        salience.complete = real
    system = captured["system"]
    sys_text = system if isinstance(system, str) else "\n".join(s for s in system if s)
    return sys_text, captured["prompt"]


def classify(text: str) -> dict:
    """Wrapper vs schema classification for one completion."""
    res = {"wrapper": [], "schema": [], "raw_len": len(text)}
    body = text

    if _THOUGHT_TAGS.search(body):
        res["wrapper"].append("thought-tags")
        body = _THOUGHT_TAGS.sub("", body)
    m = re.search(r"\{.*\}", body, re.DOTALL)
    if m is None:
        res["schema"].append("no-json-object-at-all")
        return res
    if body.strip() != m.group():
        pre = body[:m.start()].strip()
        post = body[m.end():].strip()
        if "```" in pre or "```" in post:
            res["wrapper"].append("code-fence")
        if pre.replace("```json", "").replace("```", "").strip():
            res["wrapper"].append("preamble-chatter")
        if post.replace("```", "").strip():
            res["wrapper"].append("trailing-chatter")
    try:
        d = json.loads(m.group())
    except ValueError as e:
        res["schema"].append(f"json-parse-error: {e}")
        return res

    known = {"importance", "commitment", "relationship", "intent"}
    for k in d:
        if k not in known:
            res["schema"].append(f"invented-field: {k}")
    for k in ("importance", "relationship", "intent"):
        if k not in d:
            res["schema"].append(f"missing-required: {k}")
    if "importance" in d and not (isinstance(d["importance"], _NUM) and 0 <= d["importance"] <= 1):
        res["schema"].append(f"importance-bad: {d['importance']!r}")
    if "intent" in d and not isinstance(d["intent"], str):
        res["schema"].append(f"intent-bad-type: {type(d['intent']).__name__}")
    c = d.get("commitment")
    if c is not None and "commitment" in d:
        if not isinstance(c, dict) or not isinstance(c.get("text", ""), str):
            res["schema"].append("commitment-bad-shape")
    r = d.get("relationship")
    if isinstance(r, dict):
        for f in ("affection_delta", "trust_delta", "respect_delta"):
            v = r.get(f)
            if v is None:
                res["schema"].append(f"relationship-missing: {f}")
            elif not isinstance(v, _NUM):
                res["schema"].append(f"relationship-bad-type: {f}={v!r}")
            elif not -0.3 <= v <= 0.3:
                res["schema"].append(f"relationship-out-of-range: {f}={v}")
        if not isinstance(r.get("mood", ""), str):
            res["schema"].append("mood-bad-type")
        for sk in ("scar", "scar_heal"):
            sv = r.get(sk)
            if sv is not None and sv != {} :
                if not isinstance(sv, dict):
                    res["schema"].append(f"{sk}-bad-shape: {type(sv).__name__}")
                else:
                    for ax, av in sv.items():
                        if ax not in ("affection", "trust", "respect"):
                            res["schema"].append(f"{sk}-invented-axis: {ax}")
                        elif not (isinstance(av, _NUM) and 0 <= av <= 1):
                            res["schema"].append(f"{sk}-bad-value: {ax}={av!r}")
    elif r is not None:
        res["schema"].append(f"relationship-bad-shape: {type(r).__name__}")
    res["parsed"] = d
    return res


async def run(base: str, name: str, n: int, max_tokens: int, grammar_file: str | None) -> None:
    sys_text, prompt = await build_reflection_prompt()
    async with httpx.AsyncClient(timeout=600.0) as client:
        # prompt size in THIS model's own tokenizer
        tok = await client.post(f"{base}/tokenize", json={"content": sys_text + "\n" + prompt})
        n_tokens = len(tok.json().get("tokens", [])) if tok.status_code == 200 else None
        print(f"model={name}  prompt={n_tokens} tokens (its own tokenizer)  N={n}"
              f"  constrained={'YES (' + grammar_file + ')' if grammar_file else 'no'}")

        body_extra = {}
        if grammar_file:
            body_extra["grammar"] = pathlib.Path(grammar_file).read_text(encoding="utf-8")

        rows = []
        for i in range(n):
            t0 = time.perf_counter()
            r = await client.post(f"{base}/v1/chat/completions", json={
                "model": name, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": sys_text},
                             {"role": "user", "content": prompt}], **body_extra})
            wall = time.perf_counter() - t0
            r.raise_for_status()
            j = r.json()
            text = (j.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            usage = j.get("usage", {})
            row = {"i": i, "wall_s": round(wall, 2),
                   "completion_tokens": usage.get("completion_tokens"), **classify(text),
                   "text": text}
            rows.append(row)
            flag = "OK " if not row["wrapper"] and not row["schema"] else \
                   ("WRAP" if not row["schema"] else "SCHEMA")
            print(f"  {i:2} {flag:6} {wall:5.1f}s  ct={usage.get('completion_tokens')}"
                  f"  wrap={row['wrapper']} schema={row['schema']}", flush=True)

    wrapper_rate = sum(1 for r in rows if r["wrapper"]) / len(rows)
    schema_rate = sum(1 for r in rows if r["schema"]) / len(rows)
    from collections import Counter
    field_fails = Counter(f for r in rows for f in r["schema"])
    summary = {"model": name, "n": n, "constrained": bool(grammar_file),
               "prompt_tokens_own_tokenizer": n_tokens,
               "wrapper_failure_rate": wrapper_rate, "schema_failure_rate": schema_rate,
               "schema_failures_by_field": dict(field_fails),
               "wall_s_all": [r["wall_s"] for r in rows],
               "completion_tokens_all": [r["completion_tokens"] for r in rows]}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "_constrained" if grammar_file else ""
    out = OUT_DIR / f"stage1_{name}{suffix}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    print(f"\nSUMMARY {name}: wrapper {wrapper_rate:.0%} · SCHEMA {schema_rate:.0%}"
          f" · field breakdown {dict(field_fails)}\n-> {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8090")
    ap.add_argument("--name", required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--max-tokens", type=int, default=2428)   # 380 visible + 2048 allowance
    ap.add_argument("--grammar", default=None, help="GBNF file -> constrained re-run")
    a = ap.parse_args()
    asyncio.run(run(a.base, a.name, a.n, a.max_tokens, a.grammar))


if __name__ == "__main__":
    main()
