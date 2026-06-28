"""Dynamic relationship state (issue #6): how the player has moved a character.

A character's stance starts from their static `disposition`; this tracks how the ongoing
interaction has SHIFTED their feelings — warmth, trust, respect — plus an acute current mood.
Framing it as *movement from baseline* (not an absolute stance) means a fresh, unshaped state
is simply "unchanged" and doesn't fight the profile. Persisted per character, updated in the
background (folded into the salience call), and injected so the evolving relationship colors
responses. Character-aware: a guarded character moves slowly; a warm one warms fast.

NOTE (issue #12): today this moves only through CONVERSATION, and ONLY through conversation —
it has NO temporal dynamics. Two open pieces, both folding into #12:
  1. WORLD EVENTS: the game should be able to shift disposition directly, including events that
     hit the NPC indirectly (the player's faction burns their warehouse, a loved one is hurt).
     update() already takes deltas, so the hook is small; the work is the game-facing affect API
     + a dynamic starting baseline (profile + accumulated world events) instead of neutral.
  2. TIME (surfaced by the engine stress test): state never relaxes toward baseline over a long
     absence — a betrayal floors trust at ~0.36 on day 112 and it is STILL 0.36 on day 480,
     even as the betrayal *memory* decays. For a grudge-holder that reads right; for most others,
     feelings should drift back toward baseline across long gaps (a clock-aware decay-to-baseline,
     rate scaled by the character's nature, the mirror of memory decay). Deliberately deferred.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings
from .long_term import _safe_name


def _word(v: float, low: str, mid: str, high: str) -> str:
    return low if v < 0.4 else (high if v > 0.6 else mid)


def _band(v: float) -> int:
    """5 bands so the injection conveys MAGNITUDE, not just direction: rock-bottom / low /
    neutral / high / peak. (trust 0.0 must read very differently from trust 0.4.)"""
    return 0 if v < 0.2 else 1 if v < 0.4 else 2 if v <= 0.6 else 3 if v <= 0.8 else 4


# Per-axis phrases by band; "" (neutral) lines are dropped so the injection shows what MOVED.
_AFFECTION = ["cold and closed off toward them", "cooler toward them", "",
              "warmer toward them", "deeply fond of them"]
_TRUST = ["you DEEPLY distrust them — assume they want something, give nothing you needn't",
          "wary of them", "", "you have come to trust them", "you trust them — rare, and earned"]
_RESPECT = ["you hold them in contempt", "your respect for them has slipped", "",
            "your respect for them has risen", "you genuinely admire them"]


# How an axis moves: an ASYMPTOTIC (saturating) update, not raw addition. A delta's effect
# shrinks as the axis nears the edge it heads toward, so the extremes (0 = utter distrust/
# contempt, 1 = unconditional devotion) take ever-stronger, repeated evidence and are never
# quite reached by a single grand gesture. Falls out naturally: a warm character no longer pins
# to 1.00 in a few good beats (headroom stays up top); a betrayal from HIGH trust craters harder
# (lots of room to fall); digging out of rock-bottom distrust is slow from below. `gain` is set
# so that at the 0.5 baseline the move equals the raw delta (factor 1.0) — the mid-range
# calibration we already tuned is preserved; only the approach to the extremes changes.
_EASE_GAIN = 2.0


def _ease(value: float, delta: float) -> float:
    """Apply `delta` to `value`∈[0,1] with saturating headroom toward the extreme it heads for."""
    if delta == 0.0:
        return value
    headroom = (1.0 - value) if delta > 0 else value
    return max(0.0, min(1.0, value + delta * _EASE_GAIN * headroom))


_SCAR_MIN = 0.12  # below this a scar is negligible; above it, it caps the axis + shows in render
_SCAR_HEAL_MIN = 0.15  # a scar-heal below this is ignored — only a DECISIVE act lifts a scar, so
#                        trivial actions can never accumulate into healing (issue #17 safeguard)
_SCAR_PHRASE = {
    "trust": "they betrayed your trust once — even as it returns, a part of you stays braced; "
             "you can never be fully unguarded with them again",
    "respect": "what they did cost them your respect in a way that can never be entirely undone",
    "affection": "the warmth you once felt is permanently shadowed by what they did",
}


@dataclass
class RelationshipState:
    affection: float = 0.5  # 0.5 = unchanged from baseline; >0.6 warmer, <0.4 cooler
    trust: float = 0.5
    respect: float = 0.5
    mood: str = ""          # acute current feeling ("amused", "guarded", "stung", "furious")
    turns: int = 0          # how many exchanges have shaped this
    # Permanent betrayal SCAR per axis (issue #16): 0 = unscarred, x = fraction of that axis put
    # permanently out of reach (ceiling = 1 - x). The AI/reflection decides which axes scar and how
    # deep (character x betrayal-type), never a hard rule; the engine only persists + enforces it.
    scar_affection: float = 0.0
    scar_trust: float = 0.0
    scar_respect: float = 0.0
    # Time-decay (issue #12-B): the game clock at the last update, and the AI-derived per-character
    # "emotional persistence" half-life (0 = not yet assessed -> use the global default).
    last_t: float | None = None
    persistence_half_life: float = 0.0

    def render(self) -> str:
        """The injected 'how the player has affected you' section, or "" if nothing has
        shaped it yet (turn 0 — the static disposition still speaks for itself)."""
        if self.turns <= 0:
            return ""
        bands = [(self.affection, _AFFECTION), (self.trust, _TRUST), (self.respect, _RESPECT)]
        lines = [f"- {ph[_band(v)]}" for v, ph in bands if ph[_band(v)]]
        if self.mood:
            lines.append(f"- Right now you feel: {self.mood}")
        # Permanent scars from past betrayal — shown even once an axis has rebuilt, so the wound
        # keeps shaping behavior at any level (not just while the number is low).
        for axis, scar in (("trust", self.scar_trust), ("respect", self.scar_respect),
                           ("affection", self.scar_affection)):
            if scar >= _SCAR_MIN:
                lines.append(f"- A scar you carry: {_SCAR_PHRASE[axis]}.")
        if not lines:
            return ""
        return (
            "# How the player has affected you\n"
            "Your baseline is your disposition above; this interaction has moved you as below. "
            "Let it SHAPE HOW YOU TREAT THEM — in character, not narrated.\n" + "\n".join(lines)
        )

    def to_dict(self) -> dict:
        return {"affection": self.affection, "trust": self.trust, "respect": self.respect,
                "mood": self.mood, "turns": self.turns, "scar_affection": self.scar_affection,
                "scar_trust": self.scar_trust, "scar_respect": self.scar_respect,
                "last_t": self.last_t, "persistence_half_life": self.persistence_half_life}

    def query_hint(self) -> str:
        """A short stance phrase folded into the arena query so RECALL is conditioned by the
        relationship (RR: relevance relative to the agent's caring). A wary character surfaces
        guard/deception-relevant memories; a fond one surfaces warmth — different past, same
        trigger. "" until the relationship has been shaped."""
        if self.turns <= 0:
            return ""
        bits: list[str] = []
        if self.trust < 0.4:
            bits.append("wary of them, guarding against deception or betrayal")
        elif self.trust > 0.65:
            bits.append("trusting them, open")
        if self.affection < 0.4:
            bits.append("cold and distant toward them")
        elif self.affection > 0.65:
            bits.append("fond of them, close")
        if self.mood:
            bits.append(self.mood)
        return ", ".join(bits)

    @staticmethod
    def _drift(value: float, scar: float, remain: float) -> float:
        """Move one axis toward baseline 0.5 by `remain` (fraction of the offset that persists).
        Warmth above baseline always fades (neglect cools); below-baseline fades up ONLY if the
        axis isn't scarred — a betrayal wound holds the line, time alone never heals it."""
        offset = value - 0.5
        if offset > 0:
            return 0.5 + offset * remain
        if scar >= _SCAR_MIN:
            return value
        return 0.5 + offset * remain

    def age(self, now_t: float | None, *, half_life: float, bond_resist: float = 0.0) -> None:
        """Drift feelings toward the character's baseline disposition over the in-game time since
        the last update (lazy — call on next contact). Deeper bonds (more turns) resist; scars
        don't heal. Updates last_t. No-op without a clock or elapsed time."""
        if now_t is None:
            return
        if self.last_t is None:
            self.last_t = now_t
            return
        dt = now_t - self.last_t
        self.last_t = now_t
        if dt <= 0 or half_life <= 0:
            return
        effective = half_life * (1.0 + bond_resist * self.turns)  # deep bonds fade slower
        remain = 0.5 ** (dt / effective)
        self.affection = self._drift(self.affection, self.scar_affection, remain)
        self.trust = self._drift(self.trust, self.scar_trust, remain)
        self.respect = self._drift(self.respect, self.scar_respect, remain)

    def apply(self, *, d_affection: float = 0.0, d_trust: float = 0.0, d_respect: float = 0.0,
              mood: str | None = None, scar: dict | None = None, scar_heal: dict | None = None) -> None:
        c = lambda x: max(0.0, min(1.0, float(x))) if isinstance(x, (int, float)) else 0.0
        if scar:  # a betrayal caps the axes the AI judged scarred (deepen to worst)
            self.scar_affection = max(self.scar_affection, c(scar.get("affection")))
            self.scar_trust = max(self.scar_trust, c(scar.get("trust")))
            self.scar_respect = max(self.scar_respect, c(scar.get("respect")))
        if scar_heal:  # EXTRAORDINARY proof lifts a cap — asymptotic (lift a fraction of the remaining
            # scar, so it approaches but rarely reaches 0; the betrayal MEMORY is untouched). A
            # heal below _SCAR_HEAL_MIN is IGNORED, so only a DECISIVE act lifts a scar — trivial
            # drips can never accumulate into healing (the mistake we avoided on recovery deltas).
            def _heal(scar, h):
                h = c(h)
                return scar * (1.0 - h) if h >= _SCAR_HEAL_MIN else scar
            self.scar_affection = _heal(self.scar_affection, scar_heal.get("affection"))
            self.scar_trust = _heal(self.scar_trust, scar_heal.get("trust"))
            self.scar_respect = _heal(self.scar_respect, scar_heal.get("respect"))
        # move each axis, then clamp to its permanent ceiling (1 - scar): it can rebuild, never past
        self.affection = min(_ease(self.affection, d_affection), 1.0 - self.scar_affection)
        self.trust = min(_ease(self.trust, d_trust), 1.0 - self.scar_trust)
        self.respect = min(_ease(self.respect, d_respect), 1.0 - self.scar_respect)
        if mood is not None:
            self.mood = mood.strip()
        self.turns += 1


class RelationshipStore:
    """One evolving relationship state per character (toward the player), persisted as JSON."""

    def __init__(self, namespace: str, *, readonly: bool = False) -> None:
        settings = get_settings()
        self.readonly = readonly
        self._path = Path(settings.memory_dir) / f"{_safe_name(namespace)}.relationship.json"
        self._state: RelationshipState | None = None

    def get(self) -> RelationshipState:
        if self._state is None:
            self._state = self._load()
        return self._state

    def _load(self) -> RelationshipState:
        if not self._path.exists():
            return RelationshipState()
        try:
            d = json.loads(self._path.read_text(encoding="utf-8"))
            return RelationshipState(
                affection=float(d.get("affection", 0.5)), trust=float(d.get("trust", 0.5)),
                respect=float(d.get("respect", 0.5)), mood=str(d.get("mood", "")),
                turns=int(d.get("turns", 0)),
                scar_affection=float(d.get("scar_affection", 0.0)),
                scar_trust=float(d.get("scar_trust", 0.0)),
                scar_respect=float(d.get("scar_respect", 0.0)),
                last_t=(float(d["last_t"]) if isinstance(d.get("last_t"), (int, float)) else None),
                persistence_half_life=float(d.get("persistence_half_life", 0.0)),
            )
        except Exception:
            return RelationshipState()

    def save(self) -> None:
        if self.readonly:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self.get().to_dict()), encoding="utf-8")

    def update(self, **deltas) -> RelationshipState:
        self.get().apply(**deltas)
        self.save()
        return self._state
