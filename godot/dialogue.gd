extends CanvasLayer
## Dialogue overlay — a THIN input surface over the Python game-core.
## Hidden by default. main.gd opens it for talk/do; on submit it calls Net.talk / Net.do_action.
## While open it consumes input so movement keys never leak to main.gd's _unhandled_input.
## It sends NOTHING to the world/HUD; the only outward call is Net.talk / Net.do_action.
##
## NOTE: CanvasLayer extends Node (NOT CanvasItem), so it has a `visible` bool property but
## NO show()/hide() methods. Toggle visibility via `visible` only.

## Fired the moment the player submits (before the reply round-trip) so main can echo the line
## + a thinking beat in the HUD — the LLM wait reads as the character considering, not a dead UI.
signal submitted(mode: String, target_name: String, text: String)

var _open := false
var _mode := ""       # "talk" | "do"
var _target := ""     # target entity id (talk only)
var _target_name := ""

var _panel: Panel
var _prompt: Label
var _edit: LineEdit

# Palette (Color("hex") is a runtime value → plain vars, never const).
var _COL_PANEL := Color("1b1b22")
var _COL_BORDER := Color("5fd0e0")
var _COL_PROMPT := Color("c8bda0")
var _COL_HINT := Color("888890")
var _COL_TEXT := Color("f0f0f0")


func _ready() -> void:
	layer = 20  # above the HUD so the panel and its focus win.
	_build_ui()
	# CanvasLayer has no hide(); use the `visible` property.
	visible = false


func _build_ui() -> void:
	# Dim backdrop so the overlay reads as modal.
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.55)
	dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(dim)

	# Centred panel. (Sized for prompt + entry + hint — the NPC's reply lands in the HUD log,
	# not here: the overlay closes on submit, so an in-panel reply pane would never be seen.)
	_panel = Panel.new()
	_panel.custom_minimum_size = Vector2(560, 150)
	_panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	# PRESET_CENTER anchors all four sides to 0.5; set offsets so the box is centred on its size.
	_panel.offset_left = -280.0
	_panel.offset_top = -75.0
	_panel.offset_right = 280.0
	_panel.offset_bottom = 75.0
	var sb := StyleBoxFlat.new()
	sb.bg_color = _COL_PANEL
	sb.border_color = _COL_BORDER
	sb.set_border_width_all(2)
	sb.set_corner_radius_all(6)
	sb.set_content_margin_all(16)
	_panel.add_theme_stylebox_override("panel", sb)
	add_child(_panel)

	# Vertical layout inside the panel.
	var box := VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	box.offset_left = 16.0
	box.offset_top = 16.0
	box.offset_right = -16.0
	box.offset_bottom = -16.0
	box.add_theme_constant_override("separation", 12)
	_panel.add_child(box)

	_prompt = Label.new()
	_prompt.text = ""
	_prompt.add_theme_color_override("font_color", _COL_PROMPT)
	_prompt.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_prompt)

	_edit = LineEdit.new()
	_edit.placeholder_text = "type, then Enter…  (Esc to cancel)"
	_edit.custom_minimum_size = Vector2(0, 34)
	_edit.add_theme_color_override("font_color", _COL_TEXT)
	_edit.text_submitted.connect(_on_submit)
	box.add_child(_edit)

	var hint := Label.new()
	hint.text = "Enter to send   •   Esc to cancel"
	hint.add_theme_color_override("font_color", _COL_HINT)
	box.add_child(hint)


func is_open() -> bool:
	return _open


func open_talk(target_id: String, target_name: String) -> void:
	_mode = "talk"
	_target = str(target_id)
	var who := str(target_name).strip_edges()
	if who == "":
		who = "them"
	_target_name = who
	if _prompt != null:
		_prompt.text = "Say to %s:" % who
	_open_common()


func open_do() -> void:
	_mode = "do"
	_target = ""
	_target_name = ""
	if _prompt != null:
		_prompt.text = "You try to:"
	_open_common()


func _open_common() -> void:
	_open = true
	if _edit != null:
		_edit.text = ""
	# CanvasLayer has no show(); use the `visible` property.
	visible = true
	# grab_focus must happen after the node is visible/in-tree.
	if _edit != null:
		_edit.call_deferred("grab_focus")


func _on_submit(t: String) -> void:
	var msg := str(t).strip_edges()
	if msg == "":
		# Empty submit: keep the box open, refocus so the player can try again.
		if _edit != null:
			_edit.grab_focus()
		return
	if _mode == "talk":
		Net.talk(_target, msg)
	else:
		Net.do_action(msg)
	submitted.emit(_mode, _target_name, msg)
	_close()


func _close() -> void:
	_open = false
	if _edit != null:
		_edit.text = ""
	# CanvasLayer has no hide(); use the `visible` property.
	visible = false


func _input(event: InputEvent) -> void:
	# Esc must close in ONE press. _input fires BEFORE GUI input, so we catch it even while the
	# LineEdit has focus (in _unhandled_input the first Esc only made the LineEdit release focus,
	# and the player had to press it twice). ONLY Esc is intercepted here — anything broader would
	# starve the LineEdit of its character input.
	if not _open:
		return
	if event is InputEventKey and event.pressed and not event.echo and event.keycode == KEY_ESCAPE:
		_close()
		get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
	# While open, swallow ALL key input so movement/hotkeys never reach main.gd.
	if not _open:
		return
	# The LineEdit handles character entry via GUI input; any key event that still reaches
	# _unhandled_input while we're open (e.g. focus was clicked away) is consumed here so it
	# can never drive the world. Consume presses AND releases to avoid stray leaks.
	if event is InputEventKey:
		get_viewport().set_input_as_handled()
