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
const WALK_TILES_PER_S := 5.5
const RUN_TILES_PER_S := 16.0
const TREK_MAX_S := 2.5        # a route is paced to land within this many seconds
const SNAP_BEYOND_TILES := 40.0  # longer than this (new game repositioning) just snaps
# Camera vantage in TILES (converted via _tile at runtime): ~36° pitch — low enough that chibi
# characters read as PEOPLE (faces/bodies, not hat-tops), high enough to read the room; the
# waist-high walls keep sightlines clear at this angle.
const CAM_OFFSET_TILES := Vector3(0.0, 4.6, 6.4)
const CAM_FOV := 40.0

var _tile := 2.0                              # world units per grid cell (measured from the kit)
var _snap: Dictionary = {}
var _exp := {}                                # "x,y" -> true (explored)
var _vis := {}                                # "x,y" -> true (lit right now)
var _turn_id := ""

# -- scene plumbing --
var _camera: Camera3D
var _torch: OmniLight3D
var _env_node: WorldEnvironment
var _map_root: Node3D                          # static dungeon pieces (built incrementally)
var _ent_root: Node3D
var _fx_root: Node3D
var _shroud: MultiMeshInstance3D               # explored-but-unseen dim quads

# -- meshes / scenes (lazily loaded) --
var _floor_scenes: Array = []
var _wall_scene: PackedScene = null
var _door_scene: PackedScene = null
var _stairs_scene: PackedScene = null
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

## Which GLB carries each cast member / class (Stage-1 approximations; polish later).
var CAST_MODELS := {
	"rpg-vael": ADVENTURERS + "Rogue_Hooded.glb",
	"rpg-lira": ADVENTURERS + "Rogue.glb",
	"rpg-torvald": ADVENTURERS + "Barbarian.glb",
	"rpg-senna": ADVENTURERS + "Mage.glb",
}
var CLASS_MODELS := {
	"fighter": ADVENTURERS + "Knight.glb",
	"rogue": ADVENTURERS + "Rogue.glb",
	"cleric": ADVENTURERS + "Knight.glb",
	"wizard": ADVENTURERS + "Mage.glb",
}
var ENEMY_MODELS := {
	"skeleton": SKELETONS + "Skeleton_Warrior.glb",
	"zombie": SKELETONS + "Skeleton_Minion.glb",
	"shadow": SKELETONS + "Skeleton_Rogue.glb",
	"specter": SKELETONS + "Skeleton_Mage.glb",
	"wight": SKELETONS + "Skeleton_Warrior.glb",
	"ghost": SKELETONS + "Skeleton_Mage.glb",
	"ghast": SKELETONS + "Skeleton_Minion.glb",
	"ghoul": SKELETONS + "Skeleton_Minion.glb",
	"vault-drowned": SKELETONS + "Skeleton_Minion.glb",
}


func _ready() -> void:
	_load_sheet()
	_build_scene()
	_load_dungeon_pieces()
	set_slice("vault")


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
	_env_node = WorldEnvironment.new()
	_env_node.environment = env
	add_child(_env_node)

	var sun := DirectionalLight3D.new()
	sun.light_color = Color(0.55, 0.6, 0.8)
	sun.light_energy = 0.12                      # a whisper of cool fill; the torch owns the scene
	sun.rotation_degrees = Vector3(-55.0, 35.0, 0.0)
	sun.shadow_enabled = true
	add_child(sun)

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


func _load_dungeon_pieces() -> void:
	for n in ["floor_tile_small.gltf.glb", "floor_tile_small_broken_A.gltf.glb",
			"floor_tile_large_rocks.gltf.glb"]:
		var s = load(DUNGEON + n)
		if s is PackedScene:
			_floor_scenes.append(s)
	var w = load(DUNGEON + "wall.gltf.glb")
	if w is PackedScene:
		_wall_scene = w
	var d = load(DUNGEON + "wall_doorway.glb")
	if d is PackedScene:
		_door_scene = d
	var st = load(DUNGEON + "stairs.gltf.glb")
	if st is PackedScene:
		_stairs_scene = st
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


func _probe_aabb(scene: PackedScene) -> AABB:
	var probe: Node3D = scene.instantiate()
	add_child(probe)
	var mi := probe.find_children("*", "MeshInstance3D", true)
	var aabb := AABB()
	if not mi.is_empty():
		aabb = (mi[0] as MeshInstance3D).get_aabb()
	probe.queue_free()
	return aabb


func set_slice(_slice_name: String) -> void:
	# A fresh world: drop every built cell + entity + effect (ids are re-used at new positions).
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
		_build_explored(tiles)
		_update_shroud(tiles)
	_sync_entities()


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
	if _floor_scenes.is_empty():
		return
	var pick: int = (x * 7 + y * 13) % 10
	var scene: PackedScene = _floor_scenes[0]
	if pick == 7 and _floor_scenes.size() > 1:
		scene = _floor_scenes[1]
	elif pick == 3 and _floor_scenes.size() > 2:
		scene = _floor_scenes[2]
	_place_scene(scene, x, y, 0.0)


func _place_scene(scene: PackedScene, x: int, y: int, yaw: float) -> Node3D:
	var n: Node3D = scene.instantiate()
	_map_root.add_child(n)
	n.position = _world_pos(float(x), float(y))
	n.rotation.y = yaw
	return n


## A wall CELL renders as wall segments on each edge shared with an explored floor cell — the
## classic tile-to-face mapping (the far side of the wall stays void; the camera never sees it).
func _place_walls(tiles: Array, x: int, y: int) -> void:
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
			var n: Node3D = _wall_scene.instantiate()
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

func _model_for(e: Dictionary, kind: String) -> String:
	var id := str(e.get("id", ""))
	if kind == "player":
		var ct := str(e.get("creature_type", ""))
		var cls := "fighter"
		if "(" in ct and ")" in ct:
			cls = ct.substr(ct.find("(") + 1, ct.rfind(")") - ct.find("(") - 1).strip_edges()
		return str(CLASS_MODELS.get(cls, CLASS_MODELS["fighter"]))
	if CAST_MODELS.has(id):
		return str(CAST_MODELS[id])
	var nm := str(e.get("name", "")).to_lower()
	if ENEMY_MODELS.has(nm):
		return str(ENEMY_MODELS[nm])
	return ""                                   # billboard fallback


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
	var ent := {"node": root, "ap": null, "sprite": false, "state": "idle",
				"down": bool(e.get("down", false)), "label": null, "bar": null}
	var loaded := false
	# The locked Door entity (the slice's objective) is ARCHITECTURE, not a creature: give it the
	# kit's doorway piece, seated like a wall segment and aligned with the wall line it sits in.
	if kind == "door" and _door_scene != null:
		var door: Node3D = _door_scene.instantiate()
		root.add_child(door)
		door.scale = Vector3(_tile / _wall_len, 0.55, 1.0)
		door.rotation.y = 0.0 if _wall_runs_ew(at) else PI * 0.5
		loaded = true
	var model_path := _model_for(e, kind)
	if not loaded and model_path != "" and ResourceLoader.exists(model_path):
		var scene = load(model_path)
		if scene is PackedScene:
			var body: Node3D = scene.instantiate()
			root.add_child(body)
			# KayKit characters are authored for a 2-unit grid: scale to whatever the measured
			# tile actually is so people fit their cells (2u tile -> native size).
			body.scale = Vector3.ONE * (_tile * 0.5)
			var aps := body.find_children("*", "AnimationPlayer", true)
			if not aps.is_empty():
				ent["ap"] = aps[0]
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
	# floating name
	var lbl := Label3D.new()
	lbl.text = str(e.get("name", ""))
	lbl.font_size = 40
	lbl.pixel_size = 0.005
	lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	lbl.no_depth_test = true
	lbl.modulate = Color(0.95, 0.95, 0.95, 0.9)
	lbl.outline_size = 8
	lbl.position.y = _tile * 1.05
	root.add_child(lbl)
	ent["label"] = lbl
	_ents[id] = ent


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
				_play_anim(ent, ["Idle"], true)
		else:
			a["d"] = d
			_anim[id] = a
			var dirv := (Vector2(pts[1]) - Vector2(pts[0]))
			var p: Vector2 = Vector2(pts[0]) + dirv.normalized() * d
			ent["node"].position = _being_pos(p.x, p.y)
			_facing[id] = atan2(dirv.x, dirv.y)
			if str(ent["state"]) != "walk":
				ent["state"] = "walk"
				var run := float(a["speed"]) > 8.0
				_play_anim(ent, ["Running_A", "Running", "Walking_A", "Walking"] if run
					else ["Walking_A", "Walking", "Walk", "Running_A"], true)
	# smooth yaw toward the facing target — ALL modeled entities, not just movers (an attacker
	# turning toward its target eases through this same path instead of snapping)
	for id in _facing.keys():
		if _ents.has(id) and not bool(_ents[id]["sprite"]):
			var node: Node3D = _ents[id]["node"]
			node.rotation.y = lerp_angle(node.rotation.y, float(_facing[id]), minf(1.0, delta * 10.0))
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
						_play_anim(ent, ["1H_Melee_Attack_Slice", "2H_Melee_Attack", "Attack", "Unarmed_Melee_Attack"])
				"hurt":
					if _ents.has(fid):
						var ent2: Dictionary = _ents[fid]
						_play_anim(ent2, ["Hit_A", "Hit"])
						ent2["state"] = "hurt"
				"death":
					if _ents.has(fid):
						var ent3: Dictionary = _ents[fid]
						_play_anim(ent3, ["Death_A", "Death"])
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
		if float(f["t"]) >= float(f["dur"]):
			if kind == "attack" or kind == "hurt":
				if _ents.has(fid):
					if _last_pos.has(fid) and not _anim.has(fid):
						var rp: Vector2 = _last_pos[fid]
						_ents[fid]["node"].position = _being_pos(rp.x, rp.y)
					if str(_ents[fid]["state"]) != "dead":
						_ents[fid]["state"] = "idle"
						_play_anim(_ents[fid], ["Idle"], true)
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
	# floating labels rise + fade
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
	_torch.light_energy = 2.4 + 0.35 * sin(_time * 9.0) + 0.18 * sin(_time * 23.0)
	var want := target + CAM_OFFSET_TILES * _tile
	_camera.position = _camera.position.lerp(want, minf(1.0, delta * 6.0))
	_camera.look_at(target + Vector3(0, _tile * 0.3, 0))
