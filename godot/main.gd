extends Node2D
## Root wiring for the Sunken Vault Godot client.
##
## THIN renderer over the Python RPG core. This node owns NO game logic: it only
## instances the three visual modules (World / Hud / Dialogue), wires up the `Net`
## autoload's signals, kicks off the game once the WebSocket link opens, and routes
## ALL keyboard input into `Net.*` action calls (opening the Dialogue overlay for T/X).
##
## Integration invariant: main.gd is the ONLY place that reads input and calls Net.*
## for actions (except Dialogue, which calls Net.talk / Net.do_action on submit).
## World and Hud never send to Net.

var _world: Node          # World3D (default) or the classic 2D view (RPG_2D=1) — same surface
var _hud: CanvasLayer
var _dialogue: CanvasLayer
var _speech: CanvasLayer        # the portrait speech card (speech.gd)
var _talk: CanvasLayer          # the Civ 5-style talk scene (talk_scene.gd)
var _anim_panel: CanvasLayer    # dev animation browser (dev_anim.gd, F10)
var _voice: AudioStreamPlayer   # plays Hume-voiced NPC lines (PCM streamed from the server)

## Last snapshot received from the server; drives the nearest-interactable helper.
var _snapshot: Dictionary = {}

## Guards so we only start the game once per open link.
var _started: bool = false


func _ready() -> void:
	# Instance the three modules by loading their scripts and attaching them to fresh
	# nodes of the type each one `extends`. (World=Node2D, Hud/Dialogue=CanvasLayer.)
	# The 2.5D view is the DEFAULT (owner direction 2026-07-08); RPG_2D=1 launches the classic
	# 2D renderer. Both expose the identical surface: set_slice / render / combat_fx / tile_at_mouse.
	if OS.get_environment("RPG_2D") != "":
		_world = Node2D.new()
		_world.set_script(load("res://world.gd"))
	else:
		_world = Node3D.new()
		_world.set_script(load("res://world3d.gd"))
	_world.name = "World"
	add_child(_world)

	_hud = CanvasLayer.new()
	_hud.name = "Hud"
	_hud.set_script(load("res://hud.gd"))
	add_child(_hud)

	_dialogue = CanvasLayer.new()
	_dialogue.name = "Dialogue"
	_dialogue.set_script(load("res://dialogue.gd"))
	add_child(_dialogue)
	_dialogue.submitted.connect(_on_dialogue_submitted)

	_speech = CanvasLayer.new()
	_speech.name = "Speech"
	_speech.set_script(load("res://speech.gd"))
	add_child(_speech)

	# Dev animation browser (F10): click any clip on any live entity — for testing the acting
	# vocabulary without engineering game situations that trigger each verb.
	_anim_panel = CanvasLayer.new()
	_anim_panel.name = "AnimBrowser"
	_anim_panel.set_script(load("res://dev_anim.gd"))
	add_child(_anim_panel)
	_anim_panel.setup(_world)

	# Talk scene: the Civ 5-style conversation stage (whole portrait / live 3D bust + voice-
	# synced motion). Opens on T-talk; dialogue events route here while it's up.
	_talk = CanvasLayer.new()
	_talk.name = "TalkScene"
	_talk.set_script(load("res://talk_scene.gd"))
	add_child(_talk)
	_talk.closed.connect(_stop_voice)   # leaving the conversation silences the speaker

	_voice = AudioStreamPlayer.new()
	_voice.name = "Voice"
	add_child(_voice)
	_setup_audio()
	# Voice is a CONTINUOUS generator stream, not per-clip WAVs: the server STREAMS each line's
	# PCM in ~0.5s+ chunks as Hume synthesizes it, and we push frames into one generator so chunks
	# butt together gaplessly (per-clip playback had an audible seam at every chunk boundary).
	var gen := AudioStreamGenerator.new()
	gen.mix_rate = float(_voice_rate) # the wire's default PCM rate (s16le mono, AUDIO_SAMPLE_RATE);
	                                  # rebuilt in _play_voice if a message carries a different rate
	gen.buffer_length = 4.0           # generous ring buffer; _process tops it up from _pending
	_voice.stream = gen

	# Wire the Net autoload. `Net` is a global autoload (extends Node) that owns the
	# WebSocket; it emits these three signals and exposes the action methods we call.
	Net.snapshot.connect(_on_snapshot)
	Net.game_event.connect(_on_game_event)
	Net.link_status.connect(_on_link_status)

	# Dev verification hook: RPG_SHOT=<abs path.png> auto-captures the viewport a few seconds
	# after startup (RPG_SHOT_DEMO=1 additionally fakes a speech-card line first, so the card's
	# visuals can be checked without a live LLM round-trip). F12 saves a shot any time.
	var shot := OS.get_environment("RPG_SHOT")
	if shot != "":
		var t := Timer.new()
		t.wait_time = 4.0
		t.one_shot = true
		add_child(t)
		t.timeout.connect(func():
			var demo := OS.get_environment("RPG_SHOT_DEMO")
			if demo == "combat":
				await _stage_combat_demo(shot)   # serverless movement + combat verification reel
				return
			if demo != "" and _speech != null:
				_speech.show_line("Lira", "Stick close — the dark down here has teeth.", "rpg-lira")
				if _world != null:   # fake a crit beat so flash/float/shake are visible in the shot
					_world.combat_fx({"sfx": "crit", "attacker": "player", "target": "player", "damage": 7, "crit": true})
				await get_tree().create_timer(0.55).timeout
			_save_screenshot(shot))
		t.start()


## Serverless verification reel (RPG_SHOT_DEMO=combat): a synthetic snapshot populates the world,
## the player waypoint-walks a staged route, then a scripted round of combat beats plays out —
## timed screenshots capture walking / lunge / damage floats / the death-and-sink phases. Run with
## RPG_WS_URL pointed at a dead port so a live server can't clobber the stage.
func _stage_combat_demo(shot: String) -> void:
	if _world == null or not _world.has_method("follow_path"):
		_save_screenshot(shot)
		return
	var base := shot.get_basename()
	var tiles := ["##########", "#........#", "#........#", "#........#", "##########"]
	var cells: Array = []
	for y in 5:
		for x in 10:
			cells.append(str(x) + "," + str(y))
	var player := {"id": "player", "name": "You", "pos": [2, 2], "kind": "player",
		"creature_type": "humanoid (fighter)", "hp": 20, "max_hp": 20}
	var snap := {"tiles": tiles, "explored": cells, "visible": cells, "mode": "combat",
		"player": player,
		"combat_turn": "player", "combat_movement": 30, "combat_round": 1,
		"combat_order": ["player", "goblin1", "rpg-lira", "skel1"],
		"entities": [
			{"id": "rpg-lira", "name": "Lira", "pos": [5, 3], "kind": "follower", "hp": 15, "max_hp": 18},
			{"id": "goblin1", "name": "Goblin", "pos": [7, 2], "kind": "enemy"},
			{"id": "skel1", "name": "Skeleton", "pos": [8, 3], "kind": "enemy"},
		]}
	_world.render(snap)
	await get_tree().create_timer(0.4).timeout
	# 1) the player walks a real route (waypoints, not a straight lerp) toward a marked tile
	if _world.has_method("mark_destination"):
		_world.mark_destination(Vector2i(6, 2))
	_world.follow_path("player", [[2, 2], [2, 1], [3, 1], [4, 1], [5, 1], [6, 1], [6, 2]])
	var snap2: Dictionary = snap.duplicate(true)
	snap2["player"]["pos"] = [6, 2]
	_world.render(snap2)
	await get_tree().create_timer(0.6).timeout
	_save_screenshot(base + "_1.png")            # mid-walk: Walking clip, between tiles
	# stage-direction acting: Lira's mind wrote the business; her body performs it
	if _world.has_method("act_direction"):
		_world.act_direction("rpg-lira", "She crouches low and slips into the shadows, scouting ahead.")
	await get_tree().create_timer(0.9).timeout
	_save_screenshot(base + "_1b.png")           # Lira mid-sneak, turned toward the player
	await get_tree().create_timer(0.3).timeout
	# 2) a scripted round of blows (same data shapes the server emits)
	_world.combat_fx({"sfx": "hit", "attacker": "player", "target": "goblin1", "damage": 5, "crit": false})
	_world.combat_fx({"sfx": "crit", "attacker": "skel1", "target": "player", "damage": 7, "crit": true})
	_world.combat_fx({"sfx": "miss", "attacker": "goblin1", "target": "rpg-lira"})
	_world.combat_fx({"sfx": "dead", "target": "goblin1"})
	await get_tree().create_timer(0.35).timeout
	_save_screenshot(base + "_2.png")            # player mid-lunge at the goblin
	await get_tree().create_timer(0.5).timeout
	_save_screenshot(base + "_3.png")            # crit float + shake, miss float
	# 3) the killing snapshot lands while the death animation plays — the corpse must linger
	var snap3: Dictionary = snap2.duplicate(true)
	snap3["entities"] = [snap2["entities"][0], snap2["entities"][2]]
	_world.render(snap3)
	_world.combat_fx({"sfx": "victory"})         # the party cheers over the fallen goblin
	await get_tree().create_timer(1.0).timeout
	_save_screenshot(base + "_4.png")            # goblin fallen + party mid-cheer
	await get_tree().create_timer(1.6).timeout
	_save_screenshot(base + "_5.png")            # corpse sunk away; survivors idle
	if _anim_panel != null:                      # the F10 browser renders over the scene
		_anim_panel.toggle()
		await get_tree().create_timer(0.3).timeout
		_save_screenshot(base + "_6.png")
		_anim_panel.toggle()
	if _talk != null:                            # the Civ 5-style talk scene, both portrait paths
		_talk.open("rpg-lira", "Lira", _model_path_for("rpg-lira"))
		_talk.show_line("Lira", "Stick close — the dark down here has teeth, and it knows our names.", "rpg-lira", _model_path_for("rpg-lira"))
		await get_tree().create_timer(0.9).timeout
		_save_screenshot(base + "_7.png")        # painted-art path (Lira has placeholder art)
		_talk.close()
		_talk.open("player", "You", _model_path_for("player"))
		_talk.show_line("You", "Testing the live bust: no painted art, so the world model takes the stage.", "player", _model_path_for("player"))
		await get_tree().create_timer(0.9).timeout
		_save_screenshot(base + "_8.png")        # live 3D bust path (knight has no painted art)
		_talk.close()
	_save_screenshot(shot)


func _save_screenshot(path: String) -> void:
	var img := get_viewport().get_texture().get_image()
	if img != null:
		img.save_png(path)
		if _hud != null:
			_hud.log_line("[screenshot saved]")


# -- Net signal handlers ------------------------------------------------------

var _link_dropped := false   # so we can tell a reconnect from the first connect

## Slice/seed are env-overridable (RPG_SLICE / RPG_SEED, mirroring net.gd's RPG_WS_URL) so
## emberdeep — or any future slice — is reachable from this client without editing code.
func _slice() -> String:
	var s := OS.get_environment("RPG_SLICE")
	return s if s != "" else "vault"

func _seed() -> int:
	var s := OS.get_environment("RPG_SEED")
	return int(s) if s.is_valid_int() else 1337

func _on_link_status(state: String) -> void:
	# Net does NOT auto-start; main kicks off the game once the link is open. `resume=true`
	# continues the saved WORLD for this slice+seed (minds persist on their own) — including
	# straight through a reconnect, so a dropped link no longer resets the expedition. N starts over.
	if state == "open":
		if not _started:
			_started = true
			if _link_dropped and _hud != null:
				_hud.log_line("— link restored — picking up where you left off —")
			_link_dropped = false
			if _world != null:
				_world.set_slice(_slice())   # biome palette (terrain sprites + tint)
			Net.start_game(_slice(), _seed(), true)
	elif state == "closed" or state == "error":
		# Only a session that had actually STARTED counts as a drop — initial connect failures
		# retry quietly (no spurious 'link restored' on the first success).
		if _started:
			_link_dropped = true
			if _hud != null:
				_hud.log_line("— connection lost — reconnecting… —")
		_started = false


func _on_snapshot(s: Dictionary) -> void:
	if typeof(s) != TYPE_DICTIONARY:
		return
	_snapshot = s
	if _world != null:
		_world.render(s)
	if _hud != null:
		_hud.render(s)


func _on_game_event(ev: Dictionary) -> void:
	if typeof(ev) != TYPE_DICTIONARY:
		return
	if _hud != null:
		_hud.log_event(ev)
	var t := str(ev.get("type", ""))
	# The route the player actually walked this action — the world animates the walk along it
	# (the snapshot alone only carries the final position, which read as teleporting).
	if t == "path" and _world != null and _world.has_method("follow_path"):
		_world.follow_path(str(ev.get("entity", "player")), ev.get("tiles", []))
	# Speech card: the personable face of a spoken line — portrait + name + typewriter reveal.
	# Only the QUOTED speech is shown (stage directions are never player-visible text).
	if t == "dialogue":
		var line := str(ev.get("speech", ""))
		if line.strip_edges() == "":
			line = str(ev.get("text", ""))
		var slug := str(ev.get("slug", ""))
		# While the talk scene is up, lines take the STAGE (whole portrait / live bust);
		# otherwise the compact speech card handles them (ambient lines, walk-by grants).
		_voice_muted = false                       # a NEW line always plays (dismissal muted the OLD one)
		if _talk != null and _talk.is_open():
			_talk.show_line(str(ev.get("npc", "")), line, slug, _model_path_for(slug))
		elif _speech != null:
			_speech.show_line(str(ev.get("npc", "")), line, slug)
		# The line's stage business (mind-authored, never shown as text) is PERFORMED: the
		# speaker turns to you and acts it out — sneaking, crouching, drawing steel...
		if _world != null and _world.has_method("act_direction"):
			_world.act_direction(slug, str(ev.get("action", "")))
	# Combat tearing into a conversation ends the audience — the stage clears immediately.
	if t == "mode_changed" and str(ev.get("mode", "")) == "combat" and _talk != null:
		_talk.close()
	# Dialogue TEXT surfaces immediately; the line's audio arrives as a follow-up "voice" event
	# and queues below. (Dialogue-attached audio kept as a fallback path.)
	if (t == "voice" or t == "dialogue") and ev.has("audio_b64"):
		_play_voice(str(ev.get("audio_b64", "")), int(ev.get("rate", 24000)))
	# Semantic sound hints (combat beats, loot, doors, drinking, resting...) — the server tags,
	# we play. The SAME hints drive visible acting in the world (lunges, dodges, cheers, the
	# party sitting down to rest): every sfx-tagged event is forwarded; unknown keys no-op.
	var data = ev.get("data", {})
	if typeof(data) == TYPE_DICTIONARY and data.has("sfx"):
		_play_sfx(str(data["sfx"]))
		if _world != null:
			_world.combat_fx(data)


## Streamed voice playback: every arriving chunk's s16le PCM is converted to frames and appended
## to `_pending`; _process feeds the generator's ring buffer as space frees. Arrival order IS
## playback order (the server streams one line at a time), chunks are gapless, and a network gap
## just reads as a breath of silence — never a click or a cut-off line.
var _pending := PackedVector2Array()
var _voice_playback: AudioStreamGeneratorPlayback = null
var _voice_rate := 24000              # current generator mix rate; the protocol carries `rate` per message
var _voice_buf_frames := 0            # the generator ring's true capacity, measured while empty
var _amp_chunks: Array = []           # ~80ms amplitude windows [{end: abs frame idx, amp}] awaiting playback
var _pushed_frames := 0               # total frames ever pushed into the ring (playhead anchor)

## Dismissing a conversation SILENCES it (owner feedback 2026-07-09): clicking out means
## "I'm done listening." Stops playback, drops everything queued, and mutes late-arriving
## chunks of the SAME line (the server streams per line; the next dialogue event unmutes).
var _voice_muted := false

func _stop_voice() -> void:
	if _voice == null:
		return
	_voice.stop()
	var gen := AudioStreamGenerator.new()
	gen.mix_rate = float(_voice_rate)
	gen.buffer_length = 4.0
	_voice.stream = gen
	_voice_playback = null
	_voice_buf_frames = 0
	_pending = PackedVector2Array()
	_amp_chunks = []
	_pushed_frames = 0
	_voice_tail = 0.0
	_voice_muted = true


func _play_voice(b64: String, rate: int) -> void:
	if b64 == "" or _voice == null or _voice_muted:
		return
	# The protocol deliberately carries `rate` per message; if it changes, rebuild the
	# generator to match (a mismatched mix_rate would play every line pitch-shifted).
	if rate > 0 and rate != _voice_rate:
		_voice.stop()
		var gen := AudioStreamGenerator.new()
		gen.mix_rate = float(rate)
		gen.buffer_length = 4.0
		_voice.stream = gen
		_pending = PackedVector2Array()
		_voice_playback = null
		_voice_buf_frames = 0
		_voice_rate = rate
		_amp_chunks = []
		_pushed_frames = 0
	var pcm := Marshalls.base64_to_raw(b64)
	@warning_ignore("integer_division")
	var n := pcm.size() / 2
	if n <= 0:
		return
	# s16le mono -> float stereo frames (StreamPeerBuffer.get_16 = signed little-endian).
	var spb := StreamPeerBuffer.new()
	spb.data_array = pcm
	var frames := PackedVector2Array()
	frames.resize(n)
	for i in n:
		var f := float(spb.get_16()) / 32768.0
		frames[i] = Vector2(f, f)
	_pending.append_array(frames)


func _process(_delta: float) -> void:
	_poll_held_movement(_delta)
	# Speech-card glow: "speaking" = audio frames still queued or recently pushed. The generator
	# player itself never stops, so track our own tail: seconds still occupied in the generator
	# ring after each push (see below) plus a short linger; _pending covers the not-yet-pushed rest.
	if _speech != null:
		var audible := not _pending.is_empty() or (_voice_tail > 0.0)
		_speech.set_speaking(audible)
	if _voice_tail > 0.0:
		_voice_tail = maxf(0.0, _voice_tail - _delta)
	# Voice PLAYHEAD amplitude -> the talk scene's mouth/motion. Playhead = frames pushed minus
	# frames still queued in the ring, so the level tracks what's AUDIBLE right now, not what
	# just arrived (the ring buffers up to 4s ahead — feeding arrival amplitude would flap the
	# mouth seconds early).
	var level := 0.0
	if _voice_playback != null and _voice_tail > 0.0:
		var capn := _voice_buf_frames if _voice_buf_frames > 0 else int(4.0 * _voice_rate)
		var played := _pushed_frames - (capn - _voice_playback.get_frames_available())
		while _amp_chunks.size() > 0 and int(_amp_chunks[0]["end"]) <= played:
			_amp_chunks.pop_front()
		if not _amp_chunks.is_empty():
			level = float(_amp_chunks[0]["amp"])
	if _talk != null:
		_talk.set_level(level)
	if _voice == null or _pending.is_empty():
		return
	if not _voice.playing:
		_voice.play()                               # lazy-start; playback object exists after play()
		_voice_playback = _voice.get_stream_playback()
		if _voice_playback != null:
			# An empty ring's free space IS its capacity (Godot rounds buffer_length * mix_rate
			# up to a power of two internally, so measure rather than assume).
			_voice_buf_frames = _voice_playback.get_frames_available()
	if _voice_playback == null:
		return
	var avail := _voice_playback.get_frames_available()
	if avail <= 0:
		return
	var take: int = mini(avail, _pending.size())
	_voice_playback.push_buffer(_pending.slice(0, take))
	# ~80ms amplitude windows over the pushed block — the playhead lookup above consumes these
	var win := maxi(1, int(_voice_rate / 12.0))
	var i := 0
	while i < take:
		var n2: int = mini(win, take - i)
		var s := 0.0
		for j in range(i, i + n2):
			s += absf(_pending[j].x)
		_amp_chunks.append({"end": _pushed_frames + i + n2,
			"amp": clampf(s / float(n2) * 4.0, 0.0, 1.0)})
		i += n2
	_pushed_frames += take
	_pending = _pending.slice(take)
	# The glow tail covers EVERYTHING still queued in the generator ring (up to 4s), not just
	# this push: occupied frames = capacity - free space after the push.
	var cap := _voice_buf_frames if _voice_buf_frames > 0 else int(4.0 * _voice_rate)
	var occupied := float(cap - _voice_playback.get_frames_available()) / float(_voice_rate)
	_voice_tail = maxf(occupied, 0.0) + 0.25


## Seconds of already-pushed audio still (approximately) sounding — drives the speaking glow.
var _voice_tail := 0.0


# -- Audio: original synthesized SFX + per-slice ambience ----------------------
## Events carry semantic hints (data.sfx = "hit"/"loot"/...); the client maps them to the
## generated chip-style samples (assets/sfx, tools/gen_rpg_sfx.py — all original, no licenses).
## A small player pool lets overlapping hits ring without cutting each other off. Ambience is a
## slice-keyed 12s loop (loop-crafted tails) restarted on `finished`.

var _sfx: Dictionary = {}                 # key -> AudioStream
var _sfx_pool: Array = []                 # rotating AudioStreamPlayers
var _sfx_next := 0
var _ambience: AudioStreamPlayer = null

func _setup_audio() -> void:
	for key in ["hit", "crit", "miss", "down", "dead", "victory", "levelup", "loot",
			"drink", "door", "alarm", "save"]:
		var path := "res://assets/sfx/%s.wav" % key
		if ResourceLoader.exists(path):
			_sfx[key] = load(path)
	for i in 4:
		var p := AudioStreamPlayer.new()
		p.volume_db = -8.0
		add_child(p)
		_sfx_pool.append(p)
	var amb_path := "res://assets/sfx/amb_%s.wav" % _slice()
	if not ResourceLoader.exists(amb_path):
		amb_path = "res://assets/sfx/amb_vault.wav"
	if ResourceLoader.exists(amb_path):
		_ambience = AudioStreamPlayer.new()
		_ambience.stream = load(amb_path)
		_ambience.volume_db = -18.0
		add_child(_ambience)
		_ambience.finished.connect(_ambience.play)   # seamless-enough loop (tails are loop-crafted)
		_ambience.play()

func _play_sfx(key: String) -> void:
	if not _sfx.has(key) or _sfx_pool.is_empty():
		return
	var p: AudioStreamPlayer = _sfx_pool[_sfx_next % _sfx_pool.size()]
	_sfx_next += 1
	p.stream = _sfx[key]
	p.play()


# -- Input routing ------------------------------------------------------------

func _unhandled_input(event: InputEvent) -> void:
	# While the Dialogue overlay is up, it owns all input (text entry). Never let
	# movement keys leak through to the world.
	if _dialogue != null and _dialogue.is_open():
		return
	# Click-to-move: left-click a tile to walk toward it (in combat: step/attack toward it).
	# A click on an UNEXPLORED tile is rejected with feedback (the server enforces the same rule
	# authoritatively — this check just keeps the refusal from being silent).
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if _speech != null and _speech.visible:
			_speech.dismiss()   # a map click means the player moved on — card AND voice stop
			_stop_voice()
		if _world != null:
			var t: Vector2i = _world.tile_at_mouse()
			var key := str(t.x) + "," + str(t.y)
			var explored = _snapshot.get("explored", [])
			if typeof(explored) == TYPE_ARRAY and not explored.has(key):
				if _hud != null:
					_hud.log_line("Too dark to see there.")
			elif not _try_click_talk(t):
				# not a person (or mid-combat): the click is a movement/attack order
				Net.send_action("move_to", {"tx": t.x, "ty": t.y})
				if _world.has_method("mark_destination"):
					_world.mark_destination(t)   # click feedback: the walk belongs to YOUR order
		get_viewport().set_input_as_handled()
		return
	# Mouse-wheel camera dolly (3D view only; the 2D view has no zoom_step).
	if event is InputEventMouseButton and event.pressed \
			and (event.button_index == MOUSE_BUTTON_WHEEL_UP or event.button_index == MOUSE_BUTTON_WHEEL_DOWN):
		if _world != null and _world.has_method("zoom_step"):
			_world.zoom_step(-0.1 if event.button_index == MOUSE_BUTTON_WHEEL_UP else 0.1)
			get_viewport().set_input_as_handled()
		return
	if not (event is InputEventKey and event.pressed and not event.echo):
		return

	var handled: bool = true

	match event.keycode:
		KEY_UP, KEY_W:
			_send_move(0, -1)
		KEY_DOWN, KEY_S:
			_send_move(0, 1)
		KEY_LEFT, KEY_A:
			_send_move(-1, 0)
		KEY_RIGHT, KEY_D:
			_send_move(1, 0)
		KEY_PERIOD, KEY_SPACE:
			# "wait" — in combat this ENDS the player's turn; in exploration it passes time.
			Net.send_action("wait")
		KEY_L:
			Net.send_action("look")
		KEY_G:
			Net.send_action("toggle_enemy_hp")
		KEY_T:
			_open_talk_on_nearest()
		KEY_X:
			if _dialogue != null:
				_dialogue.open_do()
		KEY_R:
			_recruit_nearest()
		KEY_F:
			_help_nearest()
		KEY_H:
			# Quaff a healing draught (first drinkable in the pack). In combat this spends the action.
			Net.send_action("use")
		KEY_Z:
			# Camp rest: party heals a hit die each, real time passes, and the noise can draw danger.
			Net.send_action("rest")
		KEY_F1:
			if _hud != null:
				_hud.toggle_help()
		KEY_F10:
			# dev animation browser: click through every clip on any live entity
			if _anim_panel != null:
				_anim_panel.toggle()
		KEY_F12:
			_save_screenshot(OS.get_environment("RPG_SHOT") if OS.get_environment("RPG_SHOT") != "" else "user://rpg_shot.png")
		KEY_N:
			# New expedition: restart THIS slice+seed fresh (resume=false overwrites the save on
			# the next autosave). Minds keep their memories — the world resets, the people don't.
			if _hud != null:
				_hud.log_line("— starting a fresh expedition —")
			_greeted.clear()
			if _talk != null:
				_talk.close()
			if _world != null:
				_world.set_slice(_slice())   # also drops stale movement tweens (fresh map re-uses ids)
			Net.start_game(_slice(), _seed(), false)
		_:
			handled = false

	if handled:
		get_viewport().set_input_as_handled()


# -- Held-key movement --------------------------------------------------------
# One press = one step (via _unhandled_input); HOLDING a movement key keeps walking (owner
# feedback 2026-07-08). _process polls the held direction and sends the next step just before the
# current glide lands, so held movement chains into one continuous walk. Pacing is the glide
# itself: at most one step is in flight beyond what's animating, so releasing the key stops within
# a tile.

var _move_cd := 0.0

func _send_move(dx: int, dy: int) -> void:
	Net.send_action("move", {"dx": dx, "dy": dy})
	_move_cd = 0.10


func _held_move_dir() -> Vector2i:
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
		return Vector2i(0, -1)
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
		return Vector2i(0, 1)
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
		return Vector2i(-1, 0)
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
		return Vector2i(1, 0)
	return Vector2i.ZERO


func _poll_held_movement(delta: float) -> void:
	_move_cd = maxf(0.0, _move_cd - delta)
	if _move_cd > 0.0 or _dialogue != null and _dialogue.is_open():
		return
	# Input.is_key_pressed is GLOBAL: typing "w" into a focused text field (the anim browser's
	# filter, any future UI) must not also walk the player.
	if get_viewport().gui_get_focus_owner() != null:
		return
	var dir := _held_move_dir()
	if dir == Vector2i.ZERO:
		return
	var remaining := 0.0
	if _world != null and _world.has_method("player_glide_remaining"):
		remaining = _world.player_glide_remaining()
	# Send the next step EARLY (over half a tile out): its route concatenates onto the current
	# glide before it lands, so held-key walking is one continuous motion with no seam per tile.
	if remaining <= 0.6:
		_send_move(dir.x, dir.y)


# -- Interaction helpers ------------------------------------------------------

## Instant feedback on submit: echo the player's line and show a thinking beat, so the
## LLM round-trip reads as the character considering rather than a frozen UI. In COMBAT the
## beat is suppressed — the server rejects mid-fight talk ("No time for that"), so promising
## that someone is considering would be a lie.
func _on_dialogue_submitted(mode: String, target_name: String, text: String) -> void:
	if _hud == null:
		return
	if mode == "talk":
		_hud.log_line('You: "%s"' % text)
		if str(_snapshot.get("mode", "")) != "combat":
			var who := target_name if target_name != "" else "They"
			_hud.log_line("%s considers…" % who)
	else:
		_hud.log_line("You try to: %s" % text)


## Click a PERSON to talk to them (owner feedback 2026-07-09 — T-nearest wasn't discoverable).
## Within reach -> the conversation opens on the spot; farther -> walk toward them with a hint.
## Combat clicks stay combat orders. Returns true when the click was handled as social.
func _try_click_talk(t: Vector2i) -> bool:
	if str(_snapshot.get("mode", "")) == "combat":
		return false
	var ent := _entity_at(t)
	if ent.is_empty() or not (str(ent.get("kind", "")) in ["npc", "follower"]):
		return false
	var id := str(ent.get("id", ""))
	var who := str(ent.get("name", ""))
	var pp = _snapshot.get("player", {}).get("pos", [0, 0])
	var dist: int = absi(int(pp[0]) - t.x) + absi(int(pp[1]) - t.y)
	if dist <= 2:
		if _dialogue != null:
			_dialogue.open_talk(id, who)
		if _talk != null:
			_talk.open(id, who, _model_path_for(id))
		_maybe_greet(id, who)
	else:
		Net.send_action("move_to", {"tx": t.x, "ty": t.y})
		if _world != null and _world.has_method("mark_destination"):
			_world.mark_destination(t)
		if _hud != null:
			_hud.log_line("You approach %s — click them again to talk." % who)
	return true


func _entity_at(t: Vector2i) -> Dictionary:
	var ents = _snapshot.get("entities", [])
	if typeof(ents) != TYPE_ARRAY:
		return {}
	for e in ents:
		if typeof(e) != TYPE_DICTIONARY:
			continue
		var pos = e.get("pos", null)
		if typeof(pos) == TYPE_ARRAY and pos.size() >= 2 \
				and int(pos[0]) == t.x and int(pos[1]) == t.y:
			return e
	return {}


func _model_path_for(slug: String) -> String:
	if _world != null and _world.has_method("model_path_for"):
		return _world.model_path_for(slug)
	return ""


func _open_talk_on_nearest() -> void:
	var target: Dictionary = _nearest_interactable()
	if target.is_empty():
		_log_no_one()
		return
	var id := str(target.get("id", ""))
	var who := str(target.get("name", ""))
	if _dialogue != null:
		_dialogue.open_talk(id, who)
	if _talk != null:                     # the conversation takes the stage
		_talk.open(id, who, _model_path_for(id))
	_maybe_greet(id, who)


## The NPC speaks FIRST when a conversation opens: approaching someone is a social event they
## react to in character. Once per person per expedition (repeat opens skip straight to input).
var _greeted := {}

func _maybe_greet(id: String, who: String) -> void:
	if id == "" or _greeted.has(id):
		return
	_greeted[id] = true
	Net.send_action("greet", {"target_id": id})
	if _hud != null:
		_hud.log_line("%s turns to you…" % (who if who != "" else "They"))


func _recruit_nearest() -> void:
	var target: Dictionary = _nearest_interactable()
	if target.is_empty():
		_log_no_one()
		return
	Net.recruit(str(target.get("id", "")))


func _help_nearest() -> void:
	var target: Dictionary = _nearest_interactable()
	if target.is_empty():
		_log_no_one()
		return
	var who: String = str(target.get("name", ""))
	if who.strip_edges() == "":
		who = "a stranger"
	var fact: String = "The traveler stepped in to help " + who + ", sharing supplies and asking nothing in return."
	Net.deed(fact, [str(target.get("id", ""))], 0.8)


func _log_no_one() -> void:
	if _hud != null:
		_hud.log_line("No one beside you.")


## Nearest interactable entity from the last snapshot: an entity whose kind is
## "npc" or "follower" and whose Manhattan distance to the player is <= 1. Returns
## the closest such entity, or {} if there is none beside the player.
func _nearest_interactable() -> Dictionary:
	if _snapshot.is_empty():
		return {}
	var player = _snapshot.get("player", {})
	if typeof(player) != TYPE_DICTIONARY:
		return {}
	var ppos = player.get("pos", null)
	if typeof(ppos) != TYPE_ARRAY or ppos.size() < 2:
		return {}
	var px: int = int(ppos[0])
	var py: int = int(ppos[1])

	var best: Dictionary = {}
	var best_dist: int = 2147483647
	var entities = _snapshot.get("entities", [])
	if typeof(entities) != TYPE_ARRAY:
		return {}
	for e in entities:
		if typeof(e) != TYPE_DICTIONARY:
			continue
		var kind: String = str(e.get("kind", ""))
		if kind != "npc" and kind != "follower":
			continue
		var epos = e.get("pos", null)
		if typeof(epos) != TYPE_ARRAY or epos.size() < 2:
			continue
		var dist: int = abs(int(epos[0]) - px) + abs(int(epos[1]) - py)
		if dist <= 1 and dist < best_dist:
			best_dist = dist
			best = e
	return best
