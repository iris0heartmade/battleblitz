"""
Action routes: move, attack, skill, wait.

All routes enforce:
  - caller is the current player
  - game is in 'playing' state
  - unit belongs to caller, is alive, and has not acted yet
"""
from __future__ import annotations

import logging
import random
from typing import Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    COUNTER_DAMAGE_MULT,
    COUNTER_IMMUNE_SKILLS,
    MAP_SIZE,
    SKILL_DOUBLE_STRIKE,
    SKILL_HEAL,
    SKILL_RALLY,
    TERRAIN_CASTLE,
    TERRAIN_DEF_BONUS,
)
from app.database import get_session
from app.game_logic import (
    apply_damage,
    attack_with_double_strike,
    award_exp,
    calculate_damage,
    can_attack_from_position,
    claim_castle_if_present,
    unit_attack_range,
    unit_min_attack_range,
)
from app.classes.units import get as _get_unit
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
from app.events import GameEvent, bus
from app.utils import (
    Coord,
    bfs_reachable,
    has_line_of_sight,
    manhattan,
    pathfind,
)

logger = logging.getLogger(__name__)
audit = logging.getLogger("audit.user")

router = APIRouter(prefix="/games", tags=["actions"])


# ============================================================
# Common helpers
# ============================================================

async def _load_active_game(session: AsyncSession, game_id: int) -> Game:
    game = await session.get(Game, game_id)
    if game is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "游戏不存在")
    if game.status != "playing":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"游戏状态不是进行中（当前：{game.status}）")
    return game


async def _load_unit(session: AsyncSession, unit_id: int) -> Unit:
    unit = await session.get(Unit, unit_id)
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "单位不存在")
    if unit.hp <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "单位已阵亡")
    return unit


async def _ensure_current_player(session: AsyncSession, game: Game, player_id: int) -> Player:
    players = (
        await session.execute(select(Player).where(Player.game_id == game.id))
    ).scalars().all()
    alive_seats = sorted(p.seat for p in players if p.is_alive)
    if not alive_seats:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "场上没有存活玩家")
    expected_seat = next(
        (s for s in alive_seats if s >= game.current_player_index),
        alive_seats[0],
    )
    player = next((p for p in players if p.id == player_id), None)
    if player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "玩家不在此游戏中")
    if player.id != next(p.id for p in players if p.seat == expected_seat):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "现在不是你的回合")
    return player


def _actions_per_turn(player: Player, game: Game) -> int:
    """Max units this player can act with this turn.

    First player (seat 0) is limited to 1 action on their first turn; everyone
    else (and first player on later turns) gets 2 actions per turn.
    """
    if player.seat == 0 and not game.first_player_done_first_turn:
        return 5
    return 5


async def _check_action_budget(session: AsyncSession, player: Player, unit: Unit) -> None:
    """No-op stub: each unit acts independently, no per-player cap.

    The per-unit `has_acted` flag (checked in each action handler) is the
    only constraint. Players may end their turn at any time via
    /games/{id}/end-turn — no "must do N actions first" rule.
    """
    return


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
        raise HTTPException(status.HTTP_403_FORBIDDEN, "该单位不属于你")
    if unit.has_moved:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该单位本回合已移动过")
    await _check_action_budget(session, player, unit)
    if not (0 <= body.to_x < MAP_SIZE and 0 <= body.to_y < MAP_SIZE):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "目标超出棋盘范围")

    terrain, owners, occ = await _load_tile_grid(session, game_id)
    target = (body.to_x, body.to_y)

    # Target must be empty (no unit on it)
    if occ.get(target) is not None and occ.get(target) != unit.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "目标格已被占据")

    # Cannot enter an enemy castle
    tile_terrain = terrain.get(target)
    if tile_terrain == TERRAIN_CASTLE and owners.get(target) not in (None, player.id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "无法进入敌方城堡")

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
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "目的地不可达")

    # Compute actual cost along the chosen path
    from app.config import TERRAIN_MOVE_COST
    cost = sum(TERRAIN_MOVE_COST[terrain[c]] for c in path[1:])

    # Enforce MP budget
    if cost > unit.mp:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"移动力不足（需要 {cost}，剩余 {unit.mp}）",
        )

    # Apply move: free old tile, occupy new tile
    for t in (await session.execute(select(Tile).where(Tile.game_id == game_id))).scalars():
        if (t.x, t.y) == (unit.x, unit.y):
            t.occupied_unit_id = None
        if (t.x, t.y) == target:
            t.occupied_unit_id = unit.id
    unit.x, unit.y = target
    # Spend movement points; unit can still attack (or continue moving for
    # classes with can_move_after_action).
    unit.mp = max(0, unit.mp - cost)
    # Track move separately from has_acted so the unit can still attack/heal
    # this turn after moving. has_moved blocks further moves; has_acted blocks
    # further non-move actions.
    unit.has_moved = True

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

    # Publish to in-process event bus (consumed by AI replay / commentary / WS gateway)
    await bus.publish(GameEvent(
        type="move", game_id=game_id, turn=game.turn_number,
        actor_player_id=player.id, actor_unit_id=unit.id, actor_name=unit.name,
        context={
            "from_x": path[0][0], "from_y": path[0][1],
            "to_x": target[0], "to_y": target[1],
            "mp_cost": cost, "mp_remaining": unit.mp,
            "castle_captured": castle_captured,
        },
    ))

    audit.info(
        "USER_ACTION | user=player_%d | game=%d | action=MOVE | result=SUCCESS | "
        "unit=%d | from=(%d,%d) | to=(%d,%d) | cost=%d | castle_captured=%s",
        player.id, game_id, unit.id, path[0][0], path[0][1],
        target[0], target[1], cost, castle_captured,
    )

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
        raise HTTPException(status.HTTP_403_FORBIDDEN, "攻击者不属于你")
    if attacker.has_acted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "攻击者本回合已行动过")
    await _check_action_budget(session, player, attacker)

    target = await _load_unit(session, body.target_id)
    if target.player_id == player.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能攻击己方单位")

    distance = manhattan((attacker.x, attacker.y), (target.x, target.y))
    atk_min = unit_min_attack_range(attacker)
    atk_range = unit_attack_range(attacker)
    if distance == 0 or distance <= atk_min or distance > atk_range:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"target out of range (need {atk_min} < d={distance} <= {atk_range})",
        )

    # Ranged attacks need LOS
    if atk_range > 1:
        terrain, _owners, _occ = await _load_tile_grid(session, game_id)
        blockers = _blocker_set(terrain)
        # The target's own tile should not block LOS to itself
        blockers.discard((target.x, target.y))
        if not has_line_of_sight((attacker.x, attacker.y), (target.x, target.y), blockers):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "视线被阻挡")

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

    # Morale bonus on kill (capped server-side in award_morale).
    if is_kill:
        from app.game_logic import award_morale
        award_morale(attacker)

    # ── Counter attack ────────────────────────────────────────
    # Counter fires if:
    #   1. defender survived the initial attack (HP > 0)
    #   2. defender's current attack range can reach the attacker
    #   3. defender doesn't have an immunity skill (e.g. "kiting")
    # Damage multiplier is COUNTER_DAMAGE_MULT (default 0.5).
    counter_dmg = 0
    defender_skills = set(target.skills or [])
    has_immunity = any(s in COUNTER_IMMUNE_SKILLS for s in defender_skills)
    if (
        not is_kill
        and not has_immunity
        and can_attack_from_position(target, target.x, target.y, attacker.x, attacker.y)
    ):
        # Defender's terrain bonus is the tile the defender is on
        counter_tile = (
            await session.execute(
                select(Tile).where(
                    Tile.game_id == game_id,
                    Tile.x == target.x,
                    Tile.y == target.y,
                )
            )
        ).scalars().first()
        counter_bonus = TERRAIN_DEF_BONUS.get(
            counter_tile.terrain if counter_tile else "plain", 0
        )
        counter_rng = random.Random()
        counter_hits = attack_with_double_strike(
            target, attacker, counter_bonus, rng=counter_rng
        )
        for ch in counter_hits:
            counter_dmg += max(1, int(ch.damage * COUNTER_DAMAGE_MULT))
        apply_damage(attacker, counter_dmg)
        _log(
            session, game, player, "counter",
            f"{target.name} counter → {attacker.name}: {counter_dmg} dmg "
            f"(x{COUNTER_DAMAGE_MULT})",
        )

    # Mark attacker as having acted.
    # If the attacker's class allows move-after-action AND it still has MP,
    # keep mp as is; otherwise zero it out (unit is rooted for the turn).
    attacker.has_acted = True
    if not _get_unit(attacker.unit_type).can_move_after_action:
        attacker.mp = 0

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
         + (" [击杀]" if is_kill else "")
         + (f" crit={hits[0].is_crit}" if hits and hits[0].is_crit else ""))

    if is_kill:
        _log(session, game, player, "death", f"{target.name} was slain")

    # Publish to in-process event bus
    await bus.publish(GameEvent(
        type="kill" if is_kill else "attack",
        game_id=game_id, turn=game.turn_number,
        actor_player_id=player.id, actor_unit_id=attacker.id, actor_name=attacker.name,
        target_player_id=target.player_id, target_unit_id=target.id, target_name=target.name,
        context={
            "damage": total_dmg,
            "is_crit": hits[0].is_crit if hits else False,
            "is_kill": is_kill,
            "attacker_hp": attacker.hp,
            "target_hp": target.hp,
        },
    ))

    audit.info(
        "USER_ACTION | user=player_%d | game=%d | action=ATTACK | result=SUCCESS | "
        "attacker=%d | target=%d | total_dmg=%d | is_kill=%s | crit=%s",
        player.id, game_id, attacker.id, target.id, total_dmg,
        is_kill, hits[0].is_crit if hits else False,
    )

    return AttackResult(
        hits=[DamageInfo(damage=h.damage, is_crit=h.is_crit, is_kill=is_kill,
                         attacker_unit_id=attacker.id, target_unit_id=target.id) for h in hits],
        target_unit_id=target.id,
        target_hp_after=target.hp,
        target_def_bonus=tile_bonus,
        attacker_exp_gained=exp_gained,
        assist_unit_ids=assist_ids,
        counter_damage=counter_dmg,
        attacker_hp_after=attacker.hp,
        description=(
            f"{attacker.name} hit {target.name} for {total_dmg} damage"
            + (" [击杀]" if is_kill else f" (HP left {target.hp})")
            + (f" → counter {counter_dmg}" if counter_dmg > 0 else "")
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
    from app.classes.units.skills import get as _get_skill
    from app.classes.units.skills.base import SkillContext as _SkillCtx

    game = await _load_active_game(session, game_id)
    player = await _ensure_current_player(session, game, body.player_id)
    unit = await _load_unit(session, body.unit_id)
    if unit.player_id != player.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "该单位不属于你")
    if unit.has_acted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该单位本回合已行动过")
    await _check_action_budget(session, player, unit)

    skill_id = body.skill
    try:
        sk = _get_skill(skill_id)
    except KeyError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f'未知技能：{skill_id}')
    if skill_id not in (unit.skills or []):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"该单位没有这个技能 '{skill_id}'")
    if sk.is_passive:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"'{skill_id}' is passive; use attack endpoint")

    # Resolve target
    target = await _load_unit(session, body.target_id) if body.target_id is not None else None

    # Build context
    all_players = (await session.execute(
        select(Player).where(Player.game_id == game_id)
    )).scalars().all()
    all_units = (await session.execute(
        select(Unit).where(Unit.player_id.in_([p.id for p in all_players]))
    )).scalars().all()
    ctx = _SkillCtx(
        user=unit, target=target,
        ally_units=[u for u in all_units if u.player_id == player.id and u.hp > 0],
        enemy_units=[u for u in all_units if u.player_id != player.id and u.hp > 0],
    )

    if not sk.can_use(ctx):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"skill '{skill_id}' cannot be used right now")

    result = await sk.execute(session, ctx)
    if not result.ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.description or "技能释放失败")

    _log(session, game, player, "skill", result.description)
    audit.info(
        "USER_ACTION | user=player_%d | game=%d | action=SKILL | result=SUCCESS | "
        "skill=%s | unit=%d",
        player.id, game_id, skill_id, unit.id,
    )
    return SkillResult(
        unit_id=unit.id, skill=skill_id, target_unit_id=body.target_id,
        restored_hp=result.restored_hp,
        description=result.description,
    )


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
        raise HTTPException(status.HTTP_403_FORBIDDEN, "该单位不属于你")
    if unit.has_acted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该单位本回合已行动过")
    await _check_action_budget(session, player, unit)

    unit.has_acted = True
    unit.mp = 0  # wait consumes remaining MP
    _log(session, game, player, "wait", f"{unit.name} waited")
    # Publish to event bus
    await bus.publish(GameEvent(
        type="wait", game_id=game_id, turn=game.turn_number,
        actor_player_id=player.id, actor_unit_id=unit.id, actor_name=unit.name,
    ))
    audit.info(
        "USER_ACTION | user=player_%d | game=%d | action=WAIT | result=SUCCESS | unit=%d",
        player.id, game_id, unit.id,
    )
    return WaitResult(unit_id=unit.id, description=f"{unit.name} ends turn")