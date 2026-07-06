"""Playable SLICES — pure CONTENT for the renderer-agnostic game-core.

A slice is DATA: a map (from a generator), a cast of reskinned minds, a WorldFlavor (all the prose
the core would otherwise hard-code), a combat encounter, and an objective (a keyed door tied to a
quest). The game-core reads every one of these from state; it authors nothing and imports nothing
from here at runtime. Adding a slice is therefore a pure-content task — see `build_emberdeep_slice`,
which shares ZERO code paths in the core with `build_first_slice` yet needed no core change.

Psychology is CLONED from the tuned cast; identity is reskinned; each NPC gets a FRESH
memory_namespace so the mind meets the player here. Register new slices in `SLICES` at the bottom.
"""
from __future__ import annotations

from orchestrator.character_store import Character

from .dungeon import generate_caverns, generate_dungeon
from .minds import reskin
from .state import (Door, Encounter, Enemy, GameState, Item, NpcPlacement, PlayerCharacter,
                    QuestThread, Stats, WorldFlavor)

# ==================================================================================================
# Shared placement helpers (so no slice re-implements spawn spreading or door placement, and so an
# authored map with no stairs / a thin cast can't crash the builder — see the seam audit).
# ==================================================================================================

def _spread_cells(world_map, anchor, n: int, taken: set) -> list:
    """`n` distinct walkable cells nearest an anchor (so enemies don't stack on one tile)."""
    ax, ay = anchor
    cells = sorted(((x, y) for x in range(ax - 3, ax + 4) for y in range(ay - 3, ay + 4)
                    if world_map.walkable(x, y) and (x, y) not in taken),
                   key=lambda c: abs(c[0] - ax) + abs(c[1] - ay))
    return cells[:n] or [anchor]


def _door_near(world_map, avoid) -> tuple:
    """A walkable cell by the down-stairs to seat the objective door — with a fallback for authored
    maps that declare no stairs, so the builder never dereferences a None."""
    sd = world_map.stairs_down
    if sd is not None:
        sdx, sdy = sd
        for ox, oy in ((0, -1), (-1, 0), (1, 0), (0, 1), (0, 0)):
            cx, cy = sdx + ox, sdy + oy
            if world_map.walkable(cx, cy) and (cx, cy) != tuple(avoid):
                return (cx, cy)
        return (sdx, sdy)
    for y in range(world_map.height):                    # no stairs: first free walkable cell
        for x in range(world_map.width):
            if world_map.walkable(x, y) and (x, y) != tuple(avoid):
                return (x, y)
    return tuple(avoid)


# ==================================================================================================
# SLICE 1 — "The Sunken Vault" (rooms-and-corridors dungeon; guarded scavenger + warm sellsword)
# ==================================================================================================

KEYSTONE = "keystone"   # item id — Vael's secret, opens the Vault's inner door
VAEL = "rpg-vael"       # Corvin-derived — guarded, suspicious, a dangerous past
LIRA = "rpg-lira"       # Bri-derived — warm, quick, disarming

_VAULT_FLAVOR = WorldFlavor(
    theme="the Sunken Vault",
    world_frame=("You are deep in the Sunken Vault — a flooded, ancient dungeon of black stone, old "
                 "wards, and worse things in the dark. Torchlight, dripping water, no way out but "
                 "through. This is a world of blades and lantern-light, not of any modern place."),
    location_label="a chamber of the Sunken Vault",
    time_label="deep underground",
    scene_prose=("The player stands deep in the Sunken Vault — black stone, standing water, old wards, "
                 "torchlight the only light."),
    dm_setting="a grim, torch-lit high-fantasy dungeon crawl beneath a flooded vault",
    combat_start=("Steel rings in the dark — {enemies} boil out of the shadows! "
                  "(move into one to attack · g: toggle their HP)"),
    combat_victory="The {enemies} are down. Quiet settles back over the Vault.",
    combat_alarm="{enemies} have set on the traveler — steel is out in the dark.",
    recruit_prompt="The traveler asks you to come with them, deeper into the Vault.",
    defeat_text=("You fall in the dark of the Vault, and it closes over you. Your story ends here. "
                 "(press q to quit)"),
)


def keystone_item() -> Item:
    return Item(id=KEYSTONE, name="a black keystone", kind="key",
                data={"desc": "A palm-sized wedge of black stone, warm to the touch. It fits the "
                              "Vault's inner door."})


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
        relationships={}, sample_lines=[], greeting="",
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
        relationships={}, sample_lines=[], greeting="",
        game_data={"dnd5e": {"role": "recruitable companion",
                             "sheet": {"max_hp": 18, "ac": 15, "STR": 13, "DEX": 15, "CON": 13}}},
    )


def build_first_slice(*, seed: int = 1337) -> tuple[GameState, dict[str, Character]]:
    """The Sunken Vault: player + rooms-and-corridors dungeon + Vael/Lira + a goblin encounter (the
    proof point) + the sealed inner door whose keystone is Vael's to give. All prose lives in
    `_VAULT_FLAVOR`; the differentiator + objective are wired as DATA on the placement and door."""
    d = generate_dungeon(seed=seed)
    sp = d.spawns
    at = lambda i: sp[i] if i < len(sp) else sp[-1]

    player = PlayerCharacter(id="player", name="You", max_hp=24, hp=24, ac=14,
                             stats=Stats(STR=14, DEX=13, CON=14, WIS=11, CHA=12),
                             pos=at(0), level=1, gold=10, damage_dice="1d8", attack_ability="STR")

    # Vael hands the keystone over ONLY if he chooses to join — authored right here as data.
    vael = NpcPlacement(slug=VAEL, name="Vael", handle="a cornered man", pos=at(1),
                        game_data={"dnd5e": {"role": "cornered scavenger"}},
                        on_recruit_grant=keystone_item(),
                        on_recruit_line=("If we're in this together — here. The thing my crew died for. "
                                         "It opens the inner door. Don't make me sorry I trusted you with it."))
    lira = NpcPlacement(slug=LIRA, name="Lira", handle="a lively sellsword", pos=at(2),
                        game_data={"dnd5e": {"role": "recruitable companion"}})

    enc_pos = sp[-2] if len(sp) > 3 else sp[-1]
    taken = {tuple(player.pos), tuple(vael.pos), tuple(lira.pos)}
    gpos = _spread_cells(d.world_map, enc_pos, 3, taken)
    goblins = [Enemy(id=f"goblin{i + 1}", name="Goblin", kind="goblin", max_hp=7, hp=7, ac=12,
                     stats=Stats(STR=8, DEX=14, CON=10), damage_dice="1d4", attack_ability="DEX",
                     pos=gpos[i % len(gpos)]) for i in range(3)]
    encounter = Encounter(id="vault-guards", enemies=goblins, trigger_pos=enc_pos, region="the deep gallery")

    door = Door(id="inner-door", pos=_door_near(d.world_map, avoid=tuple(player.pos)),
                name="the Vault's sealed inner door", locked=True, key_item=KEYSTONE,
                force_dc=18, opens_quest="descend",
                open_text=("You set the black keystone to the lock; the inner door grinds open, and cold "
                           "air breathes up from a stair spiraling down into deeper dark."),
                locked_text="The sealed inner door won't give without its keystone — or a mightier effort than that.",
                force_text=("You set your shoulder to the sealed door and heave — old iron shrieks, "
                            "timber splinters, and it bursts inward on a breath of cold, deep air."),
                outro=("[End of the demo slice — the way down is open. What you carry and who walks "
                       "beside you are yours to take deeper.]"))
    quest = QuestThread(id="descend", title="Open the Vault's sealed inner door and descend",
                        notes=["The way down is barred by an ancient door.",
                               "Vael was hired to bring out its keystone — he may still have it."])

    gs = GameState(flavor=_VAULT_FLAVOR, player=player, world_map=d.world_map, npcs=[vael, lira],
                   encounters=[encounter], doors=[door], quests=[quest])
    gs.campaign_log.add(0.0, "You descend into the Sunken Vault, torchlight swallowed by old dark.", tags=["intro"])
    return gs, {c.slug: c for c in (make_vael(), make_lira())}


# ==================================================================================================
# SLICE 2 — "The Emberdeep" (cellular-automata CAVERN; proud survivor + quiet cartographer). A
# genuinely different slice: different generator, biome, enemies (slow heavy STR hitters), key item,
# objective, and cast — authored with ZERO game-core changes.
# ==================================================================================================

SIGIL = "fire-sigil"      # item id — Torvald's secret, keys the Ember Gate
TORVALD = "rpg-torvald"   # Halvard-derived — gruff, proud, self-reliant, slow to accept help
SENNA = "rpg-senna"       # Wren-derived — quiet, watchful, steadfast once she trusts

_EMBER_FLAVOR = WorldFlavor(
    theme="the Emberdeep",
    world_frame=("You are in the Emberdeep — a collapsed dwarven forge-warren bored into a living "
                 "volcano. Heat shimmers off black basalt, veins of magma light the dark a dull "
                 "orange, and the air tastes of sulphur and hot iron. A world of blade, ember, and "
                 "old stone, not of any modern place."),
    location_label="a scorched gallery of the Emberdeep",
    time_label="amid the fire-lit deep",
    scene_prose=("The player stands in the Emberdeep — basalt underfoot cracked with veins of dull "
                 "red, the air furnace-hot, ember-light throwing long shadows across the stone."),
    dm_setting="a scorching, ember-lit dungeon crawl through a collapsed forge inside a volcano",
    combat_start=("Cinders scatter as {enemies} lurch from the heat-haze! "
                  "(move into one to attack · g: toggle their HP)"),
    combat_victory="The {enemies} crumble to ash and cooling slag. The roar of the deep settles.",
    combat_alarm="{enemies} have closed on the traveler out of the ember-glow — weapons are up.",
    recruit_prompt="The traveler asks you to come with them, deeper into the Emberdeep.",
    defeat_text=("The heat takes you, and the Emberdeep swallows your ash. Your story ends here. "
                 "(press q to quit)"),
)


def sigil_item() -> Item:
    return Item(id=SIGIL, name="a smoldering forge-sigil", kind="key",
                data={"desc": "A palm-sized brand of blackened iron, its rune still warm. It keys the "
                              "Ember Gate."})


def make_torvald() -> Character:
    """Proud survivor. Halvard's gruff, self-reliant, armored temperament carries over into a
    scarred forge-delver who guards what his crew died for and is slow to accept a stranger's hand."""
    return reskin(
        "halvard-crane", slug=TORVALD, name="Torvald",
        role="a scarred forge-delver",
        concept="a proud, self-reliant survivor pinned in the deep, guarding the thing his crew died for",
        age="weathered 50s",
        backstory=(
            "Torvald led a salvage crew into the Emberdeep to recover a forge-sigil — a smith's brand "
            "that keys the great Ember Gate. A gallery came down in the heat; the others didn't make "
            "it out. He has held this pocket of the deep alone since, rationing water and pride in "
            "equal measure, too stubborn to lie down and die and too burned by the loss to trust a "
            "stranger's hand. He is not cruel; he is a hard man who has learned that help has a price."),
        goals=["get out of the Emberdeep alive", "keep the sigil safe", "owe nothing to anyone"],
        secrets=[{"text": "He carries the forge-sigil that opens the Ember Gate — the very thing his "
                          "crew died to reach.",
                  "reveal_when": "he becomes convinced the traveler is genuinely on his side"}],
        knows=["the Ember Gate is keyed to a forge-sigil", "the husks in the deep were once his crew"],
        doesnt_know=["who the traveler is or why they've come down into the fire"],
        relationships={}, sample_lines=[], greeting="",
        game_data={"dnd5e": {"role": "cornered survivor", "faction": "lost salvage crew",
                             "sheet": {"max_hp": 20, "ac": 15, "STR": 15, "DEX": 11, "CON": 14}}},
    )


def make_senna() -> Character:
    """Quiet cartographer. Wren's soft-spoken, watchful, slow-to-open temperament carries over into
    a deep-mapper who reads a room before she speaks and is steadfast once she trusts."""
    return reskin(
        "wren-alder", slug=SENNA, name="Senna",
        role="a quiet deep-cartographer",
        concept="a watchful mapmaker charting the Emberdeep, slow to trust but steadfast once she does",
        age="late 20s",
        backstory=(
            "Senna came down to map the forge-warrens for a scholar's guild and was cut off when the "
            "galleries shifted in the heat. She keeps to herself, reads a room before she speaks, and "
            "has stayed alive by being careful and quiet. She warms slowly, but what she gives she "
            "does not take back."),
        goals=["find a way back to the surface with her charts intact", "not be left behind again"],
        secrets=[{"text": "Her charts show a second way out she hasn't dared take alone.",
                  "reveal_when": "she comes to trust the traveler"}],
        knows=["the layout of the nearer galleries", "the husks shy away from running water"],
        doesnt_know=["what the traveler is really after down here"],
        relationships={}, sample_lines=[], greeting="",
        game_data={"dnd5e": {"role": "recruitable companion",
                             "sheet": {"max_hp": 16, "ac": 14, "STR": 12, "DEX": 14, "CON": 12}}},
    )


def build_emberdeep_slice(*, seed: int = 2027) -> tuple[GameState, dict[str, Character]]:
    """The Emberdeep: player + a CAVERN map (a different generator) + cinder-husks (slow, heavy STR
    hitters — a genuinely different combat feel from the goblins' quick 1d4 DEX) + the Ember Gate,
    whose forge-sigil is Torvald's to give. Pure content — no game-core path differs from slice 1."""
    d = generate_caverns(seed=seed)
    sp = d.spawns
    at = lambda i: sp[i] if i < len(sp) else sp[-1]

    player = PlayerCharacter(id="player", name="You", max_hp=26, hp=26, ac=15,
                             stats=Stats(STR=15, DEX=12, CON=14, WIS=11, CHA=12),
                             pos=at(0), level=2, gold=15, damage_dice="1d8", attack_ability="STR")

    torvald = NpcPlacement(slug=TORVALD, name="Torvald", handle="a soot-streaked survivor", pos=at(1),
                           game_data={"dnd5e": {"role": "cornered survivor"}},
                           on_recruit_grant=sigil_item(),
                           on_recruit_line=("If we walk out of here together — take it. The sigil my "
                                            "crew burned for. It keys the Ember Gate. Don't make me "
                                            "regret handing it over."))
    senna = NpcPlacement(slug=SENNA, name="Senna", handle="a wary mapmaker", pos=at(2),
                         game_data={"dnd5e": {"role": "recruitable companion"}})

    enc_pos = sp[-2] if len(sp) > 3 else sp[-1]
    taken = {tuple(player.pos), tuple(torvald.pos), tuple(senna.pos)}
    hpos = _spread_cells(d.world_map, enc_pos, 4, taken)
    husks = [Enemy(id=f"husk{i + 1}", name="Cinder-husk", kind="husk", max_hp=13, hp=13, ac=13,
                   stats=Stats(STR=15, DEX=8, CON=13), damage_dice="1d8", attack_ability="STR",
                   pos=hpos[i % len(hpos)]) for i in range(4)]
    encounter = Encounter(id="ember-husks", enemies=husks, trigger_pos=enc_pos, region="the slag gallery")

    gate = Door(id="ember-gate", pos=_door_near(d.world_map, avoid=tuple(player.pos)),
                name="the Ember Gate", locked=True, key_item=SIGIL, force_dc=20, opens_quest="breach",
                open_text=("You press the forge-sigil to the Gate's socket; the runes flare white-hot "
                           "and the vast doors grind apart on a blast of furnace air."),
                locked_text=("The Ember Gate is seamless and scorching — it needs its forge-sigil, or "
                             "a titan's strength."),
                force_text=("You set your back to the Ember Gate and heave against searing iron until, "
                            "impossibly, it gives with a shriek of tortured metal."),
                outro=("[End of the demo slice — the Ember Gate stands open. What you carry and who "
                       "walks beside you go on into the forge below.]"))
    quest = QuestThread(id="breach", title="Breach the Ember Gate and descend into the forge",
                        notes=["The way down is sealed by the Ember Gate.",
                               "Torvald's crew died reaching its forge-sigil — he may still carry it."])

    gs = GameState(flavor=_EMBER_FLAVOR, player=player, world_map=d.world_map, npcs=[torvald, senna],
                   encounters=[encounter], doors=[gate], quests=[quest])
    gs.campaign_log.add(0.0, "You descend into the Emberdeep, the heat rising to meet you.", tags=["intro"])
    return gs, {c.slug: c for c in (make_torvald(), make_senna())}


# ==================================================================================================
# Slice registry — add a builder here and it's selectable via `RpgGame.new(slice=...)` /
# `RPG_SLICE=<name>`; no game-core change is ever needed.
# ==================================================================================================

SLICES = {
    "vault": build_first_slice,
    "emberdeep": build_emberdeep_slice,
}


def characters() -> dict[str, Character]:
    """Back-compat: the named minds for the default (Vault) slice."""
    return {c.slug: c for c in (make_vael(), make_lira())}
