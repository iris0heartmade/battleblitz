## Mainline session state — Phase 2 small-step extraction.
##
## Holds the runtime state of an in-progress mainline (campaign) flow:
## which chapter is active, what payload the prepare page last fetched,
## which game_id backs the current mainline battle, and the auto-retry
## flag used by the 409-retry-on-conflict path.
##
## Currently a thin holder that mirrors six mainline-related fields on
## main.gd.  Future phases can lift mutators here one field at a time.
##
## This is the **single source of truth** for mainline session state as
## of the Phase 2 refactor; main.gd still owns plain fields of the same
## name as write-through proxies so legacy call-sites keep compiling.
##
## Lifecycle:
##   * Constructed once in :func:`Main._ready`.
##   * Restored from ``UserSettings`` (session.v1.mainline_* keys).
##   * Cleared on victory / abandon / next-battle.
class_name MainlineSession
extends RefCounted

# ── Persistent (UserSettings-mirrored) ────────────────────────────

var active_mainline_id: String = ""

var selected_mainline_id: String = ""

var battle_game_id: int = 0


# ── Prepare-page payloads (transient, per chapter) ────────────────

var prepare_payload: Dictionary = {}

var shop_payload: Dictionary = {}

var mercenary_payload: Dictionary = {}


# ── Auto-retry (409 mainline_already_active) ──────────────────────

var auto_retry_pending: bool = false


# ── Bootstrap helpers ─────────────────────────────────────────────


func restore_from_settings() -> void:
	active_mainline_id = str(UserSettings.get_value("session.v1.mainline_id", ""))
	battle_game_id = int(UserSettings.get_value("session.v1.mainline_game_id", 0))


func persist_active() -> void:
	UserSettings.set_value("session.v1.mainline_id", active_mainline_id)
	UserSettings.set_value("session.v1.mainline_game_id", battle_game_id)


func clear_active() -> void:
	active_mainline_id = ""
	battle_game_id = 0
	UserSettings.set_value("session.v1.mainline_id", "")
	UserSettings.set_value("session.v1.mainline_game_id", 0)
