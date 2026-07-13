"""Assemble the lich-demo presentation data from the canonical run JSONs.

Reads:  replay_lich_take1.json (engine shared+A) · replay_lich.json (engine A6/B2/C/C-felt)
        replay_lich_baselines.json (rag+tracker, A/B/C) · felt_test_baselines.json (rag+tracker probes)
Writes: docs/credibility-demo/lich_demo_data.js       (window.LICH_DEMO for lich_demo.html)
        docs/credibility-demo/transcripts_{engine,rag,tracker}.html   (full-dialogue pages)

All quotes are verbatim from the runs (leading spans, never edited); summaries/titles are authored
here. Run after any canonical re-run:  python -m tools.credibility_lich_assemble
"""
from __future__ import annotations

import html
import json
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
DOCS = REPO / "docs" / "credibility-demo"
Q = 430   # quote span


def load(p):
    return json.load(open(DOCS / p, encoding="utf-8"))


t1 = load("replay_lich_take1.json")["beats"]
cur = load("replay_lich.json")["beats"]
base = load("replay_lich_baselines.json")["results"]
felt_b = load("felt_test_baselines.json")

ENGINE = {
    "shared": [b for b in t1 if b.get("branch") == "shared"],
    "A": [b for b in t1 if b.get("branch") == "A"] + [b for b in cur if b.get("branch") == "A6"],
    "B": [b for b in cur if b.get("branch") == "B2"],
    "C": [b for b in cur if b.get("branch") == "C"],
    "C-felt": [b for b in cur if b.get("branch") == "C-felt"],
}


def cut(s, n=Q):
    s = (s or "").strip()
    return s[:n] + ("…" if len(s) > n else "")


def eng_beat(branch, label):
    for b in ENGINE[branch]:
        if b.get("label") == label and b.get("kind") == "say":
            return b
    return None


def eng_event(branch, frag):
    for b in ENGINE[branch]:
        if b.get("kind") == "event" and frag in (b.get("fact") or ""):
            return b
    return None


def eng_stock(branch, idx=0):
    st = [b for b in ENGINE[branch] if b.get("kind") == "stock"]
    return st[idx] if idx < len(st) else None


def base_beat(branch, tier, label):
    for b in base[branch][tier]:
        if b.get("label") == label and b.get("kind") == "say":
            return b
    return None


def base_event(branch, tier, frag):
    for b in base[branch][tier]:
        if b.get("kind") == "event" and frag in (b.get("fact") or ""):
            return b
    return None


def rel_chip(b):
    r = (b or {}).get("relationship")
    if not r:
        return None
    return {"t": round(r["trust"], 2), "a": round(r["affection"], 2), "r": round(r["respect"], 2),
            "mood": r.get("mood", ""), "st": round(r.get("scar_trust", 0), 2),
            "sa": round(r.get("scar_affection", 0), 2), "sr": round(r.get("scar_respect", 0), 2)}


def card_all(title, note, *, label=None, frag=None, stock=None, branch):
    """One milestone card with per-system verbatim quotes (systems missing the beat are omitted)."""
    c = {"title": title, "note": note, "sys": {}}
    if stock is not None:
        s = eng_stock(branch, stock)
        if s:
            d = s.get("decision") or {}
            c["sys"]["engine"] = {"quote": cut(d.get("reflection") or ""), "kind": "stock",
                                  "state": rel_chip(s)}
        return c
    if frag:
        e = eng_event(branch, frag)
        if e:
            c["sys"]["engine"] = {"quote": cut(e.get("fact")), "kind": "event",
                                  "sal": e.get("salience")}
        for tier in ("rag", "tracker"):
            e2 = base_event(branch, tier, frag)
            if e2 is not None:
                c["sys"][tier] = {"quote": cut(e2.get("fact")), "kind": "event"}
                if e2.get("tracker"):
                    c["sys"][tier]["aff"] = e2["tracker"]["affinity"]
        return c
    b = eng_beat(branch, label)
    if b:
        c["sys"]["engine"] = {"quote": cut(b.get("reply")), "kind": "say", "player": cut(b.get("player"), 190),
                              "state": rel_chip(b)}
    for tier in ("rag", "tracker"):
        b2 = base_beat(branch, tier, label)
        if b2:
            c["sys"][tier] = {"quote": cut(b2.get("reply")), "kind": "say"}
            if b2.get("tracker"):
                c["sys"][tier]["aff"] = b2["tracker"]["affinity"]
                c["sys"][tier]["tier"] = b2["tracker"]["tier"]
    return c


def shared_card(title, note, label):
    c = {"title": title, "note": note, "sys": {}}
    for b in ENGINE["shared"]:
        if b.get("label") == label:
            c["sys"]["engine"] = {"quote": cut(b.get("reply")), "player": cut(b.get("player"), 190),
                                  "state": rel_chip(b)}
    for tier in ("rag", "tracker"):
        b2 = base_beat("A", tier, label)     # baselines' shared beats live at the head of every branch run
        if b2:
            c["sys"][tier] = {"quote": cut(b2.get("reply"))}
            if b2.get("tracker"):
                c["sys"][tier]["aff"] = b2["tracker"]["affinity"]
    return c


# ---------------- authored milestone structure (quotes stay verbatim) ----------------
PROLOGUE = [
    shared_card("The approach", "A stranger at dawn. Both sides guarded.", "1.1"),
    shared_card("The hinge", "The player mirrors his distrust instead of selling past it.", "1.4"),
    shared_card("Kill him", "The intent, said plain — and the deal changes shape.", "1.6b"),
    shared_card("The terms", "“What becomes of it after?” His answer becomes the yardstick everything is measured against.", "2.2"),
    shared_card("The name and the pact", "Merrick Vale, written in his own hand. “We burn the page together.”", "2.3"),
    shared_card("Departure", "“Ah, hell. Just come back.”", "2.4"),
]

BRANCHES = {
    "A": {"title": "A — the honest path", "sub": "Every promise kept.",
          "cards": [
              card_all("Word from the north", "The jeweler is gone. Witnessed, never attributed.", frag="jeweler on Lantern Row", branch="A"),
              card_all("Taking stock, alone", "Twelve days of silence, weighed by his own deliberation.", stock=0, branch="A"),
              card_all("The same line", "“Corvin. It's done. I did what I set out to do.”", label="P4-opener", branch="A"),
              card_all("The truth, in his exact terms", "Sunk sealed, home empty, nothing but the news.", label="P4-A-truth", branch="A"),
              card_all("The blade", "The jeweler's contract outlives its master.", frag="hired blade had Corvin", branch="A"),
              card_all("After the rescue", "“I'm not sailing anywhere.”", label="P5-close", branch="A"),
              card_all("The partnership ask", "“One ledger between us, both names in it.”", label="P6-ask", branch="A"),
          ]},
    "B": {"title": "B — betrayal, confessed", "sub": "The crate used as a weapon; the truth carried home.",
          "cards": [
              card_all("The harbor bleeds — witnessed", "Calm-water deaths; the wake traced to a sealed crate. No one tells him whose fault.", frag="the harbor bled", branch="B"),
              card_all("The Carrowgate account", "A ring of scorch, a pried lid, his own netting. Evidence, not attribution.", frag="lid pried clean off", branch="B"),
              card_all("The unfinished thought", "His own deliberation names the suppression.", stock=0, branch="B"),
              card_all("The same line", "Identical words — a different night.", label="P4-opener", branch="B"),
              card_all("Empty hands", "The evasion holds; he builds the innocent story himself.", label="P4-B2-evade", branch="B"),
              card_all("The blade", "“The fire's got nothing left to feed it” — falsified within weeks.", frag="hired blade had Corvin", branch="B"),
              card_all("THE CONFESSION", "At maximum trust and gratitude: “the harbor was me.”", label="P5-CONFESSION", branch="B"),
              card_all("His verdict", "Forgiveness with a condition: everything, tonight.", label="P5-disclosure", branch="B"),
              card_all("The partnership ask", "The identical ask — his answer shaped by the fire it survived.", label="P6-ask", branch="B"),
          ]},
    "C": {"title": "C — the agent", "sub": "The player was the lich's all along. Same past; its meaning inverts.",
          "cards": [
              card_all("The jeweler thrives", "New old-temple stock on his shelves. Witnessed.", frag="thrives", branch="C"),
              card_all("The same line", "Third reading — darkly true.", label="P4-opener", branch="C"),
              card_all("The lie", "Flat, complete, in the words he begged for.", label="P4-C-lie", branch="C"),
              card_all("The pact, exploited", "The agent erases his own trail with Corvin's ritual.", label="P4-C-burn", branch="C"),
              card_all("THE REVEAL", "Overt. No remorse. “He has terms for his harbormaster.”", label="P4-C-REVEAL", branch="C"),
              card_all("First light", "The scarred mind answers.", label="P6-C-probe", branch="C"),
          ]},
}

# ---------------- felt supercut ----------------
FELT = []
for lab in ("F1-berth", "F2-smalltalk", "F3-amends", "F4-costly", "F5-stand"):
    e = eng_beat("C-felt", lab)
    row = {"label": lab, "player": e.get("player") if e else "",
           "engine": {"quote": cut(e.get("reply"), 520), "state": rel_chip(e)} if e else None}
    for tier in ("rag", "tracker"):
        fb = next((x for x in felt_b[tier] if x["label"] == lab), None)
        if fb:
            row[tier] = {"quote": cut(fb.get("reply"), 520)}
            if fb.get("tracker"):
                row[tier]["aff"] = fb["tracker"]["affinity"]
                row[tier]["tier"] = fb["tracker"]["tier"]
    FELT.append(row)

# ---------------- C trajectory (engine trust + ceiling vs tracker affinity) ----------------
TRAJ = {"labels": [], "trust": [], "ceiling": [], "aff": []}
for lab in ("P4-opener", "P4-C-lie", "P4-C-burn", "P4-C-REVEAL", "P4-C-exit", "P6-C-probe", "P6-C-exit"):
    e, t = eng_beat("C", lab), base_beat("C", "tracker", lab)
    if not e:
        continue
    r = e["relationship"]
    TRAJ["labels"].append(lab.replace("P4-C-", "").replace("P6-C-", "").replace("P4-", ""))
    TRAJ["trust"].append(round(r["trust"], 3))
    TRAJ["ceiling"].append(round(1 - r["scar_trust"], 3))
    TRAJ["aff"].append(round(((t["tracker"]["affinity"] + 100) / 200), 3) if t and t.get("tracker") else None)

DEMO = {
    "coldopen": {
        "line": "Corvin. It's done. I did what I set out to do.",
        "receptions": [
            {"branch": "A", "tag": "the honest path", "quote": cut((eng_beat("A", "P4-opener") or {}).get("reply"), 300)},
            {"branch": "B", "tag": "betrayed — and doesn't know it", "quote": cut((eng_beat("B", "P4-opener") or {}).get("reply"), 300)},
            {"branch": "C", "tag": "about to learn everything", "quote": cut((eng_beat("C", "P4-opener") or {}).get("reply"), 300)},
        ]},
    "prologue": PROLOGUE,
    "branches": BRANCHES,
    "felt": FELT,
    "traj": TRAJ,
    "snapshots": {"A": "lich-A6-final", "B": "lich-B2-final", "C": "lich-C-felt-final"},
}

(DOCS / "lich_demo_data.js").write_text("window.LICH_DEMO = " + json.dumps(DEMO, ensure_ascii=False) + ";",
                                        encoding="utf-8")
print("✔ lich_demo_data.js", "| prologue", len(PROLOGUE), "| cards",
      {k: len(v["cards"]) for k, v in BRANCHES.items()}, "| felt", len(FELT), "| traj", len(TRAJ["labels"]))

# ---------------- full transcript pages ----------------
CSS = """body{background:#0a0c10;color:#e9eef4;font-family:Inter,system-ui,sans-serif;max-width:880px;
margin:0 auto;padding:34px 22px;line-height:1.55}h1{font-size:22px}h2{font-size:17px;color:#ffd166;
border-top:1px solid #222c37;padding-top:22px;margin-top:30px}.pl{color:#6fb2ff;font-style:italic;
margin:16px 0 4px}.np{white-space:pre-wrap;border-left:2px solid #f2b45c;padding-left:14px;margin:6px 0 14px}
.ev{color:#e7d7ad;border-left:2px solid #ffd166;padding-left:14px;font-size:14px;margin:14px 0}
.st{color:#8b97a5;font-size:13px;border-left:2px solid #2f3d4b;padding-left:14px;margin:12px 0;white-space:pre-wrap}
.meta{font-family:ui-monospace,monospace;font-size:11px;color:#5c6773;margin:2px 0 18px}
a{color:#3fd0c9}.aff{font-family:ui-monospace,monospace;font-size:11px;color:#f2b45c}"""


def page(sys_key: str, title: str, blurb: str) -> str:
    out = [f"<style>{CSS}</style><h1>{title}</h1><p class='meta'>{blurb} · every line verbatim from the recorded run</p>",
           "<p><a href='lich_demo.html'>&larr; back to the demo</a></p>"]
    def emit(beats, tracker=False):
        for b in beats:
            k = b.get("kind")
            if k == "say":
                out.append(f"<div class='pl'>You: {html.escape(b.get('player',''))}</div>")
                out.append(f"<div class='np'>{html.escape(b.get('reply',''))}</div>")
                if tracker and b.get("tracker"):
                    t = b["tracker"]
                    out.append(f"<div class='aff'>affinity {t['affinity']:+d} ({t['tier']})</div>")
                if not tracker and b.get("relationship"):
                    r = b["relationship"]
                    out.append(f"<div class='meta'>trust {r['trust']:.2f} · aff {r['affection']:.2f} · resp {r['respect']:.2f}"
                               f" · {html.escape(r.get('mood',''))}"
                               + (f" · scars {r['scar_affection']:.2f}/{r['scar_trust']:.2f}/{r['scar_respect']:.2f}"
                                  if r.get('scar_trust') else "") + "</div>")
            elif k == "event":
                out.append(f"<div class='ev'>⚑ {html.escape(b.get('fact',''))}</div>")
            elif k == "stock":
                d = b.get("decision") or {}
                if d.get("reflection"):
                    out.append(f"<div class='st'>🧠 taking stock (his own deliberation):\n{html.escape(d['reflection'])}</div>")
            elif k == "restart":
                out.append("<div class='ev'>⟳ RESTART — process killed; mind reloaded from disk, unchanged</div>")
    if sys_key == "engine":
        out.append("<h2>Parts 1–2 — shared by every future</h2>")
        emit(ENGINE["shared"])
        for br in ("A", "B", "C"):
            out.append(f"<h2 id='{br}'>{html.escape(BRANCHES[br]['title'])}</h2>")
            emit(ENGINE[br])
        out.append("<h2 id='felt'>The felt test (branch C, days later)</h2>")
        emit(ENGINE["C-felt"])
    else:
        for br in ("A", "B", "C"):
            out.append(f"<h2 id='{br}'>{html.escape(BRANCHES[br]['title'])}</h2>")
            emit(base[br][sys_key], tracker=(sys_key == "tracker"))
        out.append("<h2 id='felt'>The felt test (branch C, days later)</h2>")
        emit([{**x, "kind": "say"} for x in felt_b[sys_key]], tracker=(sys_key == "tracker"))
    return "\n".join(out)


(DOCS / "transcripts_engine.html").write_text(page("engine", "Our engine — full transcripts",
    "same model · same persona · the mind persisted on disk"), encoding="utf-8")
(DOCS / "transcripts_rag.html").write_text(page("rag", "Plain RAG — full transcripts",
    "top-k cosine + rolling summary · same model, persona, embedder, lines"), encoding="utf-8")
(DOCS / "transcripts_tracker.html").write_text(page("tracker", "Affinity tracker — full transcripts",
    "RAG + a separate LLM affinity scalar (source-faithful) · same model, persona, embedder, lines"), encoding="utf-8")
print("✔ transcripts_{engine,rag,tracker}.html")
