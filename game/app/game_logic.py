"""
Pure-ish game logic helpers (no FastAPI imports).

Functions that need the DB session are async; pure helpers (damage calc,
map gen, etc.) are sync so they're easy to test in isolation.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.classes.units import (
    default_roster,
    get as _get_unit,
    get_or_none as _get_unit_or_none,
    type_advantage as _type_adv,
)
from app.config import (
    AI_AGGRO_RANGE, AI_MAX_ACTIONS_PER_TURN,
    BASE_CRIT_RATE, CASTLES_PER_GAME, CASTLE_NEIGHBOR_RADIUS, CLAIM_TURNS_REQUIRED,
    CRIT_MULTIPLIER, CRIT_PER_LEVEL,
    EXP_PER_ASSIST, EXP_PER_KILL, EXP_TO_LEVEL,
    LEVEL_UP_BONUS_POINTS, LEVEL_UP_STAT_BONUS, MAX_LEVEL, MAP_SIZE,
    MORALE_ATK_PER_STAR, MORALE_DEF_PER_STAR, MORALE_MAX,
    SKILL_DOUBLE_STRIKE,
    TERRAIN_BARRACKS, TERRAIN_CASTLE, TERRAIN_DEF_BONUS, TERRAIN_FOREST,
    TERRAIN_GATE, TERRAIN_MOUNTAIN, TERRAIN_PLAIN, TERRAIN_RIVER,
    TERRAIN_ROAD, TERRAIN_SPAWN_WEIGHTS, TERRAIN_VILLAGE, CASTLE_VAULT,
)

UNIT_HEALER = "healer"
UNIT_KNIGHT = "knight"

from app.models import ActionLog, ClaimSession, Game, Player, Tile, Unit
from app.utils import bfs_reachable, has_line_of_sight, manhattan, pathfind


logger = logging.getLogger(__name__)


# ============================================================
# Map generation
# ============================================================

# Pre-computed symmetric castle spawn points for 2 / 3 / 4 players.
_CASTLE_LAYOUTS: Dict[int, List[Tuple[int, int]]] = {
    2: [(2, 2), (12, 12)],
    3: [(2, 2), (12, 2), (7, 12)],
    4: [(2, 2), (12, 2), (2, 12), (12, 12)],
}


def _passable_terrain_choices(rng: random.Random) -> str:
    terrain_types = list(TERRAIN_SPAWN_WEIGHTS.keys())
    weights = list(TERRAIN_SPAWN_WEIGHTS.values())
    return rng.choices(terrain_types, weights=weights, k=1)[0]


def generate_map(seed: int, num_castles: int = CASTLES_PER_GAME) -> List[List[Tile]]:
    """Generate a 2D list of `Tile` rows for a fresh game.

    Castles are placed at predefined positions; remaining tiles are randomised
    using a seeded RNG (so the same seed reproduces the map).
    """
    if num_castles not in _CASTLE_LAYOUTS:
        num_castles = CASTLES_PER_GAME

    rng = random.Random(seed)
    castles = _CASTLE_LAYOUTS[num_castles]
    castle_set = set(castles)

    safe_zones: set = set()
    for cx, cy in castles:
        for dx in range(-CASTLE_NEIGHBOR_RADIUS, CASTLE_NEIGHBOR_RADIUS + 1):
            for dy in range(-CASTLE_NEIGHBOR_RADIUS, CASTLE_NEIGHBOR_RADIUS + 1):
                x, y = cx + dx, cy + dy
                if 0 <= x < MAP_SIZE and 0 <= y < MAP_SIZE:
                    safe_zones.add((x, y))

    grid: List[List[Tile]] = []
    for y in range(MAP_SIZE):
        row: List[Tile] = []
        for x in range(MAP_SIZE):
            if (x, y) in castle_set:
                row.append(Tile(x=x, y=y, terrain=TERRAIN_CASTLE))
            elif (x, y) in safe_zones:
                row.append(Tile(x=x, y=y, terrain=TERRAIN_PLAIN))
            else:
                row.append(Tile(x=x, y=y, terrain=_passable_terrain_choices(rng)))
        grid.append(row)
    return grid


def castle_positions(num_players: int) -> Dict[int, Tuple[int, int]]:
    """Return {seat_index: (x, y)} for the requested player count."""
    n = max(2, min(4, num_players))
    return {i: pos for i, pos in enumerate(_CASTLE_LAYOUTS[n])}


# ============================================================
# Unit creation
# ============================================================

_UNIT_NAME_SUFFIX = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"]


def _unit_name(unit_type: str, index: int) -> str:
    base = _get_unit(unit_type)
    suffix = _UNIT_NAME_SUFFIX[index] if index < len(_UNIT_NAME_SUFFIX) else f"#{index + 1}"
    return f"{base.display_en}-{suffix}"


def _spawn_xy_for_castle(castle_xy: Tuple[int, int], unit_index: int) -> Tuple[int, int]:
    cx, cy = castle_xy
    offsets = [(0, 1), (1, 0), (1, 1), (2, 0), (0, 2)]
    dx, dy = offsets[unit_index % len(offsets)]
    x = max(0, min(MAP_SIZE - 1, cx + dx))
    y = max(0, min(MAP_SIZE - 1, cy + dy))
    return x, y


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
    for sk in get_passive_for(unit):
        base = sk.modify_attack_range(base, unit)
    return base


def unit_min_attack_range(unit: Unit) -> int:
    """Minimum attack range (Manhattan distance).

    0 = can attack adjacent (d=1) → melee
    1 = must keep distance (no melee, like Fire-Emblem archers)
    """
    return _get_unit(unit.unit_type).min_attack_range


def can_attack_from_position(unit: Unit, fromX: int, fromY: int, toX: int, toY: int) -> bool:
    """True if `unit` could attack (toX, toY) when standing on (fromX, fromY).

    Distance is measured in Manhattan metric (|dx|+|dy|).
    """
    d = manhattan((fromX, fromY), (toX, toY))
    if d == 0:
        return False
    return unit_min_attack_range(unit) < d <= unit_attack_range(unit)


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
        crit = rng.random() < _crit_chance(attacker)

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
    """Delete units with hp <= 0 and free the tiles they were occupying."""
    dead = [u for u in units if u.hp <= 0]
    if not dead:
        return []
    dead_ids = [u.id for u in dead]
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
    game = await _resolve_game(session, dead[0].game_id)
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
    """Evaluate the current win condition for `game`. If a winner
    emerges, set status='finished' + win_reason and return True.
    Otherwise return False (game continues).

    Called from:
      - cleanup_dead_units (rout + post-attack recheck)
      - apply_end_of_turn (defend + final rout recheck)
      - move_unit (reach, when a unit lands on the target)
      - claim_tile (seize, when ownership flips)
    """
    if game.status != "playing":
        return game.status == "finished"

    # Always recompute alive-teams so a 0-team left means 'draw'.
    alive = await _alive_teams(session, game)

    if game.win_condition == "rout":
        if len(alive) == 1:
            _finish_game(game, alive[0], "rout")
            return True
        if len(alive) == 0:
            _finish_game(game, None, "draw")
            return True
        return False

    if game.win_condition == "defend":
        # Owner rule: "survive to round N" — interpreted as the
        # attacker has failed to wipe all defenders in N rounds.
        # Outcomes at the target turn:
        #   * exactly 1 team alive → that team wins ("defend")
        #   * 0 teams alive → draw
        #   * 2+ teams alive → the game continues (no one was wiped
        #     yet, but the scoreboard shows "Round N/N: hold on")
        if game.turn_number >= game.defend_turns and len(alive) == 1:
            _finish_game(game, alive[0], "defend")
            return True
        if len(alive) == 0:
            _finish_game(game, None, "draw")
            return True
        return False

    if game.win_condition == "reach":
        # A unit is currently on the target tile.
        if game.reach_tile_id is not None:
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
        # Rout still applies as a backup: only 1 team left = they win
        # even in reach mode (the opponent got wiped before the unit
        # reached the goal).
        if len(alive) == 1:
            _finish_game(game, alive[0], "rout")
            return True
        if len(alive) == 0:
            _finish_game(game, None, "draw")
            return True
        return False

    if game.win_condition == "seize":
        # Seize wins at the moment ownership flips (handled in
        # claim_tile). Here we only handle the rout fallback.
        if len(alive) == 1:
            _finish_game(game, alive[0], "rout")
            return True
        if len(alive) == 0:
            _finish_game(game, None, "draw")
            return True
        return False

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
    """If `unit` is standing on a castle tile, transfer ownership to its player."""
    if tile.terrain != TERRAIN_CASTLE:
        return False
    if tile.owner_id == unit.player_id:
        return False
    tile.owner_id = unit.player_id
    return True


# ============================================================
# Claim mechanic (P0.4) — see docs/superpowers/specs/2026-06-30-
# terrain-economy-claim-spec.md §4.
# ============================================================

# Terrains a unit can perform the active `claim` action on.
CLAIMABLE_TERRAINS = frozenset({TERRAIN_VILLAGE, TERRAIN_BARRACKS, CASTLE_VAULT})


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

    # P2.3 — under "seize" mode, a HQ-tile ownership flip between
    # different teams is an instant win. We do this AFTER all the
    # flips so the win_reason reflects the LAST valid seize (and
    # any earlier seizures are logged in the claim_complete rows
    # above for the action log).
    if game.win_condition == "seize" and game.status == "playing":
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

_MAPS_DIR = _Path(__file__).resolve().parent.parent / "maps"


def _load_map_presets() -> Dict[str, Dict]:
    """Load all map preset JSON files from game/maps/ at import time.

    Each preset can declare its own 'size' in the JSON; the rows in
    'layout' must be that size. We no longer hard-require MAP_SIZE=15,
    so presets can be 15×15 / 20×20 / 30×30 / 45×45 etc.
    """
    presets: Dict[str, Dict] = {
        # "classic" is special: empty layout → falls back to procedural generation
        "classic": {
            "id": "classic",
            "name": "经典随机",
            "description": "按种子随机生成的标准地图",
            "biome": "grass",
            "size": MAP_SIZE,
            "layout": [],
        },
    }
    if _MAPS_DIR.is_dir():
        for path in sorted(_MAPS_DIR.glob("*.json")):
            data = _json.loads(path.read_text(encoding="utf-8"))
            layout = data.get("layout", [])
            if layout:
                expected = int(data.get("size", MAP_SIZE))
                if len(layout) != expected or any(len(r) != expected for r in layout):
                    raise AssertionError(
                        f"Preset {data.get('id', path.stem)}: layout must be "
                        f"{expected}x{expected} (got {len(layout)} rows)"
                    )
            else:
                data["size"] = data.get("size", MAP_SIZE)
            # Default biome to "grass" if not specified in JSON
            data.setdefault("biome", "grass")
            presets[data["id"]] = data
    return presets


MAP_PRESETS: Dict[str, Dict] = _load_map_presets()


def generate_map_preset(preset_id: str, seed: int, num_castles: int = CASTLES_PER_GAME) -> List[List[Tile]]:
    """Build a Tile grid from a named preset (or fall back to procedural)."""
    if preset_id and preset_id in MAP_PRESETS and MAP_PRESETS[preset_id].get("layout"):
        layout = MAP_PRESETS[preset_id]["layout"]
        return _layout_to_tiles(layout)
    # Fall back to the original seeded random generator
    return generate_map(seed=seed, num_castles=num_castles)


def _layout_to_tiles(layout: List[List[str]]) -> List[List[Tile]]:
    """Convert a char-grid layout into Tile rows.

    Char map:
      P=plain F=forest M=mountain R=river C=castle (legacy whole-tile)
      v=village b=barracks r=road g=gate  (P0.4 new terrains)
      Single castle sub-feature chars use lowercase to mark on tile.terrain
      as the corresponding castle_* terrain and store the subtype in
      Tile.subtype. Maps to uppercase ascii (P/F/M/R/C + lowercase v/b/r/g)
      by toggling case and matching against the subtype map.
    """
    grid: List[List[Tile]] = []
    char_to_terrain = {
        "P": TERRAIN_PLAIN,
        "F": TERRAIN_FOREST,
        "M": TERRAIN_MOUNTAIN,
        "R": TERRAIN_RIVER,
        "C": TERRAIN_CASTLE,
        "v": TERRAIN_VILLAGE,
        "b": TERRAIN_BARRACKS,
        "r": TERRAIN_ROAD,
        "g": TERRAIN_GATE,
    }
    for y, row in enumerate(layout):
        out_row: List[Tile] = []
        for x, ch in enumerate(row):
            terrain = char_to_terrain.get(ch, TERRAIN_PLAIN)
            tile = Tile(x=x, y=y, terrain=terrain)
            out_row.append(tile)
        grid.append(out_row)
    return grid


# ============================================================
# Unit-composition presets
# ============================================================

# ── Delegated to app.classes.units ──
from app.classes.units import list_compositions as _list_compositions
from app.classes.units import get_roster_for_composition as _unit_get_roster

def get_roster_for_composition(composition_id: Optional[str]) -> Dict[str, int]:
    return _unit_get_roster(composition_id)


def create_initial_units_with_roster(
    game: Game,
    players: Sequence[Player],
    castle_positions_map: Dict[int, Tuple[int, int]],
    roster: Dict[str, int],
) -> List[Unit]:
    """Like create_initial_units but with a caller-supplied roster."""
    units: List[Unit] = []
    for player in players:
        castle_xy = castle_positions_map[player.seat]
        unit_index = 0
        for unit_type, count in roster.items():
            uc = _get_unit_or_none(unit_type)
            if uc is None:
                continue
            for _ in range(count):
                x, y = _spawn_xy_for_castle(castle_xy, unit_index)
                units.append(
                    Unit(
                        player_id=player.id,
                        unit_type=unit_type,
                        name=_unit_name(unit_type, unit_index),
                        level=1,
                        exp=0,
                        hp=uc.base_hp,
                        max_hp=uc.base_hp,
                        atk=uc.base_atk,
                        def_=uc.base_def,
                        matk=uc.base_matk,
                        mdef=uc.base_mdef,
                        mov=uc.mp_pool,
                        mp=uc.mp_pool,
                        morale=0,
                        x=x,
                        y=y,
                        has_acted=False,
                        has_moved=False,
                        skills=list(uc.default_skills),
                    )
                )
                unit_index += 1
    return units


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
    terrain = {(t.x, t.y): t.terrain for t in tiles}
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
    ally_units = [u for u in units_by_player.get(ai_player.id, []) if u.hp > 0]
    enemy_units = [
        u for pid, ulist in units_by_player.items()
        if pid != ai_player.id
        for u in ulist if u.hp > 0
    ]
    enemy_castles = [
        (t.x, t.y) for t in tiles
        if t.terrain == TERRAIN_CASTLE and t.owner_id is not None
        and t.owner_id != ai_player.id
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


def _unit_value(u: Unit) -> float:
    """Higher = more valuable target. Used for attack priority."""
    base = u.atk + u.def_ + u.hp / 10
    # Healer is a high-value target
    if u.unit_type == UNIT_HEALER:
        base += 30
    if u.unit_type == UNIT_KNIGHT:
        base += 10
    return base


def _ai_pick_attack_target(unit: Unit, snap: _AISnapshot) -> Optional[Unit]:
    """Choose best enemy to attack within range. None if nothing valid."""
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
        if d > 1:
            # Ranged: check line of sight
            blockers.discard((e.x, e.y))
            if not has_line_of_sight((unit.x, unit.y), (e.x, e.y), blockers):
                continue
        # Score: lower hp = better kill chance; type-advantage = bonus
        score = _unit_value(e) * 1.0
        score -= e.hp * 0.5   # lower HP = higher score
        score += 100 if e.hp <= unit.atk else 0  # can kill this turn
        type_mult = _type_adv(unit.unit_type, e.unit_type)
        score *= type_mult
        # Prefer targets within aggro range (closer = more relevant)
        score += max(0, AI_AGGRO_RANGE - d) * 5
        candidates.append((score, e))
    if not candidates:
        return None
    candidates.sort(key=lambda t: -t[0])
    return candidates[0][1]


def _ai_pick_move_target(unit: Unit, snap: _AISnapshot) -> Optional[Tuple[int, int]]:
    """Pick a destination tile to move toward (high score wins)."""
    # Don't move healers/archers into melee of multiple enemies
    blocked = {
        c for c, uid in snap.occ.items()
        if uid is not None and uid != unit.id
    }
    reachable = bfs_reachable(
        start=(unit.x, unit.y),
        terrain=snap.terrain,
        owners=snap.owners,
        mov=unit.mov,
        viewer_owner_id=None,  # AI shouldn't be blocked from entering enemy castles
        blocked_units=blocked,
    )
    if not reachable:
        return None

    # Compute "score" for each reachable tile
    def score(tile: Tuple[int, int]) -> float:
        s = 0.0
        # Reward unowned castles
        if tile in snap.unowned_castles:
            s += 200
        # Reward getting close to the nearest enemy (but not on top)
        if snap.enemy_units:
            nearest = min(manhattan(tile, (e.x, e.y)) for e in snap.enemy_units)
            s += max(0, AI_AGGRO_RANGE - nearest) * 6
            # Slight penalty if surrounded by many enemies at this tile
            in_range = sum(
                1 for e in snap.enemy_units
                if manhattan(tile, (e.x, e.y)) <= unit_attack_range(e)
            )
            s -= in_range * 8
        # Reward defensive terrain
        terr = snap.terrain.get(tile)
        if terr == TERRAIN_FOREST:
            s += TERRAIN_DEF_BONUS.get(TERRAIN_FOREST, 0) * 2
        if terr == TERRAIN_MOUNTAIN:
            s += TERRAIN_DEF_BONUS.get(TERRAIN_MOUNTAIN, 0) * 2
        if terr == TERRAIN_CASTLE:
            s += 30
        # Small bonus for keeping close to allies (concentration)
        if snap.ally_units:
            min_ally = min(manhattan(tile, (a.x, a.y)) for a in snap.ally_units if a.id != unit.id) \
                if any(a.id != unit.id for a in snap.ally_units) else 5
            s += max(0, 3 - min_ally) * 1
        return s

    best_tile = max(reachable.keys(), key=score)
    if score(best_tile) <= score((unit.x, unit.y)) - 1:
        return None  # standing still is better
    return best_tile


async def _ai_move(session: AsyncSession, game: Game, unit: Unit, dest: Tuple[int, int]) -> bool:
    """Perform an AI move. Returns True if successful."""
    tile_rows = (
        await session.execute(select(Tile).where(Tile.game_id == game.id))
    ).scalars().all()
    terrain = {(t.x, t.y): t.terrain for t in tile_rows}
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
        mov=unit.mov, viewer_owner_id=unit.player_id, blocked_units=blocked,
    )
    if not path or path[-1] != dest:
        return False
    # Apply move on tiles
    for t in tile_rows:
        if (t.x, t.y) == (unit.x, unit.y):
            t.occupied_unit_id = None
        if (t.x, t.y) == dest:
            t.occupied_unit_id = unit.id
            if t.terrain == TERRAIN_CASTLE:
                claim_castle_if_present(t, unit)
    unit.x, unit.y = dest
    # AI: move ends this unit's move (can't move again this round),
    # but the unit may still attack this turn (matches the human player rules).
    unit.has_moved = True
    return True


async def _ai_attack(session: AsyncSession, attacker: Unit, target: Unit) -> bool:
    """Perform an AI attack. Returns True if successful."""
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
    if target.hp <= 0:
        award_exp(attacker, "kill")
    else:
        award_exp(attacker, "hit")
    attacker.has_acted = True
    # Immediately remove dead unit from the board/DB
    if target.hp <= 0:
        await cleanup_dead_units(session, [target])
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


async def ai_take_turn(session: AsyncSession, game: Game, ai_player: Player) -> int:
    """Execute one AI player's full turn. Returns the number of actions taken."""
    actions = 0
    # Refresh this AI's units fresh each pass
    units_rows = (await session.execute(
        select(Unit).where(Unit.player_id == ai_player.id)
    )).scalars().all()
    # Process units in priority order: healers first, then attackers
    priority = sorted(
        [u for u in units_rows if u.hp > 0 and not u.has_acted],
        key=lambda u: (
            0 if u.unit_type == UNIT_HEALER else 1,  # healers first
            -u.atk,
        ),
    )
    for unit in priority:
        if actions >= AI_MAX_ACTIONS_PER_TURN:
            break
        # Re-fetch the latest snapshot (state may have shifted)
        snap = await _load_ai_snapshot(session, game, ai_player)
        # 1. Skill?
        if unit.unit_type == UNIT_HEALER:
            if await _ai_use_skill(session, game, unit, snap):
                actions += 1
                continue
        # 2. Attack?
        target = _ai_pick_attack_target(unit, snap)
        if target is not None:
            if await _ai_attack(session, unit, target):
                actions += 1
                continue
        # 3. Move?
        dest = _ai_pick_move_target(unit, snap)
        if dest is not None and dest != (unit.x, unit.y):
            if await _ai_move(session, game, unit, dest):
                actions += 1
                continue
        # 4. Wait
        unit.has_acted = True
        actions += 1
    return actions


async def ai_take_one_action(
    session: AsyncSession,
    game: Game,
    ai_player: Player,
) -> bool:
    """Execute ONE action of an AI's turn and return True, or False if done.

    Used by `_run_ai_turn_chain` to play actions one at a time with sleeps
    in between so the human can see them progress. Mirrors the priority
    order of `ai_take_turn` (healers first, then attackers).
    """
    # Stop if this AI has ended their turn (set by `end_turn` earlier).
    if ai_player.has_ended_turn:
        return False
    # Find first unit that hasn't acted yet.
    units_rows = (await session.execute(
        select(Unit).where(Unit.player_id == ai_player.id)
    )).scalars().all()
    pending = [u for u in units_rows if u.hp > 0 and not u.has_acted]
    if not pending:
        return False
    # Priority: healers first, then highest ATK first
    pending.sort(key=lambda u: (
        0 if u.unit_type == UNIT_HEALER else 1,
        -u.atk,
    ))
    unit = pending[0]
    snap = await _load_ai_snapshot(session, game, ai_player)
    # 1. Skill?
    if unit.unit_type == UNIT_HEALER:
        if await _ai_use_skill(session, game, unit, snap):
            return True
    # 2. Attack?
    target = _ai_pick_attack_target(unit, snap)
    if target is not None:
        if await _ai_attack(session, unit, target):
            return True
    # 3. Move?
    dest = _ai_pick_move_target(unit, snap)
    if dest is not None and dest != (unit.x, unit.y):
        if await _ai_move(session, game, unit, dest):
            return True
    # 4. Wait (still counts as an action so we can move on)
    unit.has_acted = True
    return True