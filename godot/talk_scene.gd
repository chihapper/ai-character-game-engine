extends CanvasLayer
## Talk scene — the Civ 5-style conversation presentation (owner north star 2026-07-08):
## talking to someone brings up their WHOLE portrait, and they speak to you — motion synced to
## the live Hume voice. Portrait sources, best first:
##   1. painted art  assets/portraits/<slug>.png (runtime-loaded, gitignored tier) — with an
##      optional <slug>_mouth_open.png layer that flaps on speech amplitude,
##   2. a live 3D BUST of the character's own in-world GLB in a SubViewport (everyone has one),
##      nodding and swaying with the voice,
## so the screen works for the full cast TODAY and upgrades per-character as art lands.
##
## THIN and render-only: no networking, no game logic. main.gd opens/closes it, routes dialogue
## events here while open, and feeds set_level() with the voice playhead's amplitude each frame.

const TYPE_CHARS_PER_S := 42.0

var _slug := ""
var _display := ""
var _level := 0.0            # smoothed speech amplitude 0..1 (fed by main.gd)
var _level_target := 0.0
var _time := 0.0
var _reveal := 0.0

# ui
var _dim: ColorRect
var _frame: PanelContainer          # portrait frame (right)
var _portrait: TextureRect          # painted art (when present)
var _mouth: TextureRect             # optional painted mouth-open layer
var _bust_holder: Control           # 3D bust (fallback)
var _bust_vp: SubViewport = null
var _bust_model: Node3D = null
var _name_plate: Label
var _text_panel: PanelContainer     # the spoken line (left)
var _text: RichTextLabel
var _hint: Label
var _you_frame: PanelContainer      # the PLAYER's painted portrait, small, top-left — the
var _you_portrait: TextureRect      # conversation has two sides (shown only when art exists)

var _portrait_cache := {}           # slug -> {base: Texture2D|null, mouth: Texture2D|null}


func _ready() -> void:
	layer = 14                      # above HUD (10), below speech card (15) + input overlay (20)
	visible = false
	_build_ui()


# ------------------------------------------------------------------ public

func is_open() -> bool:
	return visible


func open(slug: String, display_name: String, model_path: String) -> void:
	if slug == "":
		return
	_slug = slug
	_display = display_name
	_name_plate.text = display_name
	_text.text = ""
	_reveal = 0.0
	var art := _painted(slug)
	if art["base"] != null:
		_portrait.texture = art["base"]
		_mouth.texture = art["mouth"]
		_mouth.visible = false
		_portrait.visible = true
		_bust_holder.visible = false
	else:
		_portrait.visible = false
		_mouth.visible = false
		_bust_holder.visible = true
		_set_bust(model_path)
	var you := _painted("player")
	_you_frame.visible = you["base"] != null and slug != "player"
	if you["base"] != null:
		_you_portrait.texture = you["base"]
	visible = true


func close() -> void:
	visible = false
	_slug = ""
	if _bust_model != null:
		_bust_model.queue_free()
		_bust_model = null


## An NPC line while the scene is up. A different speaker interjecting takes the stage
## (portrait switches) — conversations stay one face at a time, like the inspiration.
func show_line(display_name: String, line: String, slug: String, model_path: String) -> void:
	if slug != "" and slug != _slug:
		open(slug, display_name, model_path)
	_text.text = line
	_text.visible_characters = 0
	_reveal = 0.0


## Voice playhead amplitude (0..1), fed by main.gd every frame — drives mouth/motion.
func set_level(l: float) -> void:
	_level_target = clampf(l, 0.0, 1.0)


# ------------------------------------------------------------------ internals

func _painted(slug: String) -> Dictionary:
	if _portrait_cache.has(slug):
		return _portrait_cache[slug]
	var out := {"base": null, "mouth": null}
	var base_path := "res://assets/portraits/%s.png" % slug
	if FileAccess.file_exists(base_path):
		var img := Image.load_from_file(base_path)
		if img != null:
			out["base"] = ImageTexture.create_from_image(img)
		var mouth_path := "res://assets/portraits/%s_mouth_open.png" % slug
		if FileAccess.file_exists(mouth_path):
			var mimg := Image.load_from_file(mouth_path)
			if mimg != null:
				out["mouth"] = ImageTexture.create_from_image(mimg)
	_portrait_cache[slug] = out
	return out


func _set_bust(model_path: String) -> void:
	if _bust_vp == null:
		_bust_vp = SubViewport.new()
		_bust_vp.size = Vector2i(460, 560)
		_bust_vp.own_world_3d = true
		_bust_vp.transparent_bg = true
		add_child(_bust_vp)
		var cam := Camera3D.new()
		cam.fov = 30.0
		# head-and-torso framing: KayKit chibis are ~2u tall with enormous heads — this distance
		# shows the face AND the body language (the acting layer reaches the talk scene too)
		cam.position = Vector3(0.8, 1.5, 3.6)
		_bust_vp.add_child(cam)
		cam.look_at(Vector3(0.0, 1.0, 0.0))
		cam.make_current()
		var key := DirectionalLight3D.new()          # warm key from camera-left
		key.light_color = Color(1.0, 0.85, 0.65)
		key.light_energy = 1.1
		key.rotation_degrees = Vector3(-25.0, 35.0, 0.0)
		_bust_vp.add_child(key)
		var fill := DirectionalLight3D.new()         # cool fill from the right
		fill.light_color = Color(0.5, 0.6, 0.9)
		fill.light_energy = 0.4
		fill.rotation_degrees = Vector3(-10.0, -120.0, 0.0)
		_bust_vp.add_child(fill)
		var tr := TextureRect.new()
		tr.texture = _bust_vp.get_texture()
		tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		tr.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		tr.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_bust_holder.add_child(tr)
	if _bust_model != null:
		_bust_model.queue_free()
		_bust_model = null
	if model_path != "" and ResourceLoader.exists(model_path):
		var scene = load(model_path)
		if scene is PackedScene:
			_bust_model = (scene as PackedScene).instantiate()
			_bust_vp.add_child(_bust_model)
			_bust_model.rotation.y = 0.35            # three-quarter stance, like a leader screen
			var aps := _bust_model.find_children("*", "AnimationPlayer", true, false)
			if not aps.is_empty():
				var ap := aps[0] as AnimationPlayer
				for a in ap.get_animation_list():
					if str(a).to_lower() == "idle":
						var anim := ap.get_animation(a)
						if anim != null:
							anim.loop_mode = Animation.LOOP_LINEAR
						ap.play(a)
						break


func _build_ui() -> void:
	_dim = ColorRect.new()
	_dim.color = Color(0.0, 0.0, 0.02, 0.45)
	_dim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_dim.mouse_filter = Control.MOUSE_FILTER_STOP   # the scene is modal; clicks close it
	add_child(_dim)

	# portrait stage, right of center
	_frame = PanelContainer.new()
	_frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_frame.anchor_left = 0.58
	_frame.anchor_right = 0.96
	_frame.anchor_top = 0.06
	_frame.anchor_bottom = 0.78
	_frame.set_offsets_preset(Control.PRESET_FULL_RECT)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.06, 0.06, 0.10, 0.97)
	sb.border_color = Color("c8bda0")
	sb.set_border_width_all(3)
	sb.set_corner_radius_all(10)
	sb.set_content_margin_all(10)
	_frame.add_theme_stylebox_override("panel", sb)
	add_child(_frame)

	var stage := Control.new()
	stage.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_frame.add_child(stage)

	_portrait = TextureRect.new()
	_portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_portrait.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	_portrait.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_portrait.mouse_filter = Control.MOUSE_FILTER_IGNORE
	stage.add_child(_portrait)

	_mouth = TextureRect.new()                       # painted mouth-open layer (optional art)
	_mouth.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_mouth.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_mouth.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	_mouth.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_mouth.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_mouth.visible = false
	stage.add_child(_mouth)

	_bust_holder = Control.new()
	_bust_holder.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_bust_holder.mouse_filter = Control.MOUSE_FILTER_IGNORE
	stage.add_child(_bust_holder)

	_name_plate = Label.new()
	_name_plate.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_name_plate.add_theme_font_size_override("font_size", 22)
	_name_plate.add_theme_color_override("font_color", Color("c8bda0"))
	_name_plate.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	_name_plate.offset_top = -34.0
	_name_plate.mouse_filter = Control.MOUSE_FILTER_IGNORE
	stage.add_child(_name_plate)

	# their line, left of the portrait
	_text_panel = PanelContainer.new()
	_text_panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_text_panel.anchor_left = 0.05
	_text_panel.anchor_right = 0.55
	_text_panel.anchor_top = 0.27
	_text_panel.anchor_bottom = 0.64
	_text_panel.set_offsets_preset(Control.PRESET_FULL_RECT)
	var tb := StyleBoxFlat.new()
	tb.bg_color = Color(0.05, 0.05, 0.08, 0.94)
	tb.border_color = Color("5fd0e0")
	tb.set_border_width_all(2)
	tb.set_corner_radius_all(8)
	tb.set_content_margin_all(14)
	_text_panel.add_theme_stylebox_override("panel", tb)
	add_child(_text_panel)

	_text = RichTextLabel.new()
	_text.bbcode_enabled = false
	_text.scroll_active = false
	_text.fit_content = false
	_text.add_theme_color_override("default_color", Color(0.95, 0.95, 0.95))
	_text.add_theme_font_size_override("normal_font_size", 17)
	_text.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_text_panel.add_child(_text)

	# the player's side of the table: a smaller framed portrait, top-left
	_you_frame = PanelContainer.new()
	_you_frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_you_frame.anchor_left = 0.05
	_you_frame.anchor_right = 0.19
	_you_frame.anchor_top = 0.045
	_you_frame.anchor_bottom = 0.25
	_you_frame.set_offsets_preset(Control.PRESET_FULL_RECT)
	var yb := StyleBoxFlat.new()
	yb.bg_color = Color(0.06, 0.06, 0.10, 0.97)
	yb.border_color = Color(0.45, 0.5, 0.6)
	yb.set_border_width_all(2)
	yb.set_corner_radius_all(8)
	yb.set_content_margin_all(6)
	_you_frame.add_theme_stylebox_override("panel", yb)
	_you_frame.visible = false
	add_child(_you_frame)
	_you_portrait = TextureRect.new()
	_you_portrait.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_you_portrait.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_you_portrait.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	_you_portrait.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_you_frame.add_child(_you_portrait)

	_hint = Label.new()
	_hint.text = "T — reply        Esc / click away — leave"
	_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_hint.add_theme_font_size_override("font_size", 13)
	_hint.add_theme_color_override("font_color", Color(0.65, 0.65, 0.7))
	# sits just under the text panel, well clear of the bottom controls bar
	_hint.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_hint.anchor_left = 0.05
	_hint.anchor_right = 0.55
	_hint.anchor_top = 0.65
	_hint.anchor_bottom = 0.69
	_hint.set_offsets_preset(Control.PRESET_FULL_RECT)
	_hint.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_hint)


func _input(event: InputEvent) -> void:
	if not visible:
		return
	# Esc leaves the conversation; a click outside the portrait/text panels does too. The text
	# entry overlay (layer 20) sits above and consumes its own input first.
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		close()
		get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		var mp: Vector2 = _frame.get_global_mouse_position()
		if not _frame.get_global_rect().has_point(mp) and not _text_panel.get_global_rect().has_point(mp):
			close()
			get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
	if not visible:
		return
	_time += delta
	_level = lerpf(_level, _level_target, minf(1.0, delta * 14.0))
	# typewriter
	var total := _text.text.length()
	if _text.visible_characters < total:
		_reveal += delta * TYPE_CHARS_PER_S
		_text.visible_characters = mini(total, int(_reveal))
	# Painted portrait: STABLE (owner feedback 2026-07-08 — the scale "breathing" read as the
	# art hovering). Speech shows as a gentle brightness lift + the frame glow; the mouth layer
	# (when the art ships one) still flaps on syllables.
	if _portrait.visible:
		_portrait.modulate = Color(1, 1, 1).lerp(Color(1.06, 1.04, 1.0), _level)
		if _mouth.texture != null:
			_mouth.visible = _level > 0.22 and fmod(_time * 9.0, 1.0) < 0.62
	# 3D bust: rock-steady base pose; speech drives one SMOOTH nod component (no fast sine —
	# jitter reads as instability at portrait scale).
	if _bust_holder.visible and _bust_model != null:
		_bust_model.rotation.y = 0.35 + 0.03 * sin(_time * 0.6)
		_bust_model.rotation.x = -0.06 * _level
	# frame glow while the voice is audible
	var fsb: StyleBoxFlat = _frame.get_theme_stylebox("panel")
	if fsb != null:
		fsb.border_color = Color("c8bda0").lerp(Color("f5d020"), _level)
