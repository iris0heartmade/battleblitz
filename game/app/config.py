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
# Unit configuration
# ============================================================

UNIT_SWORDSMAN: Final[str] = "swordsman"
UNIT_ARCHER: Final[str] = "archer"
UNIT_KNIGHT: Final[str] = "knight"
UNIT_HEALER: Final[str] = "healer"

UNIT_TYPES: Final[Tuple[str, ...]] = (
    UNIT_SWORDSMAN,
    UNIT_ARCHER,
    UNIT_KNIGHT,
    UNIT_HEALER,
)

# Skill identifiers (stored in Unit.skills JSON list)
SKILL_DOUBLE_STRIKE: Final[str] = "double_strike"  # attack twice at 50% damage each
SKILL_SNIPE: Final[str] = "snipe"                  # +1 attack range
SKILL_HEAL: Final[str] = "heal"                    # restore 20 HP to adjacent ally
SKILL_RALLY: Final[str] = "rally"                  # +10% ATK to adjacent allies this turn


# ============================================================
# Combat configuration
# ============================================================

BASE_CRIT_RATE: Final[float] = 0.05       # 5%
CRIT_PER_LEVEL: Final[float] = 0.01       # +1% per level
CRIT_MULTIPLIER: Final[float] = 1.5

# Type-advantage multipliers.
# swordsman -> knight (+20%), knight -> archer (+20%),
# archer -> mage (+20%), mage -> swordsman (+20%)
# (mage omitted from current roster; hook reserved for future expansion)
TYPE_ADVANTAGE: Final[Dict[Tuple[str, str], float]] = {
    (UNIT_SWORDSMAN, UNIT_KNIGHT): 1.20,
    (UNIT_KNIGHT, UNIT_ARCHER): 1.20,
    # (UNIT_ARCHER, "mage"): 1.20,   # reserved
    # ("mage", UNIT_SWORDSMAN): 1.20, # reserved
}

# Archer range bonus; other melee units default to 1.
DEFAULT_MELEE_RANGE: Final[int] = 1
ARCHER_BASE_RANGE: Final[int] = 2


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
# Whether the unit can MOVE AFTER attacking is per-class:
UNIT_CAN_MOVE_AFTER_ACTION: Final[Dict[str, bool]] = {
    "swordsman": False,  # committed melee fighter
    "archer":    True,   # kiting
    "knight":    True,   # mobile flanker
    "healer":    False,  # back-line support
}
# MP pool sizes (replaces previous flat-MOV movement). Tuned so that:
# - swordsman can reach a melee fight in 1-2 moves
# - knight can swing wide around the map
# - archer stays mobile enough to reposition
UNIT_MP_POOL: Final[Dict[str, int]] = {
    "swordsman": 5,
    "archer":    5,
    "knight":    8,
    "healer":    5,
}


# ============================================================
# Starting roster per player (validated against game_logic)
# ============================================================

# unit_type -> count (always 5 total per player)
STARTING_ROSTER: Final[Dict[str, int]] = {
    UNIT_SWORDSMAN: 2,
    UNIT_ARCHER: 1,
    UNIT_KNIGHT: 1,
    UNIT_HEALER: 1,
}

# Base stats per unit type. Level scaling handled in game_logic.
# HP is intentionally low so fights resolve in 2-4 exchanges.
UNIT_BASE_STATS: Final[Dict[str, Dict[str, int]]] = {
    UNIT_SWORDSMAN: {"hp": 45, "atk": 18, "def": 12, "mov": 3},
    UNIT_ARCHER:    {"hp": 35, "atk": 20, "def":  6, "mov": 3},
    UNIT_KNIGHT:    {"hp": 55, "atk": 22, "def":  8, "mov": 5},
    UNIT_HEALER:    {"hp": 40, "atk":  5, "def":  9, "mov": 3},
}

# Default skills each unit type starts with.
UNIT_DEFAULT_SKILLS: Final[Dict[str, List[str]]] = {
    UNIT_SWORDSMAN: [],
    UNIT_ARCHER:    [SKILL_SNIPE],
    UNIT_KNIGHT:    [SKILL_DOUBLE_STRIKE],
    UNIT_HEALER:    [SKILL_HEAL, SKILL_RALLY],
}

# Pretty display names (used when auto-generating unit names like "剑士甲").
UNIT_DISPLAY_NAMES: Final[Dict[str, str]] = {
    UNIT_SWORDSMAN: "Swordsman",
    UNIT_ARCHER:    "Archer",
    UNIT_KNIGHT:    "Knight",
    UNIT_HEALER:    "Healer",
}


# ============================================================
# DB / app configuration
# ============================================================

DEFAULT_DB_PATH: Final[str] = "battleblitz.db"
APP_TITLE: Final[str] = "BattleBlitz Server"
APP_VERSION: Final[str] = "0.1.0"