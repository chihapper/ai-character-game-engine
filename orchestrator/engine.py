"""The game-director engine core — runtime-agnostic (issues #2 / #7).

A GAME drives a character by calling `respond(RespondRequest)` and the world-state hooks
(`remember` / `commit` / `resolve_commitment`), advancing its OWN clock. The engine owns
everything an NPC needs to feel alive across that: relevance-realization recall with
game-time decay, always-injected commitments that convert to memory on close, and an evolving
relationship that conditions both tone and recall.

This is the seam the Inworld full loop wraps for voice (run_full_loop) — the same retrieve →
inject → generate → reflect cycle, minus the audio/Inworld plumbing. A headless game (no
voice) can drive it directly; see tools/game_demo.py. The only thing the host supplies is an
LLM with `stream_reply(messages, system)`.

The game's CLOCK is a single float in whatever unit the game chooses (days, hours, minutes —
just be consistent). The engine only ever takes differences, so any granularity works:
"due by midday" vs "due by end of day" are just different float values (e.g. 1.5 vs 2.0).
The one thing tied to the unit is the decay half-life (RR_DECAY_HALF_LIFE) — set it in the
same unit (a game running on hours tunes it in hours).
"""
from __future__ import annotations

import asyncio
import logging
import re

from .character_store import Character
from .config import EngineCaps, get_settings
from .context import (
    RespondRequest, build_arena_query, build_instructions, render_recent_happenings,
    render_situation, render_turn_context,
)
from .memory.commitments import CommitmentStore, render_commitments
from .memory.intent import IntentStore
from .memory.long_term import LongTermMemory
from .memory.relationship import RelationshipStore
from .memory.short_term import ShortTermMemory
from .agency import choose_action as _choose_action
from .agency import deliberate as _deliberate
from .agency import reconcile_goals as _reconcile_goals
from .consolidation import consolidate_beliefs
from .consistency import detect_contradiction
from .memory.agency_store import AgencyStore
from .salience import (
    NEUTRAL as NEUTRAL_SALIENCE,
    _character_summary, assess_event_impact, assess_persistence, reflect_on_turn, score_salience,
    score_salience_text,
)


_POSTSCRIPT = re.compile(r"\s*\[\[([^\[\]]{1,200})\]\]\s*$")


def _detach_postscript(reply: str) -> tuple[str, str | None]:
    """Split a trailing [[...]] stage-machinery line off a reply. The engine neither asks for
    nor interprets it — a game's performance rules define it (e.g. [[FACE happy@0 angry@0.6]]);
    detaching here keeps short-term history and the spoken line pure dialogue."""
    m = _POSTSCRIPT.search(reply or "")
    if not m:
        return reply, None
    return reply[: m.start()].rstrip(), m.group(1).strip()


class Engine:
    def __init__(self, character: Character, llm=None, *, readonly: bool = False,
                 caps: EngineCaps | None = None) -> None:
        # Capability snapshot, FROZEN at construction (arch review theme B): this engine's behavior
        # flags can't be reconfigured out from under it by another surface mutating the global
        # settings — and two engines with different capability sets can coexist in one process.
        self.caps = caps or EngineCaps.from_settings(get_settings())
        self.character = character
        self.llm = llm
        ns = character.memory_namespace
        self.long_term = LongTermMemory(ns, readonly=readonly)
        self.commitments = CommitmentStore(ns, readonly=readonly)
        self.relationship = RelationshipStore(ns, readonly=readonly)
        self.intent = IntentStore(ns, readonly=readonly)
        self.agency = AgencyStore(ns, readonly=readonly)  # evolving goals + last-deliberation clock (#20)
        self.short_term = ShortTermMemory(max_turns=self.caps.short_term_turns)
        self._bg_tasks: set[asyncio.Task] = set()  # background reflects (strong refs until done)
        self.last_postscript: str | None = None    # detached [[...]] stage machinery, per respond()
        # Reflection/consolidation (#9): accumulate exchanges + their importance until enough has
        # happened to be worth forming beliefs (process-lifetime; resets on restart).
        self._reflect_buffer: list[str] = []
        self._reflect_acc = 0.0

    # ---- the game's world-state seam (what the GAME pushes) ------------------------------
    async def remember(self, fact: str, *, player_role: str | None = None,
                       actor: str = "player", importance: float | None = None,
                       magnitude: float | None = None, **kw) -> float | None:
        """Push a durable world event into the character's memory (direct or indirect). It ALSO
        shifts the character's disposition toward the player when attributable — the AI judges the
        character-aware impact (deltas + a possible scar OR scar_heal):
          - `player_role` ("caused"/"benefited") — the PLAYER did it (#12-A); the player's faction
            burning a warehouse costs real trust.
          - `actor="self"` — the CHARACTER's own internal change with the player doing NOTHING (#19):
            a change of heart / transformation that can warm them or even heal a scar (forgiveness
            they reach on their own). This is the seam a game with autonomous NPC lives drives.
        With neither, it's a pure memory write (today's default).

        SALIENCE (#25): `importance` is the memory-weight (how reliably this is recalled later).
          - PIN it (pass a number) and it's honored verbatim — an explicit override (a sandbox test
            slider, an internal change's authored weight).
          - OMIT it and the CHARACTER appraises the event's PERSONAL salience for themselves
            (score_salience_text), optionally informed by a coarse objective `magnitude` hint the
            world/DM may supply — so a distant war they shrug off and a small kindness that marks
            them get the weight THEY would give them, not a blind author number.
        Appraisal is a per-write capability, not an engine assumption: a game with no world events
        never triggers it, and it's gated behind `salience_scoring` + the omitted-importance case.

        RETURNS the stored salience — the character's own appraised weight for this event. This is
        the engine's half of the reaction seam (see docs/engine-game-contract.md): the GAME reads it
        to decide, by its OWN policy, whether the event is worth interrupting the scene for (then
        calls deliberate()). Returns None only for an empty write, or when salience scoring is off
        AND `importance` wasn't pinned (a neutral default is stored; the game had no signal to gate on)."""
        if not (fact or "").strip():
            return None
        if player_role and "kind" not in kw:
            kw["kind"] = "player_event"  # mark player-attributable events so deliberation can ground on them (#22)
        if importance is None and self.caps.salience_scoring:
            # The NPC realizes how much THIS event matters to them (vs a fixed author weight).
            importance = await score_salience_text(self.character, fact, magnitude=magnitude)
        if importance is not None:
            kw["importance"] = importance  # else: long_term applies its default world-event salience
        await self.long_term.remember(fact, **kw)
        if not (self.caps.relationship_state and not self.relationship.readonly):
            return importance
        if actor == "self":
            attribution = ("the character THEMSELVES underwent this — their own change of heart, "
                           "decision, or transformation; the player did nothing")
        elif player_role:
            attribution = f"the player {player_role} this"
        else:
            return importance  # no attribution -> pure memory, no disposition shift
        now_t = kw.get("t")
        self._age_relationship(now_t)  # drift over the gap, then apply the event's shift
        rel = await assess_event_impact(
            self.character, fact, attribution=attribution, relationship=self.relationship.get())
        if rel:
            self.relationship.update(**rel)
        return importance

    def _age_relationship(self, now_t) -> None:
        """Drift feelings toward baseline over the in-game time since last contact (#12-B), using the
        character's persistence half-life (per-character if assessed, else the global default) and
        bond-depth resistance. Lazy + cheap (no LLM); a no-op without the feature or a clock."""
        c = self.caps
        if not (c.relationship_state and c.relationship_time_decay) or self.relationship.readonly:
            return
        rel = self.relationship.get()
        base = rel.persistence_half_life or c.relationship_decay_half_life
        rel.age(now_t, half_life=base, bond_resist=c.relationship_decay_bond_resist)
        self.relationship.save()

    def commit(self, text: str, **kw):
        """Declare an obligation the character has taken on."""
        return self.commitments.add(text, **kw)

    async def resolve_commitment(self, commitment_id: str, status: str, *, t: float | None = None):
        """Close a commitment (fulfilled/broken); it converts into an ordinary memory."""
        c = self.commitments.resolve(commitment_id, status)
        if c:
            await self._convert(c, t)
        return c

    # ---- autonomous agency: the character decides + acts on its OWN (issue #20) -----------
    async def deliberate(self, situation=None, *, mode: str = "free") -> dict:
        """The GAME calls this whenever it wants (no engine cadence) — between scenes, the character
        decides on its OWN what it does or how it changes from everything that's accumulated. The
        engine APPLIES the inner half (a change of heart via the #19 self-change seam, an updated
        intent, evolved goals) and RETURNS the Decision so the game can enact any `world_action`.
        `mode`: 'free' (DEFAULT — the RR-grounded character acts as it best sees fit; the stress
        pass found this is actually the MORE coherent, identity-preserving mode) or 'gated' (fewer,
        larger changes that need accumulated cause + a cheap structural skip — for games that want a
        controlled / on-rails environment or to minimize cost)."""
        now_t = situation.clock if situation else None
        last_t = self.agency.last_t()
        self._age_relationship(now_t)  # smooth Δt decay toward baseline over absence (#12); decoupled
        # from the internal path so player-trust fades evenly instead of jittering (#21).
        # Cheap structural skip: in gated mode, if nothing has happened since the last deliberation,
        # the character simply continues as they are — no LLM call.
        if mode != "free" and last_t is not None and now_t is not None:
            if not any(r.t is not None and r.t > last_t for r in self.long_term._all()):
                self.agency.mark_deliberated(now_t)
                return {"changed": False, "skipped": True, "reflection": "", "internal": "",
                        "new_intent": "", "new_goals": [], "world_action": ""}
        grounding = await self._agency_grounding(situation, now_t, last_t)
        decision = await _deliberate(self.character, grounding=grounding, mode=mode)
        if not decision:
            # A failed deliberation must NOT advance the taken-stock clock: marking here would let
            # gated mode's "nothing since last_t" skip swallow the very events this call failed to
            # consider — they'd never be deliberated on at all.
            return {"changed": False}
        self.agency.mark_deliberated(now_t)
        changed = bool(decision.get("changed"))
        if changed and decision["internal"]:  # a change of heart toward the player — via the #19 seam
            await self.remember(decision["internal"], actor="self", importance=0.85, t=now_t, kind="self_change")
        if changed and decision["new_intent"] and not self.intent.readonly:
            self.intent.update(decision["new_intent"])
        # Goal reconciliation (#29): runs whenever the character actually TAKES STOCK — not only on
        # changed=true — because standing goals can be stale relative to ALREADY-accumulated change (a
        # transformation that completed earlier, or that a prior deliberation captured only in feelings
        # while leaving the goals frozen). The focused pass is conservative: it returns goals UNCHANGED
        # unless something genuinely warrants moving. (Cost: a 2nd LLM call per real deliberation —
        # gate this for production, e.g. only when state moved materially since the last reconcile.)
        if not self.agency.readonly:
            current_goals = self.agency.goals() or list(self.character.goals)
            # The reconcile pass is the SINGLE authority on goals; feed it the deliberation's own
            # proposed new_goals as strong candidates (the character's own reasoning) so the two
            # writers don't fight. Report what was ACTUALLY stored — never surface a discarded proposal.
            reconciled = await _reconcile_goals(self.character, current_goals, grounding=grounding,
                                                reflection=decision.get("reflection", ""),
                                                proposed=decision.get("new_goals") or None)
            new_goals = reconciled if reconciled is not None else (decision.get("new_goals") or [])
            if new_goals and new_goals != current_goals:
                self.agency.set_goals(new_goals)
                decision["new_goals"] = new_goals
                changed = decision["changed"] = True  # a goal moved -> the deliberation changed something
            else:
                decision["new_goals"] = []  # goals held — report nothing, not a rejected proposal
        if changed:
            turning_point = decision["world_action"] or decision["reflection"]
            if turning_point and not self.long_term.readonly:  # remember the decision as their own
                await self.long_term.remember(f"(chose, of their own will) {turning_point}",
                                              kind="decision", importance=0.8, t=now_t)
        return decision

    async def choose_action(self, situation, options: list[str], *, model: str | None = None) -> dict:
        """The embodied-action seam, ON the engine surface (#30): pick the ONE action this character
        takes right now, chosen ONLY from the concrete `options` the game supplies (what the world
        currently affords) — but grounded in everything they've BECOME: evolved goals, near-term aim,
        feelings toward the player (scars included), and formed beliefs. Corvin chooses as the Corvin
        the engine knows, not as his static sheet. `situation` is the perceived scene (str or
        Situation). Returns {"action": <exact option or None>, "reason": <short, in-character>,
        "expression": <what shows on their face, free text>, "face": <neutral|happy|sad|angry|
        fear|surprise>}; the GAME executes the choice and renders (or ignores) the face —
        applied-vs-returned, per the contract. WHICH expression surfaces is psychology meeting
        the moment's relevance: unsettling characters may smile at the wrong things."""
        if not options:
            return {"action": None, "reason": ""}
        sit = situation if isinstance(situation, str) else render_situation(situation)
        parts: list[str] = []
        goals = self.agency.goals() or list(self.character.goals)
        if goals:
            parts.append("Your current goals: " + "; ".join(goals[:5]))
        aim = self.intent.get().intent
        if aim:
            parts.append("Your current near-term aim: " + aim)
        rel = self.relationship.get().render()
        if rel:
            parts.append(rel)
        beliefs = self.long_term.beliefs(limit=self.caps.beliefs_always_surface + 2)
        if beliefs:
            parts.append("Beliefs you've come to hold:\n" + "\n".join(f"- {b}" for b in beliefs))
        return await _choose_action(self.character, sit, options,
                                    grounding="\n\n".join(parts), model=model)

    async def _agency_grounding(self, situation, now_t, last_t) -> str:
        """Assemble everything the character deliberates FROM: who they are, current goals + aim,
        feelings + scars, beliefs, what's happened (esp. since they last took stock), and elapsed time."""
        goals = self.agency.goals() or self.character.goals
        parts = [_character_summary(self.character)]
        # WHERE YOU ARE, RIGHT NOW — so a self-chosen world_action is anchored to the present
        # scene, not a locale from the character's backstory. Without this, deliberation knew a
        # character's whole life but not where they physically stood, and a harbor-man's mind
        # produced "slips out of the harbormaster's office" while stranded at a ferry-inn.
        extra = getattr(situation, "extra", None) or {} if situation is not None else {}
        here = "\n".join(b for b in (
            str(getattr(situation, "location", "") or "").strip() if situation is not None else "",
            str(extra.get("Why you're here tonight", "") or "").strip(),
            str(extra.get("The world you live in", "") or "").strip()) if b)
        if here:
            parts.append("WHERE YOU ARE RIGHT NOW (any action happens in and from THIS place, "
                         "not somewhere out of your past):\n" + here)
        else:
            # No scene anchor -> world_actions can drift to a backstory locale (the "Corvin at the
            # docks" bug). The engine can't invent a place (the game owns the world), so this is a
            # caller contract violation — make it LOUD so a future ungrounded path is caught here,
            # not by a player. See docs/engine-game-contract.md.
            logging.getLogger(__name__).warning(
                "deliberate(%s) has no scene anchor (situation lacks location/world) — "
                "world_actions may drift to the sheet's backstory locale", self.character.slug)
        if goals:
            parts.append("Your current goals: " + "; ".join(goals))
        if self.intent.get().intent:
            parts.append("Your current near-term aim: " + self.intent.get().intent)
        rel = self.relationship.get().render()
        if rel:
            parts.append(rel)
        # What the player ACTUALLY did — so the character grounds claims about them in real events
        # and doesn't invent contact when the player has been absent (#22). Conflating real events is
        # fine (human); inventing a player who was never there is not.
        recs = self.long_term._all()
        # Insertion order IS arrival order (the store appends); sorting by a key that mixes
        # game-clock t with insertion index put clockless records on the wrong side of clocked ones
        # (a count is not a time). rank_window excludes these kinds by design (they render here),
        # so this window is their ONLY path into deliberation — keep it wide enough that a busy
        # scene doesn't silently drop what the player actually did.
        player_items = [r for r in recs if r.kind in ("exchange", "player_event")]
        if player_items:
            recent = "\n".join(f"- {r.text[:160]}" for r in player_items[-8:])
            note = ("What the player has ACTUALLY done with you (base anything you say about them on "
                    "this — interpret it naturally, but invent nothing beyond it):\n" + recent)
            times = [r.t for r in player_items if r.t is not None]
            last_pt = times[-1] if times else None
            if now_t is not None and last_pt is not None and now_t - last_pt > 0:
                gap = now_t - last_pt
                # A present player must not be misread as absent: weigh the gap against the RHYTHM of
                # real contact, not against zero. Only a gap that outruns their established cadence is
                # absence; a within-rhythm gap is presence. With a single establishing contact and
                # nothing since, the whole gap IS genuine, growing absence (#21/#22 — found by the Opus
                # grounding judge: weekly polling of a loyal player was stamping every off-visit tick
                # as abandonment and cratering earned trust).
                uniq = sorted(set(times))
                intervals = [b - a for a, b in zip(uniq, uniq[1:]) if b - a > 0]
                typical = sorted(intervals)[len(intervals) // 2] if intervals else None
                if typical is not None and len(uniq) >= 2 and gap <= 2.0 * typical:
                    note += (f"\n- The player has been showing up steadily — {len(uniq)} times now, the "
                             f"last {gap} ago, about the rhythm you've come to expect. This is presence, "
                             f"not silence; do not mistake a normal gap between visits for abandonment.")
                elif typical is not None and len(uniq) >= 2:
                    note += (f"\n- The player came to you steadily ({len(uniq)} times) but the last was "
                             f"{gap} ago — longer than the ~{typical} you'd grown used to. They may be "
                             f"pulling away; weigh that as THIS character would.")
                else:
                    note += (f"\n- The player has not been present or acted since clock {last_pt} "
                             f"({gap} ago); weigh that absence as THIS character would.")
            parts.append(note)
        else:
            parts.append("The player has not interacted with you at all — invent no contact, words, "
                         "or actions from them.")
        beliefs = self.long_term.beliefs()
        if beliefs:
            parts.append("Beliefs you've come to hold:\n" + "\n".join(f"- {b}" for b in beliefs))
        # Developments since they last took stock, RR-RANKED by relevance to who they are + want now
        # (the same scorer the conversational path uses), so a high-event NPC foregrounds what bears on
        # its becoming — not merely the loudest by static importance — and the rest is acknowledged as
        # background rather than silently dropped (#24).
        stance = "; ".join(h for h in (self.relationship.get().query_hint(),
                                       self.intent.get().query_hint()) if h)
        delib_query = "  ".join([*goals[:3], stance,
                                 "taking stock of what has happened and what it means for who I am becoming"]).strip()
        foreground, tail = await self.long_term.rank_window(
            delib_query, since_t=last_t, now_t=now_t,
            exclude_kinds=("exchange", "player_event"))  # already rendered in the player-activity block
        if foreground:
            label = ("Developments since you last took stock — weigh EACH below, don't let the loudest "
                     "crowd out the rest:" if len(foreground) > 1 else "Notable thing weighing on you:")
            parts.append(label + "\n" + "\n".join(f"- {r.text[:140]}" for r in foreground))
        if tail:
            shown = "; ".join(r.text[:80] for r in tail[:4])
            more = f", and {len(tail) - 4} more" if len(tail) > 4 else ""
            parts.append("Also stirring in the background this same stretch — lesser things, there if "
                         f"you reach for them, none demanding reckoning on its own: {shown}{more}.")
        if now_t is not None and last_t is not None:
            parts.append(f"Game-time since you last took stock: {now_t - last_t}.")
        return "\n\n".join(parts)

    def _recent_happenings(self, now_t, *, exclude_texts: set[str]) -> tuple[list[str], list[str]]:
        """Working memory (#30): the FRESH, high-salience things the character would still have
        top-of-mind — events around them (world/player events) and their OWN just-taken autonomous
        acts (decisions / changes of heart) — within a short recency window of `now_t` and above the
        RR-appraised salience floor, deduped against what retrieval already surfaced, newest-last,
        capped. Returns (event_texts, own_act_texts).

        Freshness needs game-time: without a clock we can't tell what 'just' happened, so it no-ops
        (leaving those memories to ordinary RR). The window makes it TRANSIENT — an item foregrounds
        for the beat it's live in, then falls back to relevance-retrieval as the scene moves on, so it
        never accumulates or floods."""
        c = self.caps
        if now_t is None or not c.recent_happenings:
            return [], []
        window, floor, cap = (c.recent_happenings_window, c.recent_happenings_salience_floor,
                              c.recent_happenings_cap)
        ev, acts = [], []
        for r in self.long_term._all():
            if r.t is None or (now_t - r.t) > window or r.importance < floor or r.text in exclude_texts:
                continue
            if r.kind in ("world_event", "player_event"):
                ev.append(r)
            elif r.kind in ("decision", "self_change"):
                acts.append(r)
        key = lambda r: (r.t if r.t is not None else float(r.index))
        prefix = "(chose, of their own will) "  # stored decision marker -> strip for 1st-person framing
        ev_txt = [r.text for r in sorted(ev, key=key)[-cap:]]
        act_txt = [(r.text[len(prefix):] if r.text.startswith(prefix) else r.text)
                   for r in sorted(acts, key=key)[-cap:]]
        return ev_txt, act_txt

    # ---- one turn, in two halves (so any driver plugs its generation in between) ---------
    async def prepare(self, request: RespondRequest) -> tuple[str, dict]:
        """First half: expire overdue commitments, build the relationship-conditioned arena
        query, retrieve (decay-aware), and render the per-turn dynamic context (memories +
        commitments + relationship + situation) to inject. Returns (injected_context, debug)."""
        now_t = request.situation.clock if request.situation else None
        for c in self.commitments.sweep_expired(now_t):
            await self._convert(c, now_t)
        self._age_relationship(now_t)  # drift feelings toward baseline over any elapsed gap (#12-B)
        # The agent's stance toward the player: feelings (#6) AND current aim (#8) both condition
        # what's relevant — a wary, "find out who sent them" character recalls a different past.
        stance = "; ".join(h for h in (self.relationship.get().query_hint(),
                                       self.intent.get().query_hint()) if h)
        evolved_goals = self.agency.goals()  # deliberation (#20) may have shifted the life direction
        if self.caps.arena_query:
            query = build_arena_query(
                request, self.character, self.short_term.messages(),
                max_recent_turns=self.caps.arena_query_recent_turns,
                relationship_hint=stance, goals=evolved_goals,
            )
        else:
            query = request.query()
        scored = await self.long_term.retrieve_scored(query, now_t=now_t) if query else {"selected": [], "scored": []}
        # Split the recalled set: beliefs (#9) render under their own header (#14), episodic
        # memories under theirs. Fall back to the flat selected list if there's no breakdown.
        chosen = [b for b in scored.get("scored", []) if b.get("selected")]
        memories = [b["text"] for b in chosen if b.get("kind") != "belief"] if chosen else scored.get("selected", [])
        # Beliefs are durable convictions: always surface the top few (#14), plus any extra a query
        # recalled — so they colour every turn, not only when relevance happens to fish one up.
        always = self.long_term.beliefs(limit=self.caps.beliefs_always_surface)
        recalled_b = [b["text"] for b in chosen if b.get("kind") == "belief"]
        beliefs = always + [t for t in recalled_b if t not in always]
        # Working-memory foregrounding (#30): the few FRESH, high-salience developments the character
        # would still have top-of-mind — surfaced regardless of whether the query recalled them,
        # deduped vs what retrieval already returned. ADDITIVE (its own small block; doesn't shrink
        # the RR top-k or the short-term window) and transient (falls back to RR as the scene ages).
        fresh_events, fresh_acts = self._recent_happenings(now_t, exclude_texts=set(memories))
        injected = render_turn_context(
            memories=memories, beliefs=beliefs, situation=request.situation, goals=evolved_goals,
            commitments=render_commitments(self.commitments.open_items()),
            relationship=self.relationship.get().render(), intent=self.intent.get().render(),
            recent_happenings=render_recent_happenings(fresh_events, fresh_acts),
        )
        return injected, {"query": query, "memories": scored.get("selected", []), "beliefs": beliefs,
                          "scored": scored.get("scored", []), "embedder": scored.get("embedder", ""),
                          "intent": self.intent.get().intent}

    async def reflect(self, user_text: str, reply: str, situation, *,
                      memories: list[str] | None = None) -> None:
        """Second half (background-safe): salience + any detected commitment + the relationship
        shift, then persist the exchange. Does NOT touch short-term — the caller owns that, so
        it can be updated synchronously before the next turn's query reads it. `memories` are the
        ones recalled this turn, used (opt-in) to record a contradiction the player just made."""
        if not user_text or not reply or self.long_term.readonly:
            return
        c = self.caps
        now_t = situation.clock if situation else None
        if c.commitment_detection or c.relationship_state or c.intent_state:
            # The want-flags travel from THIS engine's caps — reflect_on_turn must not re-derive
            # them from process globals, or per-engine capability config silently dies (the
            # pre-Unity review found exactly that: dialogue never moved trust on any live surface).
            importance, detected, rel, intent = await reflect_on_turn(
                self.character, user_text, reply,
                relationship=self.relationship.get(), intent=self.intent.get(),
                want_commit=c.commitment_detection, want_rel=c.relationship_state,
                want_intent=c.intent_state, want_salience=c.salience_scoring)
            if detected and not self.commitments.readonly:
                self.commitments.add(detected["text"], made_t=now_t,
                                     importance=detected["significance"], due=detected["due"])
            if rel and not self.relationship.readonly:
                self.relationship.update(**rel)
            if intent is not None and not self.intent.readonly:
                self.intent.update(intent)  # "" is an explicit CLEAR (the agenda ran its course)
            # Assess this character's emotional persistence ONCE (decay rate), cached (#12-B).
            # 0.0 = the assessment failed -> leave unassessed so a later turn retries, instead of
            # pinning the global default forever as if it were this character's nature.
            if (c.relationship_state and c.relationship_time_decay and not self.relationship.readonly
                    and self.relationship.get().persistence_half_life <= 0):
                assessed = await assess_persistence(self.character)
                if assessed > 0:
                    self.relationship.get().persistence_half_life = assessed
                    self.relationship.save()
        elif c.salience_scoring:
            importance = await score_salience(self.character, user_text, reply)
        else:
            importance = NEUTRAL_SALIENCE
        await self.long_term.add_exchange(user_text, reply, importance=importance, t=now_t)
        if c.contradiction_detection and memories:
            contra = await detect_contradiction(self.character, user_text, memories)
            if contra:
                await self.long_term.remember(
                    f"the player claimed {contra['claimed']}, contradicting that {contra['remembered']}",
                    kind="contradiction", importance=c.contradiction_importance, t=now_t)
        if c.reflection_enabled:
            await self._maybe_consolidate(user_text, reply, importance, now_t)

    async def _maybe_consolidate(self, user_text: str, reply: str, importance: float,
                                 now_t: float | None) -> None:
        """Accumulate the exchange; once enough importance has piled up since the last reflection,
        compress what happened into durable BELIEFS (issue #9) and store them as salient memories
        so they persist and resurface through normal recall."""
        c = self.caps
        self._reflect_buffer.append(f"User: {user_text}\nMe: {reply}")
        self._reflect_acc += importance
        if self._reflect_acc < c.reflection_importance_threshold:
            return
        recent = self._reflect_buffer[-c.reflection_max_inputs:]
        # Snapshot what this pass CONSUMES before the await: reflection runs in the background,
        # so exchanges can land in the buffer DURING the LLM call — a blanket clear afterwards
        # would silently destroy them. Drop only the consumed slice/importance when we're done.
        consumed_n = len(self._reflect_buffer)
        consumed_acc = self._reflect_acc
        beliefs = await consolidate_beliefs(self.character, recent, existing=self.long_term.beliefs())
        if beliefs is None:
            # Transient failure — keep the accumulated window so those exchanges still get their
            # consolidation; back the accumulator off so we retry after more piles up, not hot-loop.
            self._reflect_acc = c.reflection_importance_threshold * 0.5
            return
        for b in beliefs:  # add_belief supersedes near-duplicate convictions (#15), no piling up
            await self.long_term.add_belief(b, importance=c.reflection_importance, t=now_t)
        del self._reflect_buffer[:consumed_n]
        self._reflect_acc = max(0.0, self._reflect_acc - consumed_acc)

    async def respond(self, request: RespondRequest, *, debug: bool = False):
        """Headless convenience: prepare -> generate (direct LLM) -> record short-term ->
        reflect. The voice runtime instead calls prepare()/reflect() around Inworld's own
        generation (audio in, audio out)."""
        if self.llm is None:
            raise RuntimeError("Engine.respond needs an llm; voice drivers use prepare()/reflect().")
        injected, dbg = await self.prepare(request)
        # PROMPT-CACHE LAYOUT (stable precedes volatile — prefix-match caching):
        #   system   = the character sheet ONLY, byte-identical every turn (cached breakpoint).
        #   messages = history (append-only; the adapter puts a breakpoint at its end) + the current
        #              user turn carrying the DYNAMIC per-turn context.
        # The context used to be a second system block, which changed every turn and so invalidated
        # the entire message-history cache behind it — every turn paid the 1.25x cache-write premium
        # on the whole history with zero reads. In the turn (after the last breakpoint) it costs
        # nothing extra and the history finally cache-hits. The context is NOT persisted to
        # short_term, so history stays lean and byte-stable.
        stable = build_instructions(self.character)
        user_text = request.input_text()
        # A SPOKEN player line is framed as explicit address. Unframed, a line like
        # "Barkeep: a warm meal" reads as a script speaker-label ("someone called Barkeep says...")
        # and characters answer a phantom third person — seen in playtests; a prompt rule alone
        # didn't hold. Framing removes the ambiguity by construction. Game EVENT triggers
        # (request.event) are not speech and stay unframed.
        spoken = bool(request.player_input and request.player_input.strip())
        line = f'The player says to you: "{user_text}"' if spoken else user_text
        turn = (f"<context>\n(Current context for you — your memories, state, and the scene. "
                f"Not spoken by the player.)\n{injected}\n</context>\n\n{line}"
                if injected else line)
        messages = self.short_term.messages() + [{"role": "user", "content": turn}]
        reply = await self._generate([stable], messages)
        # A game's performance rules may ask for a trailing [[...]] postscript (stage machinery:
        # e.g. what shows on the face). The engine DETACHES it — history and the returned line
        # stay pure dialogue — and exposes it verbatim; interpreting it is the game's business.
        reply, self.last_postscript = _detach_postscript(reply)
        if request.input_text() and reply:
            self.short_term.add_user(line)  # the framed form — history stays unambiguous on re-reads
            self.short_term.add_assistant(reply)
        # Reflection is background work by DESIGN (its docstring says background-safe; the voice
        # loop already runs it off the reply path) — awaiting it inline taxed every game turn with
        # 1-3 LLM calls of player-visible dead time. Opt-in (caps) because short-lived callers
        # would exit before the task lands; debug keeps it inline so the returned state is post-
        # reflect (the sandbox inspects it).
        if self.caps.background_reflection and not debug:
            task = asyncio.create_task(self._reflect_bg(request.input_text(), reply,
                                                        request.situation, dbg["memories"]))
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)
        else:
            await self.reflect(request.input_text(), reply, request.situation, memories=dbg["memories"])
        if debug:
            return reply, {**dbg, "relationship": self.relationship.get().to_dict(),
                           "commitments": [{"text": c.text, "due": c.due} for c in self.commitments.open_items()]}
        return reply

    async def _reflect_bg(self, user_text: str, reply: str, situation, memories) -> None:
        try:
            await self.reflect(user_text, reply, situation, memories=memories)
        except Exception:
            logging.getLogger(__name__).exception("background reflect failed (turn state persisted "
                                                  "without affect updates)")

    async def flush_reflection(self) -> None:
        """Await any in-flight background reflects — call at scene/run end so the last turn's
        affect updates and memory writes land before the process (or the run's story) moves on."""
        if self._bg_tasks:
            await asyncio.gather(*list(self._bg_tasks), return_exceptions=True)

    # ---- internals ----------------------------------------------------------------------
    async def _generate(self, system, messages: list[dict]) -> str:
        parts: list[str] = []
        # cache_messages=True: the conversation history repeats every turn, so cache its prefix.
        async for delta in self.llm.stream_reply(messages, system, cache_messages=True):
            parts.append(delta)
        return "".join(parts).strip()

    async def _convert(self, commitment, now_t: float | None) -> None:
        await self.long_term.remember(
            commitment.memory_text(), importance=commitment.memory_importance(),
            t=now_t, kind="commitment",
        )
