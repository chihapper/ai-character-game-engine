extends CanvasLayer
## HUD (screen-space UI) for the RPG client — a THIN renderer over the Python game-core.
## Draws each StateSnapshot's status/party/controls/banner and appends the message log.
## NO networking, NO input handling, NO game logic. main.gd calls render(); log_event().

const MAX_LOG_LINES := 200

# --- Control children (built in _ready) ---
var _status_label: RichTextLabel
var _party_panel: VBoxContainer
var _party_title: Label
var _log_label: RichTextLabel
var _controls_label: Label
var _combat_banner: Label

# --- log ring-buffer ---
var _log_buf: PackedStringArray = PackedStringArray()

# --- colours (runtime values → var, never const) ---
var _col_follower := Color("78dc78")
var _col_enemy := Color("dc5a5a")
var _col_hp_back := Color(0.12, 0.12, 0.14, 0.9)
var _col_panel_bg := Color(0.05, 0.05, 0.07, 0.72)
var _col_banner := Color("dc5a5a")
var _col_text := Color(0.92, 0.92, 0.92)
var _col_dim := Color(0.68, 0.68, 0.72)


func _ready() -> void:
	layer = 10

	# ---- top-left status bar ----
	_status_label = RichTextLabel.new()
	_status_label.bbcode_enabled = false
	_status_label.scroll_active = false
	_status_label.fit_content = true
	_status_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_status_label.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	_status_label.offset_left = 12.0
	_status_label.offset_top = 8.0
	_status_label.offset_right = 620.0
	_status_label.offset_bottom = 64.0
	_status_label.add_theme_color_override("default_color", _col_text)
	add_child(_status_label)

	# ---- right-side party panel ----
	# A Container pinned on all four offsets keeps a FIXED rect and ignores its child
	# min-size. TOP_RIGHT already sets bottom-anchor == top-anchor (0), so we must NOT
	# pin offset_bottom equal to offset_top (that forces a 0px-tall box that clips every
	# row). Instead grow DOWNWARD from the top-right corner and let the PanelContainer
	# size to its content's combined minimum height.
	var party_bg := PanelContainer.new()
	party_bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	party_bg.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	party_bg.grow_horizontal = Control.GROW_DIRECTION_BEGIN  # expand leftward from the right edge
	party_bg.grow_vertical = Control.GROW_DIRECTION_END      # expand downward from the top edge
	party_bg.offset_left = -252.0
	party_bg.offset_top = 8.0
	party_bg.offset_right = -12.0
	# offset_bottom is left at the preset's default (== offset_top region); with
	# grow_vertical=END the container height is driven by its content min-size.
	var pbg_style := StyleBoxFlat.new()
	pbg_style.bg_color = _col_panel_bg
	pbg_style.set_corner_radius_all(6)
	pbg_style.set_content_margin_all(8.0)
	party_bg.add_theme_stylebox_override("panel", pbg_style)
	add_child(party_bg)

	_party_panel = VBoxContainer.new()
	_party_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_party_panel.add_theme_constant_override("separation", 4)
	party_bg.add_child(_party_panel)

	_party_title = Label.new()
	_party_title.text = "Party"
	_party_title.add_theme_color_override("font_color", _col_dim)
	_party_panel.add_child(_party_title)

	# ---- bottom-left message log ----
	_log_label = RichTextLabel.new()
	_log_label.bbcode_enabled = false
	_log_label.scroll_following = true
	_log_label.scroll_active = true
	_log_label.fit_content = false
	_log_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_log_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	_log_label.offset_left = 12.0
	_log_label.offset_top = -218.0
	_log_label.offset_right = 660.0
	_log_label.offset_bottom = -40.0
	var log_style := StyleBoxFlat.new()
	log_style.bg_color = _col_panel_bg
	log_style.set_corner_radius_all(6)
	log_style.set_content_margin_all(8.0)
	_log_label.add_theme_stylebox_override("normal", log_style)
	_log_label.add_theme_color_override("default_color", _col_text)
	add_child(_log_label)

	# ---- bottom controls hint ----
	_controls_label = Label.new()
	_controls_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_controls_label.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	_controls_label.offset_left = 12.0
	_controls_label.offset_top = -32.0
	_controls_label.offset_right = 1200.0
	_controls_label.offset_bottom = -8.0
	_controls_label.add_theme_color_override("font_color", _col_dim)
	_controls_label.text = _controls_text("exploration")
	add_child(_controls_label)

	# ---- combat banner (top-centre red strip) ----
	_combat_banner = Label.new()
	_combat_banner.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_combat_banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_combat_banner.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_combat_banner.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	_combat_banner.offset_left = 260.0
	_combat_banner.offset_top = 8.0
	_combat_banner.offset_right = -260.0
	_combat_banner.offset_bottom = 40.0
	_combat_banner.text = "  COMBAT  "
	var banner_style := StyleBoxFlat.new()
	banner_style.bg_color = _col_banner
	banner_style.set_corner_radius_all(4)
	banner_style.set_content_margin_all(4.0)
	_combat_banner.add_theme_stylebox_override("normal", banner_style)
	_combat_banner.add_theme_color_override("font_color", Color(1, 1, 1))
	_combat_banner.visible = false
	add_child(_combat_banner)


# =====================================================================
# Public API (called by main.gd) — matches the shared contract exactly.
# =====================================================================

func render(snap: Dictionary) -> void:
	# `snap` is statically typed Dictionary → never null here; an empty {} is safe
	# because every helper reads through guarded .get() lookups.
	_update_status(snap)
	_update_party(snap)
	_update_controls(snap)
	_update_banner(snap)


func log_line(text: String) -> void:
	_log_buf.append(text)
	if _log_buf.size() > MAX_LOG_LINES:
		_log_buf = _log_buf.slice(_log_buf.size() - MAX_LOG_LINES)
	if _log_label != null:
		_log_label.text = "\n".join(_log_buf)


func log_event(ev: Dictionary) -> void:
	# `ev` is statically typed Dictionary; Net only emits dict events. Empty is a no-op.
	var t := str(ev.get("type", ""))
	match t:
		"narration", "combat":
			var txt := str(ev.get("text", ""))
			if txt != "":
				log_line(txt)
		"dialogue":
			var npc := str(ev.get("npc", ""))
			var speech := str(ev.get("speech", ""))
			var action := str(ev.get("action", ""))
			if speech == "":
				speech = str(ev.get("text", ""))   # fallback if the server didn't split
			if npc != "":
				log_line("%s: %s" % [npc, speech])
			else:
				log_line(speech)
			if action != "":
				log_line("   (%s)" % action)         # stage business as a dim description line
		"mode_changed":
			log_line("— %s —" % str(ev.get("mode", "")).to_upper())
		"state_changed":
			pass
		_:
			var other := str(ev.get("text", ""))
			if other != "":
				log_line(other)


# =====================================================================
# Internal render helpers
# =====================================================================

func _update_status(snap: Dictionary) -> void:
	if _status_label == null:
		return
	var player: Dictionary = snap.get("player", {})
	if typeof(player) != TYPE_DICTIONARY:
		player = {}
	# hp / max_hp may be null on a partial snapshot — coerce to a safe display int.
	var hp := _to_int(player.get("hp", 0), 0)
	var max_hp := _to_int(player.get("max_hp", 0), 0)
	var mode := str(snap.get("mode", "exploration"))
	var clock := _to_float(snap.get("clock", 0.0), 0.0)
	# item count: prefer top-level inventory, fall back to player.inventory
	var inv = snap.get("inventory", null)
	if typeof(inv) != TYPE_ARRAY:
		inv = player.get("inventory", [])
	var item_count := 0
	if typeof(inv) == TYPE_ARRAY:
		item_count = (inv as Array).size()
	var objective := str(snap.get("objective", ""))

	var line1 := "HP %d/%d   %s   t=%.1f   items:%d" % [
		hp, max_hp, mode.to_upper(), clock, item_count
	]
	if objective != "":
		_status_label.text = line1 + "\n" + objective
	else:
		_status_label.text = line1


func _update_party(snap: Dictionary) -> void:
	if _party_panel == null:
		return
	# clear previous rows (keep the title at index 0)
	for i in range(_party_panel.get_child_count() - 1, 0, -1):
		var child := _party_panel.get_child(i)
		_party_panel.remove_child(child)
		child.queue_free()

	var entities = snap.get("entities", [])
	if typeof(entities) != TYPE_ARRAY:
		entities = []
	var any := false
	for e in entities:
		if typeof(e) != TYPE_DICTIONARY:
			continue
		if str(e.get("kind", "")) != "follower":
			continue
		any = true
		_party_panel.add_child(_make_party_row(e))

	if not any:
		var none := Label.new()
		none.text = "(no companions)"
		none.add_theme_color_override("font_color", _col_dim)
		_party_panel.add_child(none)


func _make_party_row(e: Dictionary) -> Control:
	var row := VBoxContainer.new()
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.custom_minimum_size = Vector2(220, 0)
	row.add_theme_constant_override("separation", 2)

	var name_label := Label.new()
	name_label.text = str(e.get("name", "?"))
	name_label.add_theme_color_override("font_color", _col_follower)
	row.add_child(name_label)

	# hp / max_hp may be null (contract) — the bar treats null as "unknown".
	var hp = e.get("hp", null)
	var max_hp = e.get("max_hp", null)
	var bar := _HpBar.new()
	bar.set_hp(hp, max_hp, _col_follower, _col_hp_back)
	bar.custom_minimum_size = Vector2(200, 8)
	row.add_child(bar)
	return row


func _update_controls(snap: Dictionary) -> void:
	if _controls_label == null:
		return
	_controls_label.text = _controls_text(str(snap.get("mode", "exploration")))


func _controls_text(mode: String) -> String:
	if mode == "combat":
		return "move into a foe to attack   G toggle enemy HP   . wait"
	return "move: arrows/WASD   T talk   X do   R recruit   F help   L look   . wait"


func _update_banner(snap: Dictionary) -> void:
	if _combat_banner == null:
		return
	_combat_banner.visible = str(snap.get("mode", "exploration")) == "combat"


# =====================================================================
# Safe numeric coercion — JSON numbers arrive as float/int, but a partial
# snapshot may carry null (or a stray String). int()/float() on null raise
# a runtime error, so route every cast through these guards.
# =====================================================================

func _to_int(v, fallback: int) -> int:
	match typeof(v):
		TYPE_INT:
			return v
		TYPE_FLOAT:
			return int(v)
		TYPE_STRING, TYPE_STRING_NAME:
			return int(str(v)) if str(v).is_valid_int() else fallback
		_:
			return fallback


func _to_float(v, fallback: float) -> float:
	match typeof(v):
		TYPE_FLOAT:
			return v
		TYPE_INT:
			return float(v)
		TYPE_STRING, TYPE_STRING_NAME:
			return float(str(v)) if str(v).is_valid_float() else fallback
		_:
			return fallback


# =====================================================================
# Small self-drawing HP bar widget used in the party panel.
# =====================================================================

class _HpBar extends Control:
	var _frac := 1.0
	var _fill := Color(0.47, 0.86, 0.47)
	var _back := Color(0.12, 0.12, 0.14, 0.9)
	var _known := false

	func set_hp(hp, max_hp, fill: Color, back: Color) -> void:
		_fill = fill
		_back = back
		# hp/max_hp may be null OR JSON numbers (float/int); only draw a fill when
		# both are usable numbers and max_hp is positive.
		if not _is_num(hp) or not _is_num(max_hp):
			_known = false
			_frac = 1.0
		else:
			var mh := float(max_hp)
			if mh <= 0.0:
				_known = false
				_frac = 1.0
			else:
				_known = true
				_frac = clampf(float(hp) / mh, 0.0, 1.0)
		queue_redraw()

	func _is_num(v) -> bool:
		return typeof(v) == TYPE_INT or typeof(v) == TYPE_FLOAT

	func _draw() -> void:
		var sz := size
		if sz.x <= 0.0 or sz.y <= 0.0:
			sz = custom_minimum_size
		if sz.x <= 0.0 or sz.y <= 0.0:
			return
		draw_rect(Rect2(Vector2.ZERO, sz), _back, true)
		if _known:
			draw_rect(Rect2(Vector2.ZERO, Vector2(sz.x * _frac, sz.y)), _fill, true)
		# 1px border
		draw_rect(Rect2(Vector2.ZERO, sz), Color(0, 0, 0, 0.5), false, 1.0)
