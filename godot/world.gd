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
var _facing := {}                     # id -> -1.0 (left) / 1.0 (right), from the last horizontal move
var _last_sprite := {}                # id -> last drawn sprite idx (death ghosts use it)

# --- transient combat effects (lunge / flash / floating text / death ghost / shake) ---
var _fx: Array = []                   # {kind, delay, t, dur, id?/pos?/text?/color?/dir?/sprite?}
var _fx_stagger := 0.0                # incoming beats space themselves out so a round reads as beats
var _shake := 0.0                     # crit screen-shake seconds remaining
var _time := 0.0                      # frame clock for jitter/hop phases
var FLOAT_COLOR := Color(1, 1, 1)
var FLOAT_CRIT := Color("f5d020")
var FLOAT_MISS := Color(0.65, 0.65, 0.7)

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
	# tween/fx state would streak tokens or replay old beats, so drop it all wholesale.
	_anim.clear()
	_last_pos.clear()
	_facing.clear()
	_last_sprite.clear()
	_fx.clear()
	_fx_stagger = 0.0
	_shake = 0.0
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
			if now.x != prev.x:                                # face the way you walk
				_facing[id] = 1.0 if now.x > prev.x else -1.0
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


## Queue a combat beat from the server's event data (main.gd forwards CombatEvent.data). Beats
## STAGGER themselves (~0.28s apart) so a whole resolved round reads as blows landing in sequence
## rather than one simultaneous blur. Positions come from _last_pos (captured pre-turn — where
## everyone stood when the blow landed).
func combat_fx(data: Dictionary) -> void:
	var sfx := str(data.get("sfx", ""))
	var target := str(data.get("target", ""))
	var attacker := str(data.get("attacker", ""))
	match sfx:
		"hit", "crit", "miss":
			if attacker != "" and _last_pos.has(attacker) and _last_pos.has(target):
				var dirv: Vector2 = (Vector2(_last_pos[target]) - Vector2(_last_pos[attacker]))
				_fx.append({"kind": "lunge", "id": attacker, "delay": _fx_stagger,
					"t": 0.0, "dur": 0.18,
					"dir": dirv.normalized() if dirv.length() > 0.01 else Vector2.RIGHT})
			if _last_pos.has(target):
				if sfx == "miss":
					_fx.append({"kind": "float", "pos": Vector2(_last_pos[target]), "text": "miss",
						"color": FLOAT_MISS, "delay": _fx_stagger + 0.10, "t": 0.0, "dur": 0.8})
				else:
					var crit := sfx == "crit"
					_fx.append({"kind": "flash", "id": target, "delay": _fx_stagger + 0.10,
						"t": 0.0, "dur": 0.30 if crit else 0.22,
						"color": Color(1, 0.9, 0.5) if crit else Color(1, 1, 1)})
					_fx.append({"kind": "float", "pos": Vector2(_last_pos[target]),
						"text": "-" + str(int(data.get("damage", 0))),
						"color": FLOAT_CRIT if crit else FLOAT_COLOR,
						"delay": _fx_stagger + 0.10, "t": 0.0, "dur": 0.9})
					if crit:
						_fx.append({"kind": "shake", "delay": _fx_stagger + 0.10, "t": 0.0, "dur": 0.01})
			_fx_stagger += 0.28
		"dead", "down":
			if _last_pos.has(target):
				_fx.append({"kind": "ghost", "pos": Vector2(_last_pos[target]),
					"sprite": int(_last_sprite.get(target, -1)),
					"delay": _fx_stagger, "t": 0.0, "dur": 0.6})
		"levelup":
			var pid := str(snap.get("player", {}).get("id", "player")) if typeof(snap.get("player")) == TYPE_DICTIONARY else "player"
			if _last_pos.has(pid):
				_fx.append({"kind": "float", "pos": Vector2(_last_pos[pid]), "text": "LEVEL UP!",
					"color": FLOAT_CRIT, "delay": 0.2, "t": 0.0, "dur": 1.4})


func _process(delta: float) -> void:
	_time += delta
	var busy := false
	# movement tweens
	for id in _anim.keys().duplicate():
		var a: Dictionary = _anim[id]
		a["t"] = float(a["t"]) + delta * TWEEN_TILES_PER_S / max(0.001, Vector2(a["from"]).distance_to(a["to"]))
		if float(a["t"]) >= 1.0:
			_anim.erase(id)
		else:
			_anim[id] = a
		busy = true
	# combat effects
	for i in range(_fx.size() - 1, -1, -1):
		var f: Dictionary = _fx[i]
		if float(f.get("delay", 0.0)) > 0.0:
			f["delay"] = float(f["delay"]) - delta
			_fx[i] = f
			busy = true
			continue
		if str(f["kind"]) == "shake":
			_shake = maxf(_shake, 0.25)
			_fx.remove_at(i)
			busy = true
			continue
		f["t"] = float(f["t"]) + delta
		if float(f["t"]) >= float(f["dur"]):
			_fx.remove_at(i)
		else:
			_fx[i] = f
		busy = true
	if _fx.is_empty():
		_fx_stagger = 0.0
	# crit screen shake (deterministic jitter, no rng)
	if _shake > 0.0:
		_shake = maxf(0.0, _shake - delta)
		var k := _shake / 0.25
		if _camera != null:
			_camera.offset = Vector2(sin(_time * 71.0), cos(_time * 53.0)) * 3.5 * k
		busy = true
	elif _camera != null and _camera.offset != Vector2.ZERO:
		_camera.offset = Vector2.ZERO
	if busy:
		_move_camera_to_player()
		queue_redraw()


## An entity's DRAW position in tile coords (float) — the tween if one is running.
func _draw_pos(id: String, pos) -> Vector2:
	if _anim.has(id):
		var a: Dictionary = _anim[id]
		return Vector2(a["from"]).lerp(Vector2(a["to"]), ease(float(a["t"]), -1.8))
	return Vector2(float(pos[0]), float(pos[1]))


## Contract parity with world3d.gd (main.gd calls these on whichever view is active). The 2D view
## keeps its snapshot-to-snapshot hop tween, so the server's walked route is simply ignored, and
## held-key pacing falls back to main.gd's cooldown alone.
func follow_path(_id: String, _tiles: Array) -> void:
	pass


func player_glide_remaining() -> float:
	return 0.0


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
	_draw_fx()


## Transient overlays: floating damage/miss text (rises + fades) and death ghosts (the fallen
## sprite fading out where it stood — the snapshot removes the entity the moment it dies).
func _draw_fx() -> void:
	for f in _fx:
		if float(f.get("delay", 0.0)) > 0.0:
			continue
		var kind := str(f.get("kind", ""))
		var k: float = clampf(float(f["t"]) / float(f["dur"]), 0.0, 1.0)
		if kind == "float" and _font != null:
			var pos: Vector2 = Vector2(f["pos"])
			var col: Color = Color(f["color"])
			col.a = 1.0 - k * k
			var txt := str(f["text"])
			var w := _text_width(txt, _font_size + 2)
			draw_string(_font, Vector2(pos.x * CELL + CELL * 0.5 - w * 0.5,
				pos.y * CELL - 4.0 - 16.0 * k), txt,
				HORIZONTAL_ALIGNMENT_LEFT, -1, _font_size + 2, col)
		elif kind == "ghost" and _atlas != null and int(f.get("sprite", -1)) >= 0:
			var gpos: Vector2 = Vector2(f["pos"])
			var mod := Color(0.7, 0.4, 0.4, 1.0 - k)
			draw_texture_rect_region(_atlas,
				Rect2(Vector2(gpos.x * CELL, gpos.y * CELL + 3.0 * k), Vector2(CELL, CELL)),
				_src_rect(int(f["sprite"])), mod)


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


## Walk-cycle offset: a little pixel hop while gliding (one arc per tile) — single-frame sprites
## read as WALKING with just this. Returns pixels of vertical lift.
func _hop(id: String) -> float:
	if not _anim.has(id):
		return 0.0
	var a: Dictionary = _anim[id]
	var tiles: float = max(1.0, Vector2(a["from"]).distance_to(a["to"]))
	return -3.0 * abs(sin(float(a["t"]) * PI * tiles))


## Active lunge offset (pixels) for an attacker mid-beat, and flash color override for a victim.
func _fx_offset(id: String) -> Vector2:
	for f in _fx:
		if str(f.get("kind", "")) == "lunge" and str(f.get("id", "")) == id and float(f.get("delay", 0.0)) <= 0.0:
			var k: float = sin(float(f["t"]) / float(f["dur"]) * PI)
			return Vector2(f["dir"]) * 7.0 * k
	return Vector2.ZERO


func _fx_flash(id: String) -> Color:
	for f in _fx:
		if str(f.get("kind", "")) == "flash" and str(f.get("id", "")) == id and float(f.get("delay", 0.0)) <= 0.0:
			var k: float = 1.0 - float(f["t"]) / float(f["dur"])
			return Color(f["color"]).lerp(Color(1, 1, 1), 1.0 - k) * Color(1.6, 1.6, 1.6)   # bright pop
	return Color(1, 1, 1)


## One being: its mapped sprite (preferred) or the classic circle token (fallback). `p` is the
## tween-aware TILE position (float). Movement hops; attackers lunge; victims flash; walkers face
## their direction (negative-width source region = horizontal flip).
func _draw_being(p: Vector2, e: Dictionary, kind: String, down: bool, active: bool) -> void:
	var id := str(e.get("id", ""))
	var origin := Vector2(p.x * CELL, p.y * CELL) + Vector2(0, _hop(id)) + _fx_offset(id)
	var centre := origin + Vector2(CELL * 0.5, CELL * 0.5)
	var ent_name := str(e.get("name", ""))

	if active:
		draw_arc(centre, CELL * 0.52, 0.0, TAU, 24, TURN_RING, 2.0, true)

	var idx := _sprite_for(e, kind)
	if idx >= 0:
		_last_sprite[id] = idx            # death ghosts reuse the last look
		var mod := _fx_flash(id)
		if down:
			mod = Color(0.55, 0.3, 0.3)   # crumpled: dark red, no separate sprite needed
		var src := _src_rect(idx)
		if float(_facing.get(id, 1.0)) < 0.0:
			src = Rect2(src.position.x + src.size.x, src.position.y, -src.size.x, src.size.y)
		draw_texture_rect_region(_atlas, Rect2(origin, Vector2(CELL, CELL)), src, mod)
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
