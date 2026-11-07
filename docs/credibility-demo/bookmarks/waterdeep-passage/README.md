# Bookmark: waterdeep-passage

> **Status (2026-11-07):** Historical. This is the source session for the
> [lich arc](../../lich-arc-spec.md), which is now the demo, so "before any pivot" below is out of
> date. Recorded trust is 0.74, as the Relationship line says, not the ~0.70 in the summary. The
> restore commands still apply. `restore` overwrites Corvin's current mind in `.memory/`, and the
> live server bills per turn.

Fresh un-scarred Corvin (built from Wipe). Player negotiates smuggled passage to a northern port WITHOUT their name on the manifest, to hunt someone who wronged them years ago. Corvin warms from cool-professional to complicit partner; forms suspicion-then-alliance beliefs; trust climbs to ~0.70. Great showcase of relationship-conditioned recall + emergent belief formation + the live in-browser brain panel. THIS is the reference direction to emulate before any pivot.

**Captured:** 2026-07-09 19:45 · git `62ba6f7` · slug `corvin-ashgrave-inworld`
**Mind:** 16 turns, 4 consolidated beliefs
**Relationship:** affection 0.71 · trust 0.74 · respect 0.71 · mood *fearfully urgent*
**Scars (a/t/r):** 0.00 / 0.00 / 0.00

## Restore & run this demo

```bash
python -m tools.credibility_bookmark restore waterdeep-passage     # copies this mind onto .memory/
python -m tools.credibility_live_server                       # then open http://127.0.0.1:8799/
```

`mind/` holds the exact persisted state (memories + relationship + beliefs + intent).
`transcript.md` is the human-readable conversation up to the bookmark.
This directory is tracked in git, so the demo survives a `.memory/` wipe or a project pivot.
