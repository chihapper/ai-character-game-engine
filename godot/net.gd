extends Node
## Net — the WebSocket lifecycle autoload (global `Net`).
##
## A THIN transport layer over the Python RPG core. Owns the WebSocket, parses JSON,
## and re-emits server messages as Godot signals. Contains NO game logic, NO UI, NO drawing.
##
## Wire protocol (JSON objects; "t" = type). A server batch always ENDS with a snapshot.
##   Client->Server: start / action / deed / state
##   Server->Client: snapshot / event / error
##
## Signals (the only surface other modules bind to):
##   snapshot(snap: Dictionary)   — a StateSnapshot
##   game_event(ev: Dictionary)   — a GameEvent
##   link_status(state: String)   — "connecting" | "open" | "closed" | "error"
##
## Does NOT auto-start the game: main.gd calls start_game() once link_status == "open".

signal snapshot(snap: Dictionary)
signal game_event(ev: Dictionary)
signal link_status(state: String)

const DEFAULT_URL := "ws://127.0.0.1:8787"

## A voiced dialogue event carries the WHOLE utterance as base64 PCM (24 kHz s16le) in ONE text
## frame — easily hundreds of KB. Godot's WebSocketPeer default inbound buffer is 64 KB, and an
## oversized frame doesn't just drop: the peer CLOSES the connection with 1009 ("message too big"),
## which killed the first voiced reply in live trial. 8 MiB ≈ two minutes of speech — ample.
const INBOUND_BUFFER := 8 * 1024 * 1024

## Seconds between reconnect attempts after the link drops. A bare WebSocketPeer never reconnects
## by itself; without this, one dropped frame permanently killed the session (silent dead socket).
const RETRY_DELAY := 2.0

var _url := DEFAULT_URL
var _ws := WebSocketPeer.new()
var _last_state: String = ""
var _connect_ok := false
var _retry_accum := 0.0


func _ready() -> void:
	# Optional override so the same client can point at a LAN host (RPG_WS_URL=ws://host:port).
	var env_url := OS.get_environment("RPG_WS_URL")
	if env_url != "":
		_url = env_url
	_connect_ws()


func _connect_ws() -> void:
	_ws = WebSocketPeer.new()
	_ws.inbound_buffer_size = INBOUND_BUFFER   # MUST be set before connect_to_url
	var err := _ws.connect_to_url(_url)
	if err != OK:
		_connect_ok = false
		push_warning("Net: connect_to_url(%s) failed: %d" % [_url, err])
		_set_link_status("error")
	else:
		_connect_ok = true
		_set_link_status("connecting")


func _process(delta: float) -> void:
	if not _connect_ok:
		# Initial connect failed (e.g. server not up yet) — keep retrying on the same cadence.
		_retry_accum += delta
		if _retry_accum >= RETRY_DELAY:
			_retry_accum = 0.0
			_connect_ws()
		return
	_ws.poll()
	var rs := _ws.get_ready_state()
	match rs:
		WebSocketPeer.STATE_CONNECTING:
			_set_link_status("connecting")
		WebSocketPeer.STATE_OPEN:
			_set_link_status("open")
			while _ws.get_available_packet_count() > 0:
				var pkt := _ws.get_packet()
				_handle_packet(pkt.get_string_from_utf8())
		WebSocketPeer.STATE_CLOSING:
			# Draining — keep polling; a CLOSED state will follow.
			pass
		WebSocketPeer.STATE_CLOSED:
			# Dropped. Surface it, then reconnect after a short delay — main.gd sees the
			# "closed" -> "open" transition and starts a fresh game on the new connection
			# (the server is one-game-per-connection).
			_set_link_status("closed")
			_retry_accum += delta
			if _retry_accum >= RETRY_DELAY:
				_retry_accum = 0.0
				_connect_ws()


# --- Public API (see the shared contract) --------------------------------------------------

func start_game(slice: String, seed: int, resume: bool = false, fresh_minds: bool = false) -> void:
	# resume=true continues the saved WORLD for this slice+seed if the server has one
	# (fresh game otherwise); minds persist on their own. fresh_minds=true (dev reset,
	# Shift+N) ALSO wipes the cast's memories — a true first meeting.
	_send({"t": "start", "slice": slice, "seed": seed, "resume": resume, "fresh_minds": fresh_minds})


func send_action(kind: String, fields: Dictionary = {}) -> void:
	var action := {"kind": kind}
	for k in fields.keys():
		action[k] = fields[k]
	_send({"t": "action", "action": action})


func talk(target_id: String, text: String) -> void:
	send_action("talk", {"target_id": target_id, "text": text})


func do_action(text: String) -> void:
	send_action("do", {"text": text})


func recruit(target_id: String) -> void:
	send_action("recruit", {"target_id": target_id})


func deed(fact: String, targets: Array, magnitude: float = 0.8) -> void:
	_send({
		"t": "deed",
		"fact": fact,
		"targets": targets,
		"player_role": "caused",
		"magnitude": magnitude,
	})


func request_state() -> void:
	_send({"t": "state"})


# --- Internals -----------------------------------------------------------------------------

func _send(d: Dictionary) -> void:
	if not _connect_ok:
		return
	if _ws.get_ready_state() != WebSocketPeer.STATE_OPEN:
		# Not connected (yet / anymore) — drop rather than crash.
		return
	var err := _ws.send_text(JSON.stringify(d))
	if err != OK:
		push_warning("Net: send_text failed: %d" % err)


func _handle_packet(text: String) -> void:
	if text == "":
		return
	var msg = JSON.parse_string(text)
	if typeof(msg) != TYPE_DICTIONARY:
		push_warning("Net: dropped non-dict packet: %s" % text)
		return
	var t := str(msg.get("t", ""))
	match t:
		"snapshot":
			var snap = msg.get("snapshot", {})
			if typeof(snap) == TYPE_DICTIONARY:
				snapshot.emit(snap)
		"event":
			var ev = msg.get("event", {})
			if typeof(ev) == TYPE_DICTIONARY:
				game_event.emit(ev)
		"voice":
			# A dialogue line's audio, arriving AFTER its text (synthesis runs server-side in the
			# background so the world never freezes on TTS). Re-emit as a game event; main.gd
			# queues it for playback in arrival (= spoken) order.
			game_event.emit({"type": "voice", "npc": str(msg.get("npc", "")),
				"slug": str(msg.get("slug", "")), "audio_b64": str(msg.get("audio_b64", "")),
				"rate": int(msg.get("rate", 24000))})
		"error":
			# Surface server-side failures IN the game log (hud logs any event with a `text`) —
			# a silent push_warning left live failures invisible to the player.
			push_warning("Net: server error: %s" % str(msg.get("message", "")))
			game_event.emit({"type": "error", "text": "[server error] " + str(msg.get("message", ""))})
		_:
			# Unknown message type — ignore, forward nothing.
			pass


func _set_link_status(state: String) -> void:
	if state == _last_state:
		return
	_last_state = state
	link_status.emit(state)


func _exit_tree() -> void:
	# Autoloads are freed on app quit; close the socket politely so the Python
	# server sees a clean disconnect rather than a dropped TCP connection.
	if _connect_ok and _ws.get_ready_state() != WebSocketPeer.STATE_CLOSED:
		_ws.close()
