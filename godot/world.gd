extends Node2D
## World renderer — a THIN view over the Python game-core's StateSnapshot.
## Draws the tile grid, entities, the player, and HP bars in WORLD space, and owns a
## Camera2D child that follows the player. NO networking, NO input, NO game logic here:
## main.gd feeds us snapshots via render(); we only paint them.
##
## Art: Kenney Tiny Dungeon (CC0) via assets/sprites.json — terrain, doors, and any
## character/creature the mapping knows. Anything unmapped falls back to the classic
## colored-circle token, so new content never breaks rendering. Movement TWEENS between
## snapshots (tokens glide a tile instead of teleporting); lit tiles get a radial light
## falloff around the player; each slice tints the world its own way (set_slice).
##
## Coordinate rules (shared contract): tiles[y][x]; player/entity pos is [x,y];
## world pixel = pos * CELL.

const CELL := 24
const TWEEN_TILES_PER_S := 9.0        # how fast a token glides between tiles

var snap: Dictionary = {}
var _vis := {}   # "x,y" -> true : tiles lit right now
var _exp := {}   # "x,y" -> true : tiles ever seen (dim, remembered)
var _turn_id := ""   # id of the combatant whose turn it is (empty out of combat)

var _camera: Camera2D
var _font: Font
var _font_size := 12

# --- sprite atlas (assets/sprites.json over the CC0 tilemap) ---
var _atlas: Texture2D = null
var _sheet: Dictionary = {}           # parsed sprites.json
var _cols := 12
var _ts := 16
var _theme: Dictionary = {}           # terrain palette for the current slice
var _tint := Color(1, 1, 1)

# --- movement tweening: id -> {from: Vector2, to: Vector2, t: float} (tile coords) ---
var _anim := {}
var _last_pos := {}                   # id -> Vector2i last snapshot tile

# Runtime Color() values must live in `var`, never `const` (contract / Godot rule).
var TILE_COLORS := {
	"#": Color("2f2f37"),   # wall
	".": Color("c8bda0"),   # floor
	"+": Color("9c6b3f"),   # door
	">": Color("e0a020"),   # down-stair
	"<": Color("63991f"),   # up-stair
	" ": Color("161616"),   # void
}
var ENT_COLORS := {
	"player": Color("ffffff"),
	"npc": Color("5fd0e0"),
	"follower": Color("78dc78"),
	"enemy": Color("dc5a5a"),
	"door": Color("cd9646"),
}

var BG_COLOR := Color("101014")
var VOID_COLOR := Color("101014")
var TURN_RING := Color("f5d020")   # highlight ring around the combatant whose turn it is
var DOWN_COLOR := Color("6b3535")  # a downed (0 HP, unconscious) combatant token
var LABEL_COLOR := Color(0.92, 0.92, 0.92)
var TOKEN_LETTER_COLOR := Color(0.08, 0.08, 0.08)
var HP_BACK_COLOR := Color(0.12, 0.12, 0.12)
var HP_FILL_COLOR := Color("78dc78")
var HP_LOW_COLOR := Color("dc5a5a")


func _ready() -> void:
	_font = _resolve_font()
	# Crisp pixels: nearest-neighbor filtering for everything this node draws.
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_camera = Camera2D.new()
	add_child(_camera)
	# In 4.x a Camera2D is enabled by default; make_current() guarantees it's the active one.
	_camera.enabled = true
	_camera.make_current()
	_load_sheet()
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


## main.gd tells us which slice is playing so terrain + tint match the biome.
func set_slice(slice_name: String) -> void:
	# A fresh world (connect or N-key restart) re-uses entity ids at new positions — stale
	# tween state would streak tokens across the map, so drop it wholesale.
	_anim.clear()
	_last_pos.clear()
	var terrains = _sheet.get("terrain", {})
	if typeof(terrains) != TYPE_DICTIONARY:
		terrains = {}
	_theme = terrains.get(slice_name, terrains.get("default", {}))
	if typeof(_theme) != TYPE_DICTIONARY:
		_theme = {}
	_tint = Color(str(_theme.get("tint", "#ffffff")))


func _src_rect(idx: int) -> Rect2:
	@warning_ignore("integer_division")
	return Rect2((idx % _cols) * _ts, (idx / _cols) * _ts, _ts, _ts)


## main.gd calls this on every snapshot. We never talk back to Net.
func render(s: Dictionary) -> void:
	snap = s if typeof(s) == TYPE_DICTIONARY else {}
	_turn_id = str(snap.get("combat_turn", "")) if typeof(snap) == TYPE_DICTIONARY else ""
	_vis.clear()
	_exp.clear()
	for k in snap.get("visible", []):
		_vis[k] = true
	for k in snap.get("explored", []):
		_exp[k] = true
	_update_anims()
	_move_camera_to_player()
	queue_redraw()


## Start a glide for anything whose tile changed since the last snapshot.
func _update_anims() -> void:
	var seen_ids := {}
	for e in _all_drawables():
		var id := str(e.get("id", ""))
		var pos = e.get("pos", null)
		if id == "" or typeof(pos) != TYPE_ARRAY or pos.size() < 2:
			continue
		seen_ids[id] = true
		var now := Vector2(float(pos[0]), float(pos[1]))
		if _last_pos.has(id):
			var prev: Vector2 = _last_pos[id]
			if prev != now and prev.distance_to(now) <= 3.0:   # glide short hops; teleport long ones
				_anim[id] = {"from": prev, "to": now, "t": 0.0}
			elif prev != now:
				_anim.erase(id)
		_last_pos[id] = now
	# drop anims/positions for anything gone from the snapshot (died, left)
	for id in _anim.keys().duplicate():
		if not seen_ids.has(id):
			_anim.erase(id)
	for id in _last_pos.keys().duplicate():
		if not seen_ids.has(id):
			_last_pos.erase(id)


func _all_drawables() -> Array:
	var out: Array = []
	var player = snap.get("player", {})
	if typeof(player) == TYPE_DICTIONARY and player.has("pos"):
		out.append(player)
	var entities = snap.get("entities", [])
	if typeof(entities) == TYPE_ARRAY:
		for e in entities:
			if typeof(e) == TYPE_DICTIONARY:
				out.append(e)
	return out


func _process(delta: float) -> void:
	if _anim.is_empty():
		return
	var moved := false
	for id in _anim.keys().duplicate():
		var a: Dictionary = _anim[id]
		a["t"] = float(a["t"]) + delta * TWEEN_TILES_PER_S / max(0.001, Vector2(a["from"]).distance_to(a["to"]))
		if float(a["t"]) >= 1.0:
			_anim.erase(id)
		else:
			_anim[id] = a
		moved = true
	if moved:
		_move_camera_to_player()
		queue_redraw()


## An entity's DRAW position in tile coords (float) — the tween if one is running.
func _draw_pos(id: String, pos) -> Vector2:
	if _anim.has(id):
		var a: Dictionary = _anim[id]
		return Vector2(a["from"]).lerp(Vector2(a["to"]), ease(float(a["t"]), -1.8))
	return Vector2(float(pos[0]), float(pos[1]))


## The tile (x,y) under the mouse right now — get_global_mouse_position() accounts for the
## camera transform, so a click maps straight to a grid cell (world pixel = tile * CELL).
func tile_at_mouse() -> Vector2i:
	var wp := get_global_mouse_position()
	return Vector2i(int(floor(wp.x / float(CELL))), int(floor(wp.y / float(CELL))))


func _move_camera_to_player() -> void:
	if _camera == null:
		return
	var player = snap.get("player", {})
	if typeof(player) != TYPE_DICTIONARY:
		return
	var pos = player.get("pos", null)
	if typeof(pos) != TYPE_ARRAY or pos.size() < 2:
		return
	var p := _draw_pos(str(player.get("id", "player")), pos)
	_camera.position = Vector2(p.x * CELL + CELL * 0.5, p.y * CELL + CELL * 0.5)


func _draw() -> void:
	# Dark background wide enough to cover the viewport regardless of camera pan.
	var vp_size := get_viewport_rect().size
	var cam_pos := _camera.position if _camera != null else Vector2.ZERO
	draw_rect(Rect2(cam_pos - vp_size, vp_size * 2.0), BG_COLOR, true)

	if snap.is_empty():
		return

	_draw_tiles()
	_draw_entities()
	_draw_player()


## Per-tile brightness: slice tint x radial light falloff around the player (lit tiles only).
func _light(x: int, y: int, px: float, py: float, lit: bool) -> Color:
	if not lit:
		return _tint.darkened(0.62)
	var d := Vector2(x - px, y - py).length()
	var falloff: float = clampf(1.0 - 0.045 * d * d / 8.0, 0.55, 1.0)
	return Color(_tint.r * falloff, _tint.g * falloff, _tint.b * falloff)


func _floor_idx(x: int, y: int) -> int:
	var floors = _theme.get("floor", [])
	if typeof(floors) != TYPE_ARRAY or floors.is_empty():
		return -1
	return int(floors[(x * 7 + y * 13) % floors.size()])   # deterministic per-cell variety


func _draw_tiles() -> void:
	var tiles = snap.get("tiles", [])
	if typeof(tiles) != TYPE_ARRAY:
		return
	var player = snap.get("player", {})
	var ppos = player.get("pos", [0, 0]) if typeof(player) == TYPE_DICTIONARY else [0, 0]
	var px := float(ppos[0]) if typeof(ppos) == TYPE_ARRAY and ppos.size() > 1 else 0.0
	var py := float(ppos[1]) if typeof(ppos) == TYPE_ARRAY and ppos.size() > 1 else 0.0
	var use_atlas := _atlas != null and not _theme.is_empty()

	for y in tiles.size():
		var row = tiles[y]
		if typeof(row) != TYPE_STRING:
			continue
		for x in row.length():
			var key := str(x) + "," + str(y)
			# Fog of war: unexplored tiles stay black (skip); explored-but-unseen are dimmed
			# (remembered terrain); only lit tiles draw at full colour.
			if not _exp.has(key):
				continue
			var lit := _vis.has(key)
			var ch: String = row[x]
			var rect := Rect2(x * CELL, y * CELL, CELL, CELL)
			if ch == " ":
				continue
			if use_atlas:
				var mod := _light(x, y, px, py, lit)
				var idx := -1
				match ch:
					".":
						idx = _floor_idx(x, y)
					"#":
						idx = int(_theme.get("wall", -1))
					"+":
						idx = _floor_idx(x, y)
					">":
						idx = int(_theme.get("stairs_down", -1))
					"<":
						idx = int(_theme.get("stairs_up", -1))
				if idx >= 0:
					# stairs sit on a floor tile so their transparent edges don't show black
					if ch == ">" or ch == "<":
						var fi := _floor_idx(x, y)
						if fi >= 0:
							draw_texture_rect_region(_atlas, rect, _src_rect(fi), mod)
					draw_texture_rect_region(_atlas, rect, _src_rect(idx), mod)
					if ch == "+":
						var didx := int(_sheet.get("props", {}).get("door", -1))
						if didx >= 0:
							draw_texture_rect_region(_atlas, rect, _src_rect(didx), mod)
					continue
			# fallback: classic flat tiles
			var col: Color = TILE_COLORS.get(ch, VOID_COLOR)
			if not lit:
				col = col.darkened(0.6)
			draw_rect(rect, col, true)


## Sprite index for an entity: player -> class; npc/follower -> slug; enemy -> name. -1 = none.
func _sprite_for(e: Dictionary, kind: String) -> int:
	if _atlas == null or _sheet.is_empty():
		return -1
	if kind == "player":
		var ct := str(e.get("creature_type", ""))
		var cls := "fighter"
		if "(" in ct and ")" in ct:
			cls = ct.substr(ct.find("(") + 1, ct.rfind(")") - ct.find("(") - 1).strip_edges()
		var v = _sheet.get("by_class", {}).get(cls, _sheet.get("by_id", {}).get("player", -1))
		return int(v)
	var by_id = _sheet.get("by_id", {})
	var id := str(e.get("id", ""))
	if by_id.has(id):
		return int(by_id[id])
	var by_name = _sheet.get("by_name", {})
	var nm := str(e.get("name", "")).to_lower()
	if by_name.has(nm):
		return int(by_name[nm])
	return -1


func _draw_entities() -> void:
	var entities = snap.get("entities", [])
	if typeof(entities) != TYPE_ARRAY:
		return
	var show_enemy_hp := bool(snap.get("show_enemy_hp", false))
	for e in entities:
		if typeof(e) != TYPE_DICTIONARY:
			continue
		var pos = e.get("pos", null)
		if typeof(pos) != TYPE_ARRAY or pos.size() < 2:
			continue
		var kind := str(e.get("kind", "enemy"))
		var id := str(e.get("id", ""))
		var down := bool(e.get("down", false))
		var active := _turn_id != "" and id == _turn_id
		var p := _draw_pos(id, pos)
		_draw_being(p, e, kind, down, active)

		# HP bars: under followers ALWAYS; under enemies only when show_enemy_hp and hp!=null.
		var hp = e.get("hp", null)
		var max_hp = e.get("max_hp", null)
		var want_bar := false
		if kind == "follower":
			want_bar = true
		elif kind == "enemy" and show_enemy_hp and hp != null:
			want_bar = true
		if want_bar and hp != null and max_hp != null:
			_draw_hp_bar(p, float(hp), float(max_hp))


func _draw_player() -> void:
	var player = snap.get("player", {})
	if typeof(player) != TYPE_DICTIONARY:
		return
	var pos = player.get("pos", null)
	if typeof(pos) != TYPE_ARRAY or pos.size() < 2:
		return
	var id := str(player.get("id", "player"))
	var active := _turn_id != "" and id == _turn_id
	var p := _draw_pos(id, pos)
	_draw_being(p, player, "player", false, active)


## One being: its mapped sprite (preferred) or the classic circle token (fallback). `p` is the
## tween-aware TILE position (float).
func _draw_being(p: Vector2, e: Dictionary, kind: String, down: bool, active: bool) -> void:
	var origin := Vector2(p.x * CELL, p.y * CELL)
	var centre := origin + Vector2(CELL * 0.5, CELL * 0.5)
	var ent_name := str(e.get("name", ""))

	if active:
		draw_arc(centre, CELL * 0.52, 0.0, TAU, 24, TURN_RING, 2.0, true)

	var idx := _sprite_for(e, kind)
	if idx >= 0:
		var mod := Color(1, 1, 1)
		if down:
			mod = Color(0.55, 0.3, 0.3)   # crumpled: dark red, no separate sprite needed
		draw_texture_rect_region(_atlas, Rect2(origin, Vector2(CELL, CELL)), _src_rect(idx), mod)
	else:
		var col: Color = ENT_COLORS.get(kind, Color(0.85, 0.85, 0.85))
		if down:
			col = DOWN_COLOR
		draw_circle(centre, CELL * 0.40, col)
		var letter := ent_name.substr(0, 1).to_upper() if ent_name.length() > 0 else ""
		if letter != "" and _font != null:
			var lw := _text_width(letter)
			draw_string(_font, Vector2(centre.x - lw * 0.5, centre.y + _font_size * 0.35),
				letter, HORIZONTAL_ALIGNMENT_LEFT, -1, _font_size, TOKEN_LETTER_COLOR)

	# Small name label above (subtle).
	if ent_name != "" and _font != null:
		var label_size: int = max(8, _font_size - 3)
		var name_w := _text_width(ent_name, label_size)
		draw_string(_font, Vector2(centre.x - name_w * 0.5, origin.y - 2.0),
			ent_name, HORIZONTAL_ALIGNMENT_LEFT, -1, label_size, LABEL_COLOR)


## A thin HP bar drawn just under the being's cell. `p` = tween-aware tile position.
func _draw_hp_bar(p: Vector2, hp: float, max_hp: float) -> void:
	if max_hp <= 0.0:
		return
	var frac: float = clamp(hp / max_hp, 0.0, 1.0)
	var bx := p.x * CELL + 2.0
	var by := p.y * CELL + CELL - 1.0
	draw_rect(Rect2(bx, by, CELL - 4.0, 3.0), HP_BACK_COLOR, true)
	var fill_col := HP_FILL_COLOR if frac > 0.33 else HP_LOW_COLOR
	if frac > 0.0:
		draw_rect(Rect2(bx, by, (CELL - 4.0) * frac, 3.0), fill_col, true)


func _text_width(text: String, size: int = -1) -> float:
	if _font == null or text == "":
		return 0.0
	var sz := size if size > 0 else _font_size
	return _font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, sz).x


func _resolve_font() -> Font:
	# ThemeDB is a global singleton in 4.x and fallback_font is always populated,
	# so this never returns null. (Node2D has NO get_theme_default_font() — that
	# method only exists on Control/Window, so we must not call it here.)
	return ThemeDB.fallback_font
