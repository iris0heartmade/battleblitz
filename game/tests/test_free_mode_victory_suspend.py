from __future__ import annotations

import pytest
from sqlalchemy import select


pytestmark = pytest.mark.integration


async def _create_profile(client, user_name: str) -> None:
    r = await client.post("/progression/profiles", json={"user_name": user_name})
    assert r.status_code == 201, r.text


async def _make_free_room(client) -> tuple[int, int, int]:
    r = await client.post("/games", json={
        "name": "free-rout-cleanup",
        "map_preset": "classic",
        "map_seed": 42,
        "mode": "free",
        "win_condition": "rout",
    })
    assert r.status_code == 201, r.text
    game_id = r.json()["id"]

    joined = await client.post(
        f"/games/{game_id}/join",
        json={"user_name": "alice", "color": "red"},
    )
    assert joined.status_code == 201, joined.text
    alice_id = joined.json()["id"]

    ai = await client.post(
        f"/games/{game_id}/add-ai",
        json={"difficulty": "normal", "agent_kind": "rules", "personality": "balanced"},
    )
    assert ai.status_code == 201, ai.text
    ai_id = ai.json()["id"]

    started = await client.post(f"/games/{game_id}/start", json={})
    assert started.status_code == 200, started.text
    return game_id, alice_id, ai_id


async def _arrange_last_enemy_kill(SessionLocal, game_id: int, alice_id: int, ai_id: int) -> tuple[int, int]:
    from app.models import Game, Tile, Unit

    async with SessionLocal() as session:
        game = await session.get(Game, game_id)
        assert game is not None
        game.current_player_index = 0

        alice_units = (await session.execute(
            select(Unit).where(Unit.player_id == alice_id)
        )).scalars().all()
        ai_units = (await session.execute(
            select(Unit).where(Unit.player_id == ai_id)
        )).scalars().all()
        assert alice_units and ai_units

        attacker = alice_units[0]
        target = ai_units[0]
        for extra in ai_units[1:]:
            extra.hp = 0
            tile = (await session.execute(
                select(Tile).where(Tile.game_id == game_id, Tile.occupied_unit_id == extra.id)
            )).scalars().first()
            if tile is not None:
                tile.occupied_unit_id = None
            await session.delete(extra)

        old_attacker_tile = (await session.execute(
            select(Tile).where(Tile.game_id == game_id, Tile.occupied_unit_id == attacker.id)
        )).scalars().first()
        old_target_tile = (await session.execute(
            select(Tile).where(Tile.game_id == game_id, Tile.occupied_unit_id == target.id)
        )).scalars().first()
        if old_attacker_tile is not None:
            old_attacker_tile.occupied_unit_id = None
        if old_target_tile is not None:
            old_target_tile.occupied_unit_id = None

        attacker.x = 1
        attacker.y = 1
        attacker.atk = 99
        attacker.has_acted = False
        attacker.has_moved = False
        attacker.mp = 5
        target.x = 2
        target.y = 1
        target.hp = 1
        target.def_ = 0
        target.has_acted = False

        for x, y, unit_id in ((1, 1, attacker.id), (2, 1, target.id)):
            tile = (await session.execute(
                select(Tile).where(Tile.game_id == game_id, Tile.x == x, Tile.y == y)
            )).scalars().first()
            assert tile is not None
            tile.occupied_unit_id = unit_id

        await session.commit()
        return attacker.id, target.id


async def test_free_mode_attack_rout_finishes_immediately_and_clears_suspend(client):
    from app.database import AsyncSessionLocal
    from app.models import Game

    await _create_profile(client, "alice")
    game_id, alice_id, ai_id = await _make_free_room(client)

    suspend = await client.post(f"/games/{game_id}/suspend", json={"user_name": "alice"})
    assert suspend.status_code == 200, suspend.text
    listed_before = await client.get("/saves", params={"user_name": "alice"})
    assert listed_before.status_code == 200, listed_before.text
    assert listed_before.json()["suspend"] is not None

    attacker_id, target_id = await _arrange_last_enemy_kill(
        AsyncSessionLocal, game_id, alice_id, ai_id
    )
    attacked = await client.post(f"/games/{game_id}/attack", json={
        "player_id": alice_id,
        "attacker_id": attacker_id,
        "target_id": target_id,
    })
    assert attacked.status_code == 200, attacked.text
    assert attacked.json()["target_hp_after"] == 0

    async with AsyncSessionLocal() as session:
        from app.models import Unit
        from app.game_logic import _alive_teams

        enemy_units = (await session.execute(
            select(Unit).where(Unit.player_id == ai_id)
        )).scalars().all()
        assert enemy_units == []

        game = await session.get(Game, game_id)
        assert game is not None
        assert await _alive_teams(session, game) == [f"player_{alice_id}"]
        assert game.status == "finished"
        assert game.win_reason == "rout"

    listed_after = await client.get("/saves", params={"user_name": "alice"})
    assert listed_after.status_code == 200, listed_after.text
    assert listed_after.json()["suspend"] is None
