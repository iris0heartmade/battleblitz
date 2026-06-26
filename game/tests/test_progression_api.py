"""
Integration tests for the progression API.

Covers repository + service + REST endpoints end-to-end (in-process).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


# We import the FastAPI app lazily inside the fixture so init_db's table
# creation runs after conftest sets DATABASE_URL.


@pytest.fixture
async def prog_client():
    """ASGI client with a freshly-cleaned DB per test."""
    from app.main import app
    from app.database import (
        AsyncSessionLocal,
        Base,
        dispose_db,
        engine,
        init_db,
    )

    # Drop and recreate to ensure no leakage between tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    # Clean up for the next test
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


# ============================================================
# Profile endpoints
# ============================================================

@pytest.mark.integration
class TestProfileAPI:
    async def test_create_profile(self, prog_client):
        r = await prog_client.post("/progression/profiles", json={"user_name": "alice"})
        assert r.status_code == 201
        body = r.json()
        assert body["user_name"] == "alice"
        assert body["rating"] == 1000
        assert body["gold"] == 0
        assert "id" in body

    async def test_create_duplicate_returns_409(self, prog_client):
        await prog_client.post("/progression/profiles", json={"user_name": "bob"})
        r = await prog_client.post("/progression/profiles", json={"user_name": "bob"})
        assert r.status_code == 409

    async def test_list_profiles(self, prog_client):
        await prog_client.post("/progression/profiles", json={"user_name": "p1"})
        await prog_client.post("/progression/profiles", json={"user_name": "p2"})
        r = await prog_client.get("/progression/profiles")
        assert r.status_code == 200
        names = [p["user_name"] for p in r.json()]
        assert "p1" in names and "p2" in names

    async def test_get_profile_404(self, prog_client):
        r = await prog_client.get("/progression/profiles/9999")
        assert r.status_code == 404

    async def test_get_profile_ok(self, prog_client):
        created = (await prog_client.post(
            "/progression/profiles", json={"user_name": "carol"}
        )).json()
        r = await prog_client.get(f"/progression/profiles/{created['id']}")
        assert r.status_code == 200
        assert r.json()["user_name"] == "carol"


# ============================================================
# Unit endpoints
# ============================================================

@pytest.mark.integration
class TestUnitAPI:
    async def _profile(self, client, name="owner") -> int:
        r = await client.post("/progression/profiles", json={"user_name": name})
        return r.json()["id"]

    async def test_create_unit(self, prog_client):
        pid = await self._profile(prog_client, "u1")
        r = await prog_client.post(
            f"/progression/profiles/{pid}/units",
            json={"base_type": "swordsman", "nickname": "MyHero"},
        )
        assert r.status_code == 201
        u = r.json()
        assert u["base_type"] == "swordsman"
        assert u["nickname"] == "MyHero"
        assert u["level"] == 1
        assert u["tier"] == 1
        assert u["talent_points"] == 0

    async def test_create_unit_invalid_nickname_400(self, prog_client):
        pid = await self._profile(prog_client, "u1")
        r = await prog_client.post(
            f"/progression/profiles/{pid}/units",
            json={"base_type": "swordsman", "nickname": ""},
        )
        assert r.status_code == 422  # Pydantic validation

    async def test_create_unit_invalid_base_type(self, prog_client):
        pid = await self._profile(prog_client, "u1")
        r = await prog_client.post(
            f"/progression/profiles/{pid}/units",
            json={"base_type": "wizard", "nickname": "X"},
        )
        assert r.status_code == 422  # Pydantic regex pattern

    async def test_create_unit_for_missing_profile_404(self, prog_client):
        r = await prog_client.post(
            "/progression/profiles/9999/units",
            json={"base_type": "archer", "nickname": "X"},
        )
        assert r.status_code == 404

    async def test_duplicate_nickname_409(self, prog_client):
        pid = await self._profile(prog_client, "u1")
        await prog_client.post(
            f"/progression/profiles/{pid}/units",
            json={"base_type": "swordsman", "nickname": "Same"},
        )
        r = await prog_client.post(
            f"/progression/profiles/{pid}/units",
            json={"base_type": "archer", "nickname": "Same"},
        )
        assert r.status_code == 409

    async def test_list_units(self, prog_client):
        pid = await self._profile(prog_client, "u1")
        for n in ("alpha", "beta"):
            await prog_client.post(
                f"/progression/profiles/{pid}/units",
                json={"base_type": "swordsman", "nickname": n},
            )
        r = await prog_client.get(f"/progression/profiles/{pid}/units")
        assert r.status_code == 200
        nicks = [u["nickname"] for u in r.json()]
        assert nicks == ["alpha", "beta"]

    async def test_get_unit(self, prog_client):
        pid = await self._profile(prog_client, "u1")
        u = (await prog_client.post(
            f"/progression/profiles/{pid}/units",
            json={"base_type": "knight", "nickname": "SirK"},
        )).json()
        r = await prog_client.get(f"/progression/units/{u['id']}")
        assert r.status_code == 200
        assert r.json()["nickname"] == "SirK"


# ============================================================
# Leveling endpoints
# ============================================================

@pytest.mark.integration
class TestLevelingAPI:
    async def _unit(self, client) -> int:
        pid = (await client.post(
            "/progression/profiles", json={"user_name": "lvl"}
        )).json()["id"]
        u = (await client.post(
            f"/progression/profiles/{pid}/units",
            json={"base_type": "swordsman", "nickname": "Hero"},
        )).json()
        return u["id"]

    async def test_award_xp_levels_up(self, prog_client):
        uid = await self._unit(prog_client)
        r = await prog_client.post(
            f"/progression/units/{uid}/xp",
            json={"amount": 100, "reason": "test"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["levels_gained"] == 1
        assert body["new_level"] == 2
        assert body["talent_points_awarded"] == 1

    async def test_award_xp_partial(self, prog_client):
        uid = await self._unit(prog_client)
        r = await prog_client.post(
            f"/progression/units/{uid}/xp",
            json={"amount": 50},
        )
        body = r.json()
        assert body["levels_gained"] == 0
        assert body["new_level"] == 1
        assert body["new_exp"] == 50

    async def test_award_xp_at_cap(self, prog_client):
        uid = await self._unit(prog_client)
        # Push the unit to Lv 20 first (use max allowed per request)
        await prog_client.post(
            f"/progression/units/{uid}/xp", json={"amount": 100_000}
        )
        # Now award more — should be capped
        r = await prog_client.post(
            f"/progression/units/{uid}/xp", json={"amount": 1000}
        )
        body = r.json()
        assert body["new_level"] == 20  # tier 1 cap
        assert body["capped"] is True

    async def test_award_xp_missing_unit_404(self, prog_client):
        r = await prog_client.post(
            "/progression/units/9999/xp", json={"amount": 100}
        )
        assert r.status_code == 404

    async def test_promote(self, prog_client):
        uid = await self._unit(prog_client)
        # Level to 20 first (max per-request is 100_000)
        await prog_client.post(
            f"/progression/units/{uid}/xp", json={"amount": 100_000}
        )
        r = await prog_client.post(
            f"/progression/units/{uid}/promote", json={}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["old_tier"] == 1
        assert body["new_tier"] == 2
        assert body["new_level_cap"] == 35

    async def test_promote_too_early_400(self, prog_client):
        uid = await self._unit(prog_client)
        r = await prog_client.post(
            f"/progression/units/{uid}/promote", json={}
        )
        assert r.status_code == 400

    async def test_promote_max_tier_400(self, prog_client):
        uid = await self._unit(prog_client)
        # Force-promote twice to reach tier 3
        await prog_client.post(
            f"/progression/units/{uid}/xp", json={"amount": 100_000}
        )
        await prog_client.post(
            f"/progression/units/{uid}/promote", json={"force": True}
        )
        # Now at tier 2, level 20. Force to tier 3
        await prog_client.post(
            f"/progression/units/{uid}/xp", json={"amount": 100_000}
        )
        await prog_client.post(
            f"/progression/units/{uid}/promote", json={"force": True}
        )
        # Now tier 3 — cannot promote further
        r = await prog_client.post(
            f"/progression/units/{uid}/promote", json={"force": True}
        )
        assert r.status_code == 400


# ============================================================
# Delete
# ============================================================

@pytest.mark.integration
class TestDeleteUnit:
    async def test_delete_unit(self, prog_client):
        pid = (await prog_client.post(
            "/progression/profiles", json={"user_name": "del"}
        )).json()["id"]
        u = (await prog_client.post(
            f"/progression/profiles/{pid}/units",
            json={"base_type": "archer", "nickname": "Bye"},
        )).json()
        r = await prog_client.delete(f"/progression/units/{u['id']}")
        assert r.status_code == 204
        # Verify it's gone
        r = await prog_client.get(f"/progression/units/{u['id']}")
        assert r.status_code == 404
