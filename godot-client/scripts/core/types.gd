class_name BBTypes
extends RefCounted
## BBTypes — wire-format constants + helpers mirroring the Pydantic
## `*Out` schemas in `game/app/schemas.py`.
##
## The Godot client holds the *Out payloads as plain Dictionaries (since
## they come straight from JSON). This file centralises:
##   1. The expected key set for each *Out type, so we can validate
##      payloads and catch schema drift early.
##   2. Helpers to extract typed values with safe defaults (e.g.
##      `unit_def(unit)` returning the int from `unit["def_"]`).
##   3. Constants for the 17 GameEvent types and the WS message types
##      defined in `protocol/v1.py`.
##
## If the Pydantic schema gains a new field, add the constant here
## and the helper (if any). Tests live in `tests/test_types.gd` (M2+).

# ============================================================
# TileOut
# ============================================================
const TILE_KEYS := ["x", "y", "terrain", "subtype", "owner_id", "occupied_unit_id"]

static func tile_terrain(tile: Dictionary) -> String:
	return String(tile.get("terrain", "plain"))

static func tile_subtype(tile: Dictionary) -> String:
	return String(tile.get("subtype", ""))

static func tile_is_castle(tile: Dictionary) -> bool:
	return tile_terrain(tile) == "castle" or tile_terrain(tile).begins_with("castle_")


# ============================================================
# UnitOut
# ============================================================
const UNIT_KEYS := [
	"id", "player_id", "unit_type", "name", "level", "exp",
	"hp", "max_hp", "atk", "def_", "matk", "mdef",
	"mov", "mp", "morale", "x", "y", "has_acted", "has_moved",
	"skills", "attack_range", "min_attack_range", "hero_id",
	# 通用 status effect (P+):list[dict],每项 type/remaining_turns/params 等
	"status_effects",
	# 过渡期字段(silence 迁移后会删除):沉默到该 turn 之前都算沉默中
	"silence_until_turn",
]

## The "def_" key is the int field stored as `def_` in the JSON
## because `def` is a Python keyword. DO NOT rename.
const UNIT_DEF_KEY := "def_"

static func unit_def(unit: Dictionary) -> int:
	return int(unit.get(UNIT_DEF_KEY, 0))

static func unit_mp_budget(unit: Dictionary) -> int:
	# `unit.mov` is the per-turn budget in MP; the engine stores
	# `unit.mp` (remaining) as a half-point integer. Movement
	# costs are stored ×2 in Config, so `mp * 2` is the budget
	# in cost-units (mp=4 → budget=8 → can move across 4 plains).
	return int(unit.get("mp", unit.get("mov", 0))) * 2

static func unit_skill_list(unit: Dictionary) -> Array:
	var raw: Variant = unit.get("skills", [])
	if raw is Array:
		return raw
	return []


# ============================================================
# PlayerOut
# ============================================================
const PLAYER_KEYS := [
	"id", "user_name", "color", "is_alive", "has_ended_turn", "seat",
	"is_ai", "agent_kind", "agent_personality", "gold",
	"team", "is_spectator", "units",
]

static func player_units(player: Dictionary) -> Array:
	var raw: Variant = player.get("units", [])
	if raw is Array:
		return raw
	return []


# ============================================================
# GameSummaryOut
# ============================================================
const GAME_SUMMARY_KEYS := [
	"id", "name", "status", "turn_number", "current_player_index",
	"map_seed", "map_preset", "map_biome", "phase", "win_condition",
	"win_reason", "capacity", "battle_config", "created_at",
]


# ============================================================
# PendingClaimOut
# ============================================================
const PENDING_CLAIM_KEYS := [
	"tile_id", "tile_x", "tile_y", "started_turn", "completes_turn",
	"turns_remaining", "total_turns", "target_player_id",
]

static func claim_progress(claim: Dictionary) -> float:
	var total: int = int(claim.get("total_turns", 1))
	if total <= 0:
		return 0.0
	var remaining: int = int(claim.get("turns_remaining", total))
	return clamp(1.0 - float(remaining) / float(total), 0.0, 1.0)


# ============================================================
# PlayerCOStateOut
# ============================================================
const PLAYER_CO_STATE_KEYS := [
	"player_id", "seat", "color", "commander_id",
	"stars_earned_total", "threshold", "power_cost",
	"meter", "is_power_active", "can_fire",
]


# ============================================================
# GameStateOut (the full snapshot)
# ============================================================
const GAME_STATE_KEYS := [
	"game", "tiles", "players", "current_player_id",
	"logs", "pending_claims", "co_states",
]


# ============================================================
# ActionLogOut
# ============================================================
const ACTION_LOG_KEYS := [
	"id", "turn_number", "player_id", "action_type",
	"description", "created_at",
]


# ============================================================
# GameEvent — `event.delta.payload` shape (17 types)
# ============================================================
const EVENT_TYPES := {
	"move": 0,
	"attack": 1,
	"kill": 2,
	"skill": 3,
	"wait": 4,
	"turn_end": 5,
	"round_end": 6,
	"match_start": 7,
	"match_end": 8,
	"castle_captured": 9,
	"level_up": 10,
	"low_hp_warning": 11,
	"comeback": 12,
	"victory_imminent": 13,
	"ai_step": 14,
	"auto_skip": 15,
	"error": 16,
}
const EVENT_IMPORTANCE := {
	# Mirrors `importance` field in GameEvent (protocol/v1.py).
	"kill": "critical",
	"castle_captured": "critical",
	"comeback": "critical",
	"victory_imminent": "critical",
	"match_end": "critical",
	"level_up": "important",
	"round_end": "important",
	"match_start": "important",
	"low_hp_warning": "important",
	"auto_skip": "important",
}

static func event_type_name(idx: int) -> String:
	for k in EVENT_TYPES:
		if EVENT_TYPES[k] == idx:
			return k
	return "unknown"

static func event_is_critical(event_type: String) -> bool:
	return EVENT_IMPORTANCE.get(event_type, "") == "critical"


# ============================================================
# WebSocket message types (protocol/v1.py)
# ============================================================
const WS_MSG_SERVER_HELLO := "server.hello"
const WS_MSG_STATE_SNAPSHOT := "state.snapshot"
const WS_MSG_EVENT_DELTA := "event.delta"
const WS_MSG_TURN_ADVANCE := "turn.advance"
const WS_MSG_SERVER_PONG := "server.pong"
const WS_MSG_COMMENTARY_TEXT := "commentary.text"
const WS_MSG_COMMENTARY_AUDIO := "commentary.audio"
const WS_MSG_ERROR := "error"

# === Error codes (ws_gateway.py ErrorCode) ===
const WS_ERROR_CODES := [
	"OUT_OF_MP", "OUT_OF_RANGE", "NOT_YOUR_TURN", "INVALID_TARGET",
	"GAME_FINISHED", "GAME_NOT_FOUND", "INTERNAL", "AUTH_REQUIRED",
	"RATE_LIMITED", "PROTOCOL_MISMATCH",
]


# ============================================================
# Validation helpers — useful for tests + startup checks
# ============================================================

## Returns the subset of `expected` keys missing from `dict`. Empty
## array = OK. Used by the M2 snapshot validator.
static func missing_keys(dict: Dictionary, expected: Array) -> Array:
	var out: Array = []
	for k in expected:
		if not dict.has(k):
			out.append(k)
	return out

## Returns the first key from `expected` whose type does not match
## `expected_type` (e.g. TYPE_INT, TYPE_STRING, TYPE_ARRAY,
## TYPE_DICTIONARY). Empty string = OK.
static func first_wrong_type(dict: Dictionary, expected: Array, expected_type: int) -> String:
	for k in expected:
		if dict.has(k) and typeof(dict[k]) != expected_type:
			return k
	return ""
