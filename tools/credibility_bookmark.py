"""Durable, git-tracked bookmarks of a Credibility-demo mind — reproduce a demo direction
even after the working .memory/ is wiped, or the project pivots.

    python -m tools.credibility_bookmark save waterdeep-passage      # current mind -> repo (tracked)
    python -m tools.credibility_bookmark list
    python -m tools.credibility_bookmark restore waterdeep-passage   # repo -> .memory/ (then restart server)

Why not just .memory/snapshots/? Those are gitignored and get overwritten (pre-live, pre-web,
arc-baseline are working scratch). A bookmark is copied into docs/credibility-demo/bookmarks/<name>/
which IS tracked in git — so the exact mind (memories + relationship + beliefs + intent), a
human-readable transcript, and metadata are versioned and restorable forever.

Restoring copies the mind onto .memory/ and invalidates the in-process cache; restart the
free-hand server (python -m tools.credibility_live_server) so it reloads and re-seeds the clock.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import pathlib
import re
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

MEM = REPO / ".memory"
BOOKMARKS = REPO / "docs" / "credibility-demo" / "bookmarks"
DEFAULT_SLUG = "corvin-ashgrave-inworld"


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                                       text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _mind_files(slug: str) -> list[pathlib.Path]:
    # the mind = the flat per-namespace files (NOT the snapshots/ subdir)
    return [pathlib.Path(p) for p in glob.glob(str(MEM / f"{slug}.*")) if pathlib.Path(p).is_file()]


def _reply_of(text: str) -> tuple[str, str]:
    parts = re.split(r"\nMe:", text, maxsplit=1)
    user = parts[0].replace("User:", "", 1).strip() if parts else ""
    reply = parts[1].strip() if len(parts) > 1 else ""
    return user, reply


def _build_transcript(jsonl: pathlib.Path, rel: dict, meta: dict) -> str:
    recs = [json.loads(l) for l in jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    L = [f"# {meta['name']} — bookmarked transcript", "",
         f"*Character: {meta['slug']} · saved {meta['saved_at']} · git {meta['git_commit']}*", "",
         (f"**State:** affection {rel['affection']:.2f} · trust {rel['trust']:.2f} · "
          f"respect {rel['respect']:.2f} · mood *{rel.get('mood', '')}* · scars a/t/r "
          f"{rel['scar_affection']:.2f}/{rel['scar_trust']:.2f}/{rel['scar_respect']:.2f} · "
          f"{rel.get('turns')} turns"), "", "---", ""]
    n = 0
    for r in recs:
        if r.get("kind") == "exchange":
            n += 1
            u, rep = _reply_of(r.get("text", ""))
            cut = bool(rep) and not rep.rstrip().endswith((".", "!", "?", '"', "”", ")", "…", ":"))
            L += [f"**{n}. You:** {u}", "", f"**Corvin:** {rep}" + (" **[cut off]**" if cut else ""), ""]
        elif r.get("kind") == "belief":
            L += [f"> 💭 *belief consolidated:* {r.get('text', '').strip()}", ""]
    return "\n".join(L)


def save(name: str, slug: str, note: str) -> None:
    files = _mind_files(slug)
    if not files:
        raise SystemExit(f"no mind files for '{slug}' in {MEM}")
    dst = BOOKMARKS / name
    (dst / "mind").mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, dst / "mind" / f.name)
    rel = json.loads((MEM / f"{slug}.relationship.json").read_text(encoding="utf-8"))
    jsonl = MEM / f"{slug}.jsonl"
    n_ex = sum(1 for l in jsonl.read_text(encoding="utf-8").splitlines()
               if l.strip() and json.loads(l).get("kind") == "exchange")
    n_bel = sum(1 for l in jsonl.read_text(encoding="utf-8").splitlines()
                if l.strip() and json.loads(l).get("kind") == "belief")
    meta = {
        "name": name, "slug": slug,
        "saved_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "git_commit": _git_commit(), "note": note,
        "turns": n_ex, "beliefs": n_bel,
        "relationship": {k: rel.get(k) for k in
                         ("affection", "trust", "respect", "mood",
                          "scar_affection", "scar_trust", "scar_respect", "persistence_half_life")},
        "mind_files": [f.name for f in files],
    }
    (dst / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    (dst / "transcript.md").write_text(_build_transcript(jsonl, rel, meta), encoding="utf-8")
    (dst / "README.md").write_text(_readme(meta), encoding="utf-8")
    print(f"✔ bookmarked '{name}'  ->  {dst.relative_to(REPO)}")
    print(f"   {n_ex} turns · {n_bel} beliefs · trust {rel['trust']:.2f} · mood {rel.get('mood', '')!r}")
    print(f"   files: {', '.join(f.name for f in files)} + transcript.md + meta.json + README.md")
    print(f"   restore later:  python -m tools.credibility_bookmark restore {name}")


def restore(name: str, slug: str) -> None:
    src = BOOKMARKS / name / "mind"
    files = list(src.glob(f"{slug}.*")) if src.exists() else []
    if not files:
        raise SystemExit(f"no bookmark '{name}' (looked in {src})")
    MEM.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, MEM / f.name)
    try:  # drop any in-process cache so a running engine re-reads from disk
        from orchestrator.memory.long_term import LongTermMemory
        LongTermMemory.invalidate(slug)
    except Exception:  # noqa: BLE001
        pass
    print(f"✔ restored '{name}' -> {MEM} ({len(files)} files)")
    print("   RESTART the free-hand server so it reloads + re-seeds the clock:")
    print("     python -m tools.credibility_live_server")


def do_list() -> None:
    if not BOOKMARKS.exists():
        print("(no bookmarks yet)")
        return
    for d in sorted(p for p in BOOKMARKS.iterdir() if p.is_dir()):
        mp = d / "meta.json"
        if mp.exists():
            m = json.loads(mp.read_text(encoding="utf-8"))
            r = m.get("relationship", {})
            print(f"• {m['name']:<22} {m.get('turns', '?')} turns · trust "
                  f"{r.get('trust', '?')} · {m.get('saved_at', '')} · git {m.get('git_commit', '')}")
            if m.get("note"):
                print(f"    {m['note']}")
        else:
            print(f"• {d.name} (no meta)")


def _readme(m: dict) -> str:
    r = m["relationship"]
    return f"""# Bookmark: {m['name']}

{m.get('note', '')}

**Captured:** {m['saved_at']} · git `{m['git_commit']}` · slug `{m['slug']}`
**Mind:** {m['turns']} turns, {m['beliefs']} consolidated beliefs
**Relationship:** affection {r['affection']:.2f} · trust {r['trust']:.2f} · respect {r['respect']:.2f} · mood *{r.get('mood', '')}*
**Scars (a/t/r):** {r['scar_affection']:.2f} / {r['scar_trust']:.2f} / {r['scar_respect']:.2f}

## Restore & run this demo

```bash
python -m tools.credibility_bookmark restore {m['name']}     # copies this mind onto .memory/
python -m tools.credibility_live_server                       # then open http://127.0.0.1:8799/
```

`mind/` holds the exact persisted state (memories + relationship + beliefs + intent).
`transcript.md` is the human-readable conversation up to the bookmark.
This directory is tracked in git, so the demo survives a `.memory/` wipe or a project pivot.
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("save"); sp.add_argument("name"); sp.add_argument("--slug", default=DEFAULT_SLUG)
    sp.add_argument("--note", default="")
    rp = sub.add_parser("restore"); rp.add_argument("name"); rp.add_argument("--slug", default=DEFAULT_SLUG)
    sub.add_parser("list")
    args = ap.parse_args()
    if args.cmd == "save":
        save(args.name, args.slug, args.note)
    elif args.cmd == "restore":
        restore(args.name, args.slug)
    else:
        do_list()


if __name__ == "__main__":
    main()
