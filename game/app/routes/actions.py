"""
Action routes: move, attack, skill, wait.

All routes enforce:
  - caller is the current player
  - game is in 'playing' state
  - unit belongs to caller, is alive, and has not acted yet
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    MAP_SIZE,
    SKILL_DOUBLE_STRIKE,
    SKILL_HEAL,
    SKILL_RALLY,
    TERRAIN_CASTLE,
    TERRAIN_DEF_BONUS,
)
from app.database import get_session
from app.game_logic import (
    HEAL_AMOUNT,
    apply_damage,
    attack_with_double_strike,
    award_exp,
    calculate_damage,
    claim_castle_if_present,
    heal_adjacent_ally,
    unit_attack_range,
)
from app.models import ActionLog, Game, Player, Tile, Unit
from app.schemas import (
    AttackRequest,
    AttackResult,
    DamageInfo,
    MoveRequest,
    MoveResult,
    SkillRequest,
    SkillResult,
    WaitRequest,
    WaitResult,
)
from app.utils import (
    Coord,
    bfs_reachable,
    chebyshev,
    has_line_of_sight,
    pathfind,
)

router = APIRouter(prefix="/games", tags=["actions"])


# ============================================================
# Common helpers
# ============================================================

async def _load_active_game(session: AsyncSession, game_id: int) -> Game:
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "game not found")
    if game.status != "playing":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"game is {game.status}")
    return game


async def _load_unit(session: AsyncSession, unit_id: int) -> Unit:
    unit = await session.get(Unit, unit_id)
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unit not found")
    if unit.hp <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unit is dead")
    return unit


async def _ensure_current_player(session: AsyncSession, game: Game, player_id: int) -> Player:
    players = (
        await session.execute(select(Player).where(Player.game_id == game.id))
    ).scalars().all()
    alive_seats = sorted(p.seat for p in players if p.is_alive)
    if not alive_seats:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no players alive")
    expected_seat = next(
        (s for s in alive_seats if s >= game.current_player_index),
        alive_seats[0],
    )
    player = next((p for p in players if p.id == player_id), None)
    if player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "player not found in game")
    if player.id != next(p.id for p in players if p.seat == expected_seat):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your turn")
    return player


async def _load_tile_grid(session: AsyncSession, game_id: int) -> Tuple[Dict[Coord, str], Dict[Coord, Optional[int]], Dict[Coord, Optional[int]]]:
    tiles = (
        await session.execute(select(Tile).where(Tile.game_id == game_id))
    ).scalars().all()
    terrain: Dict[Coord, str] = {}
    owners: Dict[Coord, Optional[int]] = {}
    occ: Dict[Coord, Optional[int]] = {}
    for t in tiles:
        terrain[(t.x, t.y)] = t.terrain
        owners[(t.x, t.y)] = t.owner_id
        occ[(t.x, t.y)] = t.occupied_unit_id
    return terrain, owners, occ


def _blocker_set(terrain: Dict[Coord, str]) -> Set[Coord]:
    """Tiles that block line of sight (forest/mountain/river block; castle does not)."""
    from app.config import TERRAIN_FOREST, TERRAIN_MOUNTAIN, TERRAIN_RIVER
    return {c for c, t in terrain.items() if t in (TERRAIN_FOREST, TERRAIN_MOUNTAIN, TERRAIN_RIVER)}


def _log(session: AsyncSession, game: Game, player: Player, action_type: str, description: str) -> None:
    session.add(
        ActionLog(
            game_id=game.id,
            turn_number=game.turn_number,
            player_id=player.id,
            action_type=action_type,
            description=description,
        )
    )


# ============================================================
# Move
# ============================================================

@router.post("/{game_id}/move", response_model=MoveResult)
async def move_unit(
    game_id: int,
    body: MoveRequest,
    session: AsyncSession = Depends(get_session),
) -> MoveResult:
    game = await _load_active_game(session, game_id)
    player = await _ensure_current_player(session, game, body.player_id)
    unit = await _load_unit(session, body.unit_id)
    if unit.player_id != player.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "unit does not belong to you")
    if unit.has_acted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unit has already acted this turn")
    if not (0 <= body.to_x < MAP_SIZE and 0 <= body.to_y < MAP_SIZE):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "target out of bounds")

    terrain, owners, occ = await _load_tile_grid(session, game_id)
    target = (body.to_x, body.to_y)

    # Target must be empty (no unit on it)
    if occ.get(target) is not None and occ.get(target) != unit.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "target tile is occupied")

    # Cannot enter an enemy castle
    tile_terrain = terrain.get(target)
    if tile_terrain == TERRAIN_CASTLE and owners.get(target) not in (None, player.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot enter enemy castle")

    # Pathfind with movement budget
    blocked = {(x, y) for (x, y), u in occ.items() if u is not None and u != unit.id}
    path = pathfind(
        start=(unit.x, unit.y),
        goal=target,
        terrain=terrain,
        owners=owners,
        mov=unit.mov,
        viewer_owner_id=player.id,
        blocked_units=blocked,
    )
    if path is None or path[-1] != target:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "destination unreachable")

    # Compute actual cost along the chosen path
    from app.config import TERRAIN_MOVE_COST
    cost = sum(TERRAIN_MOVE_COST[terrain[c]] for c in path[1:])

    # Apply move: free old tile, occupy new tile
    for t in (await session.execute(select(Tile).where(Tile.game_id == game_id))).scalars():
        if (t.x, t.y) == (unit.x, unit.y):
            t.occupied_unit_id = None
        if (t.x, t.y) == target:
            t.occupied_unit_id = unit.id
    unit.x, unit.y = target
    # Moving counts as the unit's action this turn (no second move until next turn)
    unit.has_acted = True

    # Castle capture
    castle_captured = False
    if tile_terrain == TERRAIN_CASTLE and owners.get(target) != player.id:
        for t in (await session.execute(select(Tile).where(Tile.game_id == game_id))).scalars():
            if (t.x, t.y) == target:
                if claim_castle_if_present(t, unit):
                    castle_captured = True
                break

    _log(session, game, player, "move",
         f"{unit.name} moved to ({target[0]}, {target[1]}) cost={cost}"
         + (" [captured castle]" if castle_captured else ""))

    return MoveResult(
        unit_id=unit.id,
        from_x=path[0][0], from_y=path[0][1],
        to_x=target[0], to_y=target[1],
        cost=cost,
        castle_captured=castle_captured,
        description=f"{unit.name} moved {len(path) - 1} tiles (cost {cost})",
    )


# ============================================================
# Attack
# ============================================================

@router.post("/{game_id}/attack", response_model=AttackResult)
async def attack(
    game_id: int,
    body: AttackRequest,
    session: AsyncSession = Depends(get_session),
) -> AttackResult:
    game = await _load_active_game(session, game_id)
    player = await _ensure_current_player(session, game, body.player_id)
    attacker = await _load_unit(session, body.attacker_id)
    if attacker.player_id != player.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "attacker does not belong to you")
    if attacker.has_acted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "attacker has already acted")

    target = await _load_unit(session, body.target_id)
    if target.player_id == player.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "cannot attack your own unit")

    distance = chebyshev((attacker.x, attacker.y), (target.x, target.y))
    atk_range = unit_attack_range(attacker)
    if distance == 0 or distance > atk_range:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"target out of range (need {distance} <= {atk_range})")

    # Ranged attacks need LOS
    if atk_range > 1:
        terrain, _owners, _occ = await _load_tile_grid(session, game_id)
        blockers = _blocker_set(terrain)
        # The target's own tile should not block LOS to itself
        blockers.discard((target.x, target.y))
        if not has_line_of_sight((attacker.x, attacker.y), (target.x, target.y), blockers):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "line of sight blocked")

    # Determine defender's terrain bonus
    def_tile = (
        await session.execute(
            select(Tile).where(Tile.game_id == game_id, Tile.x == target.x, Tile.y == target.y)
        )
    ).scalars().first()
    tile_bonus = TERRAIN_DEF_BONUS.get(def_tile.terrain if def_tile else "plain", 0)

    rng = random.Random()
    hits = attack_with_double_strike(attacker, target, tile_bonus, rng=rng)
    total_dmg = 0
    for h in hits:
        apply_damage(target, h.damage)
        total_dmg += h.damage

    is_kill = target.hp <= 0

    # Mark attacker as having acted
    attacker.has_acted = True

    # XP
    exp_gained = 0
    assist_ids: List[int] = []
    if is_kill:
        award_exp(attacker, "kill")
        exp_gained = 10
    else:
        award_exp(attacker, "hit")  # small xp on hit
        exp_gained = 5

    _log(session, game, player, "attack",
         f"{attacker.name} -> {target.name}: {total_dmg} dmg"
         + (" [KILL]" if is_kill else "")
         + (f" crit={hits[0].is_crit}" if hits and hits[0].is_crit else ""))

    if is_kill:
        _log(session, game, player, "death", f"{target.name} was slain")

    return AttackResult(
        hits=[DamageInfo(damage=h.damage, is_crit=h.is_crit, is_kill=is_kill,
                         attacker_unit_id=attacker.id, target_unit_id=target.id) for h in hits],
        target_unit_id=target.id,
        target_hp_after=target.hp,
        target_def_bonus=tile_bonus,
        attacker_exp_gained=exp_gained,
        assist_unit_ids=assist_ids,
        description=(
            f"{attacker.name} hit {target.name} for {total_dmg} damage"
            + (" [KILL]" if is_kill else f" (HP left {target.hp})")
        ),
    )


# ============================================================
# Skill
# ============================================================

@router.post("/{game_id}/skill", response_model=SkillResult)
async def use_skill(
    game_id: int,
    body: SkillRequest,
    session: AsyncSession = Depends(get_session),
) -> SkillResult:
    game = await _load_active_game(session, game_id)
    player = await _ensure_current_player(session, game, body.player_id)
    unit = await _load_unit(session, body.unit_id)
    if unit.player_id != player.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "unit does not belong to you")
    if unit.has_acted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unit has already acted")

    skill = body.skill
    if skill not in (unit.skills or []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unit does not have skill '{skill}'")

    # Skills that cost action: heal, rally. snipe/double_strike are passive.
    if skill == SKILL_HEAL:
        if body.target_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "heal requires target_id")
        ally = await _load_unit(session, body.target_id)
        if ally.player_id != player.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "can only heal your own units")
        restored = heal_adjacent_ally(unit, ally)
        if restored == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "target not adjacent / already full HP")
        unit.has_acted = True
        _log(session, game, player, "skill",
             f"{unit.name} healed {ally.name} for {restored} HP")
        return SkillResult(
            unit_id=unit.id, skill=skill, target_unit_id=ally.id,
            restored_hp=restored,
            description=f"{unit.name} healed {ally.name} for {restored} HP",
        )

    if skill == SKILL_RALLY:
        # +10% ATK to adjacent allies for this turn (apply buff to unit + adjacent allies)
        affected: List[int] = []
        adjacent_tiles = [
            (unit.x + dx, unit.y + dy)
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
            if (dx, dy) != (0, 0)
        ]
        tiles = (
            await session.execute(
                select(Tile).where(
                    Tile.game_id == game_id,
                    Tile.x.in_([c[0] for c in adjacent_tiles]),
                    Tile.y.in_([c[1] for c in adjacent_tiles]),
                )
            )
        ).scalars().all()
        affected_ids = [t.occupied_unit_id for t in tiles if t.occupied_unit_id is not None]
        for uid in affected_ids:
            u = await session.get(Unit, uid)
            if u and u.player_id == player.id and u.hp > 0:
                u.atk = int(round(u.atk * 1.10))
                affected.append(u.id)
        unit.has_acted = True
        _log(session, game, player, "skill",
             f"{unit.name} rallied: buffed {len(affected)} adjacent allies (+10% ATK)")
        return SkillResult(
            unit_id=unit.id, skill=skill, target_unit_id=None,
            restored_hp=0,
            description=f"{unit.name} rallied {len(affected)} allies",
        )

    if skill in (SKILL_DOUBLE_STRIKE, "snipe"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{skill}' is passive; use attack endpoint")

    raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown skill '{skill}'")


# ============================================================
# Wait
# ============================================================

@router.post("/{game_id}/wait", response_model=WaitResult)
async def wait_action(
    game_id: int,
    body: WaitRequest,
    session: AsyncSession = Depends(get_session),
) -> WaitResult:
    game = await _load_active_game(session, game_id)
    player = await _ensure_current_player(session, game, body.player_id)
    unit = await _load_unit(session, body.unit_id)
    if unit.player_id != player.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "unit does not belong to you")
    if unit.has_acted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unit has already acted")

    unit.has_acted = True
    _log(session, game, player, "wait", f"{unit.name} waited")
    return WaitResult(unit_id=unit.id, description=f"{unit.name} ends turn")