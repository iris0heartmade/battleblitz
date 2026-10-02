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


async def _pick_move_target(game_client, game_id: int, player_id: int):
    """挑一个「确实可通行且无人占」的邻格作为移动目标。

    默认对局地图 seed 随机,首单位位置与周边地形/占用都会变;硬编码
    `from_x + 1` 在目标被占/不可行时会 400(实测 ~15%),导致测试偶发
    flaky。这里按「界内 + 未占 + terrain_passable」四向找一个稳定目标。
    """
    from app.utils import terrain_passable

    state = (await game_client.get(f"/games/{game_id}/state")).json()
    player = next(p for p in state["players"] if p["id"] == player_id)
    unit = player["units"][0]
    occupied = {
        (u["x"], u["y"]) for pl in state["players"] for u in pl.get("units", [])
    }
    tiles = {(t["x"], t["y"]): t for t in state["tiles"]}
    for dx, dy in [(1, 0), (0, 1), (-1, 0), (0, -1)]:
        cx, cy = unit["x"] + dx, unit["y"] + dy
        tile = tiles.get((cx, cy))
        if tile is None or (cx, cy) in occupied:
            continue
        if terrain_passable(
            str(tile.get("terrain", "plain")),
            owner_id=tile.get("owner_id"),
            viewer_owner_id=player_id,
        ):
            return unit, (cx, cy)
    return unit, None


@pytest.mark.integration
async def test_end_turn_works_after_a_single_move(game_client):
    game, p1 = await _create_started_two_player_game(game_client, "regression")
    unit, (to_x, to_y) = await _pick_move_target(game_client, game["id"], p1["id"])
    assert to_x is not None, "no passable adjacent tile found"

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
    unit, (to_x, to_y) = await _pick_move_target(game_client, game["id"], p1["id"])
    assert to_x is not None, "no passable adjacent tile found"
    from_x, from_y = unit["x"], unit["y"]

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
