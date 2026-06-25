"""
Integration tests — exercise the full HTTP layer with an in-process ASGI client.

These run against the real FastAPI app and the real (per-test-temp) SQLite
database. They are slower than unit tests but verify the wiring end-to-end.
"""
from __future__ import annotations

import pytest


# ============================================================
# Meta / health endpoint
# ============================================================

@pytest.mark.integration
class TestMeta:
    async def test_healthz(self, client):
        r = await client.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    async def test_root_redirects_to_ui(self, client):
        r = await client.get("/", follow_redirects=False)
        assert r.status_code in (301, 302, 307)
        assert r.headers["location"].endswith("/ui/")

    async def test_ui_serves_index(self, client):
        r = await client.get("/ui/")
        assert r.status_code == 200
        assert "<!doctype html>" in r.text.lower()
        assert "BattleBlitz" in r.text


# ============================================================
# Game-lifecycle API
# ============================================================

@pytest.mark.integration
class TestGameLifecycle:
    async def test_create_game(self, client):
        r = await client.post("/games", json={"name": "Smoke Test"})
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "Smoke Test"
        assert body["status"] == "waiting"
        assert "id" in body

    async def test_create_then_list(self, client):
        await client.post("/games", json={"name": "Game A"})
        await client.post("/games", json={"name": "Game B"})
        r = await client.get("/games")
        assert r.status_code == 200
        names = [g["name"] for g in r.json()]
        assert "Game A" in names and "Game B" in names

    async def test_create_with_invalid_max_players_rejected(self, client):
        r = await client.post("/games", json={"name": "X", "max_players": 99})
        assert r.status_code == 422  # pydantic validation

    async def test_presets_endpoint(self, client):
        r = await client.get("/games/presets")
        assert r.status_code == 200
        body = r.json()
        assert "maps" in body and "unit_compositions" in body
        assert len(body["maps"]) > 0
        assert len(body["unit_compositions"]) > 0

    async def test_state_for_missing_game_returns_404(self, client):
        r = await client.get("/games/9999/state")
        assert r.status_code == 404


@pytest.mark.integration
class TestJoin:
    async def test_join_then_state(self, client):
        # Create
        g = (await client.post("/games", json={"name": "J"})).json()
        # Join
        r = await client.post(f"/games/{g['id']}/join",
                              json={"user_name": "alice"})
        assert r.status_code == 201
        player = r.json()
        assert player["user_name"] == "alice"
        assert player["seat"] == 0
        # State should show the player
        state = (await client.get(f"/games/{g['id']}/state")).json()
        assert any(p["user_name"] == "alice" for p in state["players"])

    async def test_duplicate_username_rejected(self, client):
        g = (await client.post("/games", json={"name": "J"})).json()
        await client.post(f"/games/{g['id']}/join", json={"user_name": "x"})
        r = await client.post(f"/games/{g['id']}/join", json={"user_name": "x"})
        assert r.status_code == 409

    async def test_cannot_join_started_game(self, client):
        g = (await client.post("/games", json={"name": "J"})).json()
        # Start the game with a single human + AI to satisfy MIN_PLAYERS
        await client.post(f"/games/{g['id']}/join", json={"user_name": "h"})
        await client.post(f"/games/{g['id']}/add-ai", json={})
        start = await client.post(f"/games/{g['id']}/start")
        assert start.status_code == 200
        r = await client.post(f"/games/{g['id']}/join", json={"user_name": "late"})
        assert r.status_code == 400


@pytest.mark.integration
class TestAddAI:
    async def test_add_ai_creates_player(self, client):
        g = (await client.post("/games", json={"name": "AI"})).json()
        r = await client.post(f"/games/{g['id']}/add-ai", json={})
        assert r.status_code == 201
        ai = r.json()
        assert ai["is_ai"] is True
        assert ai["user_name"].startswith("电脑-")

    async def test_add_ai_to_started_game_rejected(self, client):
        g = (await client.post("/games", json={"name": "AI"})).json()
        await client.post(f"/games/{g['id']}/join", json={"user_name": "h"})
        await client.post(f"/games/{g['id']}/add-ai", json={})
        await client.post(f"/games/{g['id']}/start")
        r = await client.post(f"/games/{g['id']}/add-ai", json={})
        assert r.status_code == 400
