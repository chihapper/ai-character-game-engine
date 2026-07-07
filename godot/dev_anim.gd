extends CanvasLayer
## Dev animation browser (F10): a sidebar listing every modeled entity in the scene and every
## clip its AnimationPlayer carries (embedded + the shared "kk/*" library). Click a clip to play
## it on the live model; Idle resets. Pure dev tooling — reads the world through three debug_*
## methods on world3d and never touches game state or the wire.

var _world: Node = null            # world3d (injected by main.gd)

var _panel: PanelContainer
var _who: OptionButton
var _filter: LineEdit
var _list: VBoxContainer
var _count: Label


func setup(world: Node) -> void:
	_world = world


func _ready() -> void:
	layer = 25                     # above speech card (15) and input overlay (20)
	visible = false
	_build_ui()


func toggle() -> void:
	visible = not visible
	if visible:
		_refresh_entities()


func _build_ui() -> void:
	_panel = PanelContainer.new()
	_panel.set_anchors_and_offsets_preset(Control.PRESET_RIGHT_WIDE)
	_panel.offset_left = -300.0
	_panel.offset_top = 8.0
	_panel.offset_bottom = -8.0
	_panel.offset_right = -8.0
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.05, 0.05, 0.08, 0.96)
	sb.border_color = Color("5fd0e0")
	sb.set_border_width_all(2)
	sb.set_corner_radius_all(8)
	sb.set_content_margin_all(8)
	_panel.add_theme_stylebox_override("panel", sb)
	add_child(_panel)

	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 6)
	_panel.add_child(col)

	var title := Label.new()
	title.text = "Animation browser  (F10 closes)"
	title.add_theme_font_size_override("font_size", 14)
	title.add_theme_color_override("font_color", Color("c8bda0"))
	col.add_child(title)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	col.add_child(row)
	_who = OptionButton.new()
	_who.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_who.item_selected.connect(func(_i: int): _refresh_clips())
	row.add_child(_who)
	var refresh := Button.new()
	refresh.text = "↻"
	refresh.tooltip_text = "Re-scan entities"
	refresh.pressed.connect(_refresh_entities)
	row.add_child(refresh)
	var idle := Button.new()
	idle.text = "Idle"
	idle.tooltip_text = "Reset to Idle"
	idle.pressed.connect(func():
		if _world != null and _who.item_count > 0:
			_world.debug_idle(_who.get_item_text(_who.selected)))
	row.add_child(idle)

	_filter = LineEdit.new()
	_filter.placeholder_text = "filter clips…"
	_filter.text_changed.connect(func(_t: String): _refresh_clips())
	col.add_child(_filter)

	_count = Label.new()
	_count.add_theme_font_size_override("font_size", 11)
	_count.add_theme_color_override("font_color", Color(0.6, 0.6, 0.65))
	col.add_child(_count)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	col.add_child(scroll)
	_list = VBoxContainer.new()
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_list.add_theme_constant_override("separation", 2)
	scroll.add_child(_list)


func _refresh_entities() -> void:
	if _world == null or not _world.has_method("debug_entities"):
		return
	var prev := _who.get_item_text(_who.selected) if _who.item_count > 0 else "player"
	_who.clear()
	var ids: Array = _world.debug_entities()
	for i in ids.size():
		_who.add_item(str(ids[i]))
		if str(ids[i]) == prev:
			_who.selected = i
	_refresh_clips()


func _refresh_clips() -> void:
	for c in _list.get_children():
		c.queue_free()
	if _world == null or _who.item_count == 0:
		_count.text = "no modeled entities in view"
		return
	var id := _who.get_item_text(_who.selected)
	var filt := _filter.text.to_lower()
	var clips: Array = _world.debug_clips(id)
	var shown := 0
	for clip in clips:
		var name := str(clip)
		if filt != "" and not name.to_lower().contains(filt):
			continue
		shown += 1
		var b := Button.new()
		b.text = name
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.add_theme_font_size_override("font_size", 12)
		b.pressed.connect(func(): _world.debug_play(id, name))
		_list.add_child(b)
	_count.text = "%d / %d clips" % [shown, clips.size()]
