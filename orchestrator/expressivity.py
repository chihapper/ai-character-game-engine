"""Performance tags for spoken delivery — tone, vocal delivery, non-verbals, pauses.

The LLM directs its own performance with bracketed tags ([sarcastic], [whispering],
[laughs], [pause]). We deliberately DO NOT normalize these to a fixed vocabulary —
that only existed to feed Cartesia's categorical emotion enum, which we've dropped.
Instead the model's own directions pass through to the instruction-following voices
with maximal fidelity:

  * ElevenLabs v3 — inline audio tags, anywhere in the line.
  * Inworld TTS-2 — a LEADING bracket is read as natural-language steering; a bare
    adjective is wrapped into an instruction ("[sound cold]") for best effect.
  * Cartesia (deprecated) — categorical only; it just renders [laughter] and drops
    the rest. No emotion control without the old vocab.

Physical stage directions ([glares], [sits back]) are dropped everywhere; non-verbal
sounds map to each provider's token; dramatic pauses become real engine silence
(durations in timing.py). Game-agnostic — this is performance, not game logic.
"""
from __future__ import annotations

import re

from .timing import PAUSE_HINT_MS, PAUSE_TAG_MS

# Non-verbal sound roots -> (Cartesia, Inworld, ElevenLabs) tokens. Substring match,
# so "[nervous laugh]" / "[bitter chuckle]" still resolve. None = no equivalent.
_NONVERBAL_ROOTS: dict[str, tuple[str | None, str | None, str | None]] = {
    "laugh":   ("[laughter]", "[laugh]", "[laughs]"),
    "chuckle": ("[laughter]", "[laugh]", "[laughs]"),
    "giggle":  ("[laughter]", "[laugh]", "[giggles]"),
    "snicker": ("[laughter]", "[laugh]", "[laughs]"),
    "scoff":   (None, None, "[scoffs]"),
    "sigh":    (None, "[sigh]", "[sighs]"),
    "breath":  (None, "[breathe]", "[exhales]"),
    "exhale":  (None, "[breathe]", "[exhales]"),
    "gasp":    (None, None, "[gasps]"),
    "cough":   (None, "[cough]", None),
    "yawn":    (None, "[yawn]", None),
    "throat":  (None, "[clear throat]", "[clears throat]"),
    "cry":     (None, None, "[crying]"),
    "sob":     (None, None, "[crying]"),
}

# Physical-action verbs that mark a bracket as a STAGE DIRECTION (something the
# character does, not how they sound), so we drop it. Ambiguous vocal verbs like
# "lowers"/"raises" (the voice) are intentionally excluded so vocal directions survive.
_ACTION_WORDS = frozenset(
    """sits sit sat leans lean leaned leaning glares glare glared glaring drums
    drumming taps tapping turns turn turned turning steps step stepped walks walk
    walked crosses cross crossed slams slam slammed nods nod nodded shrugs shrug
    points pointing gestures gesturing paces pacing stands stood reaches reaching
    grabs grabbing folds folded stares staring rises rose glances glance smirks smirk
    frowns frown scowls winks wipes rubs clenches grips throws tosses pours slides
    picks shoulders pushes pulls reclines flops slumps stiffens""".split()
)

# Verbs that already make a bracket an instruction for Inworld (so we don't re-wrap).
_STEER_VERBS = frozenset(
    """say says speak speaks sound sounds whisper whispers whispering shout shouts
    shouting lower lowers lowered raise raises sing sings singing give gives talk
    talks growl growls hiss hisses murmur murmurs drawl drawls snarl snarls purr
    purrs mutter mutters yell yells hush soften softens""".split()
)

_BRACKET_RE = re.compile(r"\[([^\]\n]+)\]")
_LEAD_BRACKET_RE = re.compile(r"^\s*\[([^\]\n]+)\]\s*")

# A single bracket can pack several cues the model joins with commas, periods, or
# semicolons — e.g. "[A sharp, mirthless laugh]" or "[Pause. Lowers voice]". We split
# into clauses and route each on its own, so a timing cue welded to a delivery note
# can't leak into speech as one unparsed blob.
_CLAUSE_SEP_RE = re.compile(r"[,.;]")
_ARTICLES = frozenset("a an the".split())


def _clauses(inner: str) -> list[str]:
    """The cues inside a bracket, split on , . ; and stripped of blanks."""
    return [c.strip() for c in _CLAUSE_SEP_RE.split(inner) if c.strip()]


def _strip_articles(direction: str) -> str:
    """Drop a leading article so "a sharp" -> "sharp" (the voice can't perform "a")."""
    words = direction.split()
    while words and words[0].lower() in _ARTICLES:
        words = words[1:]
    return " ".join(words)


def parse_pause(text: str) -> tuple[int, str]:
    """Extra silence (ms) to hold BEFORE this line, for dramatic pacing, read from a
    leading bracket. Returns (extra_ms, rest). A pause cue is consumed for silence — even
    when welded to a delivery note in a compound bracket ("[Pause. Lowers voice]"), where
    only the pause clause is removed and the rest is left for the renderer. A pause-implying
    word inside a richer note ("[final, quiet]") adds a beat but is left in place."""
    m = _LEAD_BRACKET_RE.match(text)
    if not m:
        return 0, text
    pause_ms = 0
    kept: list[str] = []
    for clause in _clauses(m.group(1)):
        low = clause.lower()
        if low in PAUSE_TAG_MS:
            pause_ms = max(pause_ms, PAUSE_TAG_MS[low])  # a pure pause cue — consume it
            continue
        words = low.split()
        if words and words[-1] in ("pause", "beat"):
            # A compound cue ("[Playful pause]", "[long awkward pause]", "[dramatic beat]"):
            # consume the beat for real silence AND keep the manner word as the tone, so the
            # line isn't left flat. Without this the whole tag is dropped — no pause, no tone.
            ms = PAUSE_TAG_MS["beat"] if words[-1] == "beat" else PAUSE_TAG_MS["pause"]
            if "long" in words or "longer" in words:
                ms = PAUSE_TAG_MS["long pause"]
            pause_ms = max(pause_ms, ms)
            manner = [w for w in words if w not in ("pause", "beat", "long", "longer")]
            if manner:
                kept.append(" ".join(manner))
            continue
        kept.append(clause)
    for hint, ms in PAUSE_HINT_MS.items():  # pause-implying words add a beat, stay in place
        if any(hint in c.lower() for c in kept):
            pause_ms = max(pause_ms, ms)
    rest = text[m.end():]
    if kept:  # rebuild the bracket from the non-pause clauses so the renderer still sees them
        rest = f"[{', '.join(kept)}] {rest}"  # the space the lead-bracket regex ate back
    return pause_ms, rest


def _tone_of(inner: str) -> str | None:
    """The tone/delivery direction inside a bracket (e.g. "whispering", "flat,
    unimpressed"), or None if it's only a sound, a physical action, or a pure pause."""
    directions: list[str] = []
    for part in _clauses(inner):
        low = part.lower()
        if low in PAUSE_TAG_MS:
            continue
        if any(root in low for root in _NONVERBAL_ROOTS):
            continue  # a sound, not a tone
        if set(low.split()) & _ACTION_WORDS:
            continue  # a physical action, not a tone
        directions.append(low)
    return ", ".join(directions) if directions else None


def leading_tone(text: str) -> str | None:
    """The tone a line LEADS with, or None if it opens with a sound/action/no bracket.
    The pipeline carries this onto following untagged lines so the delivery doesn't snap
    back to neutral after a pause or "..."."""
    m = _LEAD_BRACKET_RE.match(text)
    return _tone_of(m.group(1)) if m else None


def split_inline_tones(text: str) -> list[str]:
    """Split a line at MID-line tone tags into sub-lines, each led by its tone — so a
    provider that can't shift tone within one utterance (Inworld) can synthesize each
    part as its own call, with a tiny beat between standing in for the change. E.g.
    "[calm] Look — [yell] get out!" -> ["[calm] Look —", "[yell] get out!"]. Sounds,
    actions, and pure pause tags are never split points."""
    cuts: list[int] = []
    seg_start = 0
    for m in _BRACKET_RE.finditer(text):
        if _tone_of(m.group(1)) is None:
            continue
        # only a split point if real words precede this tag in the current sub-line
        if any(c.isalnum() for c in text[seg_start : m.start()]):
            cuts.append(m.start())
            seg_start = m.start()
    if not cuts:
        return [text]
    bounds = [0, *cuts, len(text)]
    return [u for u in (text[a:b].strip() for a, b in zip(bounds, bounds[1:])) if u]


def _inworld_steer(direction: str) -> str:
    """Format a delivery direction as an Inworld steering instruction. A bare adjective
    ([cold]) becomes an instruction ([sound cold]); something already imperative
    ([lowers her voice to a whisper]) is kept as-is."""
    d = direction.strip().lower()
    head = d.split()[0] if d.split() else ""
    return f"[{d}]" if head in _STEER_VERBS else f"[sound {d}]"


# Meta-descriptor words that add nothing to a delivery direction but that TTS-2
# occasionally reads ALOUD instead of consuming (e.g. "[speak in a hushed style]" ->
# the voice says "style"). Strip them from Inworld directions as a safety net.
_META_WORD_RE = re.compile(r"\b(?:style|manner|fashion)\b", re.IGNORECASE)


def _strip_meta_words(direction: str) -> str:
    return re.sub(r"\s+", " ", _META_WORD_RE.sub("", direction)).strip(" ,")


# Delivery/emotion words the instruction-following voices reliably PERFORM rather than
# read out loud. This is the safety net: a bracket the model invents (a made-up or
# misspelled cue like "[Shusing]", a sound-effect like "[explosion]", or an overly
# long atmospheric phrase) is DROPPED instead of spoken. We never rewrite the model's
# wording — a recognized tag passes through verbatim; only the risky ones are dropped.
# Generous on purpose, and the per-provider directives steer the model to stay inside
# it so drops stay rare. (Non-verbal SOUNDS are handled separately by _NONVERBAL_ROOTS.)
_TONE_WORDS = frozenset(
    """angry angrily mad furious furiously irate livid seething
    sad sadly sorrowful mournful mournfully grief grieving heartbroken melancholy wistful
    happy happily glad joyful joyfully gleeful giddy elated cheerful cheerfully merry sunny
    excited excitedly eager eagerly thrilled enthusiastic animated breathless breathlessly
    nervous nervously anxious anxiously uneasy jittery tense edgy worried fretful
    calm calmly serene serenely composed measured even steady level unhurried relaxed
    cold coldly cool icy frosty aloof distant detached clinical flat flatly hollow blank
    warm warmly tender tenderly gentle gently soft softly soothing kind kindly affectionate
    playful playfully teasing teasingly cheeky impish mischievous flirty flirtatious sultry
    wry wryly dry deadpan sardonic ironic sarcastic sarcastically mocking mockingly snide
    grave gravely solemn somber somberly serious sober earnest earnestly sincere heavy
    defeated defeatedly weary wearily tired exhausted resigned hopeless dejected despondent
    hopeful hopefully wistfully longing yearning pleading desperate desperately frantic frantic
    proud proudly smug smugly arrogant haughty condescending dismissive disdainful contemptuous
    ashamed guilty sheepish embarrassed bashful timid shy meek hesitant hesitantly uncertain
    confident confidently assured bold brazen commanding firm firmly stern sternly hard harsh
    afraid scared fearful frightened terrified petrified panicked alarmed wary suspicious guarded
    surprised shocked stunned startled astonished incredulous disbelieving bewildered confused
    disgusted revolted appalled horrified bitter bitterly resentful jealous envious spiteful
    menacing menacingly threatening dangerous ominous ominously sinister dark brooding grim
    low high deep faint weak quiet quietly hushed soft loud loudly booming thunderous strong
    whisper whispers whispering whispered murmur murmurs murmuring mutter mutters muttering
    shout shouts shouting yell yells yelling growl growls growling snarl snarls snarling hiss
    trembling shaky shaking quavering quaking unsteady cracking faltering halting stammering
    drawl drawls drawling drawn clipped crisp sharp sharply bright brightly lilting singsong
    rushed hurried breathy raspy gravelly throaty velvety smooth honeyed silky purring seductive
    slow slowly deliberate deliberately careful pointed emphatic intense intensely urgent urgently
    amused amusedly delighted curious thoughtful pensive reflective dreamy faraway absent
    relieved relief content peaceful gentle reverent awed reverent wondering breath taken
    venomous icy seething withering scathing cutting accusing pleading coaxing reassuring
    matter-of-fact knowing conspiratorial secretive sly coy guarded measured weary""".split()
)

# Per-provider vocabularies. ElevenLabs v3 READS unrecognized tags aloud, so it gets the
# strict set above. Inworld TTS-2 does free natural-language steering (no preset list), so
# it can perform descriptive manner words EL would just speak — those live ONLY in the
# Inworld set. Keeping them apart is the point: adding an Inworld word can never loosen EL.
# Each profile carries its own set (VoiceProfile.tone_words); edit one without touching the
# other. (Sounds/actions/pauses stay shared — they behave the same everywhere.)
_INWORLD_EXTRA = frozenset(
    "softer trailing sing song intrigue intrigued breezy airy husky smoky feigned "
    "dramatic awkward".split()
)
_EL_TONE_WORDS = _TONE_WORDS
_INWORLD_TONE_WORDS = _TONE_WORDS | _INWORLD_EXTRA

# Small fillers allowed between tone words (so "playful but firm" / "low and menacing"
# pass, and "drawn out" reduces to just "drawn"). Kept minimal on purpose: prose-y
# prepositions like "beneath"/"into" signal an atmospheric phrase, not a tag, so they
# are NOT fillers — they count as words and trip the recognizer.
_TONE_CONNECTORS = frozenset("and or but with a an the of it out off".split())
_MAX_TONE_WORDS = 4  # beyond this it's an atmospheric phrase a voice tends to read aloud


def _recognized_tone(direction: str, vocab: frozenset = _TONE_WORDS) -> bool:
    """True if we're confident a voice will PERFORM this direction rather than speak it:
    it's short, and every content word is in that provider's delivery `vocab`."""
    words = re.findall(r"[a-z]+", direction.lower())
    if not words or len(words) > _MAX_TONE_WORDS:
        return False  # an overlong phrase reads as prose; the voice voices it
    content = [w for w in words if w not in _TONE_CONNECTORS]
    return bool(content) and all(w in vocab for w in content)


# --- Per-provider voice profiles ------------------------------------------------
# All provider-specific behavior lives in ONE profile per provider: its non-verbal
# token column, how it renders a tone direction, its LLM directive, and whether the
# pipeline splits a line at mid-line tone shifts. Shared concepts (sounds, actions,
# pauses, tone-carry) live OUTSIDE the profiles. To change one provider, edit only
# its profile — the others cannot be touched by accident.

_HEADER = "# Performance tags (spoken aloud; the bracketed directions are never read out)\n"
# Tone-continuity nudge — shared by the expressive providers (the rule is the same;
# only its rendering differs per provider, via render_direction).
_CARRY = (
    "Your tone CARRIES to the following lines until you change it, so don't snap back "
    "to a flat/neutral tone after a pause or '...'. EASE big EMOTIONAL shifts — step "
    "through them (tender -> wistful -> cold), don't jump in a single beat. BUT match each "
    "sentence's OWN energy to its punctuation: a '!' lifts into excitement/emphasis, a '?' "
    "lifts with curiosity, a '.' settles — let the punctuation move you, and never flatten "
    "a '!' or '?' just because the line before it was calm or teasing.\n"
)


class VoiceProfile:
    """How one TTS provider consumes performance tags. One subclass per provider."""

    name: str = ""
    sound_idx: int = 0  # column into _NONVERBAL_ROOTS for this provider
    splits_mid_line: bool = False  # pipeline splits a line at mid-line tone shifts
    tone_words: frozenset = frozenset()  # delivery words THIS voice reliably performs

    def render_direction(self, tone: str, leading: bool) -> str | None:
        """Render a tone/delivery direction (e.g. "cold, clipped") for this provider,
        or None to drop it. `leading` = the direction opened the line."""
        return None

    def directive(self) -> str:
        """The how-to-perform instructions handed to the LLM for this provider."""
        raise NotImplementedError


class ElevenLabsProfile(VoiceProfile):
    name = "elevenlabs"
    sound_idx = 2
    splits_mid_line = False  # v3 shifts tone inline; no need to split
    tone_words = _EL_TONE_WORDS  # strict: v3 voices anything it doesn't recognize

    def render_direction(self, tone: str, leading: bool) -> str | None:
        # v3 acts on inline tags anywhere, BUT it reads unrecognized brackets out loud,
        # so a direction we're not confident it performs is dropped, not voiced.
        d = _strip_articles(tone.strip()).lower()
        return f"[{d}]" if d and _recognized_tone(d, self.tone_words) else None

    def directive(self) -> str:
        return (
            _HEADER
            + "Direct your delivery with bracketed tags, placed exactly where they apply. "
            "Keep each tag to ONE or TWO real delivery words — this voice PERFORMS known "
            "emotion/delivery words but READS OUT LOUD anything it doesn't recognize, so "
            "never invent long atmospheric phrases or sound-effects:\n"
            + "- Lead most lines with a TONE/EMOTION: [sarcastic], [cold], [tender], [wry], "
            "[grave], [giddy], [defeated], [nervous], [smug], [bitter], [playful but firm].\n"
            + "- Add DELIVERY where it sharpens things: [whispering], [shouting], [breathless], "
            "[trembling], [clipped], [low and menacing], [drawn out].\n"
            + "- Drop in SOUNDS where natural: [laughs], [giggles], [sighs], [scoffs], [gasps], [exhales].\n"
            + "- TIMING: put [pause] or [long pause] on its own line — the engine holds a beat.\n"
            + _CARRY
            + "Match every tag to the words; never stay flat. No physical actions — you are only a voice."
        )


class InworldProfile(VoiceProfile):
    name = "inworld"
    sound_idx = 1
    splits_mid_line = True  # can't shift tone within one utterance -> split + beat
    tone_words = _INWORLD_TONE_WORDS  # broader: free-form steering, performs descriptors

    def render_direction(self, tone: str, leading: bool) -> str | None:
        # Inworld reads a LEADING bracket as natural-language steering; a mid-line
        # direction can't be honored, so drop it (the pipeline splits true shifts).
        if not leading:
            return None
        d = _strip_meta_words(_strip_articles(tone.strip()).lower())
        if not d:
            return None
        # An imperative instruction ("lowers his voice", "speak low and slow") is what
        # Inworld steers on best — trust it as-is. A bare adjective ("cold") becomes a
        # "[sound cold]" instruction. Anything else (a prose fragment / made-up cue like
        # "[Shusing]") it would just read aloud, so drop it.
        if d.split()[0].lower() in _STEER_VERBS:
            return f"[{d}]"
        if _recognized_tone(d, self.tone_words):
            return _inworld_steer(d)
        return None

    def directive(self) -> str:
        return (
            _HEADER
            + "The voice carries tone ALMOST ENTIRELY through these tags — punctuation and "
            "word choice barely move it on their own, so the TAG does the work. Lead nearly "
            "EVERY sentence with a vivid DELIVERY DIRECTION that says HOW to speak. Start it "
            "with a verb (speak/whisper/lower/growl/snap/drawl) or a feeling word — then "
            "perform it:\n"
            + '- e.g. "[speak low and unhurried]", "[lower your voice, careful now]", '
            '"[whisper, conspiratorial]", "[a bright, teasing lilt, almost laughing]".\n'
            + "- DESCRIBE the manner and MATCH ITS INTENSITY to the moment — the more (and "
            "STRONGER) you describe, the more the voice moves. A bare word (\"[playful]\") "
            'barely shifts it; a vivid one moves it ("[warm and playful, a grin in your '
            'voice]"); for a BIG beat go BIG ("[practically shouting, bursting with '
            'excitement]"). You can stack a sound + a delivery at the start: '
            '"[giggling][breathless and thrilled] You know I\'m in!".\n'
            + "- ONE direction per sentence, at the very START — the voice applies a tag where "
            "a sentence begins, NOT mid-sentence. For a sudden shift, break to a NEW sentence "
            'and lead it with the new tag: "[calm] For the last time. [snap] GET OUT."\n'
            + "- Keep cues clean: don't weld a pause onto a delivery note, and use plain "
            'feeling/verb words — never tack on "style", "manner", or "in a ... way" (the '
            "voice may read those aloud). Natural sounds go inline where they fit: [laughs], "
            "[sighs], [breathes], [coughs], [clears throat]. Put a stressed word in CAPITALS.\n"
            + "- PAUSES come from PUNCTUATION or a break tag — NEVER a word-tag. Use \"...\" or "
            'an em-dash for a natural trailing beat (real speech trails off — keep those), or '
            '<break time="600ms" /> for a held silence. "[pause]"/"[pauses]" do NOTHING here; '
            'and never fold timing into a delivery note ("[pauses, whispering]" is ignored).\n'
            + "- Be GENEROUS, not sparse — a real voice keeps moving. Don't ride one tone for a "
            "whole reply: when the feeling turns, START THE NEXT SENTENCE with a fresh direction, "
            "and lace in natural sounds where a person would — [laughs], [soft laugh], [sighs], "
            "[scoffs], [hums]. Lead nearly EVERY sentence with its own fresh, vivid cue — "
            "under-tagging is exactly what makes the voice sound flat and robotic.\n"
            + _CARRY
            + "Match every direction to the words; never stay flat. No physical actions — you "
            "are only a voice."
        )


class CartesiaProfile(VoiceProfile):
    name = "cartesia"
    sound_idx = 0
    splits_mid_line = False

    def render_direction(self, tone: str, leading: bool) -> str | None:
        return None  # categorical model — no free-form direction

    def directive(self) -> str:
        return (
            _HEADER
            + "Lead most lines with a simple one-word emotion ([angry], [sad], [excited]); "
            "you may use [laughs] where it fits. This voice can't whisper or perform other "
            "vocal directions, so keep tags simple."
        )


_PROFILES: dict[str, VoiceProfile] = {
    "elevenlabs": ElevenLabsProfile(),
    "inworld": InworldProfile(),
    "cartesia": CartesiaProfile(),
}


def profile_for(provider: str) -> VoiceProfile:
    """The voice profile for a provider (defaults to Cartesia's flat behavior)."""
    return _PROFILES.get(provider, _PROFILES["cartesia"])


def splits_mid_line(provider: str) -> bool:
    """Whether the pipeline splits a line at mid-line tone shifts for this provider."""
    return profile_for(provider).splits_mid_line


def renders_tone(text: str, provider: str) -> bool:
    """True if the LEADING bracket of `text` yields real steering for this provider (vs
    being dropped). The pipeline uses this so a tone the model invents that this voice
    CAN'T perform doesn't poison tone-carry — instead the engine keeps carrying the last
    tone that actually performs, rather than snapping the following lines to flat."""
    m = _LEAD_BRACKET_RE.match(text)
    if not m:
        return False
    prof = profile_for(provider)
    for clause in _clauses(m.group(1)):
        low = clause.lower()
        if low in PAUSE_TAG_MS:
            continue
        if any(root in low for root in _NONVERBAL_ROOTS):
            continue  # a sound, not a tone
        if set(low.split()) & _ACTION_WORDS:
            continue  # a physical action, not a tone
        if prof.render_direction(clause, True):
            return True
    return False


def render_tags(text: str, provider: str) -> str:
    """Convert the model's bracket tags to what a provider can act on. Each bracket is
    split into clauses (on , . ;) and routed cue by cue: a pure pause is dropped (its
    silence is handled in the pipeline), a non-verbal sound maps to the provider's token,
    a physical action is dropped, and a delivery direction is handed to the provider's
    profile — which renders it or drops it when the voice would read it aloud instead."""
    prof = profile_for(provider)

    def repl(m: re.Match) -> str:
        leading = text[: m.start()].strip() == ""
        out: list[str] = []
        for clause in _clauses(m.group(1)):
            low = clause.lower()
            if low in PAUSE_TAG_MS:
                continue  # pure pause cue — silence is injected by the pipeline, never voiced
            matched_sound = False
            for root, tokens in _NONVERBAL_ROOTS.items():
                if root in low:
                    matched_sound = True
                    if tokens[prof.sound_idx]:
                        out.append(tokens[prof.sound_idx])
                    break
            if matched_sound:
                continue
            if set(low.split()) & _ACTION_WORDS:
                continue  # physical stage direction — never spoken or voiced
            rendered = prof.render_direction(clause, leading)
            if rendered:
                out.append(rendered)
        return " ".join(out)

    return _BRACKET_RE.sub(repl, text).strip()


def has_speakable(text: str) -> bool:
    """True if there's anything worth sending to TTS (a letter/digit somewhere)."""
    return any(ch.isalnum() for ch in text)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def performance_directive(provider: str) -> str:
    """How-to-perform instructions for the LLM, tailored to the character's voice.
    Each provider's text lives on its own profile (see VoiceProfile subclasses)."""
    return profile_for(provider).directive()
