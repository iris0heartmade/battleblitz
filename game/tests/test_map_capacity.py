"""P2.4 — per-room capacity tests.

Verifies that:
  - Game.capacity is derived from the chosen map's `recommended_players`
  - Legacy presets (no `recommended_players` in JSON) default to MAX_PLAYERS=4
  - join_game rejects players beyond the room's capacity
  - add_ai_player rejects when the room is full
  - get_lobby_info returns max_players = game.capacity (not the global
    MAX_PLAYERS constant)
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Base, dispose_db, engine, init_db
from app.main import app
from app.models import Game, Player


@pytest.fixture
async def game_client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


# ============================================================
# Capacity derivation on create_game
# ============================================================

@pytest.mark.asyncio
async def test_create_game_2p_map_capacity_2(game_client):
    """Choosing a 2p preset yields a room with capacity=2."""
    r = await game_client.post("/games", json={
        "name": "2p test",
        "map_preset": "realistic_grass_2p_20",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["capacity"] == 2


@pytest.mark.asyncio
async def test_create_game_4p_map_capacity_4(game_client):
    r = await game_client.post("/games", json={
        "name": "4p test",
        "map_preset": "balanced_4p_20",
    })
    assert r.status_code == 201
    assert r.json()["capacity"] == 4


@pytest.mark.asyncio
async def test_create_game_balanced_2p_capacity_2(game_client):
    """P2.6+ — balanced_2p_15 is a 2-castle 15×15 map. A room using
    it should be locked to 2 players (its `recommended_players`)."""
    r = await game_client.post("/games", json={
        "name": "balanced-2p",
        "map_preset": "balanced_2p_15",
    })
    assert r.status_code == 201, r.text
    assert r.json()["capacity"] == 2


@pytest.mark.asyncio
async def test_create_game_custom_map_defaults_to_4(game_client):
    """`custom:<id>` is not in MAP_PRESETS — should also default to 4."""
    r = await game_client.post("/games", json={
        "name": "custom",
        "map_preset": "custom:nonexistent",
    })
    assert r.status_code == 201
    assert r.json()["capacity"] == 4


# ============================================================
# join_game gate
# ============================================================

@pytest.mark.asyncio
async def test_join_2p_room_rejects_third_player(game_client):
    r = await game_client.post("/games", json={
        "name": "2p",
        "map_preset": "realistic_grass_2p_20",
    })
    gid = r.json()["id"]

    # Two players join (real human, capacity=2).
    for name in ("alice", "bob"):
        r = await game_client.post(f"/games/{gid}/join", json={"user_name": name})
        assert r.status_code == 201

    # Third player must be rejected with 409.
    r = await game_client.post(f"/games/{gid}/join", json={"user_name": "carol"})
    assert r.status_code == 409, r.text
    assert "房间已满" in r.json()["detail"]


@pytest.mark.asyncio
async def test_join_4p_room_allows_four_players(game_client):
    r = await game_client.post("/games", json={
        "name": "4p",
        "map_preset": "balanced_4p_20",
    })
    gid = r.json()["id"]

    for name in ("alice", "bob", "carol", "dave"):
        r = await game_client.post(f"/games/{gid}/join", json={"user_name": name})
        assert r.status_code == 201, r.text

    # Fifth must be rejected.
    r = await game_client.post(f"/games/{gid}/join", json={"user_name": "eve"})
    assert r.status_code == 409


# ============================================================
# add_ai_player gate
# ============================================================

@pytest.mark.asyncio
async def test_add_ai_2p_room_rejects_third_ai(game_client):
    r = await game_client.post("/games", json={
        "name": "2p-ai",
        "map_preset": "realistic_grass_2p_20",
    })
    gid = r.json()["id"]

    # First player joins.
    r = await game_client.post(f"/games/{gid}/join", json={"user_name": "host"})
    assert r.status_code == 201

    # AI joins (1 → 2, capacity reached).
    r = await game_client.post(f"/games/{gid}/add-ai", json={"difficulty": "normal"})
    assert r.status_code == 201, r.text

    # Second AI must be rejected.
    r = await game_client.post(f"/games/{gid}/add-ai", json={"difficulty": "normal"})
    assert r.status_code == 409, r.text
    assert "房间已满" in r.json()["detail"]


@pytest.mark.asyncio
async def test_add_ai_4p_room_allows_three_more_ai(game_client):
    r = await game_client.post("/games", json={
        "name": "4p-ai",
        "map_preset": "balanced_4p_20",
    })
    gid = r.json()["id"]

    r = await game_client.post(f"/games/{gid}/join", json={"user_name": "host"})
    assert r.status_code == 201

    for i in range(3):
        r = await game_client.post(f"/games/{gid}/add-ai", json={"difficulty": "normal"})
        assert r.status_code == 201, f"AI #{i+1} should succeed"

    # 4th AI rejected.
    r = await game_client.post(f"/games/{gid}/add-ai", json={"difficulty": "normal"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_spectator_does_not_consume_an_ai_player_slot(game_client):
    r = await game_client.post("/games", json={
        "name": "4p-with-spectator",
        "map_preset": "balanced_4p_20",
    })
    gid = r.json()["id"]

    assert (await game_client.post(
        f"/games/{gid}/join", json={"user_name": "host"}
    )).status_code == 201
    assert (await game_client.post(
        f"/games/{gid}/join", json={"user_name": "viewer", "role": "spectator"}
    )).status_code == 201

    for i in range(3):
        response = await game_client.post(f"/games/{gid}/add-ai", json={"difficulty": "normal"})
        assert response.status_code == 201, f"AI #{i + 1} should succeed with a spectator"

    response = await game_client.post(f"/games/{gid}/add-ai", json={"difficulty": "normal"})
    assert response.status_code == 409


# ============================================================
# Lobby endpoint reports capacity
# ============================================================

@pytest.mark.asyncio
async def test_lobby_endpoint_returns_capacity(game_client):
    r = await game_client.post("/games", json={
        "name": "lobby-cap",
        "map_preset": "realistic_grass_2p_20",
    })
    gid = r.json()["id"]

    r = await game_client.get(f"/games/{gid}/lobby")
    assert r.status_code == 200
    body = r.json()
    assert body["max_players"] == 2, (
        f"lobby must reflect capacity=2, got {body['max_players']}"
    )


@pytest.mark.asyncio
async def test_lobby_balanced_2p_reports_2(game_client):
    """P2.6+ — balanced_2p_15 lobby reports max_players=2
    (its `recommended_players`), not the legacy 4p default."""
    r = await game_client.post("/games", json={
        "name": "balanced-2p-lobby",
        "map_preset": "balanced_2p_15",
    })
    gid = r.json()["id"]

    r = await game_client.get(f"/games/{gid}/lobby")
    assert r.json()["max_players"] == 2
