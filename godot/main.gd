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

var _world: Node2D
var _hud: CanvasLayer
var _dialogue: CanvasLayer
var _voice: AudioStreamPlayer   # plays Hume-voiced NPC lines (PCM streamed from the server)

## Last snapshot received from the server; drives the nearest-interactable helper.
var _snapshot: Dictionary = {}

## Guards so we only start the game once per open link.
var _started: bool = false


func _ready() -> void:
	# Instance the three modules by loading their scripts and attaching them to fresh
	# nodes of the type each one `extends`. (World=Node2D, Hud/Dialogue=CanvasLayer.)
	_world = Node2D.new()
	_world.name = "World"
	_world.set_script(load("res://world.gd"))
	add_child(_world)

	_hud = CanvasLayer.new()
	_hud.name = "Hud"
	_hud.set_script(load("res://hud.gd"))
	add_child(_hud)

	_dialogue = CanvasLayer.new()
	_dialogue.name = "Dialogue"
	_dialogue.set_script(load("res://dialogue.gd"))
	add_child(_dialogue)

	_voice = AudioStreamPlayer.new()
	_voice.name = "Voice"
	add_child(_voice)
	# Voice is a CONTINUOUS generator stream, not per-clip WAVs: the server STREAMS each line's
	# PCM in ~0.5s+ chunks as Hume synthesizes it, and we push frames into one generator so chunks
	# butt together gaplessly (per-clip playback had an audible seam at every chunk boundary).
	var gen := AudioStreamGenerator.new()
	gen.mix_rate = 24000.0            # the wire's fixed PCM rate (s16le mono, AUDIO_SAMPLE_RATE)
	gen.buffer_length = 4.0           # generous ring buffer; _process tops it up from _pending
	_voice.stream = gen

	# Wire the Net autoload. `Net` is a global autoload (extends Node) that owns the
	# WebSocket; it emits these three signals and exposes the action methods we call.
	Net.snapshot.connect(_on_snapshot)
	Net.game_event.connect(_on_game_event)
	Net.link_status.connect(_on_link_status)


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
	# Dialogue TEXT surfaces in the HUD log immediately; the line's audio arrives as a follow-up
	# "voice" event and queues below. (Dialogue-attached audio kept as a fallback path.)
	var t := str(ev.get("type", ""))
	if (t == "voice" or t == "dialogue") and ev.has("audio_b64"):
		_play_voice(str(ev.get("audio_b64", "")), int(ev.get("rate", 24000)))


## Streamed voice playback: every arriving chunk's s16le PCM is converted to frames and appended
## to `_pending`; _process feeds the generator's ring buffer as space frees. Arrival order IS
## playback order (the server streams one line at a time), chunks are gapless, and a network gap
## just reads as a breath of silence — never a click or a cut-off line.
var _pending := PackedVector2Array()
var _voice_playback: AudioStreamGeneratorPlayback = null

func _play_voice(b64: String, _rate: int) -> void:
	if b64 == "" or _voice == null:
		return
	var pcm := Marshalls.base64_to_raw(b64)
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
	if _voice == null or _pending.is_empty():
		return
	if not _voice.playing:
		_voice.play()                               # lazy-start; playback object exists after play()
		_voice_playback = _voice.get_stream_playback()
	if _voice_playback == null:
		return
	var avail := _voice_playback.get_frames_available()
	if avail <= 0:
		return
	var take: int = mini(avail, _pending.size())
	_voice_playback.push_buffer(_pending.slice(0, take))
	_pending = _pending.slice(take)


# -- Input routing ------------------------------------------------------------

func _unhandled_input(event: InputEvent) -> void:
	# While the Dialogue overlay is up, it owns all input (text entry). Never let
	# movement keys leak through to the world.
	if _dialogue != null and _dialogue.is_open():
		return
	# Click-to-move: left-click a tile to walk toward it (in combat: step/attack toward it).
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if _world != null:
			var t: Vector2i = _world.tile_at_mouse()
			Net.send_action("move_to", {"tx": t.x, "ty": t.y})
		get_viewport().set_input_as_handled()
		return
	if not (event is InputEventKey and event.pressed and not event.echo):
		return

	var handled: bool = true

	match event.keycode:
		KEY_UP, KEY_W:
			Net.send_action("move", {"dx": 0, "dy": -1})
		KEY_DOWN, KEY_S:
			Net.send_action("move", {"dx": 0, "dy": 1})
		KEY_LEFT, KEY_A:
			Net.send_action("move", {"dx": -1, "dy": 0})
		KEY_RIGHT, KEY_D:
			Net.send_action("move", {"dx": 1, "dy": 0})
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
		KEY_N:
			# New expedition: restart THIS slice+seed fresh (resume=false overwrites the save on
			# the next autosave). Minds keep their memories — the world resets, the people don't.
			if _hud != null:
				_hud.log_line("— starting a fresh expedition —")
			Net.start_game(_slice(), _seed(), false)
		_:
			handled = false

	if handled:
		get_viewport().set_input_as_handled()


# -- Interaction helpers ------------------------------------------------------

func _open_talk_on_nearest() -> void:
	var target: Dictionary = _nearest_interactable()
	if target.is_empty():
		_log_no_one()
		return
	if _dialogue != null:
		_dialogue.open_talk(str(target.get("id", "")), str(target.get("name", "")))


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
