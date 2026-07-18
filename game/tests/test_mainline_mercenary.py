"""
Integration tests for the mercenary allocation flow on mainlines.

Wires the previously-orphaned ``app.mercenary_domain`` models into
the mainline API so the third pillar of the dual-track plan
(Mercenary 主力体系, spec §8 phase 3) has a real, tested endpoint.

Endpoints covered:
  - GET  /mainlines/{id}/mercenary/config
        → returns the chapter's ``ChapterBalanceConfig`` (defaults if
          the mainline JSON doesn't declare one)
        → plus the player's current ``CommanderAllocation`` and the
          number of mercenary points they have to spend
  - POST /mainlines/{id}/mercenary/allocate
        → body: { "user_name": ..., "unit_type": ..., "stat": ...,
                   "value": ... }; the server calculates the cost
        → decrements ``mercenary_points`` on the profile, records the
          upgrade in ``MercenaryRosterState.unit_type_upgrades``,
          returns the updated allocation
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest.fixture
async def merc_client():
    from app.main import app
    from app.database import (
        AsyncSessionLocal,
        Base,
        dispose_db,
        engine,
        init_db,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, AsyncSessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


async def _create_profile(client, user_name="alice"):
    r = await client.post("/progression/profiles", json={"user_name": user_name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ============================================================
# GET config
# ============================================================

@pytest.mark.integration
class TestMercenaryConfig:
    async def test_returns_default_balance_config(self, merc_client):
        client, _ = merc_client
        await _create_profile(client, "alice")
        r = await client.get(
            "/mainlines/chapter_01_steel_rebellion/mercenary/config",
            params={"user_name": "alice"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Default ChapterBalanceConfig: enemy_modifiers all zero.
        assert body["balance"]["enemy_modifiers"] == {
            "attack": 0, "defense": 0, "income": 0,
            "move": 0, "vision": 0,
        }
        assert body["balance"]["total_points"] == 100
        assert body["balance"]["stat_rules"]["atk"] == {
            "point_cost": 10, "max_bonus": 5,
        }
        # New player starts with a clean allocation and 100 points.
        assert body["allocation"]["total_points"] == 100
        assert body["allocation"]["spent_points"] == 0
        assert body["allocation"]["unit_type_upgrades"] == {}
        assert body["mercenary_points"] == 100

    async def test_returns_existing_allocation(self, merc_client):
        client, SessionLocal = merc_client
        await _create_profile(client, "alice")

        from app.progression.models import PlayerProfile
        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            profile.mercenary_roster_state = {
                "allocation": {
                    "total_points": 100,
                    "spent_points": 30,
                    "unit_type_upgrades": {
                        "swordsman": {"atk": 1, "def": 1},
                    },
                },
                "recruited_units": [],
            }
            await s.commit()

        r = await client.get(
            "/mainlines/chapter_01_steel_rebellion/mercenary/config",
            params={"user_name": "alice"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["allocation"]["spent_points"] == 30
        assert body["allocation"]["unit_type_upgrades"] == {
            "swordsman": {"atk": 1, "def": 1},
        }
        # Remaining points = total - spent.
        assert body["mercenary_points"] == 70


# ============================================================
# POST allocate
# ============================================================

@pytest.mark.integration
class TestMercenaryAllocate:
    async def test_allocate_records_upgrade(self, merc_client):
        client, SessionLocal = merc_client
        await _create_profile(client, "alice")

        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/mercenary/allocate",
            json={
                "user_name": "alice",
                "unit_type": "swordsman",
                "stat": "atk",
                "value": 1,
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["spent_points"] == 10
        assert body["remaining_points"] == 90
        assert body["unit_type_upgrades"] == {"swordsman": {"atk": 1}}

        # Persisted to the profile.
        from app.progression.models import PlayerProfile
        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            saved = profile.mercenary_roster_state["allocation"]
            assert saved["spent_points"] == 10
            assert saved["unit_type_upgrades"] == {"swordsman": {"atk": 1}}

    async def test_allocate_rejects_overspend(self, merc_client):
        client, _ = merc_client
        await _create_profile(client, "alice")

        # Reach 90 points within per-stat limits, then exceed the total.
        for payload in (
            {"unit_type": "swordsman", "stat": "hp", "value": 10},
            {"unit_type": "swordsman", "stat": "hp", "value": 10},
            {"unit_type": "swordsman", "stat": "atk", "value": 5},
        ):
            r1 = await client.post(
                "/mainlines/chapter_01_steel_rebellion/mercenary/allocate",
                json={"user_name": "alice", **payload},
            )
            assert r1.status_code == 200, r1.text

        r2 = await client.post(
            "/mainlines/chapter_01_steel_rebellion/mercenary/allocate",
            json={
                "user_name": "alice",
                "unit_type": "swordsman",
                "stat": "def",
                "value": 2,
            },
        )
        assert r2.status_code == 409, r2.text
        assert "points" in r2.json()["detail"].lower()

    async def test_allocate_unknown_profile_returns_404(self, merc_client):
        client, _ = merc_client
        r = await client.post(
            "/mainlines/chapter_01_steel_rebellion/mercenary/allocate",
            json={
                "user_name": "ghost",
                "unit_type": "swordsman",
                "stat": "atk",
                "value": 1,
            },
        )
        assert r.status_code == 404


@pytest.mark.integration
async def test_mainline_spawn_applies_allocation_only_to_generic_units(merc_client):
    client, SessionLocal = merc_client
    await _create_profile(client, "alice")
    allocated = await client.post(
        "/mainlines/chapter_01_steel_rebellion/mercenary/allocate",
        json={
            "user_name": "alice", "unit_type": "swordsman",
            "stat": "atk", "value": 2,
        },
    )
    assert allocated.status_code == 200, allocated.text

    started = await client.post(
        "/mainlines/chapter_01_steel_rebellion/start",
        json={"user_name": "alice", "skip_intro": True},
    )
    assert started.status_code == 201, started.text

    from app.models import Game, Player, Unit
    async with SessionLocal() as s:
        game = (await s.execute(select(Game))).scalar_one()
        human = (await s.execute(
            select(Player).where(Player.game_id == game.id, Player.is_ai.is_(False))
        )).scalar_one()
        units = (await s.execute(
            select(Unit).where(Unit.player_id == human.id)
        )).scalars().all()
        generic_swordsman = next(unit for unit in units if unit.hero_id is None and unit.unit_type == "swordsman")
        hero_warlock = next(unit for unit in units if unit.hero_id == "yun")
        assert generic_swordsman.atk == 20  # base 18 + allocated 2
        assert hero_warlock.atk == 20  # hero data, not a swordsman allocation
        assert game.battle_config["mercenary"]["unit_type_upgrades"] == {
            "swordsman": {"atk": 2},
        }
