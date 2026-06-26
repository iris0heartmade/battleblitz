"""
Regression test for the "can't end turn after moving" bug.

Original bug: `move_unit` did not set `unit.has_acted = True`, so a player
who only moved (no attack) was stuck — `end_turn` counted has_acted units
and refused to let them end with 0 has_acted.

This file is a focused end-to-end check that:
  1. Create game + 2 players + start
  2. Move ONE unit
  3. End turn — should succeed (not 400)

If this test ever fails again, someone removed `unit.has_acted = True`
from the move handler.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def game_client():
    from app.main import app
    from app.database import Base, dispose_db, engine, init_db

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


@pytest.mark.integration
async def test_end_turn_works_after_a_single_move(game_client):
    # Create + 2 players + start
    g = (await game_client.post("/games", json={"name": "regression"})).json()
    p1 = (await game_client.post(
        f"/games/{g['id']}/join", json={"user_name": "p1"}
    )).json()
    p2 = (await game_client.post(
        f"/games/{g['id']}/join", json={"user_name": "p2"}
    )).json()
    await game_client.post(f"/games/{g['id']}/start")

    # Find p1's first unit
    state = (await game_client.get(f"/games/{g['id']}/state")).json()
    p1_data = next(p for p in state["players"] if p["id"] == p1["id"])
    unit = p1_data["units"][0]

    # Move the unit (1 step, plenty of MP)
    from_x, from_y = unit["x"], unit["y"]
    r = await game_client.post(
        f"/games/{g['id']}/move",
        json={
            "player_id": p1["id"],
            "unit_id": unit["id"],
            "to_x": from_x + 1,
            "to_y": from_y,
        },
    )
    assert r.status_code == 200, f"move failed: {r.status_code} {r.text}"

    # End turn — should NOT be 400 "本回合至少需要操作..."
    r = await game_client.post(
        f"/games/{g['id']}/end-turn",
        json={"player_id": p1["id"]},
    )
    assert r.status_code == 200, (
        f"end_turn failed after move: {r.status_code} {r.text}. "
        "This is the regression — move probably doesn't set has_acted."
    )
