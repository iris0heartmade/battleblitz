"""
End-to-end tests for the mainline progress endpoints (Step 2).

Covers:
  * GET /profile/{user_name} — basic fetch + mainline fields
  * POST /profile/{user_name}/mainline/start — begin, conflict, force
  * POST /profile/{user_name}/mainline/advance — scene + battle_index
  * POST /profile/{user_name}/mainline/advance — auto-clear on finish
  * POST /profile/{user_name}/mainline/abandon — clear + idempotency
  * Service unit tests for the validator injection seam
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


# ============================================================
# Fixtures
# ============================================================

SAMPLE_ID = "chapter_01_steel_rebellion"


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

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


@pytest.fixture
def tmp_mainlines(tmp_path, monkeypatch):
    """Redirect the mainline loader to a tmp dir with one valid file."""
    from app.mainline import clear_cache
    import app.mainline.loader as loader_mod

    monkeypatch.setattr(loader_mod, "_MAINLINES_DIR", tmp_path)
    # Reload the same content from the real repo mainline so the
    # validator has something to load.
    real = Path("/home/youko/PycharmProjects/battleblitz/game/mainlines") \
        / f"{SAMPLE_ID}.json"
    (tmp_path / f"{SAMPLE_ID}.json").write_text(
        real.read_text(encoding="utf-8"), encoding="utf-8"
    )
    clear_cache()
    yield tmp_path
    clear_cache()


# ============================================================
# GET /profile/{user_name}
# ============================================================

@pytest.mark.integration
class TestGetProfile:
    async def test_get_profile_basic(self, prog_client):
        await prog_client.post("/progression/profiles", json={"user_name": "alice"})
        r = await prog_client.get("/profile/alice")
        assert r.status_code == 200
        body = r.json()
        assert body["user_name"] == "alice"
        assert body["active_mainline"] is None
        assert body["mainline_progress"] == {}

    async def test_get_profile_404(self, prog_client):
        r = await prog_client.get("/profile/ghost")
        assert r.status_code == 404

    async def test_get_profile_includes_mainline_state(self, prog_client, tmp_mainlines):
        await prog_client.post("/progression/profiles", json={"user_name": "bob"})
        await prog_client.post(
            "/profile/bob/mainline/start",
            json={"mainline_id": SAMPLE_ID},
        )
        r = await prog_client.get("/profile/bob")
        assert r.status_code == 200
        body = r.json()
        assert body["active_mainline"] == SAMPLE_ID
        prog = body["mainline_progress"]
        assert prog["battle_index"] == 0
        assert prog["scene_id"] == "intro"
        assert prog["started_at"] is not None


# ============================================================
# POST /profile/{user_name}/mainline/start
# ============================================================

@pytest.mark.integration
class TestStartMainline:
    async def test_start_ok(self, prog_client, tmp_mainlines):
        await prog_client.post("/progression/profiles", json={"user_name": "p1"})
        r = await prog_client.post(
            "/profile/p1/mainline/start",
            json={"mainline_id": SAMPLE_ID},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["user_name"] == "p1"
        assert body["active_mainline"] == SAMPLE_ID
        assert body["mainline_progress"]["battle_index"] == 0
        assert body["mainline_progress"]["scene_id"] == "intro"
        assert body["cleared"] is False

    async def test_start_profile_404(self, prog_client, tmp_mainlines):
        r = await prog_client.post(
            "/profile/ghost/mainline/start",
            json={"mainline_id": SAMPLE_ID},
        )
        assert r.status_code == 404

    async def test_start_unknown_mainline_404(self, prog_client, tmp_mainlines):
        await prog_client.post("/progression/profiles", json={"user_name": "p2"})
        r = await prog_client.post(
            "/profile/p2/mainline/start",
            json={"mainline_id": "does_not_exist_xyz"},
        )
        assert r.status_code == 404

    async def test_start_invalid_id_pattern_422(self, prog_client, tmp_mainlines):
        await prog_client.post("/progression/profiles", json={"user_name": "p3"})
        r = await prog_client.post(
            "/profile/p3/mainline/start",
            json={"mainline_id": "BAD ID WITH SPACES"},
        )
        assert r.status_code == 422  # Pydantic regex

    async def test_start_while_active_409(self, prog_client, tmp_mainlines):
        await prog_client.post("/progression/profiles", json={"user_name": "p4"})
        await prog_client.post(
            "/profile/p4/mainline/start",
            json={"mainline_id": SAMPLE_ID},
        )
        r = await prog_client.post(
            "/profile/p4/mainline/start",
            json={"mainline_id": SAMPLE_ID},
        )
        assert r.status_code == 409

    async def test_start_force_resets(self, prog_client, tmp_mainlines):
        await prog_client.post("/progression/profiles", json={"user_name": "p5"})
        # Begin, then advance the cursor, then force-restart.
        await prog_client.post(
            "/profile/p5/mainline/start",
            json={"mainline_id": SAMPLE_ID},
        )
        await prog_client.post(
            "/profile/p5/mainline/advance",
            json={"scene_id": "battle_01_after"},
        )
        r = await prog_client.post(
            "/profile/p5/mainline/start",
            json={"mainline_id": SAMPLE_ID, "force": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["active_mainline"] == SAMPLE_ID
        assert body["mainline_progress"]["battle_index"] == 0
        assert body["mainline_progress"]["scene_id"] == "intro"
        assert body["mainline_progress"]["started_at"] is not None


# ============================================================
# POST /profile/{user_name}/mainline/advance
# ============================================================

@pytest.mark.integration
class TestAdvanceMainline:
    async def _setup_started(self, client) -> None:
        await client.post("/progression/profiles", json={"user_name": "adv"})
        await client.post(
            "/profile/adv/mainline/start",
            json={"mainline_id": SAMPLE_ID},
        )

    async def test_advance_no_active_409(self, prog_client, tmp_mainlines):
        await prog_client.post("/progression/profiles", json={"user_name": "noactive"})
        r = await prog_client.post(
            "/profile/noactive/mainline/advance",
            json={"scene_id": "intro"},
        )
        assert r.status_code == 409

    async def test_advance_scene_only(self, prog_client, tmp_mainlines):
        await self._setup_started(prog_client)
        r = await prog_client.post(
            "/profile/adv/mainline/advance",
            json={"scene_id": "battle_01_after"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["active_mainline"] == SAMPLE_ID
        assert body["mainline_progress"]["scene_id"] == "battle_01_after"
        assert body["mainline_progress"]["battle_index"] == 0
        assert body["cleared"] is False

    async def test_advance_battle_only(self, prog_client, tmp_mainlines):
        await self._setup_started(prog_client)
        r = await prog_client.post(
            "/profile/adv/mainline/advance",
            json={"next_battle": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["mainline_progress"]["battle_index"] == 1
        # scene_id was not changed
        assert body["mainline_progress"]["scene_id"] == "intro"

    async def test_advance_combined(self, prog_client, tmp_mainlines):
        await self._setup_started(prog_client)
        r = await prog_client.post(
            "/profile/adv/mainline/advance",
            json={"scene_id": "battle_02_after", "next_battle": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["mainline_progress"]["battle_index"] == 1
        assert body["mainline_progress"]["scene_id"] == "battle_02_after"

    async def test_advance_invalid_scene_422(self, prog_client, tmp_mainlines):
        await self._setup_started(prog_client)
        r = await prog_client.post(
            "/profile/adv/mainline/advance",
            json={"scene_id": "no_such_dialogue"},
        )
        assert r.status_code == 422

    async def test_advance_noop_when_no_fields(self, prog_client, tmp_mainlines):
        await self._setup_started(prog_client)
        r = await prog_client.post(
            "/profile/adv/mainline/advance",
            json={},
        )
        assert r.status_code == 200
        body = r.json()
        # No movement
        assert body["mainline_progress"]["battle_index"] == 0
        assert body["mainline_progress"]["scene_id"] == "intro"
        assert body["cleared"] is False

    async def test_advance_auto_clear_on_last_battle(
        self, prog_client, tmp_mainlines
    ):
        """chapter_01 has 2 battles; advancing past index 1 must clear."""
        await self._setup_started(prog_client)
        # First advance: index 0 -> 1 (mid-campaign, no clear)
        r1 = await prog_client.post(
            "/profile/adv/mainline/advance",
            json={"next_battle": True},
        )
        assert r1.status_code == 200
        assert r1.json()["cleared"] is False
        assert r1.json()["active_mainline"] == SAMPLE_ID

        # Second advance: index 1 -> 2 (== len(battles) -> cleared)
        r2 = await prog_client.post(
            "/profile/adv/mainline/advance",
            json={"next_battle": True, "scene_id": "victory"},
        )
        assert r2.status_code == 200
        body = r2.json()
        assert body["cleared"] is True
        assert body["active_mainline"] is None
        # progress cursor kept but started_at cleared
        assert body["mainline_progress"]["battle_index"] == 2
        assert body["mainline_progress"]["scene_id"] == "victory"
        assert body["mainline_progress"]["started_at"] is None


# ============================================================
# POST /profile/{user_name}/mainline/abandon
# ============================================================

@pytest.mark.integration
class TestAbandonMainline:
    async def test_abandon_active(self, prog_client, tmp_mainlines):
        await prog_client.post("/progression/profiles", json={"user_name": "ab1"})
        await prog_client.post(
            "/profile/ab1/mainline/start",
            json={"mainline_id": SAMPLE_ID},
        )
        r = await prog_client.post(
            "/profile/ab1/mainline/abandon",
            json={},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["active_mainline"] is None
        assert body["cleared"] is True
        assert body["mainline_progress"]["started_at"] is None

    async def test_abandon_idempotent(self, prog_client, tmp_mainlines):
        await prog_client.post("/progression/profiles", json={"user_name": "ab2"})
        r = await prog_client.post(
            "/profile/ab2/mainline/abandon",
            json={},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["active_mainline"] is None
        assert body["cleared"] is True

    async def test_abandon_unknown_profile_404(self, prog_client, tmp_mainlines):
        r = await prog_client.post(
            "/profile/ghost/mainline/abandon",
            json={},
        )
        assert r.status_code == 404

    async def test_abandon_then_restart(self, prog_client, tmp_mainlines):
        await prog_client.post("/progression/profiles", json={"user_name": "ab3"})
        await prog_client.post(
            "/profile/ab3/mainline/start",
            json={"mainline_id": SAMPLE_ID},
        )
        await prog_client.post("/profile/ab3/mainline/abandon", json={})
        r = await prog_client.post(
            "/profile/ab3/mainline/start",
            json={"mainline_id": SAMPLE_ID},
        )
        assert r.status_code == 200
        assert r.json()["active_mainline"] == SAMPLE_ID


# ============================================================
# Service unit tests (validator injection seam)
# ============================================================

@pytest.mark.unit
class TestServiceValidatorInjection:
    async def test_set_active_uses_injected_validator(self, db_session):
        """A custom validator should be honoured — no real mainline file needed."""
        from app.progression import ProgressionService
        from app.progression.models import PlayerProfile

        calls: list[str] = []

        def fake_validator(mid: str) -> None:
            calls.append(mid)
            if mid != "ok":
                from app.progression.exceptions import MainlineIdNotFound
                raise MainlineIdNotFound(f"fake: {mid}")

        svc = ProgressionService(
            db_session, mainline_validator=fake_validator
        )
        db_session.add(PlayerProfile(user_name="svc1"))
        await db_session.flush()

        summary = await svc.set_active_mainline("svc1", "ok")
        assert summary.active_mainline == "ok"
        assert calls == ["ok"]

    async def test_set_active_raises_on_validator_fail(self, db_session):
        from app.progression import ProgressionService
        from app.progression.exceptions import MainlineIdNotFound
        from app.progression.models import PlayerProfile

        def bad(_mid: str) -> None:
            raise MainlineIdNotFound("denied")

        svc = ProgressionService(
            db_session, mainline_validator=bad
        )
        db_session.add(PlayerProfile(user_name="svc2"))
        await db_session.flush()

        with pytest.raises(MainlineIdNotFound):
            await svc.set_active_mainline("svc2", "anything")

    async def test_default_validator_uses_real_loader(self, db_session, tmp_mainlines):
        from app.progression import ProgressionService
        from app.progression.exceptions import MainlineIdNotFound
        from app.progression.models import PlayerProfile

        svc = ProgressionService(db_session)  # default validator
        db_session.add(PlayerProfile(user_name="svc3"))
        await db_session.flush()

        # Real id (file exists in tmp_mainlines fixture)
        summary = await svc.set_active_mainline("svc3", SAMPLE_ID)
        assert summary.active_mainline == SAMPLE_ID

        # Bogus id — default validator must raise
        with pytest.raises(MainlineIdNotFound):
            await svc.set_active_mainline("svc3", "no_such_mainline")
