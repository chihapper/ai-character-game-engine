extends Node2D
## World renderer — a THIN view over the Python game-core's StateSnapshot.
## Draws the tile grid, entities, the player, and HP bars in WORLD space, and owns a
## Camera2D child that follows the player. NO networking, NO input, NO game logic here:
## main.gd feeds us snapshots via render(); we only paint them.
##
## Coordinate rules (shared contract): tiles[y][x]; player/entity pos is [x,y];
## world pixel = pos * CELL.

const CELL := 24

var snap: Dictionary = {}

var _camera: Camera2D
var _font: Font
var _font_size := 12

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

var BG_COLOR := Color("161616")
var VOID_COLOR := Color("161616")
var TILE_BORDER := Color(0, 0, 0, 0.35)
var LABEL_COLOR := Color(0.92, 0.92, 0.92)
var TOKEN_LETTER_COLOR := Color(0.08, 0.08, 0.08)
var HP_BACK_COLOR := Color(0.12, 0.12, 0.12)
var HP_FILL_COLOR := Color("78dc78")
var HP_LOW_COLOR := Color("dc5a5a")


func _ready() -> void:
	_font = _resolve_font()
	_camera = Camera2D.new()
	add_child(_camera)
	# In 4.x a Camera2D is enabled by default; make_current() guarantees it's the active one.
	_camera.enabled = true
	_camera.make_current()


## main.gd calls this on every snapshot. We never talk back to Net.
func render(s: Dictionary) -> void:
	snap = s if typeof(s) == TYPE_DICTIONARY else {}
	_move_camera_to_player()
	queue_redraw()


## The tile (x,y) under the mouse right now — get_global_mouse_position() accounts for the
## camera transform, so a click maps straight to a grid cell (world pixel = tile * CELL).
func tile_at_mouse() -> Vector2i:
	var wp := get_global_mouse_position()
	return Vector2i(int(floor(wp.x / float(CELL))), int(floor(wp.y / float(CELL))))


func _move_camera_to_player() -> void:
	if _camera == null:
		return
	var pos = _player_pos()
	if pos == null:
		return
	# Centre the camera on the player's tile centre (world coords).
	_camera.position = Vector2(
		float(pos[0]) * CELL + CELL * 0.5,
		float(pos[1]) * CELL + CELL * 0.5
	)


func _player_pos() -> Variant:
	var player = snap.get("player", {})
	if typeof(player) != TYPE_DICTIONARY:
		return null
	var pos = player.get("pos", null)
	if typeof(pos) != TYPE_ARRAY or pos.size() < 2:
		return null
	return pos


func _draw() -> void:
	# Dark background wide enough to cover the viewport regardless of camera pan.
	# The rect lives in WORLD space, so anchor it on the camera (not on world origin)
	# or it stops covering the view once the player walks away from (0,0).
	var vp_size := get_viewport_rect().size
	var cam_pos := _camera.position if _camera != null else Vector2.ZERO
	draw_rect(Rect2(cam_pos - vp_size, vp_size * 2.0), BG_COLOR, true)

	if snap.is_empty():
		return

	_draw_tiles()
	_draw_entities()
	_draw_player()


func _draw_tiles() -> void:
	var tiles = snap.get("tiles", [])
	if typeof(tiles) != TYPE_ARRAY:
		return
	for y in tiles.size():
		var row = tiles[y]
		if typeof(row) != TYPE_STRING:
			continue
		for x in row.length():
			var ch: String = row[x]
			var col: Color = TILE_COLORS.get(ch, VOID_COLOR)
			var rect := Rect2(x * CELL, y * CELL, CELL, CELL)
			draw_rect(rect, col, true)
			# 1px darker border for grid legibility (skip on void for a clean black field).
			if ch != " ":
				draw_rect(rect, TILE_BORDER, false, 1.0)


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
		var col: Color = ENT_COLORS.get(kind, Color(0.85, 0.85, 0.85))
		var ent_name := str(e.get("name", ""))
		_draw_token(int(pos[0]), int(pos[1]), col, ent_name)

		# HP bars: under followers ALWAYS; under enemies only when show_enemy_hp and hp!=null.
		var hp = e.get("hp", null)
		var max_hp = e.get("max_hp", null)
		var want_bar := false
		if kind == "follower":
			want_bar = true
		elif kind == "enemy" and show_enemy_hp and hp != null:
			want_bar = true
		if want_bar and hp != null and max_hp != null:
			_draw_hp_bar(int(pos[0]), int(pos[1]), float(hp), float(max_hp))


func _draw_player() -> void:
	var player = snap.get("player", {})
	if typeof(player) != TYPE_DICTIONARY:
		return
	var pos = player.get("pos", null)
	if typeof(pos) != TYPE_ARRAY or pos.size() < 2:
		return
	var pname := str(player.get("name", ""))
	_draw_token(int(pos[0]), int(pos[1]), ENT_COLORS["player"], pname)


## A rounded token filling most of the cell, its first letter centred, and a small
## name label floating above it.
func _draw_token(gx: int, gy: int, col: Color, ent_name: String) -> void:
	var origin := Vector2(gx * CELL, gy * CELL)
	var centre := origin + Vector2(CELL * 0.5, CELL * 0.5)
	var radius := CELL * 0.40

	# Rounded token = a filled circle (Godot's cheapest rounded shape).
	draw_circle(centre, radius, col)

	# First letter, dark, centred in the token.
	var letter := ent_name.substr(0, 1) if ent_name.length() > 0 else ""
	if letter != "" and _font != null:
		var letter_up := letter.to_upper()
		var lw := _text_width(letter_up)
		var letter_pos := Vector2(
			centre.x - lw * 0.5,
			centre.y + _font_size * 0.35
		)
		draw_string(_font, letter_pos, letter_up, HORIZONTAL_ALIGNMENT_LEFT, -1, _font_size, TOKEN_LETTER_COLOR)

	# Small name label above the token.
	if ent_name != "" and _font != null:
		var label_size: int = max(9, _font_size - 2)
		var name_w := _text_width(ent_name, label_size)
		var name_pos := Vector2(
			centre.x - name_w * 0.5,
			origin.y - 3.0
		)
		draw_string(_font, name_pos, ent_name, HORIZONTAL_ALIGNMENT_LEFT, -1, label_size, LABEL_COLOR)


## A thin HP bar drawn just under the token's cell.
func _draw_hp_bar(gx: int, gy: int, hp: float, max_hp: float) -> void:
	if max_hp <= 0.0:
		return
	var frac: float = clamp(hp / max_hp, 0.0, 1.0)
	var bar_w := CELL - 4.0
	var bar_h := 3.0
	var bx := gx * CELL + 2.0
	var by := gy * CELL + CELL - 1.0
	draw_rect(Rect2(bx, by, bar_w, bar_h), HP_BACK_COLOR, true)
	var fill_col := HP_FILL_COLOR if frac > 0.33 else HP_LOW_COLOR
	if frac > 0.0:
		draw_rect(Rect2(bx, by, bar_w * frac, bar_h), fill_col, true)


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
