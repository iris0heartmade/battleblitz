"""
Enumerate legal actions for an AI player, given the current game state.

This is the engine-side safety net: we never let the LLM pick an action we
haven't pre-validated. The LLM only chooses from this list.

For each unit we generate:
  - move:   one entry per reachable tile (up to a cap)
  - attack: one entry per enemy in range
  - skill:  one entry per legal skill usage
  - wait:   one entry (always)

Plus one global `end_turn` action that the AI may pick at any point.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import LegalAction
from app.config import (
    AI_AGGRO_RANGE,
    SKILL_DOUBLE_STRIKE,
    SKILL_HEAL,
    SKILL_RALLY,
    SKILL_SNIPE,
    TERRAIN_CASTLE,
    TERRAIN_DEF_BONUS,
    TERRAIN_FOREST,
    TERRAIN_MOUNTAIN,
    TERRAIN_RIVER,
    UNIT_ARCHER,
    UNIT_HEALER,
)
from app.game_logic import (
    calculate_damage,
    unit_attack_range,
)
from app.models import Game, Player, Tile, Unit
from app.utils import bfs_reachable, chebyshev, has_line_of_sight


# Cap the number of move targets we list. AI doesn't need to know about every
# single reachable tile — the score function would pick the best anyway.
MAX_MOVE_TARGETS = 8


# ----------------------------------------------------------------
# Public API
# ----------------------------------------------------------------

async def enumerate_legal_actions(
    session: AsyncSession,
    game: Game,
    player: Player,
) -> List[LegalAction]:
    """Return all legal actions the AI may choose from this turn."""
    # 1. Load actors (tiles + units). Re-use the rules-AI snapshot loader
    #    if convenient; we re-query here to keep this function self-contained.
    tiles = (await session.execute(
        select(Tile).where(Tile.game_id == game.id)
    )).scalars().all()
    terrain: dict = {(t.x, t.y): t.terrain for t in tiles}
    owners: dict = {(t.x, t.y): t.owner_id for t in tiles}

    players = (await session.execute(
        select(Player).where(Player.game_id == game.id)
    )).scalars().all()
    all_units = (await session.execute(
        select(Unit).where(Unit.player_id.in_([p.id for p in players]))
    )).scalars().all()
    my_units = [u for u in all_units if u.player_id == player.id and u.hp > 0 and not u.has_acted]
    enemy_units = [u for u in all_units if u.player_id != player.id and u.hp > 0]
    ally_units = [u for u in all_units if u.player_id == player.id and u.hp > 0]

    occupied: dict = {(u.x, u.y): u.id for u in all_units if u.hp > 0}

    actions: list[LegalAction] = []

    for u in my_units:
        unit_actions = _legal_actions_for_unit(
            u, terrain, owners, occupied, enemy_units, ally_units
        )
        actions.extend(unit_actions)

    # end_turn is always available
    actions.append(LegalAction(
        action_id="end_turn",
        kind="end_turn",
        unit_id=None,
        description="结束本回合行动",
    ))

    return actions


# ----------------------------------------------------------------
# Per-unit action generation
# ----------------------------------------------------------------

def _legal_actions_for_unit(
    unit: Unit,
    terrain: dict,
    owners: dict,
    occupied: dict,
    enemy_units: list[Unit],
    ally_units: list[Unit],
) -> List[LegalAction]:
    actions: list[LegalAction] = []

    # 1. Wait — always available
    actions.append(LegalAction(
        action_id=f"wait_{unit.id}",
        kind="wait",
        unit_id=unit.id,
        description=f"{unit.name} 原地待命 (保留行动点)",
    ))

    # 2. Move — enumerate reachable tiles
    if unit.mp > 0:
        blocked = {pos for pos, uid in occupied.items() if uid != unit.id}
        reachable = bfs_reachable(
            start=(unit.x, unit.y),
            terrain=terrain,
            owners=owners,
            mov=unit.mp,
            viewer_owner_id=None,  # AI can pass through anywhere its units can
            blocked_units=blocked,
        )
        # Remove the current tile (no-op)
        reachable.pop((unit.x, unit.y), None)

        # Cap to N best candidates (closest to enemies)
        if reachable:
            scored = []
            for coord in reachable:
                if not enemy_units:
                    score = 0
                else:
                    nearest = min(
                        chebyshev(coord, (e.x, e.y)) for e in enemy_units
                    )
                    score = -nearest  # closer is better
                scored.append((score, coord))
            scored.sort(key=lambda t: -t[0])
            for _, (tx, ty) in scored[:MAX_MOVE_TARGETS]:
                actions.append(LegalAction(
                    action_id=f"move_{unit.id}_{tx}_{ty}",
                    kind="move",
                    unit_id=unit.id,
                    params={"to": [tx, ty]},
                    description=f"{unit.name} 移动到 ({tx},{ty})",
                ))

    # 3. Attack — enemies in range
    atk_range = unit_attack_range(unit)
    los_blockers = {
        c for c, t in terrain.items()
        if t in (TERRAIN_FOREST, TERRAIN_MOUNTAIN, TERRAIN_RIVER)
    }
    for e in enemy_units:
        d = chebyshev((unit.x, unit.y), (e.x, e.y))
        if d == 0 or d > atk_range:
            continue
        if d > 1:
            # Ranged: check LOS
            los_blockers.discard((e.x, e.y))
            if not has_line_of_sight((unit.x, unit.y), (e.x, e.y), los_blockers):
                continue

        # Estimate damage
        def_tile_terrain = terrain.get((e.x, e.y), "plain")
        def_bonus = TERRAIN_DEF_BONUS.get(def_tile_terrain, 0)
        try:
            dmg = calculate_damage(unit, e, def_bonus, rng=_deterministic_rng(unit, e))
            dmg_est = dmg.damage
        except Exception:
            dmg_est = unit.atk  # safe fallback

        can_kill = e.hp <= dmg_est
        desc = (
            f"{unit.name} 攻击 {e.name}"
            f" ({def_tile_terrain}, 预计 {dmg_est} 伤害"
            f"{', 可击杀' if can_kill else ''})"
        )

        # Snipe skill: if unit has it, also offer a "skill:snipe" variant
        if SKILL_SNIPE in (unit.skills or []):
            actions.append(LegalAction(
                action_id=f"skill_snipe_{unit.id}_{e.id}",
                kind="skill",
                unit_id=unit.id,
                params={"skill": "snipe", "target_id": e.id},
                description=f"{unit.name} 狙击 {e.name} (技能, +1 射程)",
                dmg_estimate=dmg_est,
            ))

        actions.append(LegalAction(
            action_id=f"attack_{unit.id}_{e.id}",
            kind="attack",
            unit_id=unit.id,
            params={"target_id": e.id},
            description=desc,
            dmg_estimate=dmg_est,
        ))

    # 4. Skills
    for skill in (unit.skills or []):
        if skill == SKILL_HEAL and unit.unit_type == UNIT_HEALER:
            # Heal adjacent wounded ally
            for a in ally_units:
                if a.id == unit.id or a.hp <= 0 or a.hp >= a.max_hp:
                    continue
                if chebyshev((unit.x, unit.y), (a.x, a.y)) != 1:
                    continue
                deficit = a.max_hp - a.hp
                actions.append(LegalAction(
                    action_id=f"skill_heal_{unit.id}_{a.id}",
                    kind="skill",
                    unit_id=unit.id,
                    params={"skill": "heal", "target_id": a.id},
                    description=f"{unit.name} 治疗 {a.name} (恢复 {min(20, deficit)} HP)",
                ))

        elif skill == SKILL_RALLY and unit.unit_type == UNIT_HEALER:
            # Rally adjacent allies (buff ATK)
            nearby = any(
                chebyshev((unit.x, unit.y), (a.x, a.y)) == 1
                for a in ally_units if a.id != unit.id and a.hp > 0
            )
            if nearby:
                actions.append(LegalAction(
                    action_id=f"skill_rally_{unit.id}",
                    kind="skill",
                    unit_id=unit.id,
                    params={"skill": "rally"},
                    description=f"{unit.name} 集结 (+10% ATK 给相邻友军)",
                ))

        elif skill == SKILL_DOUBLE_STRIKE and unit.unit_type.lower() == "knight":
            # Already covered by attack; double-strike is auto-applied
            # in attack_with_double_strike, so no separate action.
            pass

    return actions


# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

def _deterministic_rng(unit: Unit, target: Unit):
    """A fixed-seed RNG for reproducible damage estimates.

    The real combat uses random crits; for the LLM's preview we want a stable
    number so the prompt doesn't lie between calls.
    """
    import random
    seed = (unit.id * 1009 + target.id * 31) & 0xFFFFFFFF
    return random.Random(seed)
