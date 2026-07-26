"""
Regression test for the "can't end turn after moving" bug.

Original bug: `move_unit` did not set `unit.has_acted = True`, so a player
who only moved (no attack) was stuck because `end_turn` counted has_acted
units and refused to let them end with 0 has_acted.
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


async def _create_started_two_player_game(game_client, name: str):
    game = (await game_client.post("/games", json={"name": name})).json()
    p1 = (await game_client.post(
        f"/games/{game['id']}/join", json={"user_name": "p1"}
    )).json()
    await game_client.post(
        f"/games/{game['id']}/join", json={"user_name": "p2"}
    )
    await game_client.post(f"/games/{game['id']}/start")
    return game, p1


async def _first_player_unit(game_client, game_id: int, player_id: int):
    state = (await game_client.get(f"/games/{game_id}/state")).json()
    player = next(p for p in state["players"] if p["id"] == player_id)
    return player["units"][0]


@pytest.mark.integration
async def test_end_turn_works_after_a_single_move(game_client):
    game, p1 = await _create_started_two_player_game(game_client, "regression")
    unit = await _first_player_unit(game_client, game["id"], p1["id"])

    from_x, from_y = unit["x"], unit["y"]
    r = await game_client.post(
        f"/games/{game['id']}/move",
        json={
            "player_id": p1["id"],
            "unit_id": unit["id"],
            "to_x": from_x + 1,
            "to_y": from_y,
        },
    )
    assert r.status_code == 200, f"move failed: {r.status_code} {r.text}"

    r = await game_client.post(
        f"/games/{game['id']}/end-turn",
        json={"player_id": p1["id"]},
    )
    assert r.status_code == 200, (
        f"end_turn failed after move: {r.status_code} {r.text}. "
        "This is the regression: move probably does not set has_acted."
    )


@pytest.mark.integration
async def test_move_event_context_includes_authoritative_path(game_client, monkeypatch):
    from app.routes import actions

    published = []

    async def capture_event(event):
        published.append(event)

    monkeypatch.setattr(actions.bus, "publish", capture_event)

    game, p1 = await _create_started_two_player_game(game_client, "move-path-event")
    unit = await _first_player_unit(game_client, game["id"], p1["id"])

    from_x, from_y = unit["x"], unit["y"]
    to_x, to_y = from_x + 1, from_y
    r = await game_client.post(
        f"/games/{game['id']}/move",
        json={
            "player_id": p1["id"],
            "unit_id": unit["id"],
            "to_x": to_x,
            "to_y": to_y,
        },
    )
    assert r.status_code == 200, f"move failed: {r.status_code} {r.text}"

    move_events = [event for event in published if event.type == "move"]
    assert move_events, "move route should publish a move event"
    ctx = move_events[-1].context
    assert ctx["path"][0] == {"x": from_x, "y": from_y}
    assert ctx["path"][-1] == {"x": to_x, "y": to_y}
