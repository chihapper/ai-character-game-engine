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

const URL := "ws://127.0.0.1:8787"

var _ws := WebSocketPeer.new()
var _last_state: String = ""
var _connect_ok := false
var _closed_final := false   # latch once the socket reaches CLOSED so we stop polling a dead peer.


func _ready() -> void:
	var err := _ws.connect_to_url(URL)
	if err != OK:
		_connect_ok = false
		push_warning("Net: connect_to_url(%s) failed: %d" % [URL, err])
		_set_link_status("error")
	else:
		_connect_ok = true
		_set_link_status("connecting")


func _process(_delta: float) -> void:
	if not _connect_ok or _closed_final:
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
			# Terminal for this peer. Emit once, then stop polling forever
			# (a bare WebSocketPeer does not auto-reconnect).
			_closed_final = true
			_set_link_status("closed")


# --- Public API (see the shared contract) --------------------------------------------------

func start_game(slice: String, seed: int) -> void:
	_send({"t": "start", "slice": slice, "seed": seed})


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
	if not _connect_ok or _closed_final:
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
		"error":
			push_warning("Net: server error: %s" % str(msg.get("message", "")))
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
