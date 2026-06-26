"""
Game configuration constants.

All gameplay tuning values live here. Keep magic numbers out of logic modules.
"""
from __future__ import annotations

from typing import Dict, Final, List, Tuple


# ============================================================
# Map configuration
# ============================================================

MAP_SIZE: Final[int] = 15  # 15x15 grid
TOTAL_TILES: Final[int] = MAP_SIZE * MAP_SIZE

# Terrain types as string constants (also stored in DB)
TERRAIN_PLAIN: Final[str] = "plain"
TERRAIN_FOREST: Final[str] = "forest"
TERRAIN_MOUNTAIN: Final[str] = "mountain"
TERRAIN_RIVER: Final[str] = "river"
TERRAIN_CASTLE: Final[str] = "castle"

TERRAIN_TYPES: Final[Tuple[str, ...]] = (
    TERRAIN_PLAIN,
    TERRAIN_FOREST,
    TERRAIN_MOUNTAIN,
    TERRAIN_RIVER,
    TERRAIN_CASTLE,
)

# Tile movement cost when entering the tile.
# Castle is impassable for non-owner units (cost handled in game_logic).
TERRAIN_MOVE_COST: Final[Dict[str, int]] = {
    TERRAIN_PLAIN: 1,
    TERRAIN_FOREST: 2,
    TERRAIN_MOUNTAIN: 3,
    TERRAIN_RIVER: 3,
    TERRAIN_CASTLE: 1,  # owned castle counts as plain; enemy castle blocked elsewhere
}

# Defense bonus added to a defender's DEF when calculating damage.
TERRAIN_DEF_BONUS: Final[Dict[str, int]] = {
    TERRAIN_PLAIN: 0,
    TERRAIN_FOREST: 2,
    TERRAIN_MOUNTAIN: 3,
    TERRAIN_RIVER: 0,
    TERRAIN_CASTLE: 5,
}

# Relative spawn weight for procedural map generation (excluding castle).
# More weights = more of that terrain. Tuned for ~30% passable forest/mountain mix.
TERRAIN_SPAWN_WEIGHTS: Final[Dict[str, int]] = {
    TERRAIN_PLAIN: 60,
    TERRAIN_FOREST: 18,
    TERRAIN_MOUNTAIN: 10,
    TERRAIN_RIVER: 12,
}

# Castle spawn config: one castle per player, on the map's symmetric edges.
CASTLES_PER_GAME: Final[int] = 4  # max players; we generate up to 4 castles
CASTLE_NEIGHBOR_RADIUS: Final[int] = 2  # how many tiles around castle are kept passable


# ============================================================
# Player configuration
# ============================================================

MAX_PLAYERS: Final[int] = 4
MIN_PLAYERS: Final[int] = 2
DEFAULT_PLAYER_COLORS: Final[Tuple[str, ...]] = ("red", "blue", "green", "yellow")


# ============================================================
# Unit configuration — delegated to app.classes.units
# ============================================================
# All unit-type data (stats, skills, range, move-after-action, type advantage)
# now lives in `game/app/classes/units/<id>.py`.
# Import from `app.classes.units` instead of referencing the old dicts below.
# Kept as aliases for backward compatibility during migration.

from app.classes.units import (
    default_roster as _default_roster,
    get as _get_unit_class,
    get_or_none as _get_unit_class_or_none,
    get_roster_for_composition,
    list_all as _list_all_unit_classes,
    list_compositions,
    type_advantage as _unit_type_advantage,
    type_ids as _unit_type_ids,
)

# Expose stable names for existing importers
_STARTING_ROSTER = _default_roster()

def _unit_base_stats() -> Dict[str, Dict[str, int]]:
    return {p.type_id: {"hp": p.base_hp, "atk": p.base_atk, "def": p.base_def, "mov": p.base_mov}
            for p in _list_all_unit_classes()}

def _unit_mp_pool() -> Dict[str, int]:
    return {p.type_id: p.mp_pool for p in _list_all_unit_classes()}

def _unit_move_after() -> Dict[str, bool]:
    return {p.type_id: p.can_move_after_action for p in _list_all_unit_classes()}

def _unit_default_skills() -> Dict[str, List[str]]:
    return {p.type_id: list(p.default_skills) for p in _list_all_unit_classes()}

def _unit_display_names() -> Dict[str, str]:
    return {p.type_id: p.display_en for p in _list_all_unit_classes()}

# Type advantage: kept empty dict for backward compat (use _unit_type_advantage instead)
TYPE_ADVANTAGE: Final[Dict[Tuple[str, str], float]] = {}

# Skill identifiers (stored in Unit.skills JSON list)
# Skill identifiers — canonical string constants matching app.classes.units.skills
SKILL_DOUBLE_STRIKE: Final[str] = "double_strike"
SKILL_SNIPE: Final[str] = "snipe"
SKILL_HEAL: Final[str] = "heal"
SKILL_RALLY: Final[str] = "rally"


# ============================================================
# Combat configuration
# ============================================================

BASE_CRIT_RATE: Final[float] = 0.05       # 5%
CRIT_PER_LEVEL: Final[float] = 0.01       # +1% per level
CRIT_MULTIPLIER: Final[float] = 1.5

DEFAULT_MELEE_RANGE: Final[int] = 1


# ============================================================
# Progression configuration
# ============================================================

EXP_PER_KILL: Final[int] = 10
EXP_PER_ASSIST: Final[int] = 5   # if a teammate landed the killing blow
EXP_TO_LEVEL: Final[int] = 60    # every 60 EXP triggers level-up (faster pacing)
MAX_LEVEL: Final[int] = 10
LEVEL_UP_STAT_BONUS: Final[float] = 0.05   # +5% to all base stats on level up
LEVEL_UP_BONUS_POINTS: Final[int] = 2      # manual stat points per level (auto for now)


# ============================================================
# Turn / timeout configuration
# ============================================================

TURN_TIMEOUT_HOURS: Final[int] = 24
TURNS_CHECK_INTERVAL_SECONDS: Final[int] = 10  # background-task poll cadence

# Abandoned-room cleanup
ABANDONED_LOBBY_MINUTES: Final[int] = 30  # waiting game with 0 players older than this gets deleted
ABANDONED_FINISHED_HOURS: Final[int] = 24  # finished games older than this get deleted
LOBBY_CLEANUP_INTERVAL_SECONDS: Final[int] = 60  # how often to scan for abandoned lobbies


# ============================================================
# Counter-attack tuning
# ============================================================
# When a defender survives an attack and can hit the attacker, it deals
# `COUNTER_DAMAGE_MULT * normal_damage` (rounded down, min 1).
# Fire-Emblem uses 0.5 (50%); raise it to make counter more punishing,
# lower it to make counter mostly cosmetic.
COUNTER_DAMAGE_MULT: Final[float] = 0.5
# Some units may bypass counter entirely (e.g. ranged kiting units).
# Leave empty for now; populated by per-unit skills later.
COUNTER_IMMUNE_SKILLS: Final[tuple[str, ...]] = ()

# AI player
AI_THINK_DELAY_SECONDS: Final[float] = 1.2  # delay between AI actions so humans can watch
AI_MAX_ACTIONS_PER_TURN: Final[int] = 5      # safety cap so a buggy AI can't loop forever
AI_SKILL_HEAL_THRESHOLD_HP: Final[int] = 40  # heal allies below this HP% (relative to max)
AI_AGGRO_RANGE: Final[int] = 4               # AI prefers targets within this many tiles

# ============================================================
# Morale system (replaces EXP/Level)
# ============================================================
MORALE_MAX: Final[int] = 3
MORALE_ATK_PER_STAR: Final[float] = 0.10  # +10% ATK per star (max +30% at 3 stars)
MORALE_DEF_PER_STAR: Final[float] = 0.05  # +5%  DEF per star (max +15% at 3 stars)


# ============================================================
# Movement points (MP) system
# ============================================================
# Each unit starts the turn with MP equal to its `mov` value, and each
# tile entered deducts the terrain's move cost. Attacks cost 0 MP.
# Backward-compat aliases — all unit data lives in app.classes.units
UNIT_CAN_MOVE_AFTER_ACTION: Final[Dict[str, bool]] = _unit_move_after()
UNIT_MP_POOL: Final[Dict[str, int]] = _unit_mp_pool()
STARTING_ROSTER: Final[Dict[str, int]] = dict(_STARTING_ROSTER)
UNIT_BASE_STATS: Final[Dict[str, Dict[str, int]]] = _unit_base_stats()
UNIT_DEFAULT_SKILLS: Final[Dict[str, List[str]]] = _unit_default_skills()
UNIT_DISPLAY_NAMES: Final[Dict[str, str]] = _unit_display_names()
UNIT_TYPES: Final[Tuple[str, ...]] = tuple(_unit_type_ids())


# ============================================================
# DB / app configuration
# ============================================================

DEFAULT_DB_PATH: Final[str] = "battleblitz.db"
APP_TITLE: Final[str] = "BattleBlitz Server"
APP_VERSION: Final[str] = "0.1.0"