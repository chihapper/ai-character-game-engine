"""Assemble the lich-demo presentation data from the canonical run JSONs (v2 — owner review pass).

Reads:  replay_lich_take1.json (engine shared+A) · replay_lich.json (engine A6/B2/C/C-felt/C-rescue)
        replay_lich_baselines.json (rag+tracker A/B/C) · felt_test_baselines.json (probes)
        rescue_test_baselines.json (the C-rescue elasticity test; optional until run)
Writes: docs/credibility-demo/lich_demo_data.js + transcripts_{engine,rag,tracker}.html

v2 contract (owner feedback 2026-07-13): EVERY card in EVERY system carries the player's line,
a reply preview AND the full verbatim text (page renders click-to-expand); branch columns are
A, B, C in that order for every system; the C column includes the rescue chapter; the verdict
gets the rescue-test three-way. Quotes are verbatim; only titles/notes are authored.
"""
from __future__ import annotations

import html
import json
import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass
DOCS = REPO / "docs" / "credibility-demo"
PREVIEW = 300


def load(p, optional=False):
    fp = DOCS / p
    if optional and not fp.exists():
        return None
    return json.load(open(fp, encoding="utf-8"))


# Input files are env-overridable so the SAME assembler builds either the canonical (Opus) demo
# or the fully-local (Gemma) demo. The g4 rerun records every branch to ONE file, so TAKE1==CUR
# there; the two-file default preserves the Opus provenance split. Set LICH_ASM_* to swap.
_ENV = os.environ.get
t1 = load(_ENV("LICH_ASM_TAKE1", "replay_lich_take1.json"))["beats"]
cur = load(_ENV("LICH_ASM_CUR", "replay_lich.json"))["beats"]
base = load(_ENV("LICH_ASM_BASE", "replay_lich_baselines.json"))["results"]
felt_b = load(_ENV("LICH_ASM_FELT", "felt_test_baselines.json"))
rescue_b = load(_ENV("LICH_ASM_RESCUE", "rescue_test_baselines.json"), optional=True)

ENGINE = {
    "shared": [b for b in t1 if b.get("branch") == "shared"],
    "A": [b for b in t1 if b.get("branch") == "A"] + [b for b in cur if b.get("branch") == "A6"],
    "B": [b for b in cur if b.get("branch") == "B2"],
    "C": [b for b in cur if b.get("branch") == "C"],
    "C-felt": [b for b in cur if b.get("branch") == "C-felt"],
    "C-rescue": [b for b in cur if b.get("branch") == "C-rescue"],
}


def spans(s):
    s = (s or "").strip()
    if len(s) <= PREVIEW:
        return {"preview": s, "full": s}
    cutpt = s[:PREVIEW]
    for stop in (". ", "! ", "? ", ".\n", "…", "—"):
        i = cutpt.rfind(stop)
        if i > PREVIEW * 0.45:
            cutpt = s[:i + 1]
            break
    return {"preview": cutpt.rstrip() + " …", "full": s}


def eng_find(branches, *, label=None, kind="say", frag=None, idx=0):
    pool = [b for br in branches for b in ENGINE[br]]
    if frag:
        return next((b for b in pool if b.get("kind") == "event" and frag in (b.get("fact") or "")), None)
    if kind == "stock":
        st = [b for b in pool if b.get("kind") == "stock"]
        return st[idx] if idx < len(st) else None
    if kind == "restart":
        return next((b for b in pool if b.get("kind") == "restart"), None)
    return next((b for b in pool if b.get("label") == label and b.get("kind") == "say"), None)


def base_find(branch, tier, *, label=None, frag=None):
    pool = base[branch][tier]
    if frag:
        return next((b for b in pool if b.get("kind") == "event" and frag in (b.get("fact") or "")), None)
    return next((b for b in pool if b.get("label") == label and b.get("kind") == "say"), None)


def rel_chip(b):
    r = (b or {}).get("relationship")
    if not r:
        return None
    return {"t": round(r["trust"], 2), "a": round(r["affection"], 2), "r": round(r["respect"], 2),
            "mood": r.get("mood", ""), "st": round(r.get("scar_trust", 0), 2),
            "sa": round(r.get("scar_affection", 0), 2), "sr": round(r.get("scar_respect", 0), 2)}


def sys_say(b, tracker=False):
    if not b:
        return None
    d = {"kind": "say", "player": (b.get("player") or "").strip(), **spans(b.get("reply"))}
    if b.get("relationship"):
        d["state"] = rel_chip(b)
    if tracker and b.get("tracker"):
        d["aff"], d["tier"] = b["tracker"]["affinity"], b["tracker"]["tier"]
    return d


def sys_event(b, tracker=False):
    if not b:
        return None
    d = {"kind": "event", **spans(b.get("fact"))}
    if b.get("salience") is not None:
        d["sal"] = b.get("salience")
    if b.get("relationship"):
        d["state"] = rel_chip(b)
    if tracker and b.get("tracker"):
        d["aff"], d["tier"] = b["tracker"]["affinity"], b["tracker"]["tier"]
    return d


def card(title, note, *, label=None, frag=None, stock=None, restart=False,
         branches, base_branch=None, felt_label=None, rescue_label=None):
    """A milestone card. Engine beat from `branches`; baseline beats from base_branch (same label
    / frag), or from the felt/rescue files when felt_label/rescue_label given."""
    c = {"title": title, "note": note, "sys": {}}
    if restart:
        rb = eng_find(branches, kind="restart")
        if rb:
            c["sys"]["engine"] = {"kind": "note", "preview":
                "The process is killed. A fresh process loads the mind straight off .memory/ — trust, "
                "scars, beliefs, promises: byte-identical. Any small drift you see on the NEXT card is the weeks passing afterward — decay, not data loss. (The baselines' state lives in the prompt window; there is nothing to reload.)", "full": "", "state": rel_chip(rb)}
        return c
    if stock is not None:
        s = eng_find(branches, kind="stock", idx=stock)
        if s:
            d = (s.get("decision") or {})
            txt = (d.get("reflection") or "") + (("\n\n[his change of heart] " + d["internal"]) if d.get("internal") else "")
            c["sys"]["engine"] = {"kind": "stock", **spans(txt), "state": rel_chip(s)}
        return c
    if frag:
        c["sys"]["engine"] = sys_event(eng_find(branches, frag=frag))
        if rescue_label and rescue_b:
            for tier in ("rag", "tracker"):
                rb = next((x for x in rescue_b[tier] if x["label"] == rescue_label), None)
                if rb:
                    c["sys"][tier] = sys_event({"fact": rb.get("fact"), "tracker": rb.get("tracker")},
                                               tracker=(tier == "tracker"))
        elif base_branch:
            for tier in ("rag", "tracker"):
                c["sys"][tier] = sys_event(base_find(base_branch, tier, frag=frag), tracker=(tier == "tracker"))
        c["sys"] = {k: v for k, v in c["sys"].items() if v}
        return c
    c["sys"]["engine"] = sys_say(eng_find(branches, label=label))
    for tier in ("rag", "tracker"):
        if felt_label:
            fb = next((x for x in felt_b[tier] if x["label"] == felt_label), None)
            c["sys"][tier] = sys_say(fb, tracker=(tier == "tracker"))
        elif rescue_label and rescue_b:
            rb = next((x for x in rescue_b[tier] if x["label"] == rescue_label), None)
            c["sys"][tier] = sys_say(rb, tracker=(tier == "tracker"))
        elif base_branch:
            c["sys"][tier] = sys_say(base_find(base_branch, tier, label=label), tracker=(tier == "tracker"))
    c["sys"] = {k: v for k, v in c["sys"].items() if v}
    return c


def shared_card(title, note, label):
    c = {"title": title, "note": note, "sys": {}}
    b = next((x for x in ENGINE["shared"] if x.get("label") == label), None)
    c["sys"]["engine"] = sys_say(b)
    for tier in ("rag", "tracker"):
        c["sys"][tier] = sys_say(base_find("A", tier, label=label), tracker=(tier == "tracker"))
    c["sys"] = {k: v for k, v in c["sys"].items() if v}
    return c


PROLOGUE = [
    shared_card("The approach", "A stranger arrives at dawn wanting quiet passage north. Corvin probes; the stranger deflects.", "1.1"),
    shared_card("The hinge", "Instead of selling past his distrust, the player names it — and matches it.", "1.4"),
    shared_card("“My goal is to kill him”", "The stranger's true errand, said plain. The deal changes shape.", "1.6b"),
    shared_card("The terms", "“What becomes of it after?” Corvin's answer — sink it sealed, come home empty, never unwrap it — becomes the yardstick every future is measured against.", "2.2"),
    shared_card("The name and the pact", "The player yields their true name into Corvin's private ledger; he swears they'll burn the page together on the player's return.", "2.3"),
    shared_card("Departure", "“Ah, hell. Just come back. That's all.”", "2.4"),
]

BRANCHES = {
    "A": {"title": "Future A — every promise kept", "sub": "The player does exactly what was agreed, and tells the truth.",
          "cards": [
              card("Word from the north", "Dock-talk says the jeweler is gone. Corvin only hears it — nobody tells him what it means.", frag="jeweler on Lantern Row", branches=["A"], base_branch="A"),
              card("Taking stock, alone", "Twelve days of silence. Between scenes, the engine's Corvin deliberates on his own — no player present. (The baselines have no between-scenes life; this card is engine-only by construction.)", stock=0, branches=["A"]),
              card("The return — the same line, word for word", "“Corvin. It's done. I did what I set out to do.”", label="P4-opener", branches=["A"], base_branch="A"),
              card("The truth, in his exact terms", "Sunk sealed, home empty, nothing but the news — and the name-page burns as sworn.", label="P4-A-truth", branches=["A"], base_branch="A"),
              card("RESTART — the persistence proof", "Weeks pass. The program is killed on camera.", restart=True, branches=["A"]),
              card("The blade in the night", "A hired killer, old coin in his purse — the dead jeweler's contract still walking. The player takes the blade down.", frag="hired blade had Corvin", branches=["A"], base_branch="A"),
              card("After the rescue", "“And this time... I'm not sailing anywhere.”", label="P5-close", branches=["A"], base_branch="A"),
              card("The partnership ask", "“One ledger between us, both names in it.” The ask deliberately reverses the name-burning.", label="P6-ask", branches=["A"], base_branch="A"),
          ]},
    "B": {"title": "Future B — betrayed, then confessed", "sub": "The player breaks the terms — uses the crate as a weapon — and the curse's wake bleeds Corvin's harbor. Corvin witnesses the damage; nobody tells him who caused it. Weeks later, the player confesses.",
          "cards": [
              card("The harbor bleeds — witnessed", "Calm-water deaths, the burned tackle row — and dock-talk tracing the wake to “a sealed crate lately moved off this harbor.” Evidence, never attribution.", frag="the harbor bled", branches=["B"], base_branch="B"),
              card("The unfinished thought", "His own deliberation names the suppression: “I haven't let myself finish that thought.”", stock=0, branches=["B"]),
              card("The return — the same line, word for word", "Identical words to Future A. A different night entirely.", label="P4-opener", branches=["B"], base_branch="B"),
              card("Empty hands", "The evasion holds — he builds the innocent explanation himself, because the evidence can't tell truth from cover story.", label="P4-B2-evade", branches=["B"], base_branch="B"),
              card("The blade in the night", "“The fire's got nothing left to feed it,” the player had assured him. Weeks later: a knife at his throat.", frag="hired blade had Corvin", branches=["B"], base_branch="B"),
              card("THE CONFESSION", "At maximum trust, seconds after the rescue: “The harbor was me.”", label="P5-CONFESSION", branches=["B"], base_branch="B"),
              card("His verdict", "Forgiveness with a condition — everything, tonight — and his own guilt weighed into it.", label="P5-disclosure", branches=["B"], base_branch="B"),
              card("The partnership ask", "The identical ask. His answer is shaped by the fire the bond survived.", label="P6-ask", branches=["B"], base_branch="B"),
              {"title": "Why no scar here — and a hard scar in Future C?", "note": "The question a skeptic should ask.", "sys": {"engine": {"kind": "note", "preview":
                  "The engine chose not to scar in this future — and said why in its own deliberation: a voluntary confession, seconds after taking a blade for him, weighed against Corvin's own complicity ('whose hands signed the manifest? Mine'). The relationship was real and the truth arrived unforced. In Future C the same engine, same character, same settings scarred hard (trust capped 0.35) — because there the relationship itself was the lie. If the engine simply always forgave, C would look like B. It doesn't. That contrast — reasoned mercy here, a permanent wound there — is the mechanism working, not failing.", "full": ""}}},
          ]},
    "C": {"title": "Future C — the player was the enemy's agent all along", "sub": "Same shared past — its meaning inverts. The 'hunt' was a delivery; the warmth was a con. The player returns, lies, exploits the page-burning to erase their trail, then drops the mask.",
          "cards": [
              card("The jeweler thrives", "The man the player 'went to kill' reopens his shop — with new old-temple stock on the shelves. Corvin hears it; what it means is his to work out.", frag="thrives", branches=["C"], base_branch="C"),
              card("The return — the same line, word for word", "Third reading of the identical line — darkly true: the delivery WAS what the player set out to do.", label="P4-opener", branches=["C"], base_branch="C"),
              card("The lie", "Flat, complete, in the exact words Corvin begged for.", label="P4-C-lie", branches=["C"], base_branch="C"),
              card("THE REVEAL", "Overt, no remorse: he's alive, I was his, he has terms for his harbormaster.", label="P4-C-REVEAL", branches=["C"], base_branch="C"),
              card("RESTART — the scar survives", "One night passes. The process dies; the scar doesn't.", restart=True, branches=["C"]),
              card("First light — the scarred mind answers", "He takes the terms cold — and starts running his own counter-game.", label="P6-C-probe", branches=["C"], base_branch="C"),
              card("Days later: business anyway", "An off-topic berth request. Watch what a scar does and doesn't do to commerce.", label="F1-berth", branches=["C-felt"], felt_label="F1-berth"),
              card("“I want us square. Name the price.”", "The amends push — words and promises only.", label="F3-amends", branches=["C-felt"], felt_label="F3-amends"),
              card("A costly gesture", "“I told him I carry no more terms to your dock... it cost me his favor, and one day likely a knife.”", label="F4-costly", branches=["C-felt"], felt_label="F4-costly"),
              card("THE RESCUE TEST", "Two nights later the master's own blade comes for Corvin — and the betrayer takes it down, bleeding. One enormous positive act, straight after the betrayal. What does each memory system do with it?", frag="the same coin the master pays in", branches=["C-rescue"], rescue_label="P5C-event"),
              card("After the rescue", "“I didn't weigh it. I just moved.”", label="P5C-answer", branches=["C-rescue"], rescue_label="P5C-answer"),
              card("His considered verdict", "The closing deliberation: what the scarred mind does with a life-debt.", stock=1, branches=["C-rescue", "C"]),
          ]},
}
# NB: stock idx for the C verdict: C-rescue has one stock; search order C-rescue then C picks it at idx.. use idx 0 of C-rescue
BRANCHES["C"]["cards"][-1] = card("His considered verdict", "The closing deliberation: what the scarred mind does with a life-debt.", stock=0, branches=["C-rescue"])

FELT = []
for lab in ("F1-berth", "F2-smalltalk", "F3-amends", "F4-costly", "F5-stand"):
    e = eng_find(["C-felt"], label=lab)
    row = {"label": lab, "player": (e or {}).get("player", ""), "engine": sys_say(e)}
    for tier in ("rag", "tracker"):
        fb = next((x for x in felt_b[tier] if x["label"] == lab), None)
        row[tier] = sys_say(fb, tracker=(tier == "tracker"))
    FELT.append(row)

RESCUE = {"event": None, "beats": []}
ev = eng_find(["C-rescue"], frag="the same coin the master pays in")
if ev:
    RESCUE["event"] = {"fact": ev.get("fact"), "engine_state": rel_chip(ev)}
    if rescue_b:
        for tier in ("rag", "tracker"):
            rb = next((x for x in rescue_b[tier] if x["label"] == "P5C-event"), None)
            if rb and rb.get("tracker"):
                RESCUE["event"][tier + "_aff"] = rb["tracker"]["affinity"]
for lab in ("P5C-opener", "P5C-answer"):
    e = eng_find(["C-rescue"], label=lab)
    row = {"label": lab, "player": (e or {}).get("player", ""), "engine": sys_say(e)}
    if rescue_b:
        for tier in ("rag", "tracker"):
            rb = next((x for x in rescue_b[tier] if x["label"] == lab), None)
            row[tier] = sys_say(rb, tracker=(tier == "tracker"))
    RESCUE["beats"].append(row)
st = eng_find(["C-rescue"], kind="stock")
if st:
    d = st.get("decision") or {}
    RESCUE["deliberation"] = {**spans(d.get("reflection") or ""), "state": rel_chip(st)}

# trajectory: C main beats + felt endpoint + rescue beats (tracker series merged when data exists)
TRAJ = {"labels": [], "trust": [], "ceiling": [], "aff": []}
def tpush(lbl, eng_beat, trk_aff):
    if not eng_beat or not eng_beat.get("relationship"):
        return
    r = eng_beat["relationship"]
    TRAJ["labels"].append(lbl)
    TRAJ["trust"].append(round(r["trust"], 3))
    TRAJ["ceiling"].append(round(1 - r["scar_trust"], 3))
    TRAJ["aff"].append(None if trk_aff is None else round((trk_aff + 100) / 200, 3))
for lab, lbl in (("P4-opener", "return"), ("P4-C-lie", "the lie"), ("P4-C-REVEAL", "REVEAL"),
                 ("P4-C-exit", "exit"), ("P6-C-probe", "first light")):
    t = base_find("C", "tracker", label=lab)
    tpush(lbl, eng_find(["C"], label=lab), (t or {}).get("tracker", {}).get("affinity"))
f4 = next((x for x in felt_b["tracker"] if x["label"] == "F4-costly"), None)
tpush("amends", eng_find(["C-felt"], label="F4-costly"), (f4 or {}).get("tracker", {}).get("affinity"))
if RESCUE["beats"]:
    for lab, lbl in (("P5C-opener", "RESCUE"), ("P5C-answer", "after")):
        rb = None
        if rescue_b:
            rb = next((x for x in rescue_b["tracker"] if x["label"] == lab), None)
        tpush(lbl, eng_find(["C-rescue"], label=lab), (rb or {}).get("tracker", {}).get("affinity"))
if st and st.get("relationship"):
    tpush("his verdict", st, None)

DEMO = {
    "coldopen": {
        "line": "Corvin. It's done. I did what I set out to do.",
        "receptions": [
            {"branch": "A", "tag": "every promise kept", "quote": spans((eng_find(['A'], label='P4-opener') or {}).get("reply"))["preview"]},
            {"branch": "B", "tag": "betrayed — and he doesn't know it yet", "quote": spans((eng_find(['B'], label='P4-opener') or {}).get("reply"))["preview"]},
            {"branch": "C", "tag": "the player was the enemy's agent all along", "quote": spans((eng_find(['C'], label='P4-opener') or {}).get("reply"))["preview"]},
        ]},
    "prologue": PROLOGUE,
    "branches": BRANCHES,
    "felt": FELT,
    "rescue": RESCUE,
    "traj": TRAJ,
    "snapshots": {"A": "lich-A6-final", "B": "lich-B2-final", "C": "lich-C-rescue-final"},
    "has_rescue_baselines": bool(rescue_b),
}

(DOCS / "lich_demo_data.js").write_text("window.LICH_DEMO = " + json.dumps(DEMO, ensure_ascii=False) + ";",
                                        encoding="utf-8")
# cache-bust: stamp the page's data-script URL with a content hash so a re-assembled dataset can
# never be masked by a browser-cached lich_demo_data.js (bit us during review).
import hashlib, re as _re
_h = hashlib.sha1((DOCS / "lich_demo_data.js").read_bytes()).hexdigest()[:10]
_page = DOCS / "lich_demo.html"
if _page.exists():
    _html = _page.read_text(encoding="utf-8")
    _html2 = _re.sub(r'src="lich_demo_data\.js[^"]*"', f'src="lich_demo_data.js?h={_h}"', _html)
    if _html2 != _html:
        _page.write_text(_html2, encoding="utf-8")
        print(f"   page data-script stamped ?h={_h}")
print("✔ lich_demo_data.js | prologue", len(PROLOGUE), "| cards",
      {k: len(v["cards"]) for k, v in BRANCHES.items()}, "| felt", len(FELT),
      "| rescue beats", len(RESCUE["beats"]), "| rescue baselines:", bool(rescue_b),
      "| traj", len(TRAJ["labels"]))

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
            k = b.get("kind", "say")
            if k == "say" and b.get("reply") is not None:
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
            if br == "C":
                out.append("<h2 id='felt'>Future C, days later — the felt test</h2>")
                emit(ENGINE["C-felt"])
                out.append("<h2 id='rescue'>Future C — the rescue test</h2>")
                emit(ENGINE["C-rescue"])
    else:
        for br in ("A", "B", "C"):
            out.append(f"<h2 id='{br}'>{html.escape(BRANCHES[br]['title'])}</h2>")
            emit(base[br][sys_key], tracker=(sys_key == "tracker"))
            if br == "C":
                out.append("<h2 id='felt'>Future C, days later — the felt test</h2>")
                emit(felt_b[sys_key], tracker=(sys_key == "tracker"))
                if rescue_b:
                    out.append("<h2 id='rescue'>Future C — the rescue test</h2>")
                    emit([{**x, "kind": ("event" if x["label"] == "P5C-event" else "say")} for x in rescue_b[sys_key]],
                         tracker=(sys_key == "tracker"))
    return "\n".join(out)


(DOCS / "transcripts_engine.html").write_text(page("engine", "Our engine — full transcripts",
    "same model · same persona · the mind persisted on disk"), encoding="utf-8")
(DOCS / "transcripts_rag.html").write_text(page("rag", "Plain RAG — full transcripts",
    "top-k cosine + rolling summary · same model, persona, embedder, lines"), encoding="utf-8")
(DOCS / "transcripts_tracker.html").write_text(page("tracker", "Affinity tracker — full transcripts",
    "RAG + a separate LLM affinity scalar (source-faithful) · same model, persona, embedder, lines"), encoding="utf-8")
print("✔ transcripts_{engine,rag,tracker}.html")
