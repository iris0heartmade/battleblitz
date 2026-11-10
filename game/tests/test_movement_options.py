"""Movement preview must use the action's rules and never mutate battle state."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def match():
    from app.database import AsyncSessionLocal, Base, engine, init_db
    from app.main import app
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/games", json={"name": "preview-test", "map_preset": "balanced_2p_15", "mode": "mainline"})
        game_id = created.json()["id"]
        red = (await client.post(f"/games/{game_id}/join", json={"user_name": "red", "color": "red", "seat": 0})).json()
        blue = (await client.post(f"/games/{game_id}/join", json={"user_name": "blue", "color": "blue", "seat": 1})).json()
        started = await client.post(f"/games/{game_id}/start", json={})
        assert started.status_code == 200
        yield client, game_id, red["id"], blue["id"], AsyncSessionLocal
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


async def test_preview_read_only_and_move_uses_same_path(match):
    client, game, red, _, _ = match
    before = (await client.get(f"/games/{game}/state")).json()
    actor = next(p for p in before["players"] if p["id"] == red)["units"][0]
    response = await client.get(f"/games/{game}/movement-options", params={"player_id": red, "unit_id": actor["id"]})
    assert response.status_code == 200
    occupied = {(u["x"], u["y"]) for p in before["players"] for u in p["units"] if u["id"] != actor["id"]}
    tiles = response.json()["tiles"]
    assert len(tiles) > 1
    for tile in tiles:
        assert (tile["x"], tile["y"]) not in occupied
        assert tile["cost_x2"] <= actor["mp"] * 2
        assert tile["path"][0] == {"x": actor["x"], "y": actor["y"]}
        assert tile["path"][-1] == {"x": tile["x"], "y": tile["y"]}
    after = (await client.get(f"/games/{game}/state")).json()
    assert before == after
    destination = next(t for t in tiles if t["cost_x2"] > 0)
    moved = await client.post(f"/games/{game}/move", json={"player_id": red, "unit_id": actor["id"], "to_x": destination["x"], "to_y": destination["y"]})
    assert moved.status_code == 200
    assert moved.json()["cost"] == destination["cost_x2"] // 2


async def test_preview_rejects_enemy_wrong_turn_and_missing_unit(match):
    client, game, red, blue, _ = match
    state = (await client.get(f"/games/{game}/state")).json()
    enemy = next(p for p in state["players"] if p["id"] == blue)["units"][0]
    for player, unit, code in [(red, enemy["id"], 403), (blue, enemy["id"], 403), (red, 9999999, 404)]:
        result = await client.get(f"/games/{game}/movement-options", params={"player_id": player, "unit_id": unit})
        assert result.status_code == code


async def test_waited_infantry_has_no_preview(match):
    client, game, red, _, _ = match
    state = (await client.get(f"/games/{game}/state")).json()
    actor = next(u for p in state["players"] if p["id"] == red for u in p["units"] if u["unit_type"] == "swordsman")
    waited = await client.post(f"/games/{game}/wait", json={"player_id": red, "unit_id": actor["id"]})
    assert waited.status_code == 200
    preview = await client.get(f"/games/{game}/movement-options", params={"player_id": red, "unit_id": actor["id"]})
    assert preview.status_code == 200 and preview.json()["tiles"] == []
