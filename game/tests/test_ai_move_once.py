"""Regression test: AI units must not move twice in one turn.

Reported 2026-07-03: an AI-controlled swordsman on a 25×25 map was seen
moving three times for 5 cells each within the same turn.

Root cause: `_ai_move` only sets `unit.has_moved = True`, not
`unit.has_acted = True`. The AI action loop's `pending` filter
(`not u.has_acted`) then re-selected the same unit after each move,
letting it pick `_ai_move` again until MP ran out.

Fix: the `pending` and `priority` filters now also exclude units that
have already moved (`not u.has_moved`).
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal, Base, dispose_db, engine, init_db
from app.game_logic import DamageResult, _ai_attack, _ai_move, ai_take_one_action


@pytest.fixture
async def db_session():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    async with AsyncSessionLocal() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


@pytest.mark.asyncio
async def test_ai_unit_cannot_move_twice_in_one_turn(db_session):
    """A swordsman that has already moved must be invisible to the AI
    action-selector (so it's not picked up for another `_ai_move`)."""
    from app.config import TERRAIN_PLAIN, TERRAIN_FOREST
    from app.models import Game, Player, Tile, Unit

    game = Game(name="ai-move-test", status="playing",
                map_seed=0, map_preset="classic", map_biome="grass",
                current_player_index=0, phase="ai",
                first_player_done_first_turn=True)
    db_session.add(game)
    await db_session.flush()

    player = Player(game_id=game.id, user_name="AI", seat=0, color="red",
                    is_alive=True, has_ended_turn=False)
    db_session.add(player)
    await db_session.flush()

    # Minimal 5×5 board: all plain except a tiny forest cluster.
    for y in range(5):
        for x in range(5):
            db_session.add(Tile(game_id=game.id, x=x, y=y,
                                terrain=TERRAIN_PLAIN))
    await db_session.flush()

    # A swordsman in the south-east corner with 5 MP.
    unit = Unit(player_id=player.id, unit_type="swordsman", name="T",
                level=1, exp=0, hp=45, max_hp=45,
                atk=18, def_=12, matk=4, mdef=4,
                mov=5, mp=5, morale=0,
                x=4, y=4, has_acted=False, has_moved=False, skills=[])
    db_session.add(unit)
    await db_session.flush()

    # First AI action: move it 1 cell north-west to (3, 3).
    assert unit.has_moved is False
    ok = await _ai_move(db_session, game, unit, (3, 3))
    assert ok, "first move should succeed"
    assert (unit.x, unit.y) == (3, 3)
    assert unit.has_moved is True
    # It must NOT have been marked acted — the AI should be allowed
    # to follow up with an attack on the same turn.
    assert unit.has_acted is False, (
        "first move should NOT set has_acted (still allow attack follow-up)"
    )

    # Now run one more AI action. The same unit must not be re-picked
    # for moving again — it should simply return False (no more moves)
    # because the unit is still alive and !has_acted, but it has moved.
    moved = await ai_take_one_action(db_session, game, player)
    assert moved is False, (
        "AI must not pick the already-moved swordsman for another move. "
        f"_ai_take_one_action returned {moved!r}."
    )

    # Sanity: the unit's position is unchanged.
    assert (unit.x, unit.y) == (3, 3), (
        f"unit position should be unchanged after second AI pass; got "
        f"({unit.x}, {unit.y})"
    )


def _hit(damage: int) -> DamageResult:
    return DamageResult(
        damage=damage,
        is_crit=False,
        is_kill=False,
        effective_atk=damage,
        defense_total=0,
    )


@pytest.mark.asyncio
async def test_ai_attack_triggers_counter_attack(db_session, monkeypatch):
    """AI combat must use the same counter-attack rule as player combat."""
    from app.config import TERRAIN_PLAIN
    from app.models import Game, Player, Tile, Unit

    game = Game(name="ai-counter-test", status="playing",
                map_seed=0, map_preset="classic", map_biome="grass",
                current_player_index=0, phase="ai",
                first_player_done_first_turn=True)
    db_session.add(game)
    await db_session.flush()

    ai_player = Player(game_id=game.id, user_name="AI", seat=0, color="red",
                       is_alive=True, has_ended_turn=False, is_ai=True)
    defender_player = Player(game_id=game.id, user_name="Human", seat=1,
                             color="blue", is_alive=True,
                             has_ended_turn=False)
    db_session.add_all([ai_player, defender_player])
    await db_session.flush()

    attacker = Unit(player_id=ai_player.id, unit_type="swordsman", name="A",
                    level=1, exp=0, hp=20, max_hp=20,
                    atk=18, def_=12, matk=4, mdef=4,
                    mov=3, mp=3, morale=0,
                    x=0, y=0, has_acted=False, has_moved=False, skills=[])
    defender = Unit(player_id=defender_player.id, unit_type="swordsman",
                    name="D", level=1, exp=0, hp=20, max_hp=20,
                    atk=18, def_=12, matk=4, mdef=4,
                    mov=3, mp=3, morale=0,
                    x=1, y=0, has_acted=False, has_moved=False, skills=[])
    db_session.add_all([attacker, defender])
    await db_session.flush()

    db_session.add_all([
        Tile(game_id=game.id, x=0, y=0, terrain=TERRAIN_PLAIN,
             occupied_unit_id=attacker.id),
        Tile(game_id=game.id, x=1, y=0, terrain=TERRAIN_PLAIN,
             occupied_unit_id=defender.id),
    ])
    await db_session.flush()

    damages = iter((1, 10))
    monkeypatch.setattr(
        "app.game_logic.attack_with_double_strike",
        lambda *args, **kwargs: [_hit(next(damages))],
    )

    assert await _ai_attack(db_session, attacker, defender)

    assert defender.hp == 19
    assert attacker.hp == 15
