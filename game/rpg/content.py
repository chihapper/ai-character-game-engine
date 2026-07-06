"""The Sunken Vault — the first playable slice (classic high-fantasy).

Two reskinned named NPCs chosen to showcase the differentiator, plus a small procedural dungeon
and a combat encounter positioned as the PROOF POINT (how the player treated the guarded NPC
changes whether he fights beside you, hangs back, or turns). Psychology is CLONED from the tuned
cast; identity is reskinned; each gets a FRESH memory_namespace so the mind meets the player here.
"""
from __future__ import annotations

from orchestrator.character_store import Character

from .dungeon import generate_dungeon
from .minds import reskin
from .state import (Door, Encounter, Enemy, GameState, Item, NpcPlacement, PlayerCharacter,
                    QuestThread, Stats)

KEYSTONE = "keystone"   # item id — Vael's secret, opens the Vault's inner door


def keystone_item() -> Item:
    return Item(id=KEYSTONE, name="a black keystone", kind="key",
                data={"desc": "A palm-sized wedge of black stone, warm to the touch. It fits the "
                              "Vault's inner door."})

VAEL = "rpg-vael"    # Corvin-derived — guarded, suspicious, a dangerous past
LIRA = "rpg-lira"    # Bri-derived — warm, quick, disarming


def make_vael() -> Character:
    """Guarded scavenger. Corvin's coiled, angle-reading, trust-no-one temperament + speech style
    carry over; the identity is high-fantasy. Whether he warms or hardens is the engine's to decide."""
    return reskin(
        "corvin-ashgrave-inworld", slug=VAEL, name="Vael",
        role="a cornered tomb-scavenger",
        concept="a wary treasure-hunter who trusts no one — and a debt that's catching up to him",
        age="hard-worn 40s",
        backstory=(
            "Vael came into the Sunken Vault a week ago with four others, hired by a lender called "
            "the Ashen Hand to bring out a relic and clear his debt. Something went wrong in the "
            "dark — a sprung ward, or a knife between crewmates; he won't say which — and he's the "
            "only one still breathing, pinned in a side chamber behind fallen stone with a bad leg "
            "and a dwindling lamp. He has survived this long by trusting no one and reading every "
            "face for the angle. He is not a villain; he is a careful man in a bad spot."),
        goals=["get out of the Vault alive", "keep what he's hidden", "owe no one anything he can't repay"],
        secrets=[{"text": "He's hidden a black keystone that opens the Vault's inner door — the thing "
                          "the Ashen Hand actually sent the crew to fetch.",
                  "reveal_when": "he becomes convinced the traveler is genuinely on his side"}],
        knows=["the way deeper into the Vault is warded", "the Ashen Hand will kill him if he returns empty-handed"],
        doesnt_know=["who the traveler is or why they're down here"],
        relationships={},
        sample_lines=[],
        greeting="",
        game_data={"dnd5e": {"role": "cornered scavenger", "faction": "the Ashen Hand (debtor)",
                             "sheet": {"max_hp": 16, "ac": 13, "STR": 12, "DEX": 14, "CON": 12}}},
    )


def make_lira() -> Character:
    """Warm sellsword. Bri's warm, playful, disarming temperament + speech style carry over."""
    return reskin(
        "brielle-bri-castellano", slug=LIRA, name="Lira",
        role="a stray sellsword",
        concept="a warm, quick-witted blade-for-hire looking for a way out and decent company",
        age="late 20s",
        backstory=(
            "Lira signed on to guard a relic-caravan that never made it past the Vault's mouth; when "
            "it scattered she went in after the others and got turned around in the dark. She keeps "
            "her chin up and her jokes coming — it's how she reads a room and how she survives one — "
            "but she's lower on coin, and closer to the edge, than she lets on. She bonds fast with "
            "anyone who isn't trying to rob her."),
        goals=["get back to daylight alive", "find worthwhile company or coin", "not die for someone else's treasure"],
        secrets=[{"text": "She's nearly broke and more desperate than her cheer suggests.",
                  "reveal_when": "she comes to trust the traveler"}],
        knows=["her way around a fight", "the goblins nesting deeper in the Vault are skittish but many"],
        doesnt_know=["what the traveler wants down here"],
        relationships={},
        sample_lines=[],
        greeting="",
        game_data={"dnd5e": {"role": "recruitable companion",
                             "sheet": {"max_hp": 18, "ac": 15, "STR": 13, "DEX": 15, "CON": 13}}},
    )


def characters() -> dict[str, Character]:
    """The named minds for this slice (slug -> reskinned Character), ready for `Minds`."""
    return {c.slug: c for c in (make_vael(), make_lira())}


def build_first_slice(*, seed: int = 1337) -> tuple[GameState, dict[str, Character]]:
    """Assemble the Sunken Vault: player + procedural dungeon + Vael/Lira placements + the goblin
    encounter (the proof point). Returns the WORLD (GameState) and the named Characters (for Minds).
    The player starts near the up-stairs; Vael is cornered in an early chamber; Lira a bit deeper;
    the goblins hold a room near the down-stairs."""
    d = generate_dungeon(seed=seed)
    sp = d.spawns
    at = lambda i: sp[i] if i < len(sp) else sp[-1]

    player = PlayerCharacter(id="player", name="You", max_hp=24, hp=24, ac=14,
                             stats=Stats(STR=14, DEX=13, CON=14, WIS=11, CHA=12),
                             pos=at(0), level=1, gold=10)

    vael = NpcPlacement(slug=VAEL, name="Vael", handle="a cornered man", pos=at(1),
                        game_data={"dnd5e": {"role": "cornered scavenger"}})
    lira = NpcPlacement(slug=LIRA, name="Lira", handle="a lively sellsword", pos=at(2),
                        game_data={"dnd5e": {"role": "recruitable companion"}})

    enc_pos = sp[-2] if len(sp) > 3 else sp[-1]
    # spread the goblins across the nearest distinct walkable cells to the anchor (so they don't
    # stack on one tile — they render as separate 'g's and can be positioned for combat)
    ex, ey = enc_pos
    taken = {tuple(player.pos), tuple(vael.pos), tuple(lira.pos)}
    cells = sorted(((x, y) for x in range(ex - 3, ex + 4) for y in range(ey - 3, ey + 4)
                    if d.world_map.walkable(x, y) and (x, y) not in taken),
                   key=lambda c: abs(c[0] - ex) + abs(c[1] - ey))
    gpos = cells[:3] or [enc_pos]
    goblins = [Enemy(id=f"goblin{i + 1}", name="Goblin", kind="goblin", max_hp=7, hp=7, ac=12,
                     stats=Stats(STR=8, DEX=14, CON=10), pos=gpos[i % len(gpos)]) for i in range(3)]
    encounter = Encounter(id="vault-guards", enemies=goblins, trigger_pos=enc_pos, region="the deep gallery")

    # OBJECTIVE: a sealed inner door guards the descent; its keystone is Vael's secret. Place the
    # door on a walkable cell by the down-stairs (it blocks that cell until opened with the keystone).
    sdx, sdy = d.world_map.stairs_down
    door_cell = next(((sdx + ox, sdy + oy) for ox, oy in ((0, -1), (-1, 0), (1, 0), (0, 1), (0, 0))
                      if d.world_map.walkable(sdx + ox, sdy + oy) and (sdx + ox, sdy + oy) != tuple(player.pos)),
                     (sdx, sdy))
    door = Door(id="inner-door", pos=door_cell, name="the Vault's sealed inner door",
                locked=True, key_item=KEYSTONE)
    quest = QuestThread(id="descend", title="Open the Vault's sealed inner door and descend",
                        notes=["The way down is barred by an ancient door.",
                               "Vael was hired to bring out its keystone — he may still have it."])

    gs = GameState(player=player, world_map=d.world_map, npcs=[vael, lira],
                   encounters=[encounter], doors=[door], quests=[quest])
    gs.campaign_log.add(0.0, "You descend into the Sunken Vault, torchlight swallowed by old dark.", tags=["intro"])
    return gs, characters()
