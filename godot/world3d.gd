extends Node3D
## World3D — the 2.5D renderer (Stage 1 of the owner-approved visual pivot). A THIN view over the
## SAME StateSnapshot contract world.gd consumes: render(snap) / combat_fx(data) / tile_at_mouse()
## / set_slice(name). The game core, wire protocol, and save files know nothing about it; world.gd
## remains the 2D fallback (RPG_2D=1).
##
## Art: KayKit Dungeon Remastered + Adventurers + Skeletons (all CC0, committed). The CAST renders
## as fully animated GLB characters (animations ship inside each .glb — Idle/Walking/attacks/
## deaths); anything unmapped (goblins, husks, future bestiary) renders as a Y-billboard pixel
## sprite from the same Kenney atlas the 2D view uses, so new content never breaks. Real lighting
## does the heavy lifting: a flickering torch on the player, dark ambience, SSAO, glow.
##
## Grid mapping: tiles[y][x] -> world (x * TILE, 0, y * TILE); TILE is measured from the floor
## mesh's actual AABB at load, so the kit's native scale is authoritative. Fog of war: unexplored
## cells are simply NEVER built; explored-but-unseen cells get a translucent dark shroud quad.

# Movement is a WAYPOINT WALK along the route actually taken (the server's "path" event for the
# player, a client-side BFS replay for followers/enemies) — never a straight lerp to the snapshot
# position, which read as teleporting and cut through wall corners. Constant speed across the whole
# polyline; long treks hustle (speed scales up) so a far click never means watching a 20-second walk.
# 2D-RPG feel (owner direction 2026-07-09): grounded walk cadence, a firm cap on the hustle
# (16 t/s read as ice-skating), and a small per-tile step-hop below — crisp tile-to-tile
# STEPS, not a glide.
const WALK_TILES_PER_S := 4.6
const RUN_TILES_PER_S := 10.0
const TREK_MAX_S := 3.0        # a route is paced to land within this many seconds
# The 88x44 maps produce legitimately LONG treks — the old 40-tile cutoff was still teleporting
# far clicks (owner report). Snapping now only covers id-reuse across a brand-new map.
const SNAP_BEYOND_TILES := 200.0
# Camera vantage in TILES (converted via _tile at runtime): ~50° pitch, pulled back — a more
# TOP-DOWN, slightly-zoomed-out RPG view (owner direction 2026-07-09) that reads the room and the
# party at a glance while chibi characters still show face + body, not just hat-tops.
const CAM_OFFSET_TILES := Vector3(0.0, 7.2, 6.0)
const CAM_FOV := 42.0

var _tile := 2.0                              # world units per grid cell (measured from the kit)
var _snap: Dictionary = {}
var _exp := {}                                # "x,y" -> true (explored)
var _vis := {}                                # "x,y" -> true (lit right now)
var _turn_id := ""

# -- scene plumbing --
var _camera: Camera3D
var _torch: OmniLight3D
var _sun: DirectionalLight3D
var _env_node: WorldEnvironment
var _map_root: Node3D                          # static dungeon pieces (built incrementally)
var _ent_root: Node3D
var _fx_root: Node3D
var _shroud: MultiMeshInstance3D               # explored-but-unseen dim quads
var _range_mm: MultiMeshInstance3D             # combat: tiles reachable with remaining movement
var _turn_ring: MeshInstance3D                 # combat: gold ring under whoever is acting NOW
var _zoom := 1.0                               # camera dolly factor (mouse wheel), 0.65..1.5
var _slice_name := "vault"
var _last_mode := ""                           # stance switching on combat start/end
var _decor := "wet"                            # per-slice floor decor: "wet" | "ember" | ""
var _daylight := false                         # town slices: bright day, no torch-lit dungeon mood
var _town_built := false                        # a town builds its whole map once (no fog)
var _ambient := []                              # cosmetic villagers wandering the town (client-only)
var _puddle_mat: StandardMaterial3D = null     # vault: still black water catching the torch
var _ember_mat: StandardMaterial3D = null      # emberdeep: glowing cracks in the stone
var _husk_overlay: StandardMaterial3D = null   # cinder-husk: ember glow over charred bone

# -- meshes / scenes (lazily loaded) --
var _floor_sets := {}                          # "wet"/"ember" -> Array[PackedScene]
var _floor_scenes: Array = []                  # the ACTIVE set (selected by palette)
var _wall_scene: PackedScene = null
var _wall_variants: Array = []                 # cracked/broken — monotony breakers
var _door_scene: PackedScene = null
var _gate_scene: PackedScene = null            # barred wall segment — the LOCKED door look
var _stairs_scene: PackedScene = null
var _torch_scene: PackedScene = null           # wall-mounted torch (with its own small light)
var _banner_scenes := {}                       # "wet"/"ember" -> PackedScene
var _prop_sets := {}                           # "wet"/"ember" -> Array[PackedScene]
var _torch_lights := 0                         # per-map light budget (unshadowed omnis are cheap,
                                               # but Forward+ still deserves a ceiling)
# -- town (daylight) tileset: grass ground + village fences + nature scatter --
var _grass_mat: StandardMaterial3D = null
var _fence_scene: PackedScene = null
var _path_scene: PackedScene = null
var _town_trees: Array = []
var _town_bushes: Array = []
var _town_rocks: Array = []
var _town_tufts: Array = []                     # small grass/flower/pebble scatter
var _town_props: Array = []                     # wagon / crate near buildings
var _wall_plaster: PackedScene = null           # village-kit building pieces (2.0-wide walls)
var _wall_window: PackedScene = null
var _wall_door: PackedScene = null
var _door_leaf: PackedScene = null
var _spire: PackedScene = null
var _corner_post: PackedScene = null
var _roofs: Array = []
var _placed := {}                              # "x,y" -> true (cell already built)
var _map_sig := ""                             # rebuild guard (N-key restart / new slice)
var _wall_len := 4.0                           # wall piece native length/thickness (measured at load)
var _wall_thick := 1.0
var _stairs_size := Vector3(5.0, 5.1, 4.0)     # stairs piece native AABB (measured at load)
var _floor_top := 0.05                         # walk-surface height (measured from the floor AABB)
var _stair_cells := {}                         # "x,y" -> Vector2 — beings standing here get a lift

# -- entities --
var _ents := {}          # id -> {node, ap (AnimationPlayer|null), sprite (bool), label, hp_bar, state}
var _anim := {}          # id -> {pts: [Vector2,...], d: float, speed: float} waypoint walk (tile space)
var _last_pos := {}      # id -> Vector2 (tile)
var _facing := {}        # id -> yaw radians target
var _pending_route := {} # id -> [[x,y],...] server-walked route, consumed by the NEXT snapshot
var _atlas: Texture2D = null
var _sheet: Dictionary = {}
var _cols := 12
var _ts := 16

# -- combat fx --
var _fx: Array = []
var _fx_stagger := 0.0
var _shake := 0.0
var _time := 0.0

const KAYKIT := "res://assets/kaykit/"
const DUNGEON := KAYKIT + "KayKit-Dungeon-Remastered-1.0-main/addons/kaykit_dungeon_remastered/Assets/gltf/"
const ADVENTURERS := KAYKIT + "KayKit-Character-Pack-Adventures-1.0-main/addons/kaykit_character_pack_adventures/Characters/gltf/"
const SKELETONS := KAYKIT + "KayKit-Character-Pack-Skeletons-1.0-main/addons/kaykit_character_pack_skeletons/Characters/gltf/"
const QUAT := "res://assets/quaternius/"

## Which GLB carries each cast member / class (Stage-1 approximations; polish later).
var CAST_MODELS := {
	"rpg-vael": ADVENTURERS + "Rogue_Hooded.glb",
	"rpg-lira": ADVENTURERS + "Rogue.glb",
	"rpg-torvald": ADVENTURERS + "Barbarian.glb",
	"rpg-senna": ADVENTURERS + "Mage.glb",
	# Graywater town cast (The Hollow Accord) — distinct silhouettes for the four townsfolk
	"rpg-maren": ADVENTURERS + "Knight.glb",         # sturdy, hard mine-boss
	"rpg-ilo": ADVENTURERS + "Mage.glb",             # robed chapel-keeper
	"rpg-sable": ADVENTURERS + "Rogue_Hooded.glb",   # shadowed fence
	"rpg-joren": ADVENTURERS + "Barbarian.glb",      # burly baker
}

## Per-character COLOUR TINT so the chibi world model reads as its painted portrait's palette
## (owner 2026-07-08 — models didn't match the faces). The tint MULTIPLIES the model's texture
## (kept subtle, near-white) so detail survives; a strong-but-light hue nudges hair/clothing
## toward the portrait. Keeps all animation (the reason we tint rather than swap to billboards).
var CAST_TINTS := {
	"rpg-lira": Color(0.98, 0.66, 0.55),    # auburn hair, tan skin, warm leather
	"rpg-maren": Color(0.86, 0.76, 0.62),   # grey hair, brown coat, coal dust
	"rpg-ilo": Color(0.84, 0.86, 0.92),     # white hair, pale grey robe
	"rpg-sable": Color(0.66, 0.62, 0.76),   # black hair, dusk-purple scarf
	"rpg-joren": Color(0.94, 0.80, 0.62),   # warm baker tones
	"rpg-vael": Color(0.72, 0.70, 0.66),    # cold grey scavenger
	"player": Color(0.74, 0.62, 0.60),      # dark-haired knight, black-and-red
}
var CLASS_MODELS := {
	"fighter": ADVENTURERS + "Knight.glb",
	"rogue": ADVENTURERS + "Rogue.glb",
	"cleric": ADVENTURERS + "Knight.glb",
	"wizard": ADVENTURERS + "Mage.glb",
}
## Enemy specs keyed by LOWERCASED bestiary display name. `h` > 0 = normalize the model to that
## height in world units (Quaternius FBX exports carry arbitrary armature scale — measure, don't
## trust); h = 0 = KayKit grid scaling. `ember` = charred-glow overlay (the cinder-husk is a
## burnt corpse: a KayKit skeleton smoldering from inside reads exactly right).
var ENEMY_MODELS := {
	"goblin": {"path": QUAT + "Goblin.glb", "h": 1.35},
	"cinder-husk": {"path": SKELETONS + "Skeleton_Minion.glb", "h": 0.0, "ember": true},
	"vault-drowned": {"path": SKELETONS + "Skeleton_Minion.glb", "h": 0.0},
	"skeleton": {"path": SKELETONS + "Skeleton_Warrior.glb", "h": 0.0},
	"zombie": {"path": SKELETONS + "Skeleton_Minion.glb", "h": 0.0},
	"shadow": {"path": SKELETONS + "Skeleton_Rogue.glb", "h": 0.0},
	"specter": {"path": SKELETONS + "Skeleton_Mage.glb", "h": 0.0},
	"wight": {"path": SKELETONS + "Skeleton_Warrior.glb", "h": 0.0},
	"ghast": {"path": SKELETONS + "Skeleton_Minion.glb", "h": 0.0},
	"ghoul": {"path": SKELETONS + "Skeleton_Minion.glb", "h": 0.0},
	"wolf": {"path": QUAT + "Wolf.glb", "h": 1.1},
	"dire wolf": {"path": QUAT + "Wolf.glb", "h": 1.55},
	"worg": {"path": QUAT + "Wolf.glb", "h": 1.4},
	"giant spider": {"path": QUAT + "Spider.glb", "h": 0.95},
	"giant rat": {"path": QUAT + "Rat.glb", "h": 0.7},
	"bandit": {"path": ADVENTURERS + "Rogue_Hooded.glb", "h": 0.0},
	"cultist": {"path": ADVENTURERS + "Rogue_Hooded.glb", "h": 0.0},
}


const TOWN := "res://assets/town/"

func _ready() -> void:
	_load_sheet()
	_build_scene()
	_load_dungeon_pieces()
	_load_town_pieces()
	set_slice("vault")


func _load_town_pieces() -> void:
	_grass_mat = StandardMaterial3D.new()
	_grass_mat.albedo_color = Color(0.36, 0.52, 0.24)   # meadow green
	_grass_mat.roughness = 1.0
	var f = load(TOWN + "Prop_WoodenFence_Single.gltf")
	if f is PackedScene:
		_fence_scene = f
	var p = load(TOWN + "RockPath_Square_Wide.gltf")
	if p is PackedScene:
		_path_scene = p
	_town_trees = _load_town_set(["CommonTree_1", "CommonTree_3", "CommonTree_5", "Pine_2", "Pine_4"])
	_town_bushes = _load_town_set(["Bush_Common", "Bush_Common_Flowers"])
	_town_rocks = _load_town_set(["Rock_Medium_1", "Rock_Medium_2"])
	_town_tufts = _load_town_set(["Grass_Common_Tall", "Grass_Wispy_Tall", "Flower_3_Group", "Pebble_Round_2"])
	_town_props = _load_town_set(["Prop_Wagon", "Prop_Crate"])
	# Quaternius village kit — real building pieces (walls are exactly 2.0 wide = one tile)
	_wall_plaster = _load_town_one("Wall_Plaster_Straight")
	_wall_window = _load_town_one("Wall_Plaster_Window_Wide_Round")
	_wall_door = _load_town_one("Wall_Plaster_Door_Round")
	_door_leaf = _load_town_one("Door_1_Round")
	_spire = _load_town_one("Roof_Tower_RoundTiles")
	_corner_post = _load_town_one("Corner_Exterior_Wood")
	_roofs = _load_town_set(["Roof_RoundTiles_4x4", "Roof_RoundTiles_6x6", "Roof_RoundTiles_6x8",
		"Roof_RoundTiles_8x8", "Roof_RoundTiles_8x10"])


func _load_town_one(n: String) -> PackedScene:
	var p := TOWN + n + ".gltf"
	var s = load(p) if ResourceLoader.exists(p) else null
	return s if s is PackedScene else null


func _load_town_set(names: Array) -> Array:
	var out: Array = []
	for n in names:
		var s = load(TOWN + str(n) + ".gltf") if ResourceLoader.exists(TOWN + str(n) + ".gltf") else null
		if s is PackedScene:
			out.append(s)
	return out


func _load_sheet() -> void:
	var f := FileAccess.open("res://assets/sprites.json", FileAccess.READ)
	if f == null:
		return
	var parsed = JSON.parse_string(f.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	_sheet = parsed
	_cols = int(_sheet.get("columns", 12))
	_ts = int(_sheet.get("tile_size", 16))
	var tex = load(str(_sheet.get("atlas", "")))
	if tex is Texture2D:
		_atlas = tex


func _build_scene() -> void:
	_map_root = Node3D.new()
	add_child(_map_root)
	_ent_root = Node3D.new()
	add_child(_ent_root)
	_fx_root = Node3D.new()
	add_child(_fx_root)

	_camera = Camera3D.new()
	_camera.fov = CAM_FOV
	add_child(_camera)
	_camera.make_current()

	# Environment: a dark, torch-lit dungeon mood — this is where most of the realism comes from.
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.02, 0.02, 0.03)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.35, 0.38, 0.48)
	env.ambient_light_energy = 0.55              # readable base; the torch adds the warm drama
	env.ssao_enabled = true
	env.ssao_intensity = 2.0
	env.glow_enabled = true
	env.glow_intensity = 0.4
	env.glow_bloom = 0.1
	env.fog_enabled = true
	env.fog_light_color = Color(0.05, 0.05, 0.08)
	env.fog_density = 0.015
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	# A real sky, kept ready — daylight (town) slices switch background to it so the world reads
	# as OUTDOORS under open sky, not a lit room (owner feedback 2026-07-09). Dungeons keep BG_COLOR.
	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Color(0.35, 0.52, 0.82)
	sky_mat.sky_horizon_color = Color(0.78, 0.82, 0.86)
	sky_mat.ground_horizon_color = Color(0.78, 0.82, 0.86)
	sky_mat.ground_bottom_color = Color(0.55, 0.6, 0.6)
	sky_mat.sun_angle_max = 30.0
	var sky := Sky.new()
	sky.sky_material = sky_mat
	env.sky = sky
	_env_node = WorldEnvironment.new()
	_env_node.environment = env
	add_child(_env_node)

	_sun = DirectionalLight3D.new()
	_sun.light_color = Color(0.55, 0.6, 0.8)
	_sun.light_energy = 0.12                     # a whisper of cool fill; the torch owns the scene
	_sun.rotation_degrees = Vector3(-55.0, 35.0, 0.0)
	_sun.shadow_enabled = true
	add_child(_sun)

	# Floor decor materials (per-slice): the vault's fiction is shin-deep black water — flat
	# metallic puddles catch the torch as broken specular patches; emberdeep gets glowing cracks.
	_puddle_mat = StandardMaterial3D.new()
	_puddle_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_puddle_mat.albedo_color = Color(0.02, 0.04, 0.06, 0.55)
	_puddle_mat.metallic = 1.0
	_puddle_mat.roughness = 0.12
	_ember_mat = StandardMaterial3D.new()
	_ember_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_ember_mat.albedo_color = Color(0.35, 0.08, 0.01, 0.6)   # smolder, not a glowing plate
	_ember_mat.emission_enabled = true
	_ember_mat.emission = Color(0.9, 0.25, 0.04)
	_ember_mat.emission_energy_multiplier = 0.7
	_ember_mat.roughness = 0.9
	_husk_overlay = StandardMaterial3D.new()   # cinder-husk: charred body, lit from within
	_husk_overlay.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_husk_overlay.albedo_color = Color(0.25, 0.05, 0.0, 0.5)
	_husk_overlay.emission_enabled = true
	_husk_overlay.emission = Color(1.0, 0.30, 0.05)
	_husk_overlay.emission_energy_multiplier = 0.9

	_torch = OmniLight3D.new()                 # the player's torch — follows them, flickers
	_torch.light_color = Color(1.0, 0.72, 0.45)
	_torch.light_energy = 6.0
	_torch.omni_range = 12.0
	_torch.shadow_enabled = true
	add_child(_torch)

	var mm := MultiMesh.new()                  # the fog shroud (explored-but-unseen dimming)
	mm.transform_format = MultiMesh.TRANSFORM_3D
	var quad := PlaneMesh.new()
	quad.size = Vector2(1, 1)                  # scaled per-instance to TILE
	var mat := StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_color = Color(0.0, 0.0, 0.02, 0.55)
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	quad.material = mat
	mm.mesh = quad
	_shroud = MultiMeshInstance3D.new()
	_shroud.multimesh = mm
	_shroud.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_shroud)

	# Combat legibility (the VTT conventions — visible budget, visible turn): a green overlay on
	# every tile the CURRENT movement allowance can reach, and a gold ring under whoever acts now.
	var rmm := MultiMesh.new()
	rmm.transform_format = MultiMesh.TRANSFORM_3D
	var rquad := PlaneMesh.new()
	rquad.size = Vector2(0.86, 0.86)           # inset so tile edges stay readable
	var rmat := StandardMaterial3D.new()
	rmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	rmat.albedo_color = Color(0.30, 0.85, 0.45, 0.28)
	rmat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	rquad.material = rmat
	rmm.mesh = rquad
	_range_mm = MultiMeshInstance3D.new()
	_range_mm.multimesh = rmm
	_range_mm.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_range_mm)

	_turn_ring = MeshInstance3D.new()
	var ring := TorusMesh.new()
	ring.inner_radius = 0.42
	ring.outer_radius = 0.52
	var ringmat := StandardMaterial3D.new()
	ringmat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	ringmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	ringmat.albedo_color = Color(0.96, 0.82, 0.25, 0.85)
	_turn_ring.mesh = ring
	_turn_ring.material_override = ringmat
	_turn_ring.scale = Vector3(1.0, 0.12, 1.0)
	_turn_ring.visible = false
	add_child(_turn_ring)


func _load_dungeon_pieces() -> void:
	# Floors per slice mood: worked stone (with broken/mossy variants) for the vault,
	# scorched dirt for the ember caverns.
	# NOTE: the BULKY variant (rocks piled on the tile) must stay LAST — _place_floor bans it
	# from corridors, where a rock pile reads as a blocked passage even though it's walkable.
	_floor_sets["wet"] = _load_set(["floor_tile_small.gltf.glb", "floor_tile_small_broken_A.gltf.glb",
			"floor_tile_small_broken_B.gltf.glb", "floor_tile_small_weeds_A.gltf.glb",
			"floor_tile_large_rocks.gltf.glb"])
	_floor_sets["ember"] = _load_set(["floor_dirt_small_A.gltf.glb", "floor_dirt_small_B.gltf.glb",
			"floor_dirt_small_C.gltf.glb", "floor_dirt_small_D.gltf.glb"])
	_floor_scenes = _floor_sets["wet"]
	var w = load(DUNGEON + "wall.gltf.glb")
	if w is PackedScene:
		_wall_scene = w
	_wall_variants = _load_set(["wall_cracked.gltf.glb", "wall_broken.gltf.glb"])
	var d = load(DUNGEON + "wall_doorway.glb")
	if d is PackedScene:
		_door_scene = d
	var g = load(DUNGEON + "wall_gated.gltf.glb")
	if g is PackedScene:
		_gate_scene = g
	var st = load(DUNGEON + "stairs.gltf.glb")
	if st is PackedScene:
		_stairs_scene = st
	var tm = load(DUNGEON + "torch_mounted.gltf.glb")
	if tm is PackedScene:
		_torch_scene = tm
	var bw = load(DUNGEON + "banner_white.gltf.glb")
	if bw is PackedScene:
		_banner_scenes["wet"] = bw
	var br = load(DUNGEON + "banner_red.gltf.glb")
	if br is PackedScene:
		_banner_scenes["ember"] = br
	# Scatter props: waterlogged storage + rubble + spilled treasure for the vault; kegs,
	# charred barricades and candle clusters for the ember caverns.
	_prop_sets["wet"] = _load_set(["rubble_half.gltf.glb", "rubble_large.gltf.glb",
			"barrel_small.gltf.glb", "box_small.gltf.glb", "trunk_small_A.gltf.glb",
			"candle_melted.gltf.glb", "bottle_C_green.gltf.glb", "coin_stack_small.gltf.glb"])
	_prop_sets["ember"] = _load_set(["keg.gltf.glb", "barrier_half.gltf.glb",
			"candle_triple.gltf.glb", "rubble_half.gltf.glb", "box_small_decorated.gltf.glb",
			"coin_stack_medium.gltf.glb"])
	# Measure the kit's native sizes from the meshes themselves so grid mapping is exact:
	# the floor gives the tile size AND the true walk-surface height; the wall gives its
	# length/thickness (needed to seat segments flush with the corridor edge).
	if not _floor_scenes.is_empty():
		var aabb := _probe_aabb(_floor_scenes[0])
		if aabb.size.x > 0.1:
			_tile = snappedf(aabb.size.x, 0.5)
			_floor_top = aabb.position.y + aabb.size.y
		print("[world3d] floor aabb=", aabb.size, " -> tile=", _tile, " top=", _floor_top)
	if _wall_scene != null:
		var wab := _probe_aabb(_wall_scene)
		if wab.size.x > 0.1:
			_wall_len = wab.size.x
			_wall_thick = wab.size.z
	if _stairs_scene != null:
		var sab := _probe_aabb(_stairs_scene)
		if sab.size.x > 0.1:
			_stairs_size = sab.size


func _load_set(names: Array) -> Array:
	var out: Array = []
	for n in names:
		var s = load(DUNGEON + str(n))
		if s is PackedScene:
			out.append(s)
	return out


func _probe_aabb(scene: PackedScene) -> AABB:
	var probe: Node3D = scene.instantiate()
	add_child(probe)
	var mi := probe.find_children("*", "MeshInstance3D", true)
	var aabb := AABB()
	if not mi.is_empty():
		aabb = (mi[0] as MeshInstance3D).get_aabb()
	probe.queue_free()
	return aabb


func set_slice(slice_name: String) -> void:
	# A fresh world: drop every built cell + entity + effect (ids are re-used at new positions).
	# ("" = same slice, new map — render()'s signature guard — so the palette carries over.)
	if slice_name != "":
		_slice_name = slice_name
		_apply_palette(slice_name)
	_placed.clear()
	_map_sig = ""
	for c in _map_root.get_children():
		c.queue_free()
	for id in _ents.keys():
		_ents[id]["node"].queue_free()
	_ents.clear()
	_anim.clear()
	_last_pos.clear()
	_facing.clear()
	_pending_route.clear()
	_stair_cells.clear()
	_fx.clear()
	_fx_stagger = 0.0
	_shake = 0.0
	_torch_lights = 0
	_town_built = false
	for a in _ambient:
		if is_instance_valid(a["node"]):
			a["node"].queue_free()
	_ambient.clear()


## Per-slice mood: the SAME dungeon geometry reads as a different place through light alone.
## The vault is cold drowned stone under a warm torch; emberdeep is heat — ember ambience, a
## furnace-red fill, glowing floor cracks. Slices the client doesn't know default to the vault look.
func _apply_palette(slice_name: String) -> void:
	var env: Environment = _env_node.environment
	_daylight = false
	match slice_name:
		"graywater", "town":
			# A TOWN OUTDOORS: open SKY background, sun-lit, grass ground + village fences + trees
			# (owner feedback 2026-07-09 — the lit-stone version still read as a dungeon).
			env.background_mode = Environment.BG_SKY
			env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
			env.ambient_light_energy = 1.0
			env.fog_light_color = Color(0.7, 0.75, 0.82)
			env.fog_density = 0.003
			_sun.light_color = Color(1.0, 0.96, 0.86)
			_sun.light_energy = 1.4
			_sun.rotation_degrees = Vector3(-52.0, 40.0, 0.0)
			_decor = ""                              # town ground is grass, not dungeon decor
			_daylight = true
		"emberdeep":
			env.background_mode = Environment.BG_COLOR
			env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
			env.background_color = Color(0.045, 0.015, 0.008)
			env.ambient_light_color = Color(0.55, 0.34, 0.22)
			env.ambient_light_energy = 0.5
			env.fog_light_color = Color(0.10, 0.03, 0.01)
			env.fog_density = 0.015
			_torch.light_color = Color(1.0, 0.55, 0.25)
			_sun.light_color = Color(0.9, 0.45, 0.25)
			_sun.light_energy = 0.10
			_decor = "ember"
			if _floor_sets.has("ember"):
				_floor_scenes = _floor_sets["ember"]
		_:
			env.background_mode = Environment.BG_COLOR
			env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
			env.background_color = Color(0.02, 0.02, 0.03)
			env.ambient_light_color = Color(0.35, 0.38, 0.48)
			env.ambient_light_energy = 0.55
			env.fog_light_color = Color(0.05, 0.05, 0.08)
			env.fog_density = 0.015
			_torch.light_color = Color(1.0, 0.72, 0.45)
			_sun.light_color = Color(0.55, 0.6, 0.8)
			_sun.light_energy = 0.12
			_decor = "wet"
			if _floor_sets.has("wet"):
				_floor_scenes = _floor_sets["wet"]


func _world_pos(tx: float, ty: float) -> Vector3:
	return Vector3((tx + 0.5) * _tile, 0.0, (ty + 0.5) * _tile)


func _being_pos(tx: float, ty: float) -> Vector3:
	var base := _world_pos(tx, ty) + Vector3(0.0, _floor_top, 0.0)
	# Stairs are walkable scenery: whoever stands on (or walks across) the stair tile rises with
	# it, so stepping onto the stairs reads as climbing rather than clipping through the mesh.
	for c in _stair_cells.values():
		var lift := clampf(1.4 - 1.4 * Vector2(tx, ty).distance_to(c), 0.0, 1.0)
		base.y += _tile * 0.30 * lift
	return base


## Click feedback: a cyan ring blooms on the tile you picked, so the walk that follows visibly
## belongs to YOUR order (main.gd calls this alongside sending move_to).
func mark_destination(t: Vector2i) -> void:
	var ring := MeshInstance3D.new()
	var tor := TorusMesh.new()
	tor.inner_radius = _tile * 0.28
	tor.outer_radius = _tile * 0.36
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.albedo_color = Color(0.37, 0.82, 0.88, 0.9)
	ring.mesh = tor
	ring.material_override = m
	ring.scale = Vector3(1.0, 0.10, 1.0)
	ring.position = _world_pos(float(t.x), float(t.y)) + Vector3(0.0, _floor_top + 0.03, 0.0)
	ring.set_meta("life", 0.6)
	ring.set_meta("ring", true)
	_fx_root.add_child(ring)


## Mouse-wheel dolly: same view angle, closer or further (clamped so the room stays readable).
func zoom_step(d: float) -> void:
	_zoom = clampf(_zoom + d, 0.65, 1.5)


func tile_at_mouse() -> Vector2i:
	if _camera == null:
		return Vector2i(-1, -1)
	var mp := get_viewport().get_mouse_position()
	var origin := _camera.project_ray_origin(mp)
	var dirv := _camera.project_ray_normal(mp)
	if absf(dirv.y) < 0.0001:
		return Vector2i(-1, -1)
	var t := -origin.y / dirv.y
	if t < 0.0:
		return Vector2i(-1, -1)
	var hit := origin + dirv * t
	return Vector2i(int(floor(hit.x / _tile)), int(floor(hit.z / _tile)))


## main.gd calls this on every snapshot. Same contract as world.gd.render.
func render(s: Dictionary) -> void:
	_snap = s if typeof(s) == TYPE_DICTIONARY else {}
	_turn_id = str(_snap.get("combat_turn", ""))
	_vis.clear()
	_exp.clear()
	for k in _snap.get("visible", []):
		_vis[k] = true
	for k in _snap.get("explored", []):
		_exp[k] = true
	var tiles = _snap.get("tiles", [])
	if typeof(tiles) == TYPE_ARRAY and not tiles.is_empty():
		var sig := str(tiles[0]) + "|" + str(tiles.size())
		if sig != _map_sig:                    # different map entirely (new game/slice)
			set_slice("")
			_map_sig = sig
		if _daylight:
			# A TOWN is built WHOLE on load (no fog-of-war — you can see across a square): full grass
			# ground, real houses on the building footprints, a boundary wall, ambient villagers.
			if not _town_built:
				_town_built = true
				_build_town_full(tiles)
		else:
			_build_explored(tiles)
			_update_shroud(tiles)
	_sync_entities()
	_update_range_overlay()
	# Combat starting/ending re-poses everyone standing: weapons come UP when initiative rolls
	# and drop when the fight ends (_idle_prefer() is the situational pick).
	var mode := str(_snap.get("mode", ""))
	if mode != _last_mode:
		_last_mode = mode
		for id in _ents:
			if str(_ents[id]["state"]) == "idle":
				_play_anim(_ents[id], _idle_prefer(), true)


# ---------------------------------------------------------------- town (whole-map build)

## A town is a PLACE you see across, not a fogged crawl: build the entire map at once — grass
## everywhere, a stone LANE from the gate through the square to each building's door, real HOUSES
## on the interior wall-blocks (a body + gable roof + door + chimney), a low boundary wall on the
## outer ring, and a handful of ambient villagers wandering. Runs once per town map.
func _build_town_full(tiles: Array) -> void:
	var h := tiles.size()
	var w := str(tiles[0]).length()
	# ground first (grass under everything, including where houses sit)
	for y in h:
		var row: String = str(tiles[y])
		for x in row.length():
			_place_grass_plain(x, y)
	# building footprints = connected '#' components NOT touching the border (which is the town wall)
	var seen := {}
	var comps: Array = []
	for y in range(1, h - 1):
		var row: String = str(tiles[y])
		for x in range(1, w - 1):
			var k := Vector2i(x, y)
			if row[x] != "#" or seen.has(k):
				continue
			# flood the component
			var cells: Array = []
			var q: Array = [k]
			seen[k] = true
			var touches_border := false
			while not q.is_empty():
				var c: Vector2i = q.pop_back()
				cells.append(c)
				if c.x <= 0 or c.y <= 0 or c.x >= w - 1 or c.y >= h - 1:
					touches_border = true
				for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
					var nb: Vector2i = c + d
					if nb.x < 0 or nb.y < 0 or nb.x >= w or nb.y >= h or seen.has(nb):
						continue
					if str(tiles[nb.y])[nb.x] == "#":
						seen[nb] = true
						q.append(nb)
			if not touches_border and cells.size() >= 2:
				comps.append(cells)
	var door_fronts: Array = []
	for cells in comps:
		if cells.size() >= 12:
			door_fronts.append(_place_house(tiles, cells))    # a real building
		else:
			_place_well(cells)                                # a small block = the plaza well
	# a stone lane linking the gate approach + each building door to the town centre
	var centre := Vector2i(w / 2, h / 2)
	_lay_lane(tiles, Vector2i(centre.x, h - 2), centre)
	for df in door_fronts:
		if df.x >= 0:
			_lay_lane(tiles, df, centre)
	# low boundary wall on the outer ring (waist-high, so it frames without boxing the view)
	_build_town_boundary(tiles)
	# scatter trees/bushes/rocks on open grass, away from lanes + doors
	for y in range(1, h - 1):
		for x in range(1, w - 1):
			if str(tiles[y])[x] in [".", "+", ">", "<"]:
				_maybe_town_scatter(x, y, (x * 131 + y * 197) % 100)
	_spawn_ambient_villagers(tiles)


## A grass quad with per-cell hue variation (no scatter — scatter is placed in a second pass so it
## can avoid lanes/doors).
func _place_grass_plain(x: int, y: int) -> void:
	if _grass_mat == null:
		return
	var q := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(_tile, _tile)
	q.mesh = pm
	var hh := (x * 131 + y * 197) % 100
	var mat := _grass_mat.duplicate() as StandardMaterial3D
	mat.albedo_color = _grass_mat.albedo_color.lerp(Color(0.30, 0.44, 0.20), float(hh) / 140.0)
	q.material_override = mat
	q.position = _world_pos(float(x), float(y)) + Vector3(0.0, 0.01, 0.0)
	_map_root.add_child(q)


## One building footprint -> a REAL building from the Quaternius village kit: plaster wall pieces
## (exactly one tile wide) around every street-facing edge, a door wall on the face toward the
## square, windows scattered on the rest, and a whole tiled roof scaled to the footprint. The tall
## chapel/mine gets a spire. Returns the street cell in front of the door (for lane-laying).
func _place_house(tiles: Array, cells: Array) -> Vector2i:
	if _wall_plaster == null:
		return Vector2i(-1, -1)
	var minx := 9999; var miny := 9999; var maxx := -1; var maxy := -1
	var cellset := {}
	for c in cells:
		minx = mini(minx, c.x); miny = mini(miny, c.y)
		maxx = maxi(maxx, c.x); maxy = maxi(maxy, c.y)
		cellset[c] = true
	var bw := (maxx - minx + 1)
	var bh := (maxy - miny + 1)
	var cx := (minx + maxx) * 0.5 + 0.5
	var cy := (miny + maxy) * 0.5 + 0.5
	var h_all := tiles.size()
	var w_all := str(tiles[0]).length()
	var wall_h := 3.12                              # the kit's plaster-wall height
	# which face holds the door: toward the town centre
	var toward := Vector2(w_all * 0.5 - cx, h_all * 0.5 - cy)
	var face := Vector2i(0, 1) if absf(toward.y) >= absf(toward.x) else Vector2i(1, 0)
	if (face.y == 1 and toward.y < 0) or (face.x == 1 and toward.x < 0):
		face = -face
	var door_front := Vector2i(-1, -1)
	var dirs := [[0, -1, 0.0], [1, 0, PI * 0.5], [0, 1, PI], [-1, 0, PI * 1.5]]
	var placed_door := false
	for c: Vector2i in cells:
		for d in dirs:
			var nb := Vector2i(c.x + int(d[0]), c.y + int(d[1]))
			if cellset.has(nb) or nb.y < 0 or nb.y >= h_all or nb.x < 0 or nb.x >= w_all:
				continue
			if not (str(tiles[nb.y])[nb.x] in [".", "+", ">", "<"]):
				continue
			var dirv := Vector2i(int(d[0]), int(d[1]))
			var kind := "straight"
			# door on the first perimeter cell of the centre-facing side; windows scattered
			if dirv == face and not placed_door and _near_face_centre(c, face, minx, miny, maxx, maxy):
				kind = "door"; placed_door = true
				door_front = nb
			elif (c.x * 3 + c.y) % 3 == 0:
				kind = "window"
			var scene: PackedScene = _wall_plaster
			if kind == "door":
				scene = _wall_door
			elif kind == "window":
				scene = _wall_window
			var wnode: Node3D = scene.instantiate()
			_map_root.add_child(wnode)
			var wd := Vector3(float(d[0]), 0.0, float(d[1]))
			# seat the wall's outer face on the cell's outward edge (piece is 0.4 thick, centred)
			wnode.position = _world_pos(float(c.x), float(c.y)) + wd * (_tile * 0.5 - 0.2)
			wnode.rotation.y = float(d[2])
			if kind == "door" and _door_leaf != null:
				var leaf: Node3D = _door_leaf.instantiate()
				wnode.add_child(leaf)
				leaf.position = Vector3(-0.5, 0.1, 0.0)
	# CORNER POSTS close the vertical seams where two perpendicular wall runs meet (the classic
	# modular-wall corner gap) so the shell is airtight at every corner.
	if _corner_post != null:
		for corner in [Vector2(minx, miny), Vector2(maxx + 1, miny),
				Vector2(minx, maxy + 1), Vector2(maxx + 1, maxy + 1)]:
			var cp: Node3D = _corner_post.instantiate()
			_map_root.add_child(cp)
			cp.position = Vector3(corner.x * _tile, 0.0, corner.y * _tile)
	# CEILING CAP over the whole footprint (just under the roof) — seals the top so the top-down
	# camera can't see into the interior, which is what read as 'not enclosed' (owner 2026-07-08).
	var cap := MeshInstance3D.new()
	var capm := BoxMesh.new()
	capm.size = Vector3(bw * _tile + 0.2, 0.3, bh * _tile + 0.2)
	cap.mesh = capm
	var capmat := StandardMaterial3D.new()
	capmat.albedo_color = Color(0.12, 0.10, 0.09)   # dark loft under the roof
	capmat.roughness = 1.0
	cap.material_override = capmat
	cap.position = Vector3(cx * _tile, wall_h - 0.15, cy * _tile)
	_map_root.add_child(cap)
	# whole tiled roof, scaled to the footprint with a clear eave overhang, on the wall tops
	if not _roofs.is_empty():
		var roof: Node3D = _roofs[(minx + miny) % _roofs.size()].instantiate()
		_map_root.add_child(roof)
		var rab := _scene_aabb(roof)
		var sx := (bw * _tile + 1.4) / maxf(rab.size.x, 0.1)
		var sz := (bh * _tile + 1.4) / maxf(rab.size.z, 0.1)
		roof.scale = Vector3(sx, 1.05, sz)
		roof.position = Vector3(cx * _tile, wall_h - 0.1, cy * _tile)
	# a spire marks the taller civic buildings (chapel / mine office) — the two topmost blocks
	if _spire != null and miny < h_all / 3:
		var sp: Node3D = _spire.instantiate()
		_map_root.add_child(sp)
		sp.position = Vector3(cx * _tile, wall_h + _tile * 0.9, cy * _tile)
		sp.scale = Vector3(0.7, 0.8, 0.7)
	return door_front


## Is this perimeter cell near the MIDDLE of the door-facing side? (so the door is centred, not
## in a corner).
func _near_face_centre(c: Vector2i, face: Vector2i, minx: int, miny: int, maxx: int, maxy: int) -> bool:
	if face.x != 0:                                 # door on a vertical face -> centre in y
		return c.y == (miny + maxy) / 2
	return c.x == (minx + maxx) / 2                 # door on a horizontal face -> centre in x


func _scene_aabb(node: Node) -> AABB:
	var mis := node.find_children("*", "MeshInstance3D", true, false)
	var ab := AABB()
	var first := true
	for m in mis:
		var a: AABB = (m as MeshInstance3D).get_aabb()
		ab = a if first else ab.merge(a)
		first = false
	return ab


## A small wall-block (the plaza's 2x2) -> a low stone well with a dark water top, not a house.
func _place_well(cells: Array) -> void:
	var minx := 9999; var miny := 9999; var maxx := -1; var maxy := -1
	for c in cells:
		minx = mini(minx, c.x); miny = mini(miny, c.y)
		maxx = maxi(maxx, c.x); maxy = maxi(maxy, c.y)
	var cx := (minx + maxx) * 0.5 + 0.5
	var cy := (miny + maxy) * 0.5 + 0.5
	var curb := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = _tile * 0.55
	cm.bottom_radius = _tile * 0.6
	cm.height = _tile * 0.5
	curb.mesh = cm
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.5, 0.5, 0.52)
	mat.roughness = 1.0
	curb.material_override = mat
	curb.position = Vector3(cx * _tile, _tile * 0.25, cy * _tile)
	_map_root.add_child(curb)
	var water := MeshInstance3D.new()
	var wm := CylinderMesh.new()
	wm.top_radius = _tile * 0.42
	wm.bottom_radius = _tile * 0.42
	wm.height = 0.05
	water.mesh = wm
	var wmat := StandardMaterial3D.new()
	wmat.albedo_color = Color(0.08, 0.12, 0.16)
	wmat.metallic = 0.6
	wmat.roughness = 0.2
	water.material_override = wmat
	water.position = Vector3(cx * _tile, _tile * 0.5, cy * _tile)
	_map_root.add_child(water)


## Lay a stone-path LANE (an L: horizontal then vertical) between two walkable tiles.
func _lay_lane(tiles: Array, a: Vector2i, b: Vector2i) -> void:
	if _path_scene == null:
		return
	var cur := a
	var guard := 0
	while cur != b and guard < 200:
		guard += 1
		_path_tile(tiles, cur.x, cur.y)
		if cur.x != b.x:
			cur.x += signi(b.x - cur.x)
		elif cur.y != b.y:
			cur.y += signi(b.y - cur.y)
	_path_tile(tiles, b.x, b.y)


func _path_tile(tiles: Array, x: int, y: int) -> void:
	if y < 0 or y >= tiles.size() or x < 0 or x >= str(tiles[y]).length():
		return
	if not (str(tiles[y])[x] in [".", "+", ">", "<"]):
		return
	var key := "lane" + str(x) + "," + str(y)
	if _placed.has(key):
		return
	_placed[key] = true
	var p: Node3D = _path_scene.instantiate()
	_map_root.add_child(p)
	p.position = _world_pos(float(x), float(y)) + Vector3(0.0, 0.03, 0.0)
	p.scale = Vector3(_tile / 2.05, 1.0, _tile / 2.0)


## The outer ring becomes a low waist-high boundary wall (fence posts), framing the town without
## boxing the camera.
func _build_town_boundary(tiles: Array) -> void:
	if _fence_scene == null:
		return
	var h := tiles.size()
	var w := str(tiles[0]).length()
	for y in h:
		for x in str(tiles[y]).length():
			if str(tiles[y])[x] != "#":
				continue
			if not (x == 0 or y == 0 or x == w - 1 or y == h - 1):
				continue
			for d in [[0, -1, 0.0], [1, 0, PI * 0.5], [0, 1, PI], [-1, 0, PI * 1.5]]:
				var nx: int = x + int(d[0]); var ny: int = y + int(d[1])
				if ny < 0 or ny >= h or nx < 0 or nx >= w:
					continue
				if str(tiles[ny])[nx] in [".", "+", ">", "<"]:
					var n: Node3D = _fence_scene.instantiate()
					_map_root.add_child(n)
					var dirv := Vector3(float(d[0]), 0.0, float(d[1]))
					n.position = _world_pos(float(x), float(y)) + dirv * (_tile * 0.5) + Vector3(0.0, 0.02, 0.0)
					n.rotation.y = float(d[2])
					n.scale = Vector3(_tile / 2.06, 1.3, 1.0)


## A few COSMETIC villagers wandering the square (client-only; not game entities). They pick a
## random nearby walkable cell, walk there, idle a beat, repeat — so the town has life in it.
func _spawn_ambient_villagers(tiles: Array) -> void:
	var open: Array = []
	for y in range(2, tiles.size() - 2):
		for x in range(2, str(tiles[y]).length() - 2):
			if str(tiles[y])[x] == "." and _orth_walls(x, y) == 0:
				open.append(Vector2i(x, y))
	if open.size() < 8:
		return
	# Farthest-point spread so they DON'T clump in one corner (owner feedback 2026-07-09): each
	# villager is placed on the open cell furthest from all already-placed ones.
	var picks: Array = [open[open.size() / 2]]
	while picks.size() < 5:
		var best: Vector2i = picks[0]
		var best_d := -1.0
		for c in open:
			var nearest := 9999.0
			for p in picks:
				nearest = minf(nearest, Vector2(c).distance_to(Vector2(p)))
			if nearest > best_d:
				best_d = nearest
				best = c
		if best_d <= 0.0:
			break
		picks.append(best)
	var models := [ADVENTURERS + "Rogue.glb", ADVENTURERS + "Barbarian.glb", ADVENTURERS + "Mage.glb",
		ADVENTURERS + "Knight.glb"]
	for i in picks.size():
		var cell: Vector2i = picks[i]
		var scene = load(models[i % models.size()])
		if not (scene is PackedScene):
			continue
		var root := Node3D.new()
		_ent_root.add_child(root)
		root.position = _being_pos(cell.x, cell.y)
		var body: Node3D = (scene as PackedScene).instantiate()
		root.add_child(body)
		body.scale = Vector3.ONE * (_tile * 0.5)
		var ap: AnimationPlayer = null
		var aps := body.find_children("*", "AnimationPlayer", true)
		if not aps.is_empty():
			ap = aps[0]
			ap.play("Idle")
		_ambient.append({"node": root, "ap": ap, "cell": Vector2(cell), "home": Vector2(cell),
			"from": Vector2(cell), "to": Vector2(cell), "t": 1.0, "wait": float(i) * 0.9, "state": "idle"})


## Build newly-explored cells: floors under '.'/'+'/stairs, wall segments on wall-cell edges that
## face explored floor, a doorway piece for '+', the stairs piece for '>'/'<'. Cells build ONCE.
func _build_explored(tiles: Array) -> void:
	for y in tiles.size():
		var row: String = str(tiles[y])
		for x in row.length():
			var key := str(x) + "," + str(y)
			if not _exp.has(key) or _placed.has(key):
				continue
			_placed[key] = true
			var ch := row[x]
			match ch:
				".", "+", ">", "<":
					_place_floor(x, y)
					if ch == "+" and _door_scene != null:
						_place_scene(_door_scene, x, y, 0.0)
					elif (ch == ">" or ch == "<") and _stairs_scene != null:
						_place_stairs(tiles, x, y)
				"#":
					_place_walls(tiles, x, y)


func _place_floor(x: int, y: int) -> void:
	if _daylight:
		_place_grass(x, y)
		return
	if _floor_scenes.is_empty():
		return
	# Mostly the plain tile; every few cells one of the character variants (broken, mossy, rocky).
	var pick: int = (x * 7 + y * 13) % 10
	var scene: PackedScene = _floor_scenes[0]
	if pick >= 7 and _floor_scenes.size() > 1:
		var vi: int = (pick + x + y) % (_floor_scenes.size() - 1) + 1
		# The bulky rock-pile variant (kept LAST in the set) never lands in a corridor: props
		# and piles are dressing, but anything volumetric in a 1-tile passage reads as an
		# obstacle the game doesn't actually have (owner feedback 2026-07-08).
		if vi == _floor_scenes.size() - 1 and _orth_walls(x, y) >= 2:
			vi = 1
		scene = _floor_scenes[vi]
	_place_scene(scene, x, y, 0.0)
	_maybe_decor(x, y)


## Town ground: a grass quad per cell (subtle per-cell green variation), a worn RockPath tile on
## the well-trodden central plaza + the gate approach, and scatter (tufts/bushes/trees/props) so
## the square reads as an outdoor village, not a lit stone room.
func _place_grass(x: int, y: int) -> void:
	var q := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(_tile, _tile)
	q.mesh = pm
	var h := (x * 131 + y * 197) % 100
	var mat := _grass_mat.duplicate() as StandardMaterial3D
	mat.albedo_color = _grass_mat.albedo_color.lerp(Color(0.30, 0.44, 0.20), float(h) / 140.0)
	q.material_override = mat
	q.position = _world_pos(float(x), float(y)) + Vector3(0.0, 0.02, 0.0)
	_map_root.add_child(q)
	# a worn stone path across the very centre of the map (the plaza + the gate lane)
	if _path_scene != null and (absi(x - int(_snap.get("map_width", 44)) / 2) <= 1 or _orth_walls(x, y) == 0 and h < 6):
		var path: Node3D = _path_scene.instantiate()
		_map_root.add_child(path)
		path.position = _world_pos(float(x), float(y)) + Vector3(0.0, 0.03, 0.0)
		path.scale = Vector3(_tile / 2.05, 1.0, _tile / 2.0)
	_maybe_town_scatter(x, y, h)


## Nature/village scatter on open grass (tufts everywhere-ish; bushes/rocks/trees/props sparser),
## deterministic, kept off cell centres where beings stand.
func _maybe_town_scatter(x: int, y: int, h: int) -> void:
	var open := _orth_walls(x, y)
	var off := Vector3(_tile * 0.28 * float(h % 3 - 1), 0.02, _tile * 0.28 * float((h / 3) % 3 - 1))
	var pos := _world_pos(float(x), float(y)) + off
	var scene: PackedScene = null
	var sc := 0.5
	if open >= 1 and h % 7 == 0 and not _town_trees.is_empty():        # trees hug buildings/edges
		scene = _town_trees[h % _town_trees.size()]; sc = 0.42
	elif h % 11 == 0 and not _town_bushes.is_empty():
		scene = _town_bushes[h % _town_bushes.size()]; sc = 0.7
	elif h % 13 == 0 and not _town_rocks.is_empty():
		scene = _town_rocks[h % _town_rocks.size()]; sc = 0.5
	elif h % 5 == 0 and not _town_tufts.is_empty():
		scene = _town_tufts[h % _town_tufts.size()]; sc = 0.55
	elif open == 1 and h % 9 == 0 and not _town_props.is_empty():      # wagon/crate against a wall
		scene = _town_props[h % _town_props.size()]; sc = 0.5
	if scene == null:
		return
	var n: Node3D = scene.instantiate()
	_map_root.add_child(n)
	n.position = pos
	n.rotation.y = float(h) * 0.7
	n.scale = Vector3(sc, sc, sc)


## Orthogonal wall-cell count around a floor cell: 0 = open room, 1 = along a room wall,
## 2+ = corridor or corner pocket (anything bulky placed there reads as a blocker).
func _orth_walls(x: int, y: int) -> int:
	var tiles = _snap.get("tiles", [])
	if typeof(tiles) != TYPE_ARRAY:
		return 0
	var n := 0
	for d: Vector2i in [Vector2i(0, -1), Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0)]:
		var ny: int = y + d.y
		if ny < 0 or ny >= tiles.size():
			continue
		var row: String = str(tiles[ny])
		var nx: int = x + d.x
		if nx >= 0 and nx < row.length() and row[nx] == "#":
			n += 1
	return n


## Deterministic floor decor (cell-hash keyed): still black puddles (vault) or glowing cracks
## (emberdeep) on ~1 in 7 open cells, plus scatter PROPS (rubble, barrels, spilled treasure) on
## wall-adjacent cells — nudged toward the wall so walkways stay visually clear. Pure dressing.
func _maybe_decor(x: int, y: int) -> void:
	if _decor == "":
		return
	_maybe_prop(x, y)
	var h := (x * 131 + y * 197) % 100
	if h >= 14:
		return
	var q := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	# puddles spread wide; ember cracks stay narrow slivers
	var base_w := 0.40 if _decor == "wet" else 0.22
	var side := _tile * (base_w + 0.05 * float(h % 6))
	pm.size = Vector2(side, side * (0.65 + 0.08 * float(h % 4)))
	q.mesh = pm
	q.material_override = _puddle_mat if _decor == "wet" else _ember_mat
	q.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	q.position = _world_pos(float(x), float(y)) \
		+ Vector3(0.18 * float(h % 3 - 1), _floor_top + 0.012, 0.14 * float(h % 5 - 2))
	q.rotation.y = float(h) * 0.6
	_map_root.add_child(q)


## A prop against the wall on ~1 in 6 wall-adjacent floor cells (deterministic). The offset toward
## the wall keeps the cell's center — where beings actually stand — visually free.
func _maybe_prop(x: int, y: int) -> void:
	var props: Array = _prop_sets.get(_decor, [])
	if props.is_empty():
		return
	# Room-edge cells ONLY (exactly one orthogonal wall): a 1-tile corridor touches walls on
	# both sides, so without this test every passage collected clutter that read as blockage.
	if _orth_walls(x, y) != 1:
		return
	var h := (x * 89 + y * 271) % 100
	if h >= 16:
		return
	var tiles = _snap.get("tiles", [])
	if typeof(tiles) != TYPE_ARRAY:
		return
	var wall_dir := Vector2i.ZERO
	for d: Vector2i in [Vector2i(0, -1), Vector2i(1, 0), Vector2i(0, 1), Vector2i(-1, 0)]:
		var ny: int = y + d.y
		if ny < 0 or ny >= tiles.size():
			continue
		var row: String = str(tiles[ny])
		var nx: int = x + d.x
		if nx >= 0 and nx < row.length() and row[nx] == "#":
			wall_dir = d
			break
	if wall_dir == Vector2i.ZERO:
		return
	var n: Node3D = (props[(h + x) % props.size()] as PackedScene).instantiate()
	_map_root.add_child(n)
	n.position = _world_pos(float(x), float(y)) \
		+ Vector3(float(wall_dir.x), 0.0, float(wall_dir.y)) * (_tile * 0.30) \
		+ Vector3(0.0, _floor_top, 0.0)
	n.rotation.y = float(h) * 1.3


func _place_scene(scene: PackedScene, x: int, y: int, yaw: float) -> Node3D:
	var n: Node3D = scene.instantiate()
	_map_root.add_child(n)
	n.position = _world_pos(float(x), float(y))
	n.rotation.y = yaw
	return n


## A wall CELL renders as wall segments on each edge shared with an explored floor cell — the
## classic tile-to-face mapping (the far side of the wall stays void; the camera never sees it).
func _place_walls(tiles: Array, x: int, y: int) -> void:
	if _daylight:
		_place_fence(tiles, x, y)
		return
	if _wall_scene == null:
		return
	var dirs := [[0, -1, 0.0], [1, 0, PI * 0.5], [0, 1, PI], [-1, 0, PI * 1.5]]
	for d in dirs:
		var nx: int = x + int(d[0])
		var ny: int = y + int(d[1])
		if ny < 0 or ny >= tiles.size():
			continue
		var row: String = str(tiles[ny])
		if nx < 0 or nx >= row.length():
			continue
		if row[nx] in [".", "+", ">", "<"] and _exp.has(str(nx) + "," + str(ny)):
			# Variety: ~1 in 6 segments is a cracked/broken variant (deterministic per edge).
			var wh := (x * 31 + y * 57 + int(d[0]) * 3 + int(d[1]) * 7) % 12
			var wall_scene := _wall_scene
			if wh < 2 and _wall_variants.size() > wh:
				wall_scene = _wall_variants[wh]
			var n: Node3D = wall_scene.instantiate()
			_map_root.add_child(n)
			# Seat the segment so its INNER FACE lies exactly on the shared edge — the mesh is
			# thick (half a tile) and Z-symmetric, so centering it on the edge would eat a
			# quarter-tile of corridor from BOTH sides (1-tile corridors read as squeeze-throughs;
			# owner feedback 2026-07-08). Length is scaled to exactly one tile: the native piece is
			# two tiles long, and the overhang made adjacent coplanar segments z-fight.
			# LOW walls (the classic 2.5D move): full-height walls between the camera and a
			# character occlude them completely — waist-high still reads as a wall.
			var dirv := Vector3(float(d[0]), 0.0, float(d[1]))
			n.position = _world_pos(float(x), float(y)) + dirv * (_tile * 0.5 - _wall_thick * 0.5)
			n.rotation.y = float(d[2])
			n.scale.x = _tile / _wall_len
			n.scale.y = 0.55
			_maybe_wall_dressing(x, y, dirv, float(d[2]), wh)


## Town buildings: a wooden PALISADE fence on each edge facing open ground — scaled a bit taller
## than the low garden fence so a building footprint reads as a walled structure, not a hedge, and
## grass tucked under so no stone shows. (Bespoke modular houses are a later polish; this reads as
## an outdoor village at a glance.)
func _place_fence(tiles: Array, x: int, y: int) -> void:
	if _fence_scene == null:
		return
	# grass under the wall cell too, so the footprint isn't a bare hole
	if _grass_mat != null:
		var g := MeshInstance3D.new()
		var pm := PlaneMesh.new()
		pm.size = Vector2(_tile, _tile)
		g.mesh = pm
		g.material_override = _grass_mat
		g.position = _world_pos(float(x), float(y)) + Vector3(0.0, 0.01, 0.0)
		_map_root.add_child(g)
	var dirs := [[0, -1, 0.0], [1, 0, PI * 0.5], [0, 1, PI], [-1, 0, PI * 1.5]]
	for d in dirs:
		var nx: int = x + int(d[0])
		var ny: int = y + int(d[1])
		if ny < 0 or ny >= tiles.size():
			continue
		var row: String = str(tiles[ny])
		if nx < 0 or nx >= row.length():
			continue
		if row[nx] in [".", "+", ">", "<"] and _exp.has(str(nx) + "," + str(ny)):
			var n: Node3D = _fence_scene.instantiate()
			_map_root.add_child(n)
			var dirv := Vector3(float(d[0]), 0.0, float(d[1]))
			n.position = _world_pos(float(x), float(y)) + dirv * (_tile * 0.5) + Vector3(0.0, 0.02, 0.0)
			n.rotation.y = float(d[2])
			n.scale = Vector3(_tile / 2.06, 2.4, 1.0)   # ~1 tile wide, raised to palisade height


## Torches and banners live on the corridor-facing side of wall segments (deterministic, sparse).
## Each torch carries its OWN small unshadowed light — the rooms stop depending on the player's
## torch alone, and light pools give distant corridors somewhere to lead the eye. Budgeted.
func _maybe_wall_dressing(x: int, y: int, dirv: Vector3, yaw: float, wh: int) -> void:
	# The corridor-facing wall surface sits ON the tile boundary (walls are inset into their
	# cell) — mount dressing a hair proud of it so brackets and cloth read against the stone.
	var edge := _world_pos(float(x), float(y)) + dirv * (_tile * 0.5 + 0.04)
	if wh == 4 and _torch_scene != null and _torch_lights < 36:
		_torch_lights += 1
		var t: Node3D = _torch_scene.instantiate()
		_map_root.add_child(t)
		t.position = edge + Vector3(0.0, 1.35, 0.0)
		t.rotation.y = yaw
		var l := OmniLight3D.new()
		l.light_color = Color(1.0, 0.62, 0.3) if _decor == "ember" else Color(1.0, 0.68, 0.38)
		l.light_energy = 1.15
		l.omni_range = 4.5
		l.shadow_enabled = false
		l.position = Vector3(0.0, 0.35, 0.0)
		t.add_child(l)
	elif wh == 9 and _banner_scenes.has(_decor):
		var b: Node3D = (_banner_scenes[_decor] as PackedScene).instantiate()
		_map_root.add_child(b)
		b.position = edge + Vector3(0.0, 0.9, 0.0)
		b.rotation.y = yaw
		b.scale = Vector3(0.6, 0.6, 0.6)


## The stairs piece is scenery the player can climb VISUALLY (the game core treats the tile as
## plain walkable ground — the slice's real exit is the locked door seated nearby). Native size is
## ~2.5x2 tiles, so unscaled it overflowed its cell and read full-height next to waist-high walls:
## scale it into ONE tile, face it toward the adjacent floor it serves, and register the cell so
## _being_pos lifts whoever stands on it.
func _place_stairs(tiles: Array, x: int, y: int) -> void:
	var n: Node3D = _stairs_scene.instantiate()
	_map_root.add_child(n)
	var s := _tile / maxf(_stairs_size.x, 0.1)
	n.scale = Vector3(s, s, s)
	# Face the first adjacent explored floor tile (the corridor the stairs serve).
	var yaw := 0.0
	var dirs := [[0, 1, 0.0], [1, 0, PI * 0.5], [0, -1, PI], [-1, 0, PI * 1.5]]
	var fwd := Vector3(0, 0, 1)
	for d in dirs:
		var nx: int = x + int(d[0])
		var ny: int = y + int(d[1])
		if ny >= 0 and ny < tiles.size():
			var row: String = str(tiles[ny])
			if nx >= 0 and nx < row.length() and row[nx] in [".", "+", ">", "<"]:
				yaw = float(d[2])
				fwd = Vector3(float(d[0]), 0.0, float(d[1]))
				break
	n.rotation.y = yaw
	# The mesh's origin sits at its z=0 base edge (it extends one native depth forward):
	# pull it back so the scaled footprint is centered in the cell.
	n.position = _world_pos(float(x), float(y)) - fwd * (_stairs_size.z * s * 0.5)
	_stair_cells[str(x) + "," + str(y)] = Vector2(float(x), float(y))


## The movement-range overlay (green tiles = where THIS turn's remaining feet can take you) —
## rebuilt on every snapshot, shown only on the player's combat turn. Same rules the server
## enforces: 5 ft per orthogonal step, living enemies are walls, occupied cells excluded.
func _update_range_overlay() -> void:
	var mm := _range_mm.multimesh
	if str(_snap.get("mode", "")) != "combat" or _turn_id != str(_snap.get("player", {}).get("id", "")):
		mm.instance_count = 0
		return
	var steps := int(float(_snap.get("combat_movement", 0)) / 5.0)
	var player = _snap.get("player", {})
	var pos = player.get("pos", null)
	if steps <= 0 or typeof(pos) != TYPE_ARRAY or pos.size() < 2:
		mm.instance_count = 0
		return
	var tiles = _snap.get("tiles", [])
	if typeof(tiles) != TYPE_ARRAY or tiles.is_empty():
		mm.instance_count = 0
		return
	var blocked := {}
	for e in _snap.get("entities", []):
		if typeof(e) == TYPE_DICTIONARY and typeof(e.get("pos", null)) == TYPE_ARRAY:
			var ep: Array = e["pos"]
			blocked[Vector2i(int(ep[0]), int(ep[1]))] = true
	var src := Vector2i(int(pos[0]), int(pos[1]))
	var dist := {src: 0}
	var q: Array = [src]
	var head := 0
	var cells: Array = []
	while head < q.size():
		var c: Vector2i = q[head]
		head += 1
		if int(dist[c]) >= steps:
			continue
		for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			var nb: Vector2i = c + d
			if dist.has(nb) or nb.y < 0 or nb.y >= tiles.size():
				continue
			var row: String = str(tiles[nb.y])
			if nb.x < 0 or nb.x >= row.length() or not (row[nb.x] in [".", "+", ">", "<"]):
				continue
			if blocked.has(nb):
				continue
			dist[nb] = int(dist[c]) + 1
			q.append(nb)
			cells.append(nb)
	mm.instance_count = cells.size()
	for i in cells.size():
		var wp := _world_pos(float(cells[i].x), float(cells[i].y))
		var xf := Transform3D(Basis.from_scale(Vector3(_tile, 1.0, _tile)),
			wp + Vector3(0.0, _floor_top + 0.02, 0.0))
		mm.set_instance_transform(i, xf)


func _update_shroud(tiles: Array) -> void:
	var cells: Array = []
	for k in _exp.keys():
		if not _vis.has(k):
			cells.append(k)
	var mm := _shroud.multimesh
	mm.instance_count = cells.size()
	for i in cells.size():
		var parts: PackedStringArray = str(cells[i]).split(",")
		var wp := _world_pos(float(int(parts[0])), float(int(parts[1])))
		var xf := Transform3D(Basis.from_scale(Vector3(_tile, 1.0, _tile)), wp + Vector3(0, 0.25, 0))
		mm.set_instance_transform(i, xf)


# ---------------------------------------------------------------- entities

## Resolve an entity to a model spec {path, h, ember} — empty Dictionary = billboard fallback.
func _model_for(e: Dictionary, kind: String) -> Dictionary:
	var id := str(e.get("id", ""))
	if kind == "player":
		var ct := str(e.get("creature_type", ""))
		var cls := "fighter"
		if "(" in ct and ")" in ct:
			cls = ct.substr(ct.find("(") + 1, ct.rfind(")") - ct.find("(") - 1).strip_edges()
		return {"path": str(CLASS_MODELS.get(cls, CLASS_MODELS["fighter"])), "h": 0.0}
	if CAST_MODELS.has(id):
		return {"path": str(CAST_MODELS[id]), "h": 0.0}
	var nm := str(e.get("name", "")).to_lower()
	if ENEMY_MODELS.has(nm):
		return ENEMY_MODELS[nm]
	return {}                                   # billboard fallback


func _sprite_idx(e: Dictionary, kind: String) -> int:
	if _sheet.is_empty():
		return -1
	if kind == "player":
		return int(_sheet.get("by_id", {}).get("player", -1))
	var by_id = _sheet.get("by_id", {})
	var id := str(e.get("id", ""))
	if by_id.has(id):
		return int(by_id[id])
	var by_name = _sheet.get("by_name", {})
	var nm := str(e.get("name", "")).to_lower()
	if by_name.has(nm):
		return int(by_name[nm])
	return -1


func _all_drawables() -> Array:
	var out: Array = []
	var player = _snap.get("player", {})
	if typeof(player) == TYPE_DICTIONARY and player.has("pos"):
		var p: Dictionary = (player as Dictionary).duplicate()
		p["__kind"] = "player"
		out.append(p)
	var entities = _snap.get("entities", [])
	if typeof(entities) == TYPE_ARRAY:
		for e in entities:
			if typeof(e) == TYPE_DICTIONARY:
				var d: Dictionary = (e as Dictionary).duplicate()
				d["__kind"] = str(e.get("kind", "enemy"))
				out.append(d)
	return out


## Server-walked route for an entity (the "path" event, forwarded by main.gd). Stored and consumed
## by the NEXT snapshot's _sync_entities — the batch always ends with a snapshot, so the route and
## the position change land together.
func follow_path(id: String, tiles: Array) -> void:
	if typeof(tiles) == TYPE_ARRAY and tiles.size() >= 2:
		_pending_route[id] = tiles


## How far the player's walk animation still has to go, in tiles. main.gd paces held-key movement
## with this: the next step is sent just before the current one lands, so held WASD chains into one
## continuous walk instead of discrete hops.
func player_glide_remaining() -> float:
	if not _anim.has("player"):
		return 0.0
	var a: Dictionary = _anim["player"]
	var pts: Array = a["pts"]
	var left := -float(a["d"])
	for i in range(pts.size() - 1):
		left += (Vector2(pts[i + 1]) - Vector2(pts[i])).length()
	return maxf(0.0, left)


## BFS a visual route between two tiles over walkable terrain — the replay fallback for entities
## whose route the server doesn't narrate (followers trailing a long click-move, enemies closing
## in combat). Looks only; other beings aren't blockers. Returns [] when unreachable/too far.
func _client_path(from: Vector2, to: Vector2) -> Array:
	var tiles = _snap.get("tiles", [])
	if typeof(tiles) != TYPE_ARRAY or tiles.is_empty():
		return []
	var src := Vector2i(int(from.x), int(from.y))
	var dst := Vector2i(int(to.x), int(to.y))
	var prev := {src: src}
	var q: Array = [src]
	var head := 0
	while head < q.size() and q.size() < 4000:
		var c: Vector2i = q[head]
		head += 1
		if c == dst:
			break
		for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			var nb: Vector2i = c + d
			if prev.has(nb) or nb.y < 0 or nb.y >= tiles.size():
				continue
			var row: String = str(tiles[nb.y])
			if nb.x < 0 or nb.x >= row.length() or not (row[nb.x] in [".", "+", ">", "<"]):
				continue
			prev[nb] = c
			q.append(nb)
	if not prev.has(dst):
		return []
	var path: Array = []
	var cur := dst
	while cur != src:
		path.push_front(Vector2(float(cur.x), float(cur.y)))
		cur = prev[cur]
	path.push_front(Vector2(float(src.x), float(src.y)))
	return path


## Start (or extend) a waypoint walk for an entity toward its new snapshot tile. Route priority:
## the server's own walked path > client BFS replay > straight line (adjacent steps only).
func _start_walk(id: String, prev: Vector2, now: Vector2) -> void:
	var node: Node3D = _ents[id]["node"]
	var route: Array = []
	if _pending_route.has(id):
		var r: Array = _pending_route[id]
		var last = r[r.size() - 1]
		if typeof(last) == TYPE_ARRAY and last.size() >= 2 \
				and Vector2(float(last[0]), float(last[1])) == now:
			for p in r:
				route.append(Vector2(float(p[0]), float(p[1])))
	if route.is_empty():
		if prev.distance_to(now) <= 1.01:
			route = [prev, now]
		else:
			route = _client_path(prev, now)
	var total := 0.0
	for i in range(route.size() - 1):
		total += (Vector2(route[i + 1]) - Vector2(route[i])).length()
	if route.size() < 2 or total > SNAP_BEYOND_TILES:
		_anim.erase(id)
		node.position = _being_pos(now.x, now.y)
		return
	# Mid-walk update: continue from where the entity is actually RENDERED (held-key steps chain
	# seamlessly; a snapshot landing mid-glide no longer skips the model back a tile).
	if _anim.has(id):
		var cur := Vector2(node.position.x / _tile - 0.5, node.position.z / _tile - 0.5)
		if cur.distance_to(Vector2(route[0])) < 1.5:
			route[0] = cur
	_anim[id] = {"pts": route, "d": 0.0,
		"speed": clampf(total / TREK_MAX_S, WALK_TILES_PER_S, RUN_TILES_PER_S)}


func _sync_entities() -> void:
	var seen := {}
	for e in _all_drawables():
		var id := str(e.get("id", ""))
		var pos = e.get("pos", null)
		if id == "" or typeof(pos) != TYPE_ARRAY or pos.size() < 2:
			continue
		seen[id] = true
		var kind := str(e["__kind"])
		var now := Vector2(float(pos[0]), float(pos[1]))
		if not _ents.has(id):
			_spawn_entity(id, e, kind, now)
		else:
			# revive: a downed character coming back to their feet stands up out of the death pose
			var was_down := bool(_ents[id].get("down", false))
			_ents[id]["down"] = bool(e.get("down", false))
			if was_down and not bool(_ents[id]["down"]) and str(_ents[id]["state"]) == "dead":
				_ents[id]["state"] = "idle"
				_play_anim(_ents[id], ["Idle"], true)
		if _last_pos.has(id):
			var prev: Vector2 = _last_pos[id]
			if prev != now:
				_start_walk(id, prev, now)
		else:
			_ents[id]["node"].position = _being_pos(now.x, now.y)
		_last_pos[id] = now
		_update_bars(id, e, kind)
	_pending_route.clear()                     # routes are per-batch; never let one go stale
	# Remove the departed — EXCEPT anyone mid-death: the corpse must finish its animation and
	# sink before the node goes (they used to vanish the instant the killing snapshot landed).
	for id in _ents.keys().duplicate():
		if not seen.has(id):
			if _has_death_fx(id):      # the killing event precedes the snapshot in the same batch
				continue
			_free_entity(id)


func _has_death_fx(id: String) -> bool:
	for f in _fx:
		var k := str(f.get("kind", ""))
		if (k == "death" or k == "corpse") and str(f.get("id", "")) == id:
			return true
	return false


func _free_entity(id: String) -> void:
	if _ents.has(id):
		_ents[id]["node"].queue_free()
	_ents.erase(id)
	_anim.erase(id)
	_last_pos.erase(id)
	_facing.erase(id)


func _spawn_entity(id: String, e: Dictionary, kind: String, at: Vector2) -> void:
	var root := Node3D.new()
	_ent_root.add_child(root)
	root.position = _being_pos(at.x, at.y)
	var ent := {"node": root, "ap": null, "sprite": false, "state": "idle", "kind": kind,
				"caster": false, "down": bool(e.get("down", false)), "label": null, "bar": null}
	var loaded := false
	# The locked Door entity (the slice's objective) is ARCHITECTURE, not a creature: a BARRED
	# gate segment (reads "locked" — the open doorway hole read as a passage), seated like a wall
	# and aligned with the wall line it sits in.
	if kind == "door":
		var gate := _gate_scene if _gate_scene != null else _door_scene
		if gate != null:
			var door: Node3D = gate.instantiate()
			root.add_child(door)
			door.scale = Vector3(_tile / _wall_len, 0.55, 1.0)
			door.rotation.y = 0.0 if _wall_runs_ew(at) else PI * 0.5
			loaded = true
	var spec := _model_for(e, kind)
	var model_path := str(spec.get("path", ""))
	if not loaded and model_path != "" and ResourceLoader.exists(model_path):
		var scene = load(model_path)
		if scene is PackedScene:
			var body: Node3D = scene.instantiate()
			root.add_child(body)
			var want_h := float(spec.get("h", 0.0))
			if want_h > 0.0:
				# Third-party rigs (Quaternius FBX exports) carry arbitrary armature scale:
				# measure the assembled body in world space and normalize to the target height.
				var ab := _body_aabb(body)
				body.scale = Vector3.ONE * (want_h / maxf(ab.size.y, 0.05))
			else:
				# KayKit characters are authored for a 2-unit grid: scale to whatever the
				# measured tile actually is so people fit their cells (2u tile -> native size).
				body.scale = Vector3.ONE * (_tile * 0.5)
			if bool(spec.get("ember", false)):
				# cinder-husk: the skeleton smolders from inside (translucent ember overlay)
				for m in body.find_children("*", "MeshInstance3D", true, false):
					(m as MeshInstance3D).material_overlay = _husk_overlay
			if CAST_TINTS.has(id):
				_tint_model(body, CAST_TINTS[id])
			ent["caster"] = model_path.contains("Mage")   # spellcasters swing spells, not swords
			ent["model_path"] = model_path                # the talk scene's bust uses the same GLB
			var aps := body.find_children("*", "AnimationPlayer", true)
			if not aps.is_empty():
				ent["ap"] = aps[0]
				# KayKit-rigged characters get the shared 161-clip library on top of their
				# embedded set (sneak, lockpick, crouch, bow-work... — the acting vocabulary).
				if model_path.begins_with(ADVENTURERS) or model_path.begins_with(SKELETONS):
					(ent["ap"] as AnimationPlayer).add_animation_library("kk", _kaykit_library())
				_play_anim(ent, ["Idle"], true)
			loaded = true
	if not loaded:
		var spr := Sprite3D.new()
		spr.texture = _atlas
		spr.region_enabled = true
		var idx := _sprite_idx(e, kind)
		if idx >= 0:
			@warning_ignore("integer_division")
			spr.region_rect = Rect2((idx % _cols) * _ts, (idx / _cols) * _ts, _ts, _ts)
		spr.pixel_size = _tile * 0.055
		spr.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
		spr.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
		spr.alpha_cut = SpriteBase3D.ALPHA_CUT_DISCARD
		spr.shaded = true
		spr.position.y = _tile * 0.45
		root.add_child(spr)
		ent["sprite"] = true
	# floating name — color-coded by allegiance so a crowded room parses at a glance
	var lbl := Label3D.new()
	lbl.text = str(e.get("name", ""))
	lbl.font_size = 40
	lbl.pixel_size = 0.005
	lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	lbl.no_depth_test = true
	match kind:
		"enemy":
			lbl.modulate = Color(1.0, 0.6, 0.55, 0.95)
		"follower":
			lbl.modulate = Color(0.65, 1.0, 0.72, 0.95)
		"npc":
			lbl.modulate = Color(0.95, 0.88, 0.68, 0.95)
		"door":
			lbl.modulate = Color(0.72, 0.76, 0.85, 0.8)
		_:
			lbl.modulate = Color(0.95, 0.95, 0.95, 0.9)
	lbl.outline_size = 8
	lbl.position.y = _tile * 1.05
	root.add_child(lbl)
	ent["label"] = lbl
	_ents[id] = ent


## The KayKit Character Animations 1.1 library (assets/kaykit/animations, CC0): 161 clips —
## Sneaking/Crouching/Lockpicking/bow-work and more that the characters' embedded sets lack.
## Authored against a scene rooted "Rig_Medium"; our character GLBs root the same skeleton at
## "Rig", so each clip is duplicated with its track paths rewritten before joining the shared
## AnimationLibrary. Built once, added to every KayKit-rigged AnimationPlayer as "kk/<name>"
## (the exact->prefix->contains matcher finds those transparently).
var _kk_lib_cache: AnimationLibrary = null

const KK_ANIM_DIR := "res://assets/kaykit/animations/"
const KK_ANIM_FILES := ["Rig_Medium_General.glb", "Rig_Medium_Tools.glb",
	"Rig_Medium_MovementBasic.glb", "Rig_Medium_MovementAdvanced.glb",
	"Rig_Medium_CombatMelee.glb", "Rig_Medium_CombatRanged.glb",
	"Rig_Medium_Simulation.glb", "Rig_Medium_Special.glb"]

func _kaykit_library() -> AnimationLibrary:
	if _kk_lib_cache != null:
		return _kk_lib_cache
	_kk_lib_cache = AnimationLibrary.new()
	for f in KK_ANIM_FILES:
		var scene = load(KK_ANIM_DIR + f) if ResourceLoader.exists(KK_ANIM_DIR + f) else null
		if not (scene is PackedScene):
			continue
		var inst: Node = (scene as PackedScene).instantiate()
		var aps := inst.find_children("*", "AnimationPlayer", true, false)
		if not aps.is_empty():
			var ap := aps[0] as AnimationPlayer
			for aname in ap.get_animation_list():
				if str(aname) == "T-Pose" or _kk_lib_cache.has_animation(aname):
					continue
				var anim: Animation = ap.get_animation(aname).duplicate()
				for t in anim.get_track_count():
					var path := str(anim.track_get_path(t))
					if path.begins_with("Rig_Medium/"):
						anim.track_set_path(t, NodePath("Rig/" + path.trim_prefix("Rig_Medium/")))
				_kk_lib_cache.add_animation(aname, anim)
		inst.free()
	return _kk_lib_cache


## World-space bounding box of an instantiated body, expressed in the body's own local frame —
## robust against rigs whose scale lives on an armature node above the mesh (skinned FBX exports).
func _body_aabb(body: Node3D) -> AABB:
	var total := AABB()
	var first := true
	var inv := body.global_transform.affine_inverse()
	for m in body.find_children("*", "MeshInstance3D", true, false):
		var mi := m as MeshInstance3D
		var rel := inv * mi.global_transform
		var ab := rel * mi.get_aabb()
		total = ab if first else total.merge(ab)
		first = false
	return total


## Does the wall line through this cell run east-west? (Used to align the doorway piece.)
func _wall_runs_ew(at: Vector2) -> bool:
	var tiles = _snap.get("tiles", [])
	var x := int(at.x)
	var y := int(at.y)
	if typeof(tiles) != TYPE_ARRAY or y < 0 or y >= tiles.size():
		return true
	var row: String = str(tiles[y])
	var west := x - 1 >= 0 and x - 1 < row.length() and row[x - 1] == "#"
	var east := x + 1 >= 0 and x + 1 < row.length() and row[x + 1] == "#"
	return west or east


func _update_bars(id: String, e: Dictionary, kind: String) -> void:
	var ent: Dictionary = _ents[id]
	var hp = e.get("hp", null)
	var max_hp = e.get("max_hp", null)
	var want := (kind == "follower") or (kind == "enemy" and bool(_snap.get("show_enemy_hp", false)) and hp != null)
	var lbl: Label3D = ent.get("label")
	if lbl == null:
		return
	var base := str(e.get("name", ""))
	if want and hp != null and max_hp != null:
		lbl.text = "%s  %d/%d" % [base, int(hp), int(max_hp)]
	elif bool(e.get("down", false)):
		lbl.text = base + "  (down)"
	else:
		lbl.text = base


## Idle depends on the situation: relaxed out of combat, a FIGHTING STANCE inside it (weapons up,
## Idle_Combat/2H_Melee_Idle) — half of what made fights read as "alpha" was everyone standing
## around casually mid-battle.
func _idle_prefer() -> Array:
	if str(_snap.get("mode", "")) == "combat":
		return ["Idle_Combat", "2H_Melee_Idle", "Unarmed_Idle", "Idle"]
	return ["Idle"]


## Variety: play a RANDOM clip whose name contains `key` (skipping static poses and other
## excluded fragments) — attack/hit/death repeats stop looking identical. Falls back to the
## ordered prefer list when nothing matches.
func _play_random(ent: Dictionary, key: String, exclude: Array, fallback: Array) -> void:
	var ap: AnimationPlayer = ent.get("ap")
	if ap == null:
		return
	var picks: Array = []
	for a in ap.get_animation_list():
		var al := str(a).to_lower()
		if not al.contains(key):
			continue
		var bad := al.contains("pose")
		for ex in exclude:
			if al.contains(str(ex)):
				bad = true
		if not bad:
			picks.append(a)
	if picks.is_empty():
		_play_anim(ent, fallback)
	else:
		ap.play(picks[randi() % picks.size()])


## Multiply every surface of a character model by a tint (per-instance, so other characters
## sharing the model aren't affected) — keeps the texture detail, shifts the palette.
func _tint_model(body: Node3D, tint: Color) -> void:
	for m in body.find_children("*", "MeshInstance3D", true, false):
		var mi := m as MeshInstance3D
		if mi.mesh == null:
			continue
		for s in range(mi.mesh.get_surface_count()):
			var mat := mi.get_active_material(s)
			if mat is StandardMaterial3D:
				var dup := (mat as StandardMaterial3D).duplicate()
				dup.albedo_color = dup.albedo_color * tint
				mi.set_surface_override_material(s, dup)


func _play_anim(ent: Dictionary, prefer: Array, loop: bool = false) -> void:
	var ap: AnimationPlayer = ent.get("ap")
	if ap == null:
		return
	var list := ap.get_animation_list()
	# EXACT name first, then prefix, then substring — a bare "contains" match once put a standing
	# character into Lie_Idle (a lump on the floor) because it hit the wrong clip alphabetically.
	for pass_kind in ["exact", "prefix", "contains"]:
		for want in prefer:
			var w := str(want).to_lower()
			for a in list:
				var al := str(a).to_lower()
				var ok := false
				match pass_kind:
					"exact":
						ok = al == w
					"prefix":
						ok = al.begins_with(w)
					"contains":
						ok = al.contains(w)
				if ok:
					if loop:
						var anim := ap.get_animation(a)
						if anim != null:
							anim.loop_mode = Animation.LOOP_LINEAR
						# Already mid-clip? Leave it running — restarting Walking from frame 0 on
						# every tile was the single biggest source of the stuttery movement feel.
						if ap.current_animation == a and ap.is_playing():
							return
					ap.play(a)
					return


# ------------------------------------------------------- dev: animation browser
## Backing for the F10 animation test panel (dev_anim.gd) — inspect and fire any clip on any
## live entity. Read-only against game state; playing a clip just drives the AnimationPlayer.

func debug_entities() -> Array:
	var out: Array = []
	for id in _ents:
		if _ents[id].get("ap") != null:
			out.append(id)
	out.sort()
	return out


func debug_clips(id: String) -> Array:
	if not _ents.has(id) or _ents[id].get("ap") == null:
		return []
	var names := Array((_ents[id]["ap"] as AnimationPlayer).get_animation_list())
	names.sort()
	return names


func debug_play(id: String, clip: String) -> void:
	if not _ents.has(id) or _ents[id].get("ap") == null:
		return
	var ap: AnimationPlayer = _ents[id]["ap"]
	if ap.has_animation(clip):
		_ents[id]["state"] = "react"   # keep the idle/walk machine from instantly overriding
		ap.play(clip)


func debug_idle(id: String) -> void:
	if _ents.has(id):
		_ents[id]["state"] = "idle"
		_play_anim(_ents[id], ["Idle"], true)


## The GLB an entity renders with ("" for billboard sprites) — the talk scene builds its live
## 3D bust from the SAME model, so the face you talk to is the person you saw in the world.
func model_path_for(id: String) -> String:
	return str(_ents[id].get("model_path", "")) if _ents.has(id) else ""


# ------------------------------------------------------- stage-direction acting

## The engine ships every NPC line with third-person stage business (DialogueEvent.action),
## authored by the character's MIND — never shown as text (owner directive; the DM narrates it
## aloud only when relevant). Here the BODY performs it: keyword -> clip, first match wins,
## matched at word starts (a leading space guard keeps "sit" out of "hesitates"). Unmatched
## business just turns the speaker toward the player — acting NOTHING beats acting WRONG.
const DIRECTION_VERBS := [
	{"k": ["sneak", "slip", "stealth", "creep", "shadow"], "a": ["Sneaking", "Crouching"], "d": 1.6},
	{"k": ["lockpick", "pick the lock", "pins", "latch"], "a": ["Lockpicking", "Lockpick", "Interact"], "d": 1.8},
	{"k": ["crouch", "kneel", "stoop"], "a": ["Crouching", "PickUp"], "d": 1.2},
	{"k": ["crawl"], "a": ["Crawling"], "d": 1.5},
	{"k": ["cast", "spell", "conjure", "summon", "weave"], "a": ["Spellcast_Raise", "Ranged_Magic_Summon", "Spellcasting"], "d": 1.4},
	{"k": ["throw", "toss", "hurl", "fling"], "a": ["Throw"], "d": 0.9},
	{"k": ["dodge", "duck", "flinch", "recoil", "step back", "backs away", "darts back"], "a": ["Dodge_Backward", "Dodge_Left"], "d": 0.6},
	{"k": ["block", "shield", "brace", "guard"], "a": ["Block", "Blocking"], "d": 1.0},
	{"k": ["draws her", "draws his", "blade", "sword", "dagger"], "a": ["Block", "2H_Melee_Idle"], "d": 1.2},
	{"k": ["drink", "sip", "swig", "flask"], "a": ["Use_Item", "Interact"], "d": 1.0},
	{"k": ["pick up", "picks up", "grab", "pocket", "stow", "tuck"], "a": ["PickUp", "Interact"], "d": 1.0},
	{"k": ["search", "rummage", "examin", "inspect", "stud"], "a": ["Interact", "PickUp"], "d": 1.2},
	{"k": ["cheer", "celebrat", "triumph", "pumps a fist"], "a": ["Cheer"], "d": 1.2},
	{"k": ["taunt", "sneer", "mock", "spits"], "a": ["Taunt", "Interact"], "d": 1.2},
	{"k": ["kick", "shove", "push"], "a": ["Unarmed_Melee_Attack_Kick", "Interact"], "d": 0.8},
	{"k": ["punch"], "a": ["Unarmed_Melee_Attack_Punch_A"], "d": 0.8},
	{"k": ["jump", "leap", "spring"], "a": ["Jump_Full_Short", "Jump_Start"], "d": 0.9},
	{"k": ["sit", "settle"], "a": [], "d": 4.0, "kind": "rest"},
	{"k": ["point", "gestur", "beckon", "motions", "wave"], "a": ["Interact"], "d": 1.0},
]

func act_direction(id: String, action: String) -> void:
	if not _ents.has(id):
		return
	# a speaking character turns to their audience regardless of whether the business maps
	if id != "player" and _last_pos.has(id) and _last_pos.has("player"):
		var dirv: Vector2 = Vector2(_last_pos["player"]) - Vector2(_last_pos[id])
		if dirv.length() > 0.1:
			_facing[id] = atan2(dirv.x, dirv.y)
	var text := " " + action.to_lower()
	if text.strip_edges() == "":
		return
	for row in DIRECTION_VERBS:
		for kw in row["k"]:
			if text.contains(" " + str(kw)):
				_fx.append({"kind": str(row.get("kind", "react")), "id": id,
					"anims": row["a"], "seated": false,
					"delay": 0.15, "t": 0.0, "dur": float(row["d"])})
				return


# ---------------------------------------------------------------- combat fx

## Same semantic beats as the 2D view, staged in 3D: attackers play an attack clip and lunge,
## victims play a hit clip, damage floats as Label3D, deaths play the death clip on a fading
## ghost, crits shake the camera.
func combat_fx(data: Dictionary) -> void:
	var sfx := str(data.get("sfx", ""))
	var target := str(data.get("target", ""))
	var attacker := str(data.get("attacker", ""))
	match sfx:
		"hit", "crit", "miss":
			if _last_pos.has(attacker) and _last_pos.has(target):
				_fx.append({"kind": "attack", "id": attacker, "at": Vector2(_last_pos[attacker]),
					"toward": Vector2(_last_pos[target]), "delay": _fx_stagger, "t": 0.0, "dur": 0.5})
			if _last_pos.has(target):
				if sfx == "miss":
					_fx.append({"kind": "float", "pos": Vector2(_last_pos[target]), "text": "miss",
						"color": Color(0.7, 0.7, 0.75), "delay": _fx_stagger + 0.18, "t": 0.0, "dur": 0.9})
					# a miss isn't nothing happening — the target DODGES it (shield-bearers BLOCK)
					var shielded := _ents.has(target) and (str(_ents[target].get("model_path", "")).contains("Knight")
						or str(_ents[target].get("model_path", "")).contains("Warrior"))
					_fx.append({"kind": "react", "id": target,
						"anims": ["Block_Hit", "Block", "Dodge_Backward"] if shielded
							else ["Dodge_Backward", "Dodge_Left", "Dodge"],
						"delay": _fx_stagger + 0.10, "t": 0.0, "dur": 0.55})
				else:
					var from: Vector2 = Vector2(_last_pos[attacker]) if _last_pos.has(attacker) \
						else Vector2(_last_pos[target]) + Vector2(0, 1)
					_fx.append({"kind": "hurt", "id": target, "from": from,
						"delay": _fx_stagger + 0.18, "t": 0.0, "dur": 0.4})
					_fx.append({"kind": "float", "pos": Vector2(_last_pos[target]),
						"text": "-" + str(int(data.get("damage", 0))),
						"color": Color("f5d020") if sfx == "crit" else Color(1, 1, 1),
						"delay": _fx_stagger + 0.18, "t": 0.0, "dur": 1.0})
					if sfx == "crit":
						_fx.append({"kind": "shake", "delay": _fx_stagger + 0.18, "t": 0.0, "dur": 0.01})
			_fx_stagger += 0.32
		"dead", "down":
			if _ents.has(target):
				# fatal deaths chain into a sinking corpse then free the node; "down" characters
				# stay lying where they fell (they're still in the snapshot, possibly revivable)
				_fx.append({"kind": "death", "id": target, "fatal": sfx == "dead",
					"delay": _fx_stagger, "t": 0.0, "dur": 1.4})
		"levelup":
			var pid := "player"
			if _last_pos.has(pid):
				_fx.append({"kind": "float", "pos": Vector2(_last_pos[pid]), "text": "LEVEL UP!",
					"color": Color("f5d020"), "delay": 0.2, "t": 0.0, "dur": 1.5})
				_fx.append({"kind": "react", "id": pid, "anims": ["Cheer"],
					"delay": 0.2, "t": 0.0, "dur": 1.2})
		"victory":
			# the party celebrates — staggered so it reads as people, not a chorus line
			var vi := 0
			for id in _ents:
				if str(_ents[id]["kind"]) in ["player", "follower"]:
					_fx.append({"kind": "react", "id": id, "anims": ["Cheer"],
						"delay": 0.25 + 0.18 * vi, "t": 0.0, "dur": 1.3})
					vi += 1
		"drink":
			_fx.append({"kind": "react", "id": "player", "anims": ["Use_Item", "Interact"],
				"delay": 0.0, "t": 0.0, "dur": 1.0})
		"door":
			_fx.append({"kind": "react", "id": "player", "anims": ["Interact", "Use_Item"],
				"delay": 0.0, "t": 0.0, "dur": 0.9})
		"loot":
			_fx.append({"kind": "react", "id": "player", "anims": ["PickUp", "Interact"],
				"delay": 0.3, "t": 0.0, "dur": 1.0})
		"rest":
			# the whole party settles at the fire: sit down, stay seated, stand back up
			var ri := 0
			for id in _ents:
				if str(_ents[id]["kind"]) in ["player", "follower"]:
					_fx.append({"kind": "rest", "id": id, "seated": false,
						"delay": 0.15 * ri, "t": 0.0, "dur": 3.6})
					ri += 1
		"alarm":
			# enemies ANSWER the call to arms: a taunt where the rig has one, a menacing hop
			# where it doesn't (the goblin) — combat starts as an event, not a mode flag
			var ai := 0
			for id in _ents:
				if str(_ents[id]["kind"]) == "enemy":
					_fx.append({"kind": "react", "id": id,
						"anims": ["Taunt", "Jump_Full_Short", "Jump"],
						"delay": 0.2 + 0.15 * ai, "t": 0.0, "dur": 1.1})
					ai += 1
			# combat interrupts any camp: cancel rest beats and get everyone on their feet
			for i in range(_fx.size() - 1, -1, -1):
				if str(_fx[i].get("kind", "")) == "rest":
					var rid := str(_fx[i].get("id", ""))
					if _ents.has(rid) and str(_ents[rid]["state"]) == "rest":
						_ents[rid]["state"] = "idle"
						_play_anim(_ents[rid], ["Idle"], true)
					_fx.remove_at(i)


func _spawn_float(tile_pos: Vector2, text: String, color: Color) -> void:
	var lbl := Label3D.new()
	lbl.text = text
	lbl.font_size = 64
	lbl.pixel_size = 0.006
	lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	lbl.no_depth_test = true
	lbl.modulate = color
	lbl.outline_size = 12
	_fx_root.add_child(lbl)
	lbl.position = _being_pos(tile_pos.x, tile_pos.y) + Vector3(0, _tile * 1.1, 0)
	lbl.set_meta("vel", 1.6)
	lbl.set_meta("life", 1.0)


# ---------------------------------------------------------------- per-frame

func _process(delta: float) -> void:
	_time += delta
	# Waypoint walks: constant speed along the whole polyline (no per-tile easing pulse — that
	# plus the per-tile clip restart was the "wonky movement" the owner flagged).
	for id in _anim.keys().duplicate():
		if not _ents.has(id):
			_anim.erase(id)
			continue
		var a: Dictionary = _anim[id]
		var ent: Dictionary = _ents[id]
		var pts: Array = a["pts"]
		var d := float(a["d"]) + delta * float(a["speed"])
		while pts.size() >= 2:
			var seg := (Vector2(pts[1]) - Vector2(pts[0])).length()
			if d < seg:
				break
			d -= seg
			pts.pop_front()
		if pts.size() < 2:
			var dest: Vector2 = pts[0] if pts.size() == 1 else _last_pos.get(id, Vector2.ZERO)
			_anim.erase(id)
			ent["node"].position = _being_pos(dest.x, dest.y)
			if str(ent["state"]) == "walk":
				ent["state"] = "idle"
				_play_anim(ent, _idle_prefer(), true)
		else:
			a["d"] = d
			_anim[id] = a
			var dirv := (Vector2(pts[1]) - Vector2(pts[0]))
			var p: Vector2 = Vector2(pts[0]) + dirv.normalized() * d
			# STEP-HOP: a small arc per tile (the 2D view's bounce, in 3D) — reads as footsteps
			var frac := d / maxf(0.001, dirv.length())
			var hop := absf(sin(frac * PI)) * _tile * 0.055
			ent["node"].position = _being_pos(p.x, p.y) + Vector3(0.0, hop, 0.0)
			_facing[id] = atan2(dirv.x, dirv.y)
			if str(ent["state"]) != "walk":
				ent["state"] = "walk"
				var run := float(a["speed"]) > 8.0
				# short bare keys ("Run"/"Walk") cover third-party rigs with prefixed clip names
				_play_anim(ent, ["Running_A", "Running", "Run", "Walking_A"] if run
					else ["Walking_A", "Walking", "Walk", "Running_A", "Run"], true)
	# smooth yaw toward the facing target — ALL modeled entities, not just movers (an attacker
	# turning toward its target eases through this same path instead of snapping)
	for id in _facing.keys():
		if _ents.has(id) and not bool(_ents[id]["sprite"]):
			var node: Node3D = _ents[id]["node"]
			node.rotation.y = lerp_angle(node.rotation.y, float(_facing[id]), minf(1.0, delta * 22.0))
	# combat fx
	for i in range(_fx.size() - 1, -1, -1):
		var f: Dictionary = _fx[i]
		if float(f.get("delay", 0.0)) > 0.0:
			f["delay"] = float(f["delay"]) - delta
			_fx[i] = f
			continue
		var kind := str(f["kind"])
		var fid := str(f.get("id", ""))
		if float(f["t"]) == 0.0:               # activation edge
			match kind:
				"attack":
					if _ents.has(fid):
						var ent: Dictionary = _ents[fid]
						var dirv: Vector2 = (Vector2(f["toward"]) - Vector2(f["at"]))
						_facing[fid] = atan2(dirv.x, dirv.y)   # eased turn, same path as walking
						ent["state"] = "attack"
						if bool(ent.get("caster", false)):
							_play_random(ent, "spellcast", ["summon"], ["Spellcasting", "Attack"])
						else:
							_play_random(ent, "attack", ["jump", "spin"], ["Attack"])
				"hurt":
					if _ents.has(fid):
						var ent2: Dictionary = _ents[fid]
						_play_random(ent2, "hit", ["jump"], ["Hit_A", "Hit"])
						ent2["state"] = "hurt"
				"react":
					# a one-shot acting beat (dodge, cheer, drink, pick up, interact...)
					if _ents.has(fid) and str(_ents[fid]["state"]) in ["idle", "walk"]:
						_play_anim(_ents[fid], f.get("anims", ["Interact"]))
						_ents[fid]["state"] = "react"
				"rest":
					if _ents.has(fid) and str(_ents[fid]["state"]) in ["idle", "walk"]:
						_play_anim(_ents[fid], ["Sit_Floor_Down", "Sit_Floor_Idle"])
						_ents[fid]["state"] = "rest"
				"death":
					if _ents.has(fid):
						var ent3: Dictionary = _ents[fid]
						_play_random(ent3, "death", ["resurrect", "awaken"], ["Death_A", "Death"])
						ent3["state"] = "dead"
				"float":
					_spawn_float(Vector2(f["pos"]), str(f["text"]), Color(f["color"]))
				"shake":
					_shake = 0.3
		f["t"] = float(f["t"]) + delta
		var ph := clampf(float(f["t"]) / maxf(0.001, float(f["dur"])), 0.0, 1.0)
		# physical weight: the attacker LUNGES at the target; the victim recoils away. Offsets ride
		# on top of the settled tile position and only when the entity isn't mid-walk.
		if kind == "attack" and _ents.has(fid) and not _anim.has(fid) and _last_pos.has(fid):
			var adir := (Vector2(f["toward"]) - Vector2(f["at"])).normalized()
			var base: Vector2 = _last_pos[fid]
			var amp := _tile * 0.35 * sin(PI * ph)
			_ents[fid]["node"].position = _being_pos(base.x, base.y) \
				+ Vector3(adir.x, 0.0, adir.y) * amp
		elif kind == "hurt" and _ents.has(fid) and not _anim.has(fid) and _last_pos.has(fid):
			var hdir := (Vector2(_last_pos[fid]) - Vector2(f.get("from", _last_pos[fid]))).normalized()
			var hbase: Vector2 = _last_pos[fid]
			var hamp := _tile * 0.14 * sin(PI * ph)
			_ents[fid]["node"].position = _being_pos(hbase.x, hbase.y) \
				+ Vector3(hdir.x, 0.0, hdir.y) * hamp
		elif kind == "corpse" and _ents.has(fid):
			_ents[fid]["node"].position.y -= delta * 1.4   # the fallen sink away
		elif kind == "rest" and _ents.has(fid) and str(_ents[fid]["state"]) == "rest" \
				and not bool(f.get("seated", false)) and float(f["t"]) >= 1.0:
			f["seated"] = true                             # settled: hold the seated idle
			_play_anim(_ents[fid], ["Sit_Floor_Idle"], true)
		if float(f["t"]) >= float(f["dur"]):
			if kind == "attack" or kind == "hurt" or kind == "react":
				if _ents.has(fid):
					if _last_pos.has(fid) and not _anim.has(fid):
						var rp: Vector2 = _last_pos[fid]
						_ents[fid]["node"].position = _being_pos(rp.x, rp.y)
					if not (str(_ents[fid]["state"]) in ["dead", "rest"]):
						_ents[fid]["state"] = "idle"
						_play_anim(_ents[fid], _idle_prefer(), true)
			elif kind == "rest":
				# rested: chain into a stand-up beat, whose own completion returns to Idle
				if _ents.has(fid) and str(_ents[fid]["state"]) == "rest":
					_ents[fid]["state"] = "idle"
					_fx.append({"kind": "react", "id": fid, "anims": ["Sit_Floor_StandUp"],
						"delay": 0.0, "t": 0.0, "dur": 0.8})
			elif kind == "death" and bool(f.get("fatal", false)):
				# linger a beat on the fallen pose, then sink and free the node
				_fx.append({"kind": "corpse", "id": fid, "delay": 0.5, "t": 0.0, "dur": 0.9})
			elif kind == "corpse":
				_free_entity(fid)
			_fx.remove_at(i)
		else:
			_fx[i] = f
	if _fx.is_empty():
		_fx_stagger = 0.0
	# floating labels rise + fade; destination rings bloom + fade
	for c in _fx_root.get_children():
		if c is Label3D:
			var life := float(c.get_meta("life", 0.0)) - delta
			c.set_meta("life", life)
			c.position.y += float(c.get_meta("vel", 1.5)) * delta
			var m: Color = c.modulate
			m.a = clampf(life, 0.0, 1.0)
			c.modulate = m
			if life <= 0.0:
				c.queue_free()
		elif c is MeshInstance3D and c.has_meta("ring"):
			var rlife := float(c.get_meta("life", 0.0)) - delta
			c.set_meta("life", rlife)
			var k := 1.0 - clampf(rlife / 0.6, 0.0, 1.0)
			c.scale = Vector3(1.0 + 0.5 * k, 0.10, 1.0 + 0.5 * k)
			var rm := c.material_override as StandardMaterial3D
			if rm != null:
				rm.albedo_color.a = clampf(rlife / 0.6, 0.0, 1.0) * 0.9
			if rlife <= 0.0:
				c.queue_free()
	# gold ring under the active combatant (combat only) — the turn is a visible PLACE
	if str(_snap.get("mode", "")) == "combat" and _turn_id != "" and _ents.has(_turn_id):
		var tp: Vector3 = _ents[_turn_id]["node"].position
		var want_ring := Vector3(tp.x, _floor_top + 0.04, tp.z)
		if not _turn_ring.visible:
			_turn_ring.visible = true
			_turn_ring.position = want_ring
		else:
			_turn_ring.position = _turn_ring.position.lerp(want_ring, minf(1.0, delta * 10.0))
	else:
		_turn_ring.visible = false
	# ambient town villagers wandering (cosmetic)
	if not _ambient.is_empty():
		_update_ambient(delta)
	# torch flicker + follow
	_follow_player(delta)
	# crit shake
	if _shake > 0.0:
		_shake = maxf(0.0, _shake - delta)
		_camera.h_offset = sin(_time * 67.0) * 0.12 * (_shake / 0.3)
		_camera.v_offset = cos(_time * 51.0) * 0.12 * (_shake / 0.3)
	else:
		_camera.h_offset = 0.0
		_camera.v_offset = 0.0


func _town_walkable(x: int, y: int) -> bool:
	var tiles = _snap.get("tiles", [])
	if typeof(tiles) != TYPE_ARRAY or y < 0 or y >= tiles.size():
		return false
	var row: String = str(tiles[y])
	return x >= 0 and x < row.length() and row[x] in [".", "+", ">", "<"]


## Cosmetic villagers: idle a beat, pick a nearby open tile with a clear straight line, walk there
## (constant speed + the same step-hop), face travel, repeat. Purely client-side ambience.
func _update_ambient(delta: float) -> void:
	for a in _ambient:
		var node: Node3D = a["node"]
		if not is_instance_valid(node):
			continue
		if str(a["state"]) == "idle":
			a["wait"] = float(a["wait"]) - delta
			if float(a["wait"]) <= 0.0:
				# stroll a short step, ANCHORED to a home spot so they don't all migrate together
				# (they linger, amble a little, return) — reads as townsfolk minding their patch.
				var base: Vector2 = a["cell"]
				var home: Vector2 = a["home"]
				var h := (int(base.x) * 73 + int(base.y) * 91 + int(_time * 3.0)) % 97
				var tgt: Vector2 = base + Vector2(float(h % 5 - 2), float((h / 5) % 5 - 2))
				if base.distance_to(home) > 3.0:      # drifted — head back toward home
					tgt = base + (home - base).normalized() * 2.0
				tgt = tgt.round()
				var mid := (base + tgt) * 0.5
				if _town_walkable(int(tgt.x), int(tgt.y)) and _town_walkable(int(mid.x), int(mid.y)) \
						and tgt.distance_to(base) > 0.5:
					a["from"] = base
					a["to"] = tgt
					a["t"] = 0.0
					a["state"] = "walk"
					if a["ap"] != null:
						(a["ap"] as AnimationPlayer).play("Walking_A")
				else:
					a["wait"] = 0.6
		else:
			var d := float(a["t"]) + delta * 3.2 / maxf(0.5, Vector2(a["from"]).distance_to(a["to"]))
			a["t"] = d
			var p: Vector2 = Vector2(a["from"]).lerp(Vector2(a["to"]), clampf(d, 0.0, 1.0))
			var hop := absf(sin(clampf(d, 0.0, 1.0) * PI)) * _tile * 0.05
			node.position = _being_pos(p.x, p.y) + Vector3(0.0, hop, 0.0)
			var dirv := Vector2(a["to"]) - Vector2(a["from"])
			if dirv.length() > 0.01:
				node.rotation.y = lerp_angle(node.rotation.y, atan2(dirv.x, dirv.y), minf(1.0, delta * 12.0))
			if d >= 1.0:
				a["cell"] = a["to"]
				a["state"] = "idle"
				a["wait"] = 2.5 + float((int(p.x) * 7) % 5)   # longer, varied pauses — calmer town
				if a["ap"] != null:
					(a["ap"] as AnimationPlayer).play("Idle")


var _dbg_once := false

func _follow_player(delta: float) -> void:
	if not _ents.has("player"):
		return
	var target: Vector3 = _ents["player"]["node"].position
	if not _dbg_once and _time > 5.0:
		_dbg_once = true
		if OS.get_environment("RPG_3D_DEBUG") != "":
			for eid in _ents:
				var ent: Dictionary = _ents[eid]
				var node: Node3D = ent["node"]
				var ap: AnimationPlayer = ent.get("ap")
				print("[world3d] ent ", eid, " @", node.global_position,
					" sprite=", ent["sprite"], " anim=", (ap.current_animation if ap != null else "-"))
	_torch.position = _torch.position.lerp(target + Vector3(0, _tile * 0.9, 0), minf(1.0, delta * 8.0))
	# In daylight (town) the sun lights the scene — kill the torch so a bright square isn't
	# washed by a personal glow; underground it flickers and owns the mood.
	_torch.light_energy = 0.0 if _daylight else (2.4 + 0.35 * sin(_time * 9.0) + 0.18 * sin(_time * 23.0))
	var want := target + CAM_OFFSET_TILES * _tile * _zoom
	_camera.position = _camera.position.lerp(want, minf(1.0, delta * 6.0))
	_camera.look_at(target + Vector3(0, _tile * 0.3, 0))
