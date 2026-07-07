extends CanvasLayer
## Speech card — the personable face of dialogue. When an NPC speaks, a card slides up from the
## bottom: their pixel PORTRAIT (the character's own Tiny Dungeon sprite, nearest-neighbor
## upscaled — cohesive with the map and license-clean), their NAME, and their line revealed
## typewriter-style. The portrait frame GLOWS while their Hume voice is actually playing
## (main.gd feeds set_speaking each frame). Auto-hides a few beats after the line lands.
##
## THIN and render-only: no networking, no game logic. main.gd calls show_line()/set_speaking().
## NOTE: CanvasLayer has a `visible` bool but NO show()/hide() methods (contract rule).

const TYPE_CHARS_PER_S := 42.0
const HIDE_AFTER_S := 6.0

var _card: PanelContainer
var _portrait: TextureRect
var _frame: Panel
var _name_label: Label
var _text_label: RichTextLabel

var _sheet: Dictionary = {}
var _atlas: Texture2D = null
var _cols := 12
var _ts := 16

var _reveal := 0.0            # characters revealed so far (float accumulator)
var _idle := 0.0              # seconds since the line finished revealing (for auto-hide)
var _speaking := false
var _glow_t := 0.0

# Palette (runtime Color() -> var, never const).
var _COL_PANEL := Color(0.05, 0.05, 0.08, 0.98)   # near-opaque: the HUD log must not bleed through
var _COL_BORDER := Color("5fd0e0")
var _COL_GLOW := Color("f5d020")
var _COL_NAME := Color("c8bda0")
var _COL_TEXT := Color(0.95, 0.95, 0.95)


func _ready() -> void:
	layer = 15                 # above the HUD (10), below the input overlay (20)
	_load_sheet()
	_build_ui()
	visible = false


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


func _build_ui() -> void:
	_card = PanelContainer.new()
	_card.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_card.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	_card.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_card.offset_left = 250.0
	_card.offset_right = -250.0
	_card.offset_bottom = -44.0     # sits just above the controls hint line
	var sb := StyleBoxFlat.new()
	sb.bg_color = _COL_PANEL
	sb.border_color = _COL_BORDER
	sb.set_border_width_all(2)
	sb.set_corner_radius_all(8)
	sb.set_content_margin_all(10)
	_card.add_theme_stylebox_override("panel", sb)
	add_child(_card)

	var row := HBoxContainer.new()
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_theme_constant_override("separation", 12)
	_card.add_child(row)

	# Portrait in a glowing frame. The frame is a Panel whose border pulses while speaking.
	_frame = Panel.new()
	_frame.custom_minimum_size = Vector2(84, 84)
	_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var fb := StyleBoxFlat.new()
	fb.bg_color = Color(0.10, 0.10, 0.14)
	fb.border_color = _COL_BORDER
	fb.set_border_width_all(2)
	fb.set_corner_radius_all(6)
	_frame.add_theme_stylebox_override("panel", fb)
	row.add_child(_frame)

	_portrait = TextureRect.new()
	_portrait.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_portrait.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_portrait.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_portrait.offset_left = 6.0
	_portrait.offset_top = 6.0
	_portrait.offset_right = -6.0
	_portrait.offset_bottom = -6.0
	_frame.add_child(_portrait)

	var col := VBoxContainer.new()
	col.mouse_filter = Control.MOUSE_FILTER_IGNORE
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 4)
	row.add_child(col)

	_name_label = Label.new()
	_name_label.add_theme_color_override("font_color", _COL_NAME)
	_name_label.add_theme_font_size_override("font_size", 15)
	col.add_child(_name_label)

	_text_label = RichTextLabel.new()
	_text_label.bbcode_enabled = false
	_text_label.scroll_active = false
	_text_label.fit_content = true
	_text_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_text_label.add_theme_color_override("default_color", _COL_TEXT)
	_text_label.custom_minimum_size = Vector2(0, 52)
	_text_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_child(_text_label)


## Resolve a portrait sprite for a speaker: engine slug first, then display name (enemy path),
## then the generic villager. Returns a tile index into the atlas, or -1.
func _portrait_idx(slug: String, display_name: String) -> int:
	if _sheet.is_empty():
		return -1
	var by_id = _sheet.get("by_id", {})
	if by_id.has(slug):
		return int(by_id[slug])
	var by_name = _sheet.get("by_name", {})
	var nm := display_name.to_lower()
	if by_name.has(nm):
		return int(by_name[nm])
	return int(by_id.get("player", -1)) if slug == "player" else 85   # 85 = generic villager


## Show a spoken line. `speech` should already be the QUOTED words only (stage directions are
## never player-visible text — owner directive).
func show_line(npc_name: String, speech: String, slug: String = "") -> void:
	var line := speech.strip_edges()
	if line == "":
		return
	_name_label.text = npc_name
	_text_label.text = line
	_text_label.visible_characters = 0
	_reveal = 0.0
	_idle = 0.0
	if _atlas != null:
		var idx := _portrait_idx(slug, npc_name)
		if idx >= 0:
			var at := AtlasTexture.new()
			at.atlas = _atlas
			at.region = Rect2((idx % _cols) * _ts, (idx / _cols) * _ts, _ts, _ts)
			_portrait.texture = at
	visible = true


## main.gd feeds this each frame: true while the NPC's voice is audibly playing (or queued).
func set_speaking(on: bool) -> void:
	_speaking = on


func _process(delta: float) -> void:
	if not visible:
		return
	# typewriter reveal
	var total := _text_label.text.length()
	if _text_label.visible_characters < total:
		_reveal += delta * TYPE_CHARS_PER_S
		_text_label.visible_characters = mini(total, int(_reveal))
	elif not _speaking:
		_idle += delta
		if _idle >= HIDE_AFTER_S:
			visible = false
	else:
		_idle = 0.0
	# speaking glow: pulse the portrait frame's border while the voice plays
	var fb: StyleBoxFlat = _frame.get_theme_stylebox("panel")
	if fb != null:
		if _speaking:
			_glow_t += delta * 6.0
			fb.border_color = _COL_BORDER.lerp(_COL_GLOW, 0.5 + 0.5 * sin(_glow_t))
		else:
			fb.border_color = _COL_BORDER
