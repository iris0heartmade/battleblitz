extends Node
## GameState — autoload singleton caching the latest server snapshot.
##
## The Python backend is authoritative: all player actions POST to REST
## and the server replies via WebSocket `state.snapshot` /
## `event.delta` messages. This singleton holds the parsed snapshot
## and emits signals so the Board scene (or any HUD widget) can react.
##
## M0/M1 only uses a tiny subset (raw game dict + tile list) to drive
## MapLoader; M2 will wire the full protocol — see protocol/v1.py.

signal snapshot_received(snapshot: Dictionary)
signal tile_state_changed(tile_x: int, tile_y: int, new_state: Dictionary)
signal units_changed(units: Array)
signal current_player_changed(player_id)
signal phase_changed(phase: String)
signal connection_state_changed(connected: bool)

# Latest snapshot (parsed JSON dict from `state.snapshot.payload.game`).
# Empty until the first WS message arrives.
var latest_snapshot: Dictionary = {}

# Convenience accessors (filled in by `_ingest_snapshot`).
var game_summary: Dictionary = {}              # GameSummaryOut
var tiles: Array = []                          # Array[TileOut]
var players: Array = []                         # Array[PlayerOut]
var current_player_id: Variant = null           # int | null
var pending_claims: Array = []                  # Array[PendingClaimOut]
var co_states: Array = []                       # Array[PlayerCOStateOut]
var logs: Array = []                            # Array[ActionLogOut]
var phase: String = "player"                    # "player" | "ai" | "spectator" | "animating"

var is_connected: bool = false:
	set(value):
		if is_connected == value:
			return
		is_connected = value
		connection_state_changed.emit(value)


# ============================================================
# Public API used by NetworkClient (M2) and MapLoader (M1)
# ============================================================

## Replace the cached state with a fresh `state.snapshot` payload.
## `payload.game` follows the GameStateOut schema in schemas.py.
func ingest_snapshot(snapshot: Dictionary) -> void:
	latest_snapshot = snapshot
	game_summary = snapshot.get("game", {})
	tiles = snapshot.get("tiles", [])
	players = snapshot.get("players", [])
	current_player_id = snapshot.get("current_player_id", null)
	pending_claims = snapshot.get("pending_claims", [])
	co_states = snapshot.get("co_states", [])
	logs = snapshot.get("logs", [])
	phase = game_summary.get("phase", "player")
	snapshot_received.emit(snapshot)
	units_changed.emit(_flatten_units(players))
	current_player_changed.emit(current_player_id)
	phase_changed.emit(phase)

## Apply a single `event.delta` (forwarded as a GameEvent dict from
## protocol/v1.py). The full event-handler table lands in M2 — for M1
## we just refresh the affected tile.
func ingest_event(event: Dictionary) -> void:
	# Tile-level effects (move, claim, capture) all touch the unit's
	# new tile; re-pulling the affected tile from the latest snapshot
	# is enough to drive the basic M1 highlights.
	var tx: int = event.get("to_x", -1)
	var ty: int = event.get("to_y", -1)
	if tx >= 0 and ty >= 0:
		for t in tiles:
			if t.get("x") == tx and t.get("y") == ty:
				tile_state_changed.emit(tx, ty, t)
				break


# ============================================================
# Internal helpers
# ============================================================

func _flatten_units(players_in: Array) -> Array:
	var out: Array = []
	for p in players_in:
		if not p is Dictionary:
			continue
		var units: Variant = p.get("units", [])
		if units is Array:
			for u in units:
				if u is Dictionary:
					out.append(u)
	return out
