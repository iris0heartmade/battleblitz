"""
Pure-ish game logic helpers (no FastAPI imports).

Functions that need the DB session are async; pure helpers (damage calc,
map gen, etc.) are sync so they're easy to test in isolation.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.classes.units import (
    get as _get_unit,
    get_or_none as _get_unit_or_none,
    type_advantage as _type_adv,
)
from app.config import (
    AI_MAX_ACTIONS_PER_TURN,
    BASE_CRIT_RATE, MAX_CASTLES, CASTLE_NEIGHBOR_RADIUS, CASTLE_DOOR,
    CASTLE_FLOOR, CASTLE_STAIRS, CASTLE_THRONE, CASTLE_VAULT, CASTLE_WALL,
    CLAIM_TURNS_REQUIRED, COUNTER_DAMAGE_MULT, COUNTER_IMMUNE_SKILLS,
    CRIT_MULTIPLIER, CRIT_PER_LEVEL,
    EXP_PER_ASSIST, EXP_PER_KILL, EXP_TO_LEVEL,
    LEVEL_UP_BONUS_POINTS, LEVEL_UP_STAT_BONUS, MAP_STYLES, MAP_SIZE,
    MAX_LEVEL, MORALE_ATK_PER_STAR, MORALE_DEF_PER_STAR, MORALE_MAX,
    SKILL_DOUBLE_STRIKE, STYLE_CASTLE_INTERNAL, STYLE_COMPACT_OUTER,
    STYLE_DESERT_OUTER, STYLE_GRASS_OUTER, STYLE_SNOW_OUTER,
    TERRAIN_BARRACKS, TERRAIN_BRIDGE, TERRAIN_CASTLE, TERRAIN_DEF_BONUS,
    TERRAIN_FOREST, TERRAIN_GATE, TERRAIN_MOUNTAIN, TERRAIN_PLAIN,
    TERRAIN_RIVER, TERRAIN_ROAD, TERRAIN_SNOW_PEAK, TERRAIN_SPAWN_WEIGHTS,
    TERRAIN_VILLAGE,
)

UNIT_HEALER = "healer"
UNIT_KNIGHT = "knight"

from app.models import ActionLog, ClaimSession, Game, Player, Tile, Unit
from app.movement import movement_key, resolve_movement_profile, terrain_cost_x2
from app.utils import bfs_reachable, has_line_of_sight, manhattan, pathfind


logger = logging.getLogger(__name__)


# ============================================================
# Map generation
# ============================================================

# Pre-computed symmetric castle spawn points for 2 / 3 / 4 players.
# Inset by 2 from each edge; the previous hard-coded `_CASTLE_LAYOUTS`
# is still consulted by `castle_positions()` for back-compat.
_CASTLE_LAYOUTS: Dict[int, List[Tuple[int, int]]] = {
    2: [(2, 2), (12, 12)],
    3: [(2, 2), (12, 2), (7, 12)],
    4: [(2, 2), (12, 2), (2, 12), (12, 12)],
}


def _passable_terrain_choices(rng: random.Random, weights: Dict[str, int] = None) -> str:
    """Sample one terrain id from a weighted pool.

    `weights` defaults to the legacy single-biome table for callers that
    pre-date the style-aware generator; new code should pass
    `MAP_STYLES[style]["weights"]` instead.
    """
    if weights is None:
        weights = TERRAIN_SPAWN_WEIGHTS
    terrain_types = list(weights.keys())
    weight_values = list(weights.values())
    return rng.choices(terrain_types, weights=weight_values, k=1)[0]


def _weighted_subtype(rng: random.Random, palette: Dict[str, int]) -> str:
    """Pick one castle_* sub-feature id from a palette dict."""
    types = list(palette.keys())
    weights = list(palette.values())
    return rng.choices(types, weights=weights, k=1)[0]


def _generate_outer_map(
    rng: random.Random,
    style_cfg: Dict,
    castles: List[Tuple[int, int]],
    size: int,
) -> List[List[Tile]]:
    """Outer-style generator: HQ centre on whole-tile `castle`, safe-zone
    plain around it, style-weighted terrains elsewhere.
    """
    castle_set = set(castles)
    safe_radius = int(style_cfg.get("safe_zone_radius", CASTLE_NEIGHBOR_RADIUS))
    weights = style_cfg["weights"]

    safe_zones: set = set()
    for cx, cy in castles:
        for dx in range(-safe_radius, safe_radius + 1):
            for dy in range(-safe_radius, safe_radius + 1):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    safe_zones.add((x, y))

    grid: List[List[Tile]] = []
    for y in range(size):
        row: List[Tile] = []
        for x in range(size):
            if (x, y) in castle_set:
                row.append(Tile(x=x, y=y, terrain=TERRAIN_CASTLE))
            elif (x, y) in safe_zones:
                row.append(Tile(x=x, y=y, terrain=TERRAIN_PLAIN))
            else:
                t = _passable_terrain_choices(rng, weights)
                row.append(Tile(x=x, y=y, terrain=t))
        grid.append(row)
    return grid


def _generate_castle_internal_map(
    rng: random.Random,
    style_cfg: Dict,
    castles: List[Tuple[int, int]],
    size: int,
) -> List[List[Tile]]:
    """Castle-internal style: every tile is a `castle_*` sub-feature.

    1. Fill the grid by sampling from `style_cfg["tile_palette"]`.
    2. Override each HQ centre with `castle_throne`.
    3. Around each HQ, drop `door_count_per_hq` `castle_door` cells on
       the four cardinal neighbours (when in-bounds), then
       `stairs_count_per_hq` random adjacent `castle_stairs`, and
       `vault_count_per_hq` random non-throne `castle_vault`s.
    """
    palette: Dict[str, int] = style_cfg["tile_palette"]
    door_count = int(style_cfg.get("door_count_per_hq", 2))
    stairs_count = int(style_cfg.get("stairs_count_per_hq", 1))
    vault_count = int(style_cfg.get("vault_count_per_hq", 1))

    # Step 1 — lay down the palette.
    grid: List[List[Tile]] = []
    for y in range(size):
        row: List[Tile] = []
        for x in range(size):
            sub = _weighted_subtype(rng, palette)
            # terrain still says "castle" so non-castle-aware code
            # (movement table, attack targets, ...) keeps working.
            row.append(Tile(x=x, y=y, terrain=TERRAIN_CASTLE, subtype=sub))
        grid.append(row)

    # Step 2 + 3 — place HQ decorations.
    for cx, cy in castles:
        if not (0 <= cx < size and 0 <= cy < size):
            continue
        grid[cy][cx] = Tile(x=cx, y=cy, terrain=TERRAIN_CASTLE, subtype=CASTLE_THRONE)

        # Door cells: cardinal neighbours, up to door_count.
        card_dirs = [(0, -1), (1, 0), (0, 1), (-1, 0)]
        rng.shuffle(card_dirs)
        placed_doors = 0
        for dx, dy in card_dirs:
            if placed_doors >= door_count:
                break
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < size and 0 <= ny < size:
                grid[ny][nx] = Tile(x=nx, y=ny, terrain=TERRAIN_CASTLE, subtype=CASTLE_DOOR)
                placed_doors += 1

        # Stairs cells: 1 (default) random in-bounds 8-neighbour squares.
        cand = [(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if not (dx == 0 and dy == 0)]
        rng.shuffle(cand)
        placed = 0
        for nx, ny in cand:
            if placed >= stairs_count:
                break
            if 0 <= nx < size and 0 <= ny < size:
                grid[ny][nx] = Tile(x=nx, y=ny, terrain=TERRAIN_CASTLE, subtype=CASTLE_STAIRS)
                placed += 1

        # Vault cells: random non-throne in-bounds cells (anywhere).
        all_cells = [(x, y) for y in range(size) for x in range(size)
                     if (x, y) != (cx, cy) and grid[y][x].subtype != CASTLE_THRONE]
        rng.shuffle(all_cells)
        placed = 0
        for nx, ny in all_cells:
            if placed >= vault_count:
                break
            grid[ny][nx] = Tile(x=nx, y=ny, terrain=TERRAIN_CASTLE, subtype=CASTLE_VAULT)
            placed += 1

    return grid


def generate_map(
    seed: int,
    num_castles: int = MAX_CASTLES,
    style: str = STYLE_GRASS_OUTER,
    size: int = MAP_SIZE,
    *,
    use_rich_generator: bool = False,
) -> List[List[Tile]]:
    """Generate a 2D list of `Tile` rows for a fresh game.

    `style` is a key in `MAP_STYLES` (config.py) and drives both the
    HQ mode (single_hq / hq_with_struct / castle_internal) and the
    terrain weight table.

    `size` lets the generator cover maps > 15 (P0.4 / random-map work).

    `use_rich_generator` (P1.4): when True, route through the new
    layered ``MapGenerator`` (forest / mountain clusters, rivers,
    buildings, roads).  Default False keeps the legacy byte-identical
    behaviour so existing tests / replays stay stable.
    """
    if num_castles not in _CASTLE_LAYOUTS:
        num_castles = MAX_CASTLES

    style_cfg = MAP_STYLES.get(style, MAP_STYLES[STYLE_GRASS_OUTER])
    mode = style_cfg.get("mode", "single_hq")
    # Scale the castle layout to the requested grid. Insets are kept at
    # 2 cells so a 25×25 map still has its corners at (2, 2), (22, 2), ...
    inset = max(2, size // 8)
    far_inset = size - 1 - inset
    mid_x = size // 2
    base_layouts = {
        2: [(inset, inset), (far_inset, far_inset)],
        3: [(inset, inset), (far_inset, inset), (mid_x, far_inset)],
        4: [(inset, inset), (far_inset, inset),
            (inset, far_inset), (far_inset, far_inset)],
    }
    castles = base_layouts[num_castles]

    if use_rich_generator:
        # P1.4 — delegate to the new modular generator.  Castle
        # positions and safe zones are computed by the generator
        # itself so the call below stays in sync with the legacy
        # castle_layout math.
        from app.map_generation import MapGenerator

        gen = MapGenerator(
            size=size,
            player_count=num_castles,
            style=style,
            seed=seed,
            # Outer mode defaults — the rich features are wired in but
            # default-on so the "rich" path is genuinely richer.
            use_clusters=True,
            use_rivers=True,
            use_roads=True,
            use_buildings=True,
            use_hq_structure=(mode == "hq_with_struct"),
        )
        return gen.generate()

    rng = random.Random(seed)
    if mode == "castle_internal":
        return _generate_castle_internal_map(rng, style_cfg, castles, size)
    # Default / single_hq / hq_with_struct: outer generator (hq_with_struct
    # currently shares single_hq's body; Phase 5 will swap to a 3×3 wrapper).
    return _generate_outer_map(rng, style_cfg, castles, size)


def castle_positions(num_players: int, size: int = MAP_SIZE) -> Dict[int, Tuple[int, int]]:
    """Return {seat_index: (x, y)} for the requested player count and map size."""
    from app.map_generation.symmetry import calculate_castle_positions
    positions = calculate_castle_positions(size, num_players)
    return {i: pos for i, pos in enumerate(positions)}


# ============================================================
# Unit creation
# ============================================================

_UNIT_NAME_SUFFIX = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"]


def _unit_name(unit_type: str, index: int) -> str:
    base = _get_unit(unit_type)
    suffix = _UNIT_NAME_SUFFIX[index] if index < len(_UNIT_NAME_SUFFIX) else f"#{index + 1}"
    return f"{base.display_en}-{suffix}"


# ============================================================
# Combat
# ============================================================

@dataclass(frozen=True)
class DamageResult:
    damage: int
    is_crit: bool
    is_kill: bool
    effective_atk: int
    defense_total: int


def unit_attack_range(unit: Unit) -> int:
    """Maximum attack range (Manhattan distance)."""
    from app.classes.units.skills import get_passive_for
    base = _get_unit(unit.unit_type).attack_range
    player = getattr(unit, "player", None)
    commander_id = getattr(player, "commander_id", None) if player is not None else None
    if commander_id is not None:
        from app.commanders.registry import get_commander_passive, get_commander_power

        passive = get_commander_passive(commander_id)
        base += getattr(passive, "range_delta", 0) if passive is not None else 0
        co = getattr(player, "co_state", None) or {}
        if co.get("is_power_active"):
            power = get_commander_power(commander_id)
            base += getattr(power, "range_delta", 0) if power is not None else 0
    else:
        base = getattr(unit, "_base_attack_range", base)
    for sk in get_passive_for(unit):
        base = sk.modify_attack_range(base, unit)
    return base


def unit_min_attack_range(unit: Unit) -> int:
    """Minimum attack range (Manhattan distance).

    0 = can attack adjacent (d=1) → melee
    1 = must keep distance (no melee, like Fire-Emblem archers)
    """
    return _get_unit(unit.unit_type).min_attack_range


def can_attack_from_position(
    unit: Unit,
    fromX: int, fromY: int,
    toX: int, toY: int,
    blockers: Optional[set] = None,
    board_size: int = MAP_SIZE,
) -> bool:
    """True if `unit` could attack (toX, toY) when standing on (fromX, fromY).

    Distance is measured in Manhattan metric (|dx|+|dy|). For
    attacks at distance > 1 we also require a clear line of sight
    (mountains / forests / rivers block) — unless the unit has
    `ignores_line_of_sight=True` (e.g. archer sniper), which shoots
    through obstacles. Melee (d == 1) is always allowed — the unit
    can close distance and swing.

    `blockers` is a set of (x, y) coords; pass the set of mountain
    / forest / river tiles from the AI snapshot or pass None to skip
    the LoS check (e.g. for melee-only or for callers that don't
    have the map handy — the legacy single-player tests do this).
    """
    d = manhattan((fromX, fromY), (toX, toY))
    if d == 0:
        return False
    if not (unit_min_attack_range(unit) < d <= unit_attack_range(unit)):
        return False
    if d <= 1:
        return True  # melee, no LoS needed
    # Ranged attack — apply LoS check unless the unit's class ignores it.
    # Matches the policy in routes/actions.py and agent/legal_actions.py.
    if blockers is not None and not _get_unit(unit.unit_type).ignores_line_of_sight:
        if not has_line_of_sight(
            (fromX, fromY), (toX, toY), blockers, size=board_size,
        ):
            return False
    return True


def _type_multiplier(attacker: Unit, defender: Unit) -> float:
    return _type_adv(attacker.unit_type, defender.unit_type)


def _crit_chance(unit: Unit) -> float:
    return min(1.0, BASE_CRIT_RATE + CRIT_PER_LEVEL * (unit.level - 1))


def _attack_kind_of(unit: Unit) -> str:
    """Return the attack_kind ("physical" or "magic") of a unit.

    Looks up the compiled UnitClassProfile from the unit's type_id so the
    damage formula doesn't need a column on Unit itself. Falls back to
    "physical" for unknown types so legacy units keep working.
    """
    try:
        profile = _get_unit(unit.unit_type)
    except Exception:
        return "physical"
    return getattr(profile, "attack_kind", "physical") or "physical"


def calculate_damage(
    attacker: Unit,
    defender: Unit,
    tile_def_bonus: int,
    *,
    crit: Optional[bool] = None,
    rng: Optional[random.Random] = None,
) -> DamageResult:
    """Compute one attack's damage.

    The damage type is determined by the ATTACKER's attack_kind:
      - "physical": attacker uses ATK, defender blocks with DEF (+ terrain)
      - "magic"   : attacker uses MATK, defender blocks with MDEF (+ terrain)

    Morale modifiers:
      effective_atk = X * (1 + attacker.morale * MORALE_ATK_PER_STAR)
      effective_def = (Y + terrain) * (1 + defender.morale * MORALE_DEF_PER_STAR)

    damage = eff_atk * (eff_atk / (eff_atk + eff_def)) * type_adv * crit_mult
    """
    rng = rng or random.Random()
    if crit is None:
        crit_chance = _crit_chance(attacker)
        crit = rng.random() < crit_chance
        logger.debug(f"Crit roll: {attacker.name}(id={attacker.id}) -> {defender.name}(id={defender.id}): {'CRIT' if crit else 'no crit'} (chance={crit_chance:.2f})")

    if _attack_kind_of(attacker) == "magic":
        eff_atk = attacker.matk * (1 + attacker.morale * MORALE_ATK_PER_STAR)
        eff_df = (defender.mdef + tile_def_bonus) * (1 + defender.morale * MORALE_DEF_PER_STAR)
    else:
        eff_atk = attacker.atk * (1 + attacker.morale * MORALE_ATK_PER_STAR)
        eff_df = (defender.def_ + tile_def_bonus) * (1 + defender.morale * MORALE_DEF_PER_STAR)
    eff_atk = max(1, eff_atk)
    eff_df = max(1, eff_df)

    base = eff_atk * (eff_atk / (eff_atk + eff_df))

    mult = _type_multiplier(attacker, defender)
    if crit:
        mult *= CRIT_MULTIPLIER
    dmg = max(1, int(round(base * mult)))

    return DamageResult(
        damage=dmg,
        is_crit=crit,
        is_kill=dmg >= defender.hp,
        effective_atk=int(round(eff_atk)),
        defense_total=int(round(eff_df)),
    )


def apply_damage(unit: Unit, dmg: int) -> bool:
    """Subtract HP, clamp at 0, return True if the unit died."""
    unit.hp = max(0, unit.hp - dmg)
    return unit.hp == 0


def attack_with_double_strike(
    attacker: Unit,
    defender: Unit,
    tile_def_bonus: int,
    *,
    rng: Optional[random.Random] = None,
) -> List[DamageResult]:
    """Attack twice at 50% damage each, when the unit has the Double-Strike skill.

    Returns a list of 1 or 2 DamageResults.
    """
    if SKILL_DOUBLE_STRIKE not in (attacker.skills or []):
        return [
            calculate_damage(attacker, defender, tile_def_bonus, rng=rng)
        ]
    rng = rng or random.Random()
    first = calculate_damage(attacker, defender, tile_def_bonus, rng=rng)
    second = calculate_damage(attacker, defender, tile_def_bonus, rng=rng)
    return [
        DamageResult(
            damage=max(1, first.damage // 2),
            is_crit=first.is_crit,
            is_kill=False,  # recomputed below
            effective_atk=first.effective_atk,
            defense_total=first.defense_total,
        ),
        DamageResult(
            damage=max(1, second.damage // 2),
            is_crit=second.is_crit,
            is_kill=False,
            effective_atk=second.effective_atk,
            defense_total=second.defense_total,
        ),
    ]


# ============================================================
# Progression
# ============================================================

@dataclass
class LevelUpResult:
    new_level: int
    stat_bonus_applied: float
    bonus_points: int


def level_up_if_ready(unit: Unit) -> Optional[LevelUpResult]:
    """Auto-level when EXP crosses `EXP_TO_LEVEL` (single level per call).

    Each level: +5% to all base stats (HP, ATK, DEF); +2 bonus stat points
    auto-allocated as +1 ATK, +1 DEF. MOV does not scale.
    """
    if unit.level >= MAX_LEVEL:
        return None
    if unit.exp < EXP_TO_LEVEL:
        return None

    unit.exp -= EXP_TO_LEVEL
    unit.level += 1
    factor = 1.0 + LEVEL_UP_STAT_BONUS  # 1.05
    new_max_hp = int(round(unit.max_hp * factor))
    hp_gain = new_max_hp - unit.max_hp
    unit.max_hp = new_max_hp
    unit.hp = min(unit.max_hp, unit.hp + hp_gain)
    unit.atk = int(round(unit.atk * factor))
    unit.def_ = int(round(unit.def_ * factor))

    # Auto-allocate bonus points
    unit.atk += 1
    unit.def_ += 1

    return LevelUpResult(
        new_level=unit.level,
        stat_bonus_applied=factor,
        bonus_points=LEVEL_UP_BONUS_POINTS,
    )


def award_exp(unit: Unit, kind: str) -> None:
    """Award EXP. `kind` is one of: kill | assist | hit.

    Kept for backward compatibility; only `kill` now also bumps morale.
    """
    if kind == "kill":
        unit.exp += EXP_PER_KILL
        award_morale(unit)
    elif kind == "assist":
        unit.exp += EXP_PER_ASSIST
    elif kind == "hit":
        unit.exp += max(1, EXP_PER_ASSIST // 2)
    else:
        raise ValueError(f"unknown exp kind: {kind!r}")


def award_morale(unit: Unit) -> None:
    """Kill-bonus: bump unit morale by 1 (capped at MORALE_MAX)."""
    if unit.morale < MORALE_MAX:
        unit.morale += 1


# ============================================================
# End-of-turn
# ============================================================

@dataclass
class EndTurnResult:
    leveled_units: List[Tuple[int, int]]
    dead_unit_ids: List[int]
    logs: List[str]


async def _load_game_actors(session: AsyncSession, game: Game) -> Tuple[List[Player], List[Unit]]:
    players = (
        await session.execute(select(Player).where(Player.game_id == game.id))
    ).scalars().all()
    player_ids = [p.id for p in players]
    if not player_ids:
        return list(players), []
    units = (
        await session.execute(select(Unit).where(Unit.player_id.in_(player_ids)))
    ).scalars().all()
    # Migration: the `rally` skill was removed in the 2026-06-30 magic-combat
    # refactor. Strip it from any unit that still has it so the engine
    # doesn't try to call into a non-existent skill.
    for u in units:
        if u.skills and "rally" in u.skills:
            u.skills = [s for s in u.skills if s != "rally"]
    return list(players), list(units)


async def cleanup_dead_units(session: AsyncSession, units: Sequence[Unit]) -> List[int]:
    """Delete dead units, awarding one death score per unique casualty."""
    pending_delete = tuple(getattr(session, "deleted", ()))
    dead_by_id = {
        u.id: u for u in units
        if u.hp <= 0 and not any(u is deleted for deleted in pending_delete)
    }
    dead = list(dead_by_id.values())
    if not dead:
        return []
    dead_ids = [u.id for u in dead]
    from app.commanders.meter import on_death
    from sqlalchemy.orm.attributes import flag_modified

    for player_id in {u.player_id for u in dead}:
        owning_player = await session.get(Player, player_id)
        if owning_player is None or owning_player.commander_id is None:
            continue
        for _ in (u for u in dead if u.player_id == player_id):
            on_death(owning_player)
        flag_modified(owning_player, "co_state")
    # Free tiles first so the FK SET NULL doesn't fight our delete
    await session.execute(
        update(Tile)
        .where(Tile.occupied_unit_id.in_(dead_ids))
        .values(occupied_unit_id=None)
    )
    # Cancel any pending claim sessions owned by a dying unit.
    for u in dead:
        await cancel_claim_sessions_for_unit(session, u.id)
    for u in dead:
        await session.delete(u)
    # P2.3 — re-evaluate the win condition after the dead are gone.
    # For "rout" mode this is the trigger: a team dropping to 0
    # units is the rout condition. Other modes (seize / reach /
    # defend) re-check here too so they always have a chance to
    # finish even if no other trigger fires.
    # NOTE: Unit has no game_id column (only Player does), so we
    # resolve the game via the unit's owning player.
    if dead:
        owning_player = await session.get(Player, dead[0].player_id)
        game_id = owning_player.game_id if owning_player else None
    else:
        game_id = None
    game = await _resolve_game(session, game_id) if game_id is not None else None
    if game is not None and game.status == "playing":
        await check_win_condition(session, game)
    return dead_ids


# ============================================================
# P2.3 — win-condition dispatcher
# ============================================================

async def _resolve_game(session: AsyncSession, game_id: int):
    """Tiny helper to look up a Game by id; the dead-unit path
    needs the game to evaluate the win condition but doesn't have
    it in hand."""
    from sqlalchemy import select as _sel
    return (await session.execute(
        _sel(Game).where(Game.id == game_id)
    )).scalars().first()


def _team_of(player: Player) -> str:
    """Resolve the logical 'team' id for win-condition aggregation.

    Priority:
      1. player.team_id if set (explicit team mode, e.g. 2v2 where
         two players share "red" or "blue")
      2. f"player_{player.id}" (1V1 free-for-all: each player is
         their own team so Rout/Reach/Defend work without an
         explicit team join)
    """
    if player.team_id:
        return player.team_id
    return f"player_{player.id}"


async def _alive_teams(session: AsyncSession, game: Game) -> list:
    """Return the sorted list of teams that still have at least one
    unit with hp > 0 in this game. Used by all 4 win conditions."""
    from sqlalchemy import func, select as _sel
    rows = (await session.execute(
        _sel(Player.team_id, Player.color, func.count(Unit.id))
        .join(Unit, Unit.player_id == Player.id)
        .join(Game, Game.id == Player.game_id)
        .where(Game.id == game.id, Unit.hp > 0)
        .group_by(Player.id)
    )).all()
    teams = set()
    for team_id, color, _count in rows:
        teams.add(team_id or color or "neutral")
    return sorted(teams)


def _finish_game(
    game: Game,
    winner_team: Optional[str],
    win_reason: str,
) -> None:
    """Mark a game as finished and stash the winner / reason so the
    front-end can render the right banner copy."""
    game.status = "finished"
    game.win_reason = win_reason
    # Stash the winning team on a transient attribute so the state
    # endpoint can include it without us adding yet another column.
    game._winner_team = winner_team


async def check_win_condition(session: AsyncSession, game: Game) -> bool:
    """Evaluate the win condition for `game`. Returns True if a winner
    has been decided (status now 'finished').

    P2.4 polish — rout + seize are now UNIVERSAL. The function fires
    rout (last team alive wins) regardless of `game.win_condition`,
    because rout + seize are the only modes the engine fully supports.
    Seize itself is decided in `claim_tile` (when HQ ownership flips);
    this function does not need a second pass for it.

    Legacy `defend` and `reach` modes stay supported for old game rows
    in the DB. New games always use the default ("rout"), which now
    means "rout+seize" because both fire for every game.

    Called from:
      - cleanup_dead_units (universal rout)
      - apply_end_of_turn (legacy defend + final universal rout)
      - move_unit (legacy reach, when a unit lands on the target)
      - claim_tile (seize, when HQ ownership flips)
    """
    if game.status != "playing":
        return game.status == "finished"

    # Always recompute alive-teams so a 0-team left means 'draw'.
    alive = await _alive_teams(session, game)

    # --- Legacy: defend (survive N rounds) — keep the "defend" label
    #     as a win_reason when the game was actually in defend mode
    #     AND we're at/past the target turn. Otherwise fall through
    #     to the universal rout check (which always fires). ---
    defend_winner_team = None
    if (
        game.win_condition == "defend"
        and game.turn_number >= game.defend_turns
        and len(alive) == 1
    ):
        defend_winner_team = alive[0]

    # --- UNIVERSAL rout — fires regardless of game.win_condition ---
    if len(alive) == 0:
        _finish_game(game, None, "draw")
        return True
    if len(alive) == 1:
        # In defend mode at the target turn, use "defend" as the
        # reason to preserve the original semantics; otherwise "rout".
        reason = "defend" if defend_winner_team is not None else "rout"
        _finish_game(game, alive[0], reason)
        return True

    # --- UNIVERSAL seize — handled in claim_tile when ownership flips;
    #     this function does NOT need a seize-specific branch because
    #     claim_tile calls _finish_game directly. ---

    # --- Legacy: reach (touch a target tile) ---
    if game.win_condition == "reach" and game.reach_tile_id is not None:
        from sqlalchemy import select as _sel
        tile = await session.get(Tile, game.reach_tile_id)
        if tile is not None and tile.occupied_unit_id is not None:
            winner_unit = (await session.execute(
                _sel(Unit).where(Unit.id == tile.occupied_unit_id)
            )).scalars().first()
            if winner_unit is not None and winner_unit.hp > 0:
                winner_player = (await session.execute(
                    _sel(Player).where(Player.id == winner_unit.player_id)
                )).scalars().first()
                _finish_game(game, _team_of(winner_player), "reach")
                return True

    return False


async def apply_end_of_turn(session: AsyncSession, game: Game) -> EndTurnResult:
    """Resolve end-of-turn effects.

    - Auto-level any units that crossed EXP threshold.
    - Delete dead units and free their tiles.
    - Mark players with no units as eliminated.
    - Check win condition.
    - Append a summary ActionLog entry.
    """
    leveled: List[Tuple[int, int]] = []
    logs: List[str] = []

    players, units = await _load_game_actors(session, game)

    # 1. Level-up
    for u in units:
        result = level_up_if_ready(u)
        if result:
            leveled.append((u.id, result.new_level))
            logs.append(f"{u.name} 升到了 Lv.{result.new_level}！")

    # 2. Delete dead units
    dead_ids = await cleanup_dead_units(session, units)

    # 3. Eliminate players with no alive units
    alive_counts: Dict[int, int] = {p.id: 0 for p in players}
    for u in units:
        if u.hp > 0 and u.player_id in alive_counts:
            alive_counts[u.player_id] += 1
    for p in players:
        # P2.4 — spectators are audibly "alive" forever: they have
        # no units by design and never engage in combat. Skip the
        # 0-units elimination check so they aren't struck down at
        # the end of the first round.
        if p.is_spectator:
            continue
        if p.is_alive and alive_counts.get(p.id, 0) == 0:
            p.is_alive = False
            logs.append(f"{p.user_name} 已被淘汰！")

    # 4. Win check — P2.3 dispatches through check_win_condition,
    # which understands rout / seize / reach / defend based on
    # game.win_condition. Survives the legacy '<=1 survivor' rout
    # behaviour as the fallback.
    if game.status == "playing":
        await check_win_condition(session, game)
    if game.status == "finished":
        # Translate the win_reason + winner into a human-readable
        # summary line for the turn-end ActionLog.
        winner_team = getattr(game, "_winner_team", None)
        if game.win_reason == "draw":
            logs.append("游戏结束 - 平局！")
        elif winner_team is not None:
            logs.append(f"游戏结束 - 阵营 {winner_team} 获胜（{game.win_reason}）！")
        else:
            # Defensive: status finished but no winner_team.
            logs.append(f"游戏结束 - {game.win_reason} 胜出！")

    # 5. Log summary
    if logs:
        session.add(
            ActionLog(
                game_id=game.id,
                turn_number=game.turn_number,
                player_id=None,
                action_type="turn_end",
                description=" | ".join(logs),
            )
        )

    await session.flush()
    return EndTurnResult(leveled_units=leveled, dead_unit_ids=dead_ids, logs=logs)


# ============================================================
# Castle ownership
# ============================================================

def claim_castle_if_present(tile: Tile, unit: Unit) -> bool:
    """If `unit` is standing on an enemy castle tile, transfer ownership to its player."""
    if tile.terrain != TERRAIN_CASTLE:
        return False
    if tile.owner_id == unit.player_id:
        return False
    # Only claim if it's an enemy castle, not neutral or already owned
    old_owner = tile.owner_id
    tile.owner_id = unit.player_id
    logger.info(f"Castle claimed at ({tile.x},{tile.y}): unit {unit.name}(id={unit.id},player={unit.player_id}) takes from prev_owner={old_owner}")
    return True


# ============================================================
# Claim mechanic (P0.4) — see docs/superpowers/specs/2026-06-30-
# terrain-economy-claim-spec.md §4.
# ============================================================

# Terrains a unit can perform the active `claim` action on.
CLAIMABLE_TERRAINS = frozenset({TERRAIN_VILLAGE, TERRAIN_BARRACKS, CASTLE_VAULT, TERRAIN_CASTLE})


def is_claimable(terrain: str) -> bool:
    return terrain in CLAIMABLE_TERRAINS


async def check_pending_claims(
    session: AsyncSession,
    game: Game,
) -> List[int]:
    """Resolve any ClaimSession whose completes_turn <= current turn.

    For each completed session, flip the tile's owner_id to the
    target_player, write an ActionLog, and delete the session. Returns
    the list of tile_ids whose ownership changed so the caller can
    emit events.

    Called from end_turn after the round resolves and the turn
    number has been bumped. Sessions whose `completes_turn` has
    passed are finalised here — this is the 1-turn lag rule:
    ownership flips in turn N+1, but the new owner only starts
    receiving income at the start of turn N+2.

    P2.3 — under the "seize" win condition, each completed claim
    is checked: if the tile is one of the castled HQ tiles AND the
    new owner is on a different team than the previous owner, the
    seizing team wins the match immediately. We resolve this
    AFTER the ownership flip but BEFORE returning so the caller
    doesn't have to re-poll.
    """
    rows = (
        await session.execute(
            select(ClaimSession).where(
                ClaimSession.game_id == game.id,
                ClaimSession.completes_turn <= game.turn_number,
            )
        )
    ).scalars().all()

    flipped: List[int] = []
    for cs in rows:
        tile = await session.get(Tile, cs.tile_id)
        if tile is None:
            await session.delete(cs)
            continue
        unit = await session.get(Unit, cs.unit_id)
        # If the unit died, do NOT flip ownership.
        if unit is None or unit.hp <= 0:
            await session.delete(cs)
            continue
        # If the unit moved off the tile, do NOT flip ownership.
        if (unit.x, unit.y) != (tile.x, tile.y):
            await session.delete(cs)
            continue
        old_owner = tile.owner_id
        tile.owner_id = cs.target_player_id
        flipped.append(tile.id)
        session.add(ActionLog(
            game_id=game.id,
            turn_number=game.turn_number,
            player_id=cs.target_player_id,
            action_type="claim_complete",
            description=(
                f"占领完成：({tile.x},{tile.y}) 由阵营 {old_owner or '无主'}"
                f" 变更为阵营 {cs.target_player_id}"
            ),
        ))
        await session.delete(cs)

    # P0.5 — seize check is UNIVERSAL (works on any game, not just
    # those with win_condition=="seize"). Any HQ-ownership flip between
    # different teams is an instant win. We do this AFTER all the
    # flips so the win_reason reflects the LAST valid seize (and
    # any earlier seizures are logged in the claim_complete rows
    # above for the action log).
    if game.status == "playing":
        for tile_id in flipped:
            tile = await session.get(Tile, tile_id)
            if tile is None or tile.terrain != TERRAIN_CASTLE:
                continue  # only castle tiles can be a HQ
            # The new owner's team vs the previous owner's team.
            new_player = await session.get(Player, tile.owner_id) if tile.owner_id else None
            # Find the team of the previous owner by reading the
            # ActionLog we just wrote (it has the old owner id).
            # In practice, 'seize' always involves a flip between
            # different players (ClaimSession wouldn't have been
            # created if the same player tried to claim their own
            # tile), so old != new. We still treat an unchanged-team
            # flip as 'no win' (defensive coding).
            winner_team = _team_of(new_player) if new_player else None
            if winner_team:
                # Rout fallback: only 1 team left alive?
                alive = await _alive_teams(session, game)
                if len(alive) == 1 and alive[0] == winner_team:
                    _finish_game(game, winner_team, "seize")
                elif len(alive) == 0:
                    _finish_game(game, None, "draw")
                else:
                    # Multiple teams still alive — seize wins outright
                    # (the owner just lost their HQ; surviving that
                    # is the "you have to retake it" path, but the
                    # owner-rule for Seize is "seize = win", so we
                    # end the match here).
                    _finish_game(game, winner_team, "seize")
                if game.status == "finished":
                    session.add(ActionLog(
                        game_id=game.id,
                        turn_number=game.turn_number,
                        player_id=new_player.id,
                        action_type="victory",
                        description=(
                            f"🏆 {winner_team} 阵营占领了对方 HQ，胜利！"
                        ),
                    ))
                    break  # no need to check further tiles
    return flipped


async def cancel_claim_sessions_for_unit(
    session: AsyncSession,
    unit_id: int,
) -> int:
    """Delete any active ClaimSession for a given unit. Returns count.

    Called when the unit dies, moves, or is removed for any reason.
    """
    rows = (
        await session.execute(
            select(ClaimSession).where(ClaimSession.unit_id == unit_id)
        )
    ).scalars().all()
    n = 0
    for cs in rows:
        await session.delete(cs)
        n += 1
    return n


__all__ = [
    "DamageResult",
    "EndTurnResult",
    "LevelUpResult",
    "MAP_PRESETS",
    "MapPresetResult",
    "apply_damage",
    "apply_end_of_turn",
    "attack_with_double_strike",
    "award_exp",
    "ai_take_turn",
    "build_ai_player",
    "calculate_damage",
    "castle_positions",
    "claim_castle_if_present",
    "cleanup_dead_units",
    "generate_map",
    "generate_map_preset",
    "level_up_if_ready",
    "unit_attack_range",
]


# ============================================================
# Map presets (loaded from game/maps/*.json)
# ============================================================
# Each preset is a JSON file with:
#   - "id":          string id
#   - "name":        human-readable name
#   - "description": short tag
#   - "layout":      List[str], each row a 15-char string. Chars:
#                    'P' plain, 'F' forest, 'M' mountain, 'R' river, 'C' castle
#                    Castles are placed at symmetric corner positions for 2-4 players.
#
# Empty or missing "layout" → generate_map_preset() falls back to procedural generation.
#
# Adding a new preset: drop a JSON file in game/maps/, restart the server.
# Regenerate JSON from an in-Python layout:  python tools/gen_map_json.py

import json as _json
from pathlib import Path as _Path


def _resolve_size(size: Union[int, Dict[str, int]]) -> Dict[str, int]:
    """Normalize `size` from JSON to {width, height} dict.

    Legacy preset: ``size=15`` -> ``{width: 15, height: 15}``
    New preset: ``size={width:10, height:7}`` -> pass-through.
    """
    if isinstance(size, int):
        return {"width": size, "height": size}
    if isinstance(size, dict) and "width" in size and "height" in size:
        return dict(size)
    raise TypeError(
        f"size must be int or dict with width/height, got {type(size).__name__}"
    )


_MAPS_DIR = _Path(__file__).resolve().parent.parent / "maps"


# Classic-roster helper used both for the static "classic" entry in
# MAP_PRESETS (so the BattleSpec model_validator sees all 4 colors
# present in initial_units) and for the procedural fallback in
# `generate_map_preset`. Keeping the two paths in sync means the
# schema-level color check and the runtime spawn agree on what
# `classic` actually means.
_CLASSIC_ROSTER: list[tuple[str, int]] = [
    ("swordsman", 2), ("archer", 1), ("knight", 1), ("healer", 1),
]
_CLASSIC_COLORS: tuple[str, ...] = ("red", "blue", "green", "yellow")
_CLASSIC_OFFSETS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 0), (1, 1), (2, 0), (0, 2),
)

# P2.7+ — varied roster templates for procedurally-generated maps.
# Each entry is (name, weight, [(type, count), ...]).  Warlocks
# appear in 4 of the 7 templates (up from 0% before).
_VARIED_ROSTERS: list[tuple[str, int, list[tuple[str, int]]]] = [
    ("defensive", 2, [
        ("swordsman", 2), ("archer", 1), ("healer", 1),
    ]),
    ("offensive", 2, [
        ("swordsman", 1), ("knight", 1), ("archer", 1), ("warlock", 1),
    ]),
    ("balanced", 2, [
        ("swordsman", 2), ("archer", 1), ("knight", 1), ("healer", 1),
    ]),
    ("fast", 1, [
        ("knight", 2), ("archer", 1), ("swordsman", 1),
    ]),
    ("magic", 1, [
        ("warlock", 1), ("healer", 1), ("archer", 1), ("swordsman", 1),
    ]),
    ("siege", 1, [
        ("knight", 1), ("warlock", 1), ("swordsman", 1),
    ]),
    ("economy", 1, [
        ("swordsman", 2), ("archer", 2), ("healer", 1),
    ]),
]
# Total weight sum = 2+2+2+1+1+1+1 = 10


def _castle_positions_for_size(num_castles: int, width: int, height: int) -> List[Tuple[int, int]]:
    """Compute symmetric castle positions for any map size.

    `_CASTLE_LAYOUTS` is hardcoded for 15x15 maps; this helper scales
    the same "inset corners" geometry to whatever the map actually is,
    so the legacy-map fallback works for 10x10 / 20x20 / etc.
    """
    inset_x = max(2, width // 4)
    inset_y = max(2, height // 4)
    corners = [
        (inset_x, inset_y),
        (width - 1 - inset_x, inset_y),
        (inset_x, height - 1 - inset_y),
        (width - 1 - inset_x, height - 1 - inset_y),
    ]
    positions: List[Tuple[int, int]] = []
    if num_castles <= 0:
        return positions
    if num_castles == 1:
        positions.append((width // 2, height // 2))
    elif num_castles == 2:
        positions = [corners[0], corners[3]]
    elif num_castles == 3:
        positions = [corners[0], corners[1], corners[2]]
    else:  # 4+
        positions = corners[:4]
        # 5+ players: clamp extra seats to the last corner
        for _ in range(num_castles - 4):
            positions.append(corners[3])
    return positions


def _classic_initial_units(num_castles: int = 2) -> List[Dict[str, Any]]:
    """Generate the static 'classic' roster as a flat initial_units list.

    Used both as the static entry in ``MAP_PRESETS`` (so schema
    validation sees a full set of colors) and as the runtime fallback
    inside ``generate_map_preset`` (so the actual spawn is identical).
    """
    # Use the static 15x15 castle positions for the canonical entry —
    # keeps MAP_PRESETS["classic"] stable. The size-aware variant is
    # used by `_load_map_presets` for legacy maps of arbitrary size.
    castles = _CASTLE_LAYOUTS.get(num_castles, _CASTLE_LAYOUTS[2])
    return _build_initial_units_from_castles(castles[:num_castles])


def _build_initial_units_from_castles(
    castles: List[Tuple[int, int]],
) -> List[Dict[str, Any]]:
    """Build the canonical 5-unit roster around each castle.

    Pure helper — separates castle geometry from roster composition
    so the legacy-map fallback can pass size-aware castle positions
    while still producing the classic 2 swordsman / 1 archer /
    1 knight / 1 healer layout per castle.
    """
    units: List[Dict[str, Any]] = []
    for seat, (cx, cy) in enumerate(castles):
        color = (_CLASSIC_COLORS[seat]
                 if seat < len(_CLASSIC_COLORS) else _CLASSIC_COLORS[-1])
        idx = 0
        for unit_type, count in _CLASSIC_ROSTER:
            for _ in range(count):
                dx, dy = _CLASSIC_OFFSETS[idx % len(_CLASSIC_OFFSETS)]
                units.append({
                    "x": cx + dx, "y": cy + dy,
                    "type": unit_type,
                    "color": color,
                    "level": 1,
                })
                idx += 1
    return units


def _build_varied_initial_units(
    castles: List[Tuple[int, int]],
    rng: random.Random,
    map_size: int = 15,
) -> List[Dict[str, Any]]:
    """P2.7+ — build a randomised starting roster per castle.

    Each HQ gets a template picked from ``_VARIED_ROSTERS`` by
    weighted random, producing 3–7 units with varied compositions
    (including warlocks, which never appeared in the old classic
    roster).  30% of the time one swordsman is promoted to Lv2.

    The placement pattern mirrors ``_CLASSIC_OFFSETS`` but
    truncated/extended for the random count.  Units that would
    fall outside the map boundaries are silently skipped so
    realistic HQ placement (which can put castles near the edge)
    doesn't produce out-of-bounds spawns.
    """
    weights = [w for _, w, _ in _VARIED_ROSTERS]
    templates = [t for t, _, _ in _VARIED_ROSTERS]
    unit_types_flat: list[str] = [
        ut for t, _, roster in _VARIED_ROSTERS
        for ut, _ in roster
    ]
    units: List[Dict[str, Any]] = []
    for seat, (cx, cy) in enumerate(castles):
        color = (_CLASSIC_COLORS[seat]
                 if seat < len(_CLASSIC_COLORS) else _CLASSIC_COLORS[-1])
        # Pick template.
        tpl = rng.choices(templates, weights=weights, k=1)[0]
        roster: list[tuple[str, int]] = [
            (ut, c) for tname, _, r in _VARIED_ROSTERS
            if tname == tpl for ut, c in r
        ]
        # Build unit list from roster.
        raw: list[tuple[str, int]] = []
        for ut, c in roster:
            raw.extend([(ut, 1)] * c)
        total = len(raw)
        # Clamp count to [3, 7].
        if total < 3:
            extra = rng.choice([u for u in unit_types_flat if u != "healer"])
            raw.append((extra, 1))
        elif total > 7:
            raw = raw[:7]
        # 30% chance to promote one swordsman to Lv2.
        promote = False
        if rng.random() < 0.30:
            swordsmen = [i for i, (ut, _) in enumerate(raw) if ut == "swordsman"]
            if swordsmen:
                promote = True
        idx = 0
        for unit_type, _ in raw:
            dx, dy = _CLASSIC_OFFSETS[idx % len(_CLASSIC_OFFSETS)]
            ux, uy = cx + dx, cy + dy
            # Skip units that would fall outside the map
            # (can happen when realistic_hq places a castle
            # near the edge and the offset pushes past the
            # boundary).
            if not (0 <= ux < map_size and 0 <= uy < map_size):
                idx += 1
                continue
            lvl = 2 if (promote and unit_type == "swordsman"
                        and idx == [i for i, (ut, _) in enumerate(raw)
                                   if ut == "swordsman"][0]) else 1
            units.append({
                "x": ux, "y": uy,
                "type": unit_type,
                "color": color,
                "level": lvl,
            })
            idx += 1
    return units


def _load_map_presets() -> Dict[str, Dict]:
    """Load all map preset JSON files from game/maps/ at import time.

    Each preset can declare its own 'size' in the JSON; the rows in
    'layout' must be that size. We no longer hard-require MAP_SIZE=15,
    so presets can be 15×15 / 20×20 / 30×30 / 45×45 etc.
    """
    presets: Dict[str, Dict] = {
        # "classic" is special: empty layout → falls back to procedural
        # generation. The static initial_units list mirrors the
        # procedural roster (4 colors, 5 units each) so schema-level
        # color checks see every color that's actually available at
        # runtime — see `_classic_initial_units()`.
        "classic": {
            "id": "classic",
            "name": "经典随机",
            "description": "按种子随机生成的标准地图",
            "biome": "grass",
            "size": MAP_SIZE,
            "layout": [],
            "initial_units": _classic_initial_units(num_castles=2),
        },
    }
    if _MAPS_DIR.is_dir():
        for path in sorted(_MAPS_DIR.glob("*.json")):
            data = _json.loads(path.read_text(encoding="utf-8"))
            # P2.6 — initial_units is the canonical source of truth for spawns.
            # For backward-compat, maps that pre-date P2.6 (or were authored
            # without this field) get a default roster auto-generated from
            # `_castle_positions_for_size(...)` + `_build_initial_units_from_castles(...)`,
            # scoped to the map's actual dimensions and `recommended_players`.
            # The runtime fallback in `generate_map_preset` uses the
            # size-aware castle positions for legacy maps too, so legacy
            # 10x10 / 20x20 / etc. maps behave identically to maps that
            # declare `initial_units` explicitly.
            initial_units = data.get("initial_units")
            if not initial_units:
                size = _resolve_size(data["size"])
                num_castles = max(
                    1, int(data.get("recommended_players", 2))
                )
                castles = _castle_positions_for_size(
                    num_castles, size["width"], size["height"]
                )
                initial_units = _build_initial_units_from_castles(castles)
                data["initial_units"] = initial_units
            size = _resolve_size(data["size"])
            seen_positions = set()
            for u in initial_units:
                for k in ("x", "y", "type", "color"):
                    if k not in u:
                        raise ValueError(
                            f"Map {data.get('id')!r}: initial_unit missing field {k!r}: {u}"
                        )
                x, y = int(u["x"]), int(u["y"])
                if not (0 <= x < size["width"] and 0 <= y < size["height"]):
                    raise ValueError(
                        f"Map {data.get('id')!r}: initial_unit ({x},{y}) out of bounds"
                    )
                if (x, y) in seen_positions:
                    raise ValueError(
                        f"Map {data.get('id')!r}: duplicate initial_unit at ({x},{y})"
                    )
                seen_positions.add((x, y))
            layout = data.get("layout", [])
            if layout:
                expected_w = size["width"]
                expected_h = size["height"]
                if len(layout) != expected_h or any(len(r) != expected_w for r in layout):
                    raise AssertionError(
                        f"Preset {data.get('id', path.stem)}: layout must be "
                        f"{expected_w}x{expected_h} (got {len(layout)} rows)"
                    )
            else:
                data["size"] = data.get("size", MAP_SIZE)
            # Default biome to "grass" if not specified in JSON
            data.setdefault("biome", "grass")
            presets[data["id"]] = data
    return presets


MAP_PRESETS: Dict[str, Dict] = _load_map_presets()


@dataclass
class MapPresetResult:
    """Result of building a map preset: terrain grid + initial unit placements.

    Returned by ``generate_map_preset()`` so callers can both lay down the
    tile grid AND seed the configured starting units without re-reading the
    preset JSON.
    """

    tiles: List[List[Tile]]
    initial_units: List[Dict[str, Any]] = field(default_factory=list)


def generate_map_preset(
    preset_id: str,
    seed: int,
    num_castles: int = MAX_CASTLES,
) -> MapPresetResult:
    """Build a Tile grid + initial units from a named preset (or fall back
    to procedural map generation with empty initial_units)."""
    if preset_id and preset_id in MAP_PRESETS and MAP_PRESETS[preset_id].get("layout"):
        data = MAP_PRESETS[preset_id]
        return MapPresetResult(
            tiles=_layout_to_tiles(data["layout"]),
            initial_units=list(data.get("initial_units", [])),
        )
    # P1.4 — route through the rich layered generator (clusters, rivers,
    # roads, buildings).  Flip to False to restore the legacy simple
    # random-fill behaviour for debugging.
    # P2.6 — even for procedurally generated "classic" maps, drop a
    # default roster of units at each castle so players aren't empty.
    # The same roster is also baked into MAP_PRESETS so schema-level
    # color checks see every color that's actually spawned.
    fallback_units: List[Dict[str, Any]] = []
    if preset_id == "classic":
        # P2.7+ — use the varied roster (random composition per HQ)
        # instead of the fixed 5-unit classic roster.  The static
        # MAP_PRESETS entry still holds the old 5-unit list for
        # schema validation; the *runtime* spawn gets variety.
        castles = _castle_positions_for_size(num_castles, MAP_SIZE, MAP_SIZE)
        fallback_units = _build_varied_initial_units(
            castles[:num_castles],
            rng=random.Random(seed),
            map_size=MAP_SIZE,
        )
    return MapPresetResult(
        tiles=generate_map(seed=seed, num_castles=num_castles, use_rich_generator=True),
        initial_units=fallback_units,
    )


def _layout_to_tiles(layout: List[List[str]]) -> List[List[Tile]]:
    """Convert a char-grid layout into Tile rows.

    Char map (uppercase = terrain, lowercase = castle sub-feature):

      Outer terrains (stored in `Tile.terrain`):
        P = plain         F = forest     M = mountain
        R = river         C = castle     v = village
        b = barracks      r = road       g = gate

      Castle sub-features (stored in `Tile.subtype`, terrain = "castle"):
        F or f = castle_floor       W or w = castle_wall
        T or t = castle_throne      D or d = castle_door
        S or s = castle_stairs      V or v_seg = castle_vault
        (Note: `v` collides with `village` — the loader below treats
        village first; for sub-feature use lowercase variant `x_vault`
        via the explicit mapping entry `seg_vault`.)
    """
    # P0.4 single-char legacy table (preserved exactly).
    char_to_terrain = {
        "P": TERRAIN_PLAIN,
        "F": TERRAIN_FOREST,
        "M": TERRAIN_MOUNTAIN,
        "S": TERRAIN_SNOW_PEAK,   # P2.4 — snow-biome silver peaks
        "R": TERRAIN_RIVER,
        "C": TERRAIN_CASTLE,
        "H": TERRAIN_CASTLE,        # P2.6+ — alias for "HQ" in hand-authored maps.
        "v": TERRAIN_VILLAGE,
        "b": TERRAIN_BARRACKS,
        "r": TERRAIN_ROAD,
        "j": TERRAIN_BRIDGE,         # P2.8+ — bridge (road over river)
        "g": TERRAIN_GATE,
        "$": CASTLE_VAULT,         # P2.6 economy test: 4 vaults in showcase
    }
    # Castle sub-feature chars (uppercase + lowercase variant).
    # Multi-char codes use the `:` prefix in JSON.
    char_to_subtype = {
        "f": CASTLE_FLOOR,
        "w": CASTLE_WALL,
        "t": CASTLE_THRONE,
        "d": CASTLE_DOOR,
        "s": CASTLE_STAIRS,
        # 'v' collides with village — JSON authors should use uppercase
        # or use the `>vault` multi-char token below.
        # We also accept `>` prefixed multi-char tokens at the cell level.
    }
    multi_char_subtype = {
        ":floor":  CASTLE_FLOOR,
        ":wall":   CASTLE_WALL,
        ":throne": CASTLE_THRONE,
        ":door":   CASTLE_DOOR,
        ":stairs": CASTLE_STAIRS,
        ":vault":  CASTLE_VAULT,
    }

    grid: List[List[Tile]] = []
    for y, row in enumerate(layout):
        out_row: List[Tile] = []
        i = 0
        while i < len(row):
            # Multi-char subtype token? (`>xxx` consumes 4 chars total).
            if row[i] == ":" and row[i:i + 7] in multi_char_subtype:
                sub = multi_char_subtype[row[i:i + 7]]
                # The first character `:` is also where the *terrain*
                # char would normally live — there's no terrain letter
                # for this tile, so we treat the whole `:xxx` as the
                # marker. Use a sentinel char '.' before it for terrain.
                # Authors should write `.>floor` in JSON; this branch
                # handles the rare `>xxx` at start.
                # For simplicity and predictability, just skip 7 chars.
                i += 7
                out_row.append(Tile(x=len(out_row), y=y, terrain=TERRAIN_CASTLE, subtype=sub))
                continue
            ch = row[i]
            # Castle sub-feature chars: terrain = castle, subtype = feature.
            if ch in char_to_subtype:
                out_row.append(Tile(
                    x=len(out_row), y=y,
                    terrain=TERRAIN_CASTLE,
                    subtype=char_to_subtype[ch],
                ))
                i += 1
                continue
            # Castle throne as capital `T` (capital escapes legacy P/F/M/R).
            if ch == "T":
                out_row.append(Tile(
                    x=len(out_row), y=y,
                    terrain=TERRAIN_CASTLE,
                    subtype=CASTLE_THRONE,
                ))
                i += 1
                continue
            terrain = char_to_terrain.get(ch, TERRAIN_PLAIN)
            out_row.append(Tile(x=len(out_row), y=y, terrain=terrain))
            i += 1
        grid.append(out_row)
    return grid


# ============================================================
# AI player
# ============================================================

def build_ai_player(game: Game, seat: int, color: str, name: str) -> Player:
    """Build a fresh AI Player row (not yet persisted)."""
    return Player(
        game_id=game.id,
        user_name=name,
        color=color,
        seat=seat,
        is_ai=True,
    )


# AI decision helpers --------------------------------------------------

@dataclass
class _AISnapshot:
    """Compact snapshot used by the AI to decide moves without DB hits."""
    terrain: Dict[Tuple[int, int], str]
    owners: Dict[Tuple[int, int], Optional[int]]
    occ: Dict[Tuple[int, int], Optional[int]]
    enemy_units: List[Unit]
    ally_units: List[Unit]
    my_units: List[Unit]
    enemy_castles: List[Tuple[int, int]]
    unowned_castles: List[Tuple[int, int]]


async def _load_ai_snapshot(session: AsyncSession, game: Game, ai_player: Player) -> _AISnapshot:
    tiles = (
        await session.execute(select(Tile).where(Tile.game_id == game.id))
    ).scalars().all()
    terrain = {(t.x, t.y): movement_key(t) for t in tiles}
    owners = {(t.x, t.y): t.owner_id for t in tiles}
    occ = {(t.x, t.y): t.occupied_unit_id for t in tiles}
    players = (
        await session.execute(select(Player).where(Player.game_id == game.id))
    ).scalars().all()
    # Load units explicitly to avoid lazy-load in async context
    player_ids = [p.id for p in players]
    units_rows = (
        await session.execute(
            select(Unit).where(Unit.player_id.in_(player_ids))
        )
    ).scalars().all()
    units_by_player: Dict[int, List[Unit]] = {}
    for u in units_rows:
        units_by_player.setdefault(u.player_id, []).append(u)
    # Resolve the AI's team_id. In 1V1 free-for-all every player is
    # their own team (team_id == None) and attacks anyone else. In
    # team mode players sharing a team_id are allies.
    my_team = _team_of(ai_player) if ai_player is not None else None
    ally_player_ids: set[int] = set()
    enemy_player_ids: set[int] = set()
    for p in players:
        if p.id == ai_player.id:
            continue
        p_team = _team_of(p)
        if my_team is not None and p_team is not None and p_team == my_team:
            ally_player_ids.add(p.id)  # teammate — must not be attacked
        else:
            enemy_player_ids.add(p.id)
    ally_units = [u for u in units_by_player.get(ai_player.id, []) if u.hp > 0]
    enemy_units = [
        u for pid in enemy_player_ids
        for u in units_by_player.get(pid, []) if u.hp > 0
    ]
    enemy_castles = [
        (t.x, t.y) for t in tiles
        if t.terrain == TERRAIN_CASTLE and t.owner_id is not None
        and t.owner_id != ai_player.id
        and t.owner_id not in ally_player_ids
    ]
    unowned_castles = [
        (t.x, t.y) for t in tiles
        if t.terrain == TERRAIN_CASTLE and t.owner_id is None
    ]
    return _AISnapshot(
        terrain=terrain, owners=owners, occ=occ,
        enemy_units=enemy_units, ally_units=ally_units, my_units=ally_units,
        enemy_castles=enemy_castles, unowned_castles=unowned_castles,
    )


# ============================================================
# AI personality profiles (P2.5)
# ============================================================
# Each personality is a frozen dataclass of weights/biases that the AI
# decision helpers read. The three profiles share the same code path —
# only the numbers differ — so behaviour stays predictable across maps.
# `agent_personality` on Player picks the profile; default is "balanced".
#
# Design (graduated): every numeric field goes  aggressive > balanced >
# conservative. Two of the most game-defining numbers (`castle_pull`,
# `claim_emergency_bonus`) are intentionally high across all three —
# seizing enemy HQ and reclaiming an enemy claim both equal "win or
# avoid loss", so even the conservative AI cares about them deeply.
from dataclasses import dataclass


@dataclass(frozen=True)
class AIProfile:
    # --- Claim (occupation) ---
    claim_distance: int         # max tiles willing to walk to claim
    distance_weight: float      # score penalty per tile distance to tile
    risk_penalty: float         # score penalty per enemy within 2 tiles
    claim_emergency_bonus: int  # bonus if enemy is actively claiming this tile

    # --- Castle / HQ ---
    castle_pull: int            # bonus for moving toward enemy HQ
    HQ_defense_range: int       # how close enemy can be before we react

    # --- Combat ---
    aggro_range: int            # how far we look for enemies
    aggression: float           # multiplier on attack/move score (0..1)
    in_range_penalty: float     # penalty per enemy that can hit this tile
    kill_bonus_move: int        # bonus if move tile enables a kill next turn
    flee_hp_pct: float          # HP % below which we retreat

    # --- Economy ---
    recruit_threshold: int      # min gold before considering recruit
    recruit_max_roster: int     # cap on units in the field

    # --- Healer behaviour ---
    healer_offense: bool        # if True, healer may also attack


_AI_PROFILES: Dict[str, AIProfile] = {
    "aggressive": AIProfile(
        claim_distance=8, distance_weight=8,  risk_penalty=5,
        claim_emergency_bonus=200,
        castle_pull=400, HQ_defense_range=5,
        aggro_range=7, aggression=1.0, in_range_penalty=-3, kill_bonus_move=80,
        flee_hp_pct=0.10,
        recruit_threshold=200, recruit_max_roster=10,
        healer_offense=True,
    ),
    "balanced": AIProfile(
        claim_distance=6, distance_weight=18, risk_penalty=12,
        claim_emergency_bonus=175,
        castle_pull=300, HQ_defense_range=4,
        aggro_range=5, aggression=0.7, in_range_penalty=-5, kill_bonus_move=50,
        flee_hp_pct=0.20,
        recruit_threshold=300, recruit_max_roster=8,
        healer_offense=False,
    ),
    "conservative": AIProfile(
        claim_distance=4, distance_weight=28, risk_penalty=20,
        claim_emergency_bonus=150,
        castle_pull=250, HQ_defense_range=3,
        aggro_range=4, aggression=0.4, in_range_penalty=-8, kill_bonus_move=25,
        flee_hp_pct=0.30,
        recruit_threshold=350, recruit_max_roster=7,
        healer_offense=False,
    ),
}


def _ai_profile(player: Player) -> AIProfile:
    """Look up the AIProfile for a player; default to balanced."""
    if player is None:
        return _AI_PROFILES["balanced"]
    return _AI_PROFILES.get(player.agent_personality or "balanced",
                            _AI_PROFILES["balanced"])


def _unit_value(u: Unit) -> float:
    """Higher = more valuable target. Used for attack priority."""
    base = u.atk + u.def_ + u.hp / 10
    # Healer is a high-value target
    if u.unit_type == UNIT_HEALER:
        base += 30
    if u.unit_type == UNIT_KNIGHT:
        base += 10
    return base


def _ai_pick_attack_target(
    unit: Unit, snap: _AISnapshot, profile: AIProfile,
) -> Optional[Unit]:
    """Choose best enemy to attack within range. None if nothing valid.

    P2.5 — scaled by `profile.aggression` (0..1) so the conservative AI
    rarely attacks (low base score) while the aggressive AI always takes
    the shot. Kill-shots (1-hit kill) bypass the scaling — guaranteed.
    """
    atk_range = unit_attack_range(unit)
    blockers = {
        c for c, t in snap.terrain.items()
        if t in (TERRAIN_FOREST, TERRAIN_MOUNTAIN, TERRAIN_RIVER)
    }
    candidates = []
    for e in snap.enemy_units:
        d = manhattan((unit.x, unit.y), (e.x, e.y))
        if d == 0 or d > atk_range:
            continue
        if d > 1 and not _get_unit(unit.unit_type).ignores_line_of_sight:
            # Ranged: check line of sight (archer's "snipe" ignores obstacles)
            blockers.discard((e.x, e.y))
            if not has_line_of_sight((unit.x, unit.y), (e.x, e.y), blockers):
                continue
        # Score: lower hp = better kill chance; type-advantage = bonus
        score = _unit_value(e) * 1.0
        score -= e.hp * 0.5   # lower HP = higher score
        killable = e.hp <= unit.atk
        score += 100 if killable else 0  # can kill this turn
        type_mult = _type_adv(unit.unit_type, e.unit_type)
        score *= type_mult
        # Prefer targets within aggro range (closer = more relevant)
        # aggro_range now comes from the profile (P2.5).
        score += max(0, profile.aggro_range - d) * 5
        # Apply personality aggression. A kill shot is always taken;
        # anything else is scaled down for the conservative AI.
        if not killable:
            score *= profile.aggression
        candidates.append((score, e))
    if not candidates:
        logger.info(f"AI unit {unit.name}(id={unit.id},type={unit.unit_type}) at ({unit.x},{unit.y}): no valid attack target")
        return None
    candidates.sort(key=lambda t: -t[0])
    return candidates[0][1]


def _ai_pick_move_target(
    unit: Unit, snap: _AISnapshot, profile: AIProfile,
    my_castle_xy: Optional[Tuple[int, int]] = None,
    enemy_castle_xy: Optional[Tuple[int, int]] = None,
) -> Optional[Tuple[int, int]]:
    """Pick a destination tile to move toward (high score wins).

    P2.5 — the score function is now profile-aware:
      * `profile.in_range_penalty` (more negative = more scared of
        being surrounded)
      * `profile.aggro_range` (how far we look for enemies)
      * `profile.castle_pull` (big bonus for moving toward enemy HQ —
        seize = win)
      * `profile.HQ_defense_range` triggers a return-to-Home boost
        when an enemy is within that radius of our castle.
    """
    # Don't move healers/archers into melee of multiple enemies
    blocked = {
        c for c, uid in snap.occ.items()
        if uid is not None and uid != unit.id
    }
    reachable = bfs_reachable(
        start=(unit.x, unit.y),
        terrain=snap.terrain,
        owners=snap.owners,
        mov=unit.mp,
        viewer_owner_id=None,  # AI shouldn't be blocked from entering enemy castles
        blocked_units=blocked,
        movement_profile=resolve_movement_profile(unit),
    )
    if not reachable:
        return None

    # Compute "score" for each reachable tile
    def score(tile: Tuple[int, int]) -> float:
        s = 0.0
        # Reward unowned castles
        if tile in snap.unowned_castles:
            s += 200
        # HQ defense: if an enemy is within HQ_defense_range of our
        # castle, bias toward tiles between us and the threat (or
        # back toward the castle).
        if my_castle_xy and snap.enemy_units:
            closest_threat = min(
                manhattan(my_castle_xy, (e.x, e.y)) for e in snap.enemy_units
            )
            if closest_threat <= profile.HQ_defense_range:
                # Bigger bonus the closer the threat is.
                s += (profile.HQ_defense_range - closest_threat + 1) * 40
                # Tiles that move us toward the castle / between castle
                # and threat get an extra nudge.
                d_to_castle = manhattan(tile, my_castle_xy)
                if d_to_castle <= profile.HQ_defense_range:
                    s += (profile.HQ_defense_range - d_to_castle) * 10
        # Castle pull — moving toward the enemy HQ is worth it because
        # standing on it is an instant win. 3 档都重视，但激进最强。
        if enemy_castle_xy:
            d_to_enemy_hq = manhattan(tile, enemy_castle_xy)
            # Closer is better. Add the score proportional to how much
            # closer this tile is than the unit's current position.
            cur_d = manhattan((unit.x, unit.y), enemy_castle_xy)
            if d_to_enemy_hq < cur_d:
                s += (cur_d - d_to_enemy_hq) * (profile.castle_pull / 8.0)
        # Reward getting close to the nearest enemy (but not on top).
        # Uses profile.aggro_range so the conservative AI looks less
        # far than the aggressive one.
        if snap.enemy_units:
            nearest = min(manhattan(tile, (e.x, e.y)) for e in snap.enemy_units)
            s += max(0, profile.aggro_range - nearest) * 6
            # Slight penalty if surrounded by many enemies at this tile.
            in_range = sum(
                1 for e in snap.enemy_units
                if manhattan(tile, (e.x, e.y)) <= unit_attack_range(e)
            )
            s -= in_range * abs(profile.in_range_penalty)
        # Reward defensive terrain
        terr = snap.terrain.get(tile)
        if terr == TERRAIN_FOREST:
            s += TERRAIN_DEF_BONUS.get(TERRAIN_FOREST, 0) * 2
        if terr == TERRAIN_MOUNTAIN:
            s += TERRAIN_DEF_BONUS.get(TERRAIN_MOUNTAIN, 0) * 2
        if terr == TERRAIN_CASTLE:
            s += 30
        # Kill-shot bonus: if moving here lets us attack-kill an enemy
        # next turn, that's worth pursuing. Aggressive gets the biggest
        # bonus, conservative the smallest.
        if snap.enemy_units:
            atk_range = unit_attack_range(unit)
            for e in snap.enemy_units:
                d = manhattan(tile, (e.x, e.y))
                if 1 <= d <= atk_range and e.hp <= unit.atk:
                    s += profile.kill_bonus_move
                    break
        # Small bonus for keeping close to allies (concentration)
        if snap.ally_units:
            min_ally = min(manhattan(tile, (a.x, a.y)) for a in snap.ally_units if a.id != unit.id) \
                if any(a.id != unit.id for a in snap.ally_units) else 5
            s += max(0, 3 - min_ally) * 1
        return s

    # P2.5 — exclude the unit's current tile from candidates. bfs_reachable
    # includes the start position with cost 0; selecting it makes the
    # AI "move to itself" (self-move bug).
    candidates = {t for t in reachable.keys() if t != (unit.x, unit.y)}
    if not candidates:
        return None
    best_tile = max(candidates, key=score)
    if score(best_tile) <= score((unit.x, unit.y)):
        logger.info(f"AI unit {unit.name}(id={unit.id}) at ({unit.x},{unit.y}): stays (best={best_tile},score={score(best_tile):.1f} vs current={score((unit.x,unit.y)):.1f})")
        return None  # standing still is better
    logger.info(f"AI unit {unit.name}(id={unit.id}) at ({unit.x},{unit.y}): move -> {best_tile} (score={score(best_tile):.1f})")
    return best_tile


async def _ai_move(session: AsyncSession, game: Game, unit: Unit, dest: Tuple[int, int]) -> bool:
    """Perform an AI move. Returns True if successful."""
    tile_rows = (
        await session.execute(select(Tile).where(Tile.game_id == game.id))
    ).scalars().all()
    terrain = {(t.x, t.y): movement_key(t) for t in tile_rows}
    owners = {(t.x, t.y): t.owner_id for t in tile_rows}
    # Build blocked set from currently-alive units
    all_units = (
        await session.execute(
            select(Unit).where(Unit.player_id.in_(
                select(Player.id).where(Player.game_id == game.id)
            ))
        )
    ).scalars().all()
    blocked = {(u.x, u.y) for u in all_units if u.id != unit.id and u.hp > 0}
    path = pathfind(
        start=(unit.x, unit.y), goal=dest, terrain=terrain, owners=owners,
        mov=unit.mp, viewer_owner_id=unit.player_id, blocked_units=blocked,
        movement_profile=resolve_movement_profile(unit),
    )
    if not path or path[-1] != dest:
        return False
    # Apply move on tiles
    for t in tile_rows:
        if (t.x, t.y) == (unit.x, unit.y):
            t.occupied_unit_id = None
        if (t.x, t.y) == dest:
            t.occupied_unit_id = unit.id
    unit.x, unit.y = dest
    # Deduct movement cost — same logic as the human route (actions.py).
    movement_profile = resolve_movement_profile(unit)
    cost_x2 = sum(terrain_cost_x2(movement_profile, terrain[c]) or 0 for c in path[1:])
    spent_mp = cost_x2 // 2
    unit.mp = max(0, unit.mp - spent_mp)
    # AI: a unit that has moved may still attack this turn (matches the
    # human player rules), but it must NOT be picked up for another move
    # by `_ai_take_one_action`. Setting `has_acted=False` here is
    # intentional — it lets the AI one-shot a unit's attack+move pair
    # without triggering a second move when attack is out of range.
    # The duplicate-move guard lives in `_ai_take_one_action` which now
    # filters `not has_moved` out of the `pending` pool.
    unit.has_moved = True
    return True


async def _ai_attack(session: AsyncSession, attacker: Unit, target: Unit) -> bool:
    """Perform an AI attack. Returns True if successful."""
    logger.info(f"AI attack: {attacker.name}(id={attacker.id},type={attacker.unit_type}) at ({attacker.x},{attacker.y}) -> {target.name}(id={target.id},type={target.unit_type},hp={target.hp}) at ({target.x},{target.y})")
    target_tile = (
        await session.execute(
            select(Tile).where(Tile.occupied_unit_id == target.id)
        )
    ).scalars().first()
    if target_tile is None:
        return False
    bonus = TERRAIN_DEF_BONUS.get(target_tile.terrain, 0)
    rng = random.Random()
    hits = attack_with_double_strike(attacker, target, bonus, rng=rng)
    for h in hits:
        apply_damage(target, h.damage)

    counter_dmg = 0
    defender_skills = set(target.skills or [])
    has_counter_immunity = any(s in COUNTER_IMMUNE_SKILLS for s in defender_skills)
    if (
        target.hp > 0
        and not has_counter_immunity
        and can_attack_from_position(target, target.x, target.y, attacker.x, attacker.y)
    ):
        counter_hits = attack_with_double_strike(target, attacker, bonus, rng=random.Random())
        for h in counter_hits:
            counter_dmg += max(1, int(h.damage * COUNTER_DAMAGE_MULT))
        apply_damage(attacker, counter_dmg)

    if target.hp <= 0:
        award_exp(attacker, "kill")
    else:
        award_exp(attacker, "hit")
    attacker.has_acted = True
    # Immediately remove dead unit from the board/DB
    dead_after_combat = [u for u in (target, attacker) if u.hp <= 0]
    if dead_after_combat:
        await cleanup_dead_units(session, dead_after_combat)
    return True


async def _ai_use_skill(session: AsyncSession, game: Game, unit: Unit, snap: _AISnapshot) -> bool:
    """Use the unit's best active skill (delegated to the skill registry).

    Returns True if any skill was used.
    """
    from app.classes.units.skills import get_active_for
    from app.classes.units.skills.base import SkillContext

    active_skills = get_active_for(unit)
    if not active_skills:
        return False

    for sk in active_skills:
        # For heal: pick the ally with the biggest HP deficit
        if sk.skill_id == "heal":
            candidates = [
                a for a in snap.ally_units
                if a.id != unit.id
                and 0 < a.hp < a.max_hp
                and manhattan((unit.x, unit.y), (a.x, a.y)) == 1
            ]
            if not candidates:
                continue
            target = max(candidates, key=lambda a: (a.max_hp - a.hp))
            ctx = SkillContext(user=unit, target=target, ally_units=list(snap.ally_units))
        else:
            ctx = SkillContext(user=unit, ally_units=list(snap.ally_units))

        if not sk.can_use(ctx):
            continue
        result = await sk.execute(session, ctx)
        if result.ok:
            return True
    return False


# ============================================================
# P2.5 — flee / claim / recruit helpers (profile-aware)
# ============================================================

def _ai_should_flee(unit: Unit, profile: AIProfile) -> bool:
    """True when the unit's HP is below the profile's flee threshold.

    Conservative AI flees at 30% HP, aggressive keeps fighting until
    10%. Used as the very first gate in the AI action loop.
    """
    if unit.max_hp <= 0:
        return False
    return (unit.hp / unit.max_hp) <= profile.flee_hp_pct


def _ai_pick_claim_target(
    unit: Unit, snap: _AISnapshot, profile: AIProfile,
    active_claims: set,
    my_castle_xy: Optional[Tuple[int, int]],
) -> Optional[Tuple[int, int]]:
    """Pick a claimable tile to walk toward, or None.

    Scoring (3 档共享，越激越愿占远处 / 越保越怕敌人旁):
      base = 50 village / 100 barracks / 150 castle_vault
      − d * distance_weight
      − (enemies within 2 tiles) * risk_penalty
      + claim_emergency_bonus  if tile in active_claims
      + 50                       if within 3 tiles of my castle (protect economy)
      + 80                       if unowned castle (seize bait)

    Tiles beyond `claim_distance` are immediately rejected.
    """
    from app.config import TERRAIN_VILLAGE, TERRAIN_BARRACKS, CASTLE_VAULT
    building_value = {
        TERRAIN_VILLAGE: 50,
        TERRAIN_BARRACKS: 100,
        CASTLE_VAULT: 150,
    }
    best: Optional[Tuple[int, int]] = None
    best_score = float("-inf")
    for (x, y), t in snap.terrain.items():
        if t not in building_value:
            continue
        d = manhattan((unit.x, unit.y), (x, y))
        # Distance filter — but emergency claim (enemy is currently
        # claiming this tile) overrides the cap. Losing a tile to the
        # enemy is more costly than walking a bit further.
        is_emergency = (x, y) in active_claims
        if d == 0 or (d > profile.claim_distance and not is_emergency):
            continue
        s = building_value[t]
        s -= d * profile.distance_weight
        nearby_enemies = sum(
            1 for e in snap.enemy_units
            if manhattan((e.x, e.y), (x, y)) <= 2
        )
        s -= nearby_enemies * profile.risk_penalty
        if is_emergency:
            s += profile.claim_emergency_bonus
        if my_castle_xy and manhattan((x, y), my_castle_xy) <= 3:
            s += 50
        if (x, y) in snap.unowned_castles:
            s += 80  # seize bait
        # Negative score means "more cost than value" — don't bother.
        if s <= 0:
            continue
        if s > best_score:
            best_score = s
            best = (x, y)
    return best


async def _ai_try_claim(
    session: AsyncSession, game: Game, ai_player: Player,
    unit: Unit, profile: AIProfile, active_claims: set,
    my_castle_xy: Optional[Tuple[int, int]],
) -> bool:
    """If the unit is on a claimable tile, start a claim. Returns True
    if the action consumed a turn.
    """
    from app.game_logic import is_claimable
    from app.models import ClaimSession
    # Need a current target tile. We pick the best reachable one; the
    # actual claim-start only fires when the unit is already ON it.
    target = _ai_pick_claim_target(unit, await _load_ai_snapshot(session, game, ai_player),
                                    profile, active_claims, my_castle_xy)
    if target is None:
        return False
    if (unit.x, unit.y) != target:
        return False  # not standing on the target yet — move there next
    tile = (await session.execute(
        select(Tile).where(
            Tile.game_id == game.id, Tile.x == target[0], Tile.y == target[1],
        )
    )).scalars().first()
    if tile is None or not is_claimable(tile.terrain):
        return False
    if tile.owner_id == ai_player.id:
        return False
    # Start the claim via the same logic the HTTP route uses.
    from app.config import CLAIM_TURNS_REQUIRED
    cs = ClaimSession(
        game_id=game.id,
        tile_id=tile.id,
        unit_id=unit.id,
        target_player_id=ai_player.id,
        started_turn=game.turn_number,
        completes_turn=game.turn_number + CLAIM_TURNS_REQUIRED - 1,
    )
    session.add(cs)
    unit.has_acted = True
    unit.mp = 0
    logger.info(
        f"AI CLAIM: player {ai_player.id} unit {unit.name} starts claim on "
        f"({target[0]},{target[1]}) (completes turn {cs.completes_turn})"
    )
    return True


async def _ai_try_recruit(
    session: AsyncSession, game: Game, ai_player: Player, profile: AIProfile,
) -> bool:
    """Recruit at one of the AI's empty barracks. Returns True on success.

    Called once at the END of `ai_take_turn` / `ai_take_one_action` so
    the recruit doesn't block combat for that turn.
    """
    from app.config import RECRUIT_COST, TERRAIN_BARRACKS
    from app.models import Unit as _U
    from sqlalchemy import func as _func

    unit_count = (await session.execute(
        select(_func.count(_U.id)).where(_U.player_id == ai_player.id, _U.hp > 0)
    )).scalar() or 0
    if unit_count >= profile.recruit_max_roster:
        return False
    if (ai_player.gold or 0) < profile.recruit_threshold:
        return False
    # Find empty owned barracks.
    tiles_rows = (await session.execute(
        select(Tile).where(
            Tile.game_id == game.id,
            Tile.terrain == TERRAIN_BARRACKS,
            Tile.owner_id == ai_player.id,
            Tile.occupied_unit_id.is_(None),
        )
    )).scalars().all()
    if not tiles_rows:
        return False
    # Pick the unit type. Aggressive prefers knight/archer, others
    # prefer cheap swordsman. Falls back to whatever the player can
    # afford.
    pref_order = {
        "aggressive":   ["knight", "archer", "swordsman"],
        "balanced":     ["swordsman", "archer", "knight"],
        "conservative": ["swordsman", "archer", "knight"],
    }.get(ai_player.agent_personality or "balanced",
          ["swordsman", "archer", "knight"])
    chosen_type = None
    chosen_cost = None
    for t in pref_order:
        c = RECRUIT_COST.get(t, 0)
        if (ai_player.gold or 0) >= c and c > 0:
            chosen_type = t
            chosen_cost = c
            break
    if chosen_type is None:
        return False
    tile = tiles_rows[0]
    # Spawn the unit (mirror of routes/actions.py:recruit_unit).
    profile_obj = _get_unit(chosen_type)
    n_existing = (await session.execute(
        select(_func.count(_U.id)).where(
            _U.player_id == ai_player.id, _U.unit_type == chosen_type,
        )
    )).scalar() or 0
    ai_player.gold = (ai_player.gold or 0) - chosen_cost
    new_unit = _U(
        player_id=ai_player.id,
        unit_type=chosen_type,
        name=_unit_name(chosen_type, int(n_existing)),
        level=1, exp=0,
        hp=profile_obj.base_hp, max_hp=profile_obj.base_hp,
        atk=profile_obj.base_atk, def_=profile_obj.base_def,
        matk=profile_obj.base_matk, mdef=profile_obj.base_mdef,
        mov=profile_obj.mp_pool, mp=0, morale=0,
        x=tile.x, y=tile.y,
        has_acted=True, has_moved=True,
        skills=list(profile_obj.default_skills),
    )
    session.add(new_unit)
    await session.flush()
    tile.occupied_unit_id = new_unit.id
    logger.info(
        f"AI RECRUIT: player {ai_player.id} spawned {chosen_type} "
        f"({new_unit.name}) at ({tile.x},{tile.y}) for {chosen_cost}g "
        f"(gold_left={ai_player.gold})"
    )
    return True


async def _load_my_castle_xy(
    session: AsyncSession, game: Game, ai_player: Player,
) -> Optional[Tuple[int, int]]:
    """The AI's HQ tile. Used by claim / move scoring."""
    tile = (await session.execute(
        select(Tile).where(
            Tile.game_id == game.id,
            Tile.terrain == TERRAIN_CASTLE,
            Tile.owner_id == ai_player.id,
        )
    )).scalars().first()
    if tile is None:
        return None
    return (tile.x, tile.y)


async def _load_enemy_castles_xy(
    session: AsyncSession, game: Game, ai_player: Player,
) -> list:
    """All enemy HQ positions — for the castle_pull move bonus."""
    rows = (await session.execute(
        select(Tile).where(
            Tile.game_id == game.id,
            Tile.terrain == TERRAIN_CASTLE,
        )
    )).scalars().all()
    return [(t.x, t.y) for t in rows
            if t.owner_id is not None and t.owner_id != ai_player.id]


async def _load_active_claim_tile_set(
    session: AsyncSession, game: Game,
) -> set:
    """Tiles with an active ClaimSession right now — used for the
    `claim_emergency_bonus` so AI swarms to grab tiles the enemy is
    about to flip."""
    rows = (await session.execute(
        select(ClaimSession.tile_id).where(ClaimSession.game_id == game.id)
    )).scalars().all()
    # Resolve tile coords for the bonuses.
    if not rows:
        return set()
    tile_id_to_xy = dict((t.id, (t.x, t.y)) for t in (
        await session.execute(
            select(Tile).where(Tile.game_id == game.id, Tile.id.in_(rows))
        )
    ).scalars())
    return {tile_id_to_xy[tid] for tid in rows if tid in tile_id_to_xy}


# ============================================================
# AI turn entry points
# ============================================================

async def ai_take_turn(session: AsyncSession, game: Game, ai_player: Player) -> int:
    """Execute one AI player's full turn. Returns the number of actions taken.

    P2.5 — fully profile-aware: every decision consults the player's
    `agent_personality` (aggressive / balanced / conservative).
    """
    profile = _ai_profile(ai_player)
    logger.info(
        f"AI turn: player {ai_player.id}(seat={ai_player.seat}) starts "
        f"(game={game.id}, turn={game.turn_number}, personality={ai_player.agent_personality})"
    )
    actions = 0
    # Refresh this AI's units fresh each pass
    units_rows = (await session.execute(
        select(Unit).where(Unit.player_id == ai_player.id)
    )).scalars().all()
    # Process units in priority order: healers first, then attackers
    priority = sorted(
        [u for u in units_rows if u.hp > 0 and not u.has_acted and not u.has_moved],
        key=lambda u: (
            0 if u.unit_type == UNIT_HEALER else 1,  # healers first
            -u.atk,
        ),
    )
    my_castle = await _load_my_castle_xy(session, game, ai_player)
    enemy_castles = await _load_enemy_castles_xy(session, game, ai_player)
    active_claims = await _load_active_claim_tile_set(session, game)
    enemy_castle_xy = enemy_castles[0] if enemy_castles else None
    for unit in priority:
        if actions >= AI_MAX_ACTIONS_PER_TURN:
            break
        # Re-fetch the latest snapshot (state may have shifted)
        snap = await _load_ai_snapshot(session, game, ai_player)
        # 0. Flee?
        if _ai_should_flee(unit, profile):
            # Try to move toward our castle / away from enemies.
            from app.utils import bfs_reachable
            blocked = {
                c for c, uid in snap.occ.items()
                if uid is not None and uid != unit.id
            }
            reachable = bfs_reachable(
                start=(unit.x, unit.y), terrain=snap.terrain,
                owners=snap.owners, mov=unit.mp,
                viewer_owner_id=None, blocked_units=blocked,
                movement_profile=resolve_movement_profile(unit),
            )
            if reachable:
                # Score each reachable tile by distance-to-castle
                # (closer = better, more negative distance).
                def flee_score(t):
                    if my_castle is None:
                        return 0
                    return -manhattan(t, my_castle)
                best = max(reachable.keys(), key=flee_score)
                if best != (unit.x, unit.y):
                    if await _ai_move(session, game, unit, best):
                        actions += 1
                        continue
            unit.has_acted = True
            actions += 1
            continue
        # 1. Skill? (healer_offense profile controls whether healer
        #    treats offense > healing; in current code, healer always
        #    tries heal first when there are injured allies nearby.)
        if unit.unit_type == UNIT_HEALER:
            # Conservative AI's healer can still attack if no healing target
            if not profile.healer_offense and await _ai_use_skill(session, game, unit, snap):
                actions += 1
                continue
            if profile.healer_offense and await _ai_use_skill(session, game, unit, snap):
                actions += 1
                continue
        # 2. Attack?
        target = _ai_pick_attack_target(unit, snap, profile)
        if target is not None:
            if await _ai_attack(session, unit, target):
                actions += 1
                continue
        # 3. Claim (if standing on a claimable tile).
        if await _ai_try_claim(session, game, ai_player, unit, profile,
                               active_claims, my_castle):
            actions += 1
            continue
        # 4. Move (profile-aware incl. castle_pull + HQ_defense).
        dest = _ai_pick_move_target(
            unit, snap, profile, my_castle, enemy_castle_xy,
        )
        if dest is not None and dest != (unit.x, unit.y):
            if await _ai_move(session, game, unit, dest):
                actions += 1
                continue
        # 5. Wait
        unit.has_acted = True
        actions += 1

    # 6. One recruit at end of turn if affordable (post-combat).
    await _ai_try_recruit(session, game, ai_player, profile)
    return actions


async def ai_take_one_action(
    session: AsyncSession,
    game: Game,
    ai_player: Player,
) -> bool:
    """Execute ONE action of an AI's turn and return True, or False if done.

    P2.5 — same priority order as `ai_take_turn`, but only one action
    per call (so the human can watch via the chain animation).
    """
    profile = _ai_profile(ai_player)
    # Stop if this AI has ended their turn (set by `end_turn` earlier).
    if ai_player.has_ended_turn:
        return False
    # Find first unit that hasn't acted yet.
    units_rows = (await session.execute(
        select(Unit).where(Unit.player_id == ai_player.id)
    )).scalars().all()
    pending = [u for u in units_rows if u.hp > 0 and not u.has_acted and not u.has_moved]
    if not pending:
        # End of turn — try one recruit.
        if await _ai_try_recruit(session, game, ai_player, profile):
            return True
        return False
    # Priority: healers first, then highest ATK first
    pending.sort(key=lambda u: (
        0 if u.unit_type == UNIT_HEALER else 1,
        -u.atk,
    ))
    unit = pending[0]
    snap = await _load_ai_snapshot(session, game, ai_player)
    my_castle = await _load_my_castle_xy(session, game, ai_player)
    enemy_castles = await _load_enemy_castles_xy(session, game, ai_player)
    active_claims = await _load_active_claim_tile_set(session, game)
    enemy_castle_xy = enemy_castles[0] if enemy_castles else None

    # 0. Flee?
    if _ai_should_flee(unit, profile):
        from app.utils import bfs_reachable
        blocked = {
            c for c, uid in snap.occ.items()
            if uid is not None and uid != unit.id
        }
        reachable = bfs_reachable(
            start=(unit.x, unit.y), terrain=snap.terrain,
            owners=snap.owners, mov=unit.mp,
            viewer_owner_id=None, blocked_units=blocked,
            movement_profile=resolve_movement_profile(unit),
        )
        if reachable:
            def flee_score(t):
                if my_castle is None:
                    return 0
                return -manhattan(t, my_castle)
            best = max(reachable.keys(), key=flee_score)
            if best != (unit.x, unit.y):
                if await _ai_move(session, game, unit, best):
                    return True
        unit.has_acted = True
        return True
    # 1. Skill?
    if unit.unit_type == UNIT_HEALER:
        if await _ai_use_skill(session, game, unit, snap):
            return True
    # 2. Attack?
    target = _ai_pick_attack_target(unit, snap, profile)
    if target is not None:
        if await _ai_attack(session, unit, target):
            return True
    # 3. Claim?
    if await _ai_try_claim(session, game, ai_player, unit, profile,
                           active_claims, my_castle):
        return True
    # 4. Move?
    dest = _ai_pick_move_target(
        unit, snap, profile, my_castle, enemy_castle_xy,
    )
    if dest is not None and dest != (unit.x, unit.y):
        if await _ai_move(session, game, unit, dest):
            return True
    # 5. Wait (still counts as an action so we can move on)
    unit.has_acted = True
    return True
