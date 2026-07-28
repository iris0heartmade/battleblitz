"""
Tests for ``DELETE /saves/suspend?user_name=...`` — the "放弃中断存档" endpoint.

Motivation: the Godot pause-panel "中断退出" flow *writes* a SuspendState
row.  When the player then re-enters the multiplayer lobby from the main
menu, the lobby needs a way to *clear* that row so the player can start
fresh without resuming the suspended battle.  ``SaveService.clear_suspend``
already exists; this test pins the route-level contract.

Coverage:
  * Idempotent drop: clears an existing suspend, returns cleared=True.
  * No-op drop: returns cleared=False when no suspend exists.
  * 404 on unknown user.
  * GET /saves after discard returns suspend=None (the row is really gone,
    not just hidden).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest.fixture
async def discard_client():
    from app.main import app
    from app.database import (
        AsyncSessionLocal,
        Base,
        dispose_db,
        engine,
        init_db,
    )
    from app.mainline import clear_cache

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()
    clear_cache()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, AsyncSessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_db()


async def _create_profile(client, user_name: str) -> int:
    r = await client.post("/progression/profiles", json={"user_name": user_name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _capture_suspend(client, user_name: str = "alice") -> int:
    """Drive the public POST /games/{id}/suspend to write a SuspendState row."""
    await _create_profile(client, user_name)
    r = await client.post(
        "/mainlines/chapter_test_01/start",
        json={"user_name": user_name, "skip_intro": True},
    )
    assert r.status_code == 201, r.text
    gid = r.json()["game_id"]
    r2 = await client.post(
        f"/games/{gid}/suspend",
        json={"user_name": user_name},
    )
    assert r2.status_code == 200, r2.text
    return gid


class TestDiscardSuspend:
    async def test_discard_clears_existing_suspend(self, discard_client):
        client, _ = discard_client
        gid = await _capture_suspend(client)

        # Sanity: suspend is present before discard.
        before = await client.get("/saves", params={"user_name": "alice"})
        assert before.status_code == 200, before.text
        assert before.json()["suspend"] is not None
        assert before.json()["suspend"]["game_id"] == gid

        # Discard.
        r = await client.delete(
            "/saves/suspend", params={"user_name": "alice"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["cleared"] is True

        # GET /saves reflects the drop.
        after = await client.get("/saves", params={"user_name": "alice"})
        assert after.json()["suspend"] is None

    async def test_discard_is_idempotent_when_no_suspend(self, discard_client):
        client, _ = discard_client
        await _create_profile(client, "alice")

        # No prior suspend — should still 200, cleared=False.
        r = await client.delete(
            "/saves/suspend", params={"user_name": "alice"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["cleared"] is False

    async def test_discard_rejects_unknown_user(self, discard_client):
        client, _ = discard_client
        # 'ghost' has no profile → must surface as 404, not silent success.
        r = await client.delete(
            "/saves/suspend", params={"user_name": "ghost"},
        )
        assert r.status_code == 404, r.text

    async def test_discard_rejects_empty_user_name(self, discard_client):
        client, _ = discard_client
        # FastAPI's min_length=1 on Query is enforced; empty string → 422.
        r = await client.delete("/saves/suspend", params={"user_name": ""})
        assert r.status_code == 422, r.text

    async def test_double_discard_first_true_second_false(self, discard_client):
        """Idempotency check at the row level: after the first drop the
        second call must observe cleared=False (no row to remove)."""
        client, SessionLocal = discard_client
        await _capture_suspend(client)

        r1 = await client.delete(
            "/saves/suspend", params={"user_name": "alice"},
        )
        assert r1.json()["cleared"] is True

        r2 = await client.delete(
            "/saves/suspend", params={"user_name": "alice"},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["cleared"] is False

        # And the underlying SuspendState row count for 'alice' is zero.
        from app.save.models import SuspendState
        async with SessionLocal() as s:
            count = len((await s.execute(
                select(SuspendState).where(SuspendState.user_name == "alice")
            )).scalars().all())
        assert count == 0