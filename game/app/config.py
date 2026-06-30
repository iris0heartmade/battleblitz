"""
Game configuration constants.

All gameplay tuning values live here. Keep magic numbers out of logic modules.
"""
from __future__ import annotations

from typing import Dict, Final, Tuple


# ============================================================
# Map configuration
# ============================================================

MAP_SIZE: Final[int] = 15  # 15x15 grid

# Terrain types as string constants (also stored in DB)
TERRAIN_PLAIN: Final[str] = "plain"
TERRAIN_FOREST: Final[str] = "forest"
TERRAIN_MOUNTAIN: Final[str] = "mountain"
TERRAIN_RIVER: Final[str] = "river"
TERRAIN_CASTLE: Final[str] = "castle"
# New terrains (2026-06-30 P0.4)
TERRAIN_VILLAGE: Final[str] = "village"   # 村落
TERRAIN_BARRACKS: Final[str] = "barracks" # 佣兵站
TERRAIN_ROAD: Final[str] = "road"         # 道路（MP 减半）
TERRAIN_GATE: Final[str] = "gate"         # 关卡（敌方阻拦，不可走）

# Castle interior sub-features (stored in Tile.subtype column)
CASTLE_FLOOR: Final[str] = "castle_floor"     # 地板
CASTLE_WALL: Final[str] = "castle_wall"       # 墙壁（不可走）
CASTLE_THRONE: Final[str] = "castle_throne"   # 王座
CASTLE_STAIRS: Final[str] = "castle_stairs"   # 阶梯
CASTLE_VAULT: Final[str] = "castle_vault"     # 金库
CASTLE_DOOR: Final[str] = "castle_door"       # 门扉

TERRAIN_TYPES: Final[Tuple[str, ...]] = (
    TERRAIN_PLAIN,
    TERRAIN_FOREST,
    TERRAIN_MOUNTAIN,
    TERRAIN_RIVER,
    TERRAIN_CASTLE,
    TERRAIN_VILLAGE,
    TERRAIN_BARRACKS,
    TERRAIN_ROAD,
    TERRAIN_GATE,
)

CASTLE_SUBTYPES: Final[Tuple[str, ...]] = (
    CASTLE_FLOOR,
    CASTLE_WALL,
    CASTLE_THRONE,
    CASTLE_STAIRS,
    CASTLE_VAULT,
    CASTLE_DOOR,
)

# Tile movement cost when entering the tile, expressed as INTEGER × 2 so
# we never hit float precision in the BFS pathfinder. Road costs `1`
# (i.e. half a plain tile). Blockers cost a high sentinel so the BFS
# filters them out before consulting terrain_passable().
#
# Real cost = integer_cost / 2.
TERRAIN_MOVE_COST: Final[Dict[str, int]] = {
    TERRAIN_PLAIN: 2,
    TERRAIN_FOREST: 4,
    TERRAIN_MOUNTAIN: 6,
    TERRAIN_RIVER: 6,
    TERRAIN_CASTLE: 2,
    TERRAIN_VILLAGE: 2,
    TERRAIN_BARRACKS: 2,
    TERRAIN_ROAD: 1,   # road = half cost
    TERRAIN_GATE: 9999,  # impassable
    # Castle sub-features
    CASTLE_FLOOR: 2,
    CASTLE_WALL: 9999,   # impassable
    CASTLE_THRONE: 2,
    CASTLE_STAIRS: 2,
    CASTLE_VAULT: 2,
    CASTLE_DOOR: 2,
}

# Defense bonus added to a defender's DEF when calculating damage.
TERRAIN_DEF_BONUS: Final[Dict[str, int]] = {
    TERRAIN_PLAIN: 0,
    TERRAIN_FOREST: 2,
    TERRAIN_MOUNTAIN: 3,
    TERRAIN_RIVER: 0,
    TERRAIN_CASTLE: 5,  # legacy; new code uses CASTLE_SUBTYPE_DEF_BONUS
    TERRAIN_VILLAGE: 0,
    TERRAIN_BARRACKS: 1,
    TERRAIN_ROAD: 0,
    TERRAIN_GATE: 0,
    # Castle sub-features: throne is the safest spot, vault is also strong
    CASTLE_FLOOR: 3,
    CASTLE_WALL: 99,   # blocking tile, never actually defends
    CASTLE_THRONE: 6,
    CASTLE_STAIRS: 3,
    CASTLE_VAULT: 5,
    CASTLE_DOOR: 4,
}

# Subset of terrains that produce gold income for their owner.
INCOME_TERRAINS: Final[Tuple[str, ...]] = (
    TERRAIN_VILLAGE,
    TERRAIN_BARRACKS,
    CASTLE_VAULT,
)

# Per-turn gold income by terrain (occupying player gains this much at
# the start of their turn). Placeholder values — owner will tune later.
INCOME_PER_TURN: Final[Dict[str, int]] = {
    TERRAIN_VILLAGE: 50,
    TERRAIN_BARRACKS: 100,
    CASTLE_VAULT: 150,
}

# Recruit cost (gold) for spawning a new unit at an owned barracks.
# Placeholder values.
RECRUIT_COST: Final[Dict[str, int]] = {
    "swordsman": 200,
    "archer":    250,
    "knight":    400,
    "warlock":   300,
    "healer":    350,
}

# Relative spawn weight for procedural map generation (excluding castle).
# More weights = more of that terrain. Tuned for ~30% passable forest/mountain mix.
TERRAIN_SPAWN_WEIGHTS: Final[Dict[str, int]] = {
    TERRAIN_PLAIN: 55,
    TERRAIN_FOREST: 14,
    TERRAIN_MOUNTAIN: 8,
    TERRAIN_RIVER: 10,
    TERRAIN_VILLAGE: 5,
    TERRAIN_BARRACKS: 2,
    TERRAIN_ROAD: 5,
    TERRAIN_GATE: 1,  # rare; gates are enemy-built blockers, often placed by hand
}

# Claim mechanic: units must stand on a claim-eligible tile for this many
# of their own turns (the unit performs the claim action each turn) before
# ownership flips.
CLAIM_TURNS_REQUIRED: Final[int] = 2

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
# Skill identifiers — canonical string constants
# ============================================================
# Logic lives in app/classes/units/skills/. These are the only stable IDs.

SKILL_DOUBLE_STRIKE: Final[str] = "double_strike"
SKILL_SNIPE:        Final[str] = "snipe"


# ============================================================
# Combat configuration
# ============================================================

BASE_CRIT_RATE: Final[float] = 0.05       # 5%
CRIT_PER_LEVEL: Final[float] = 0.01       # +1% per level
CRIT_MULTIPLIER: Final[float] = 1.5


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
# Per-unit MP pool / move-after-action behaviour: see app/classes/units/.


# ============================================================
# DB / app configuration
# ============================================================

DEFAULT_DB_PATH: Final[str] = "battleblitz.db"
APP_TITLE: Final[str] = "BattleBlitz Server"
APP_VERSION: Final[str] = "0.1.0"