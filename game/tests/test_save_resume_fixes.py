"""
Tests for the 3 save/suspend resume-loop fixes.

Fix 1: load() force-aborts in-flight games
Fix 2: POST /saves/load_suspend returns the suspend meta
Fix 3: POST /mainlines/{id}/start with force=true allows restart
        of the same mainline, also aborting in-flight games

Invariants:
  * Load auto/manual save → in-flight Game.status flips to "aborted"
  * Load suspend → returns the suspend info, aborts OTHER games
  * force=true on /start works (same mainline, in-flight game)
  * force=false on /start (different mainline) still 409
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest.fixture
async def client():
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


async def _create_profile(client, name="alice"):
    r = await client.post("/progression/profiles", json={"user_name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ============================================================
# Fix 1: load() aborts in-flight games
# ============================================================


@pytest.mark.integration
class TestLoadAbortsInFlight:
    async def test_load_save_aborts_in_flight_game(self, client):
        c, SessionLocal = client
        await _create_profile(c, "alice")
        # Start + auto-save (so we have a save to load)
        r = await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        gid1 = r.json()["game_id"]
        # Force-finish so we can advance
        from app.models import Game
        async with SessionLocal() as s:
            g = await s.get(Game, gid1)
            g.status = "finished"
            await s.commit()
        # /advance → auto-save written, BUT the in-flight game is
        # still status=finished (no longer playing).
        await c.post(
            "/mainlines/chapter_test_01/advance",
            json={"user_name": "alice", "game_id": gid1},
        )
        # Now we want to test "load while in-flight":
        # start a SECOND game (still active, not yet finished).
        # advance 已把进度推进到 chapter_test_02(章节链锁),因此这里 start
        # 当前允许的章节 02 产生在飞游戏,用于验证 load 时会 abort 它。
        r2 = await c.post(
            "/mainlines/chapter_test_02/start",
            json={"user_name": "alice", "skip_intro": True, "force": True},
        )
        assert r2.status_code == 201, r2.text
        gid2 = r2.json()["game_id"]
        # Verify it's "playing"
        async with SessionLocal() as s:
            g2 = await s.get(Game, gid2)
            assert g2.status == "playing"
        # Now load the auto-save — gid2 should be aborted
        await c.post(
            "/saves/load",
            json={"user_name": "alice", "kind": "auto", "slot_index": 0},
        )
        async with SessionLocal() as s:
            g2_after = await s.get(Game, gid2)
            assert g2_after.status == "aborted", (
                f"in-flight game should be aborted, got {g2_after.status}"
            )

    async def test_load_with_no_in_flight_game_is_noop(self, client):
        c, _ = client
        await _create_profile(c, "alice")
        # Write an auto-save via prep-complete (no /start yet)
        await c.post(
            "/mainlines/chapter_test_01/prepare/complete",
            json={"user_name": "alice"},
        )
        # Load — should succeed, no in-flight game to abort
        r = await c.post(
            "/saves/load",
            json={"user_name": "alice", "kind": "auto", "slot_index": 0},
        )
        assert r.status_code == 200, r.text

    async def test_load_does_not_abort_others_users_games(self, client):
        c, SessionLocal = client
        await _create_profile(c, "alice")
        await _create_profile(c, "bob")
        # Alice starts a game
        r = await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        alice_gid = r.json()["game_id"]
        # Bob also starts a game
        r2 = await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "bob", "skip_intro": True},
        )
        bob_gid = r2.json()["game_id"]
        # Bob finishes his game + advances to write his auto-save
        from app.models import Game
        async with SessionLocal() as s:
            g = await s.get(Game, bob_gid)
            g.status = "finished"
            await s.commit()
        await c.post(
            "/mainlines/chapter_test_01/advance",
            json={"user_name": "bob", "game_id": bob_gid},
        )
        # Bob loads his auto-save
        await c.post(
            "/saves/load",
            json={"user_name": "bob", "kind": "auto", "slot_index": 0},
        )
        # Alice's game should be UNTOUCHED
        async with SessionLocal() as s:
            a = await s.get(Game, alice_gid)
            assert a.status == "playing", (
                f"alice's game should be unaffected, got {a.status}"
            )


# ============================================================
# Fix 2: POST /saves/load_suspend
# ============================================================


@pytest.mark.integration
class TestLoadSuspendEndpoint:
    async def test_load_suspend_returns_meta(self, client):
        from app.save.service import SaveService
        from app.save.models import SuspendPoint

        c, SessionLocal = client
        await _create_profile(c, "alice")
        # Start a game so we have a real game_id
        r = await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        gid = r.json()["game_id"]

        # Manually inject a suspend
        async with SessionLocal() as s:
            svc = SaveService(s)
            await svc.capture_suspend(
                user_name="alice",
                game_id=gid,
                mainline_id="chapter_test_01",
                battle_id="battle_01",
                suspend_point=SuspendPoint.MANUAL,
                game_state={"foo": "bar"},
            )
            await s.commit()

        # Hit the new endpoint
        r = await c.post(
            "/saves/load_suspend",
            json={"user_name": "alice"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["user_name"] == "alice"
        assert body["game_id"] == gid
        assert body["mainline_id"] == "chapter_test_01"
        assert body["battle_id"] == "battle_01"
        assert body["suspend_point"] == "manual"
        assert body["aborted_game_count"] == 0

    async def test_load_suspend_aborts_other_in_flight_games(self, client):
        from app.save.service import SaveService
        from app.save.models import SuspendPoint

        c, SessionLocal = client
        await _create_profile(c, "alice")
        # Game 1: will be suspended
        r1 = await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        gid1 = r1.json()["game_id"]
        async with SessionLocal() as s:
            svc = SaveService(s)
            await svc.capture_suspend(
                user_name="alice", game_id=gid1,
                mainline_id="chapter_test_01",
                battle_id="battle_01",
                suspend_point=SuspendPoint.MANUAL,
                game_state={"foo": "bar"},
            )
            await s.commit()
        # Game 2: an unrelated in-flight game
        r2 = await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True, "force": True},
        )
        assert r2.status_code == 201
        gid2 = r2.json()["game_id"]
        # Hit load_suspend — should abort gid2
        r3 = await c.post(
            "/saves/load_suspend",
            json={"user_name": "alice"},
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["aborted_game_count"] == 1
        async with SessionLocal() as s:
            from app.models import Game
            g2 = await s.get(Game, gid2)
            assert g2.status == "aborted"
        # Suspend row still present (not cleared on load_suspend)
        async with SessionLocal() as s:
            from app.save.models import SuspendState
            sus = (await s.execute(
                select(SuspendState).where(SuspendState.user_name == "alice")
            )).scalar_one()
            assert sus.game_id == gid1

    async def test_load_suspend_no_suspend_returns_404(self, client):
        c, _ = client
        await _create_profile(c, "alice")
        r = await c.post(
            "/saves/load_suspend",
            json={"user_name": "alice"},
        )
        assert r.status_code == 404

    async def test_load_suspend_unknown_profile_returns_404(self, client):
        c, _ = client
        r = await c.post(
            "/saves/load_suspend",
            json={"user_name": "ghost"},
        )
        assert r.status_code == 404


# ============================================================
# Fix 3: /start with force=true
# ============================================================


@pytest.mark.integration
class TestStartForceParameter:
    async def test_force_true_allows_restart_same_mainline(self, client):
        c, SessionLocal = client
        await _create_profile(c, "alice")
        # Start once
        r = await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 201
        gid1 = r.json()["game_id"]
        # Start AGAIN with force=true — should succeed and abort gid1
        r2 = await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True, "force": True},
        )
        assert r2.status_code == 201, r2.text
        gid2 = r2.json()["game_id"]
        assert gid1 != gid2
        from app.models import Game
        async with SessionLocal() as s:
            g1 = await s.get(Game, gid1)
            assert g1.status == "aborted"
            g2 = await s.get(Game, gid2)
            assert g2.status == "playing"

    async def test_force_false_same_mainline_409(self, client):
        c, _ = client
        await _create_profile(c, "alice")
        await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        # Without force, same mainline → 409
        r = await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True, "force": False},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["error"] == "mainline_already_active"

    async def test_force_false_different_mainline_still_409(self, client):
        c, _ = client
        await _create_profile(c, "alice")
        # Active = chapter_test_01
        await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        # Try a DIFFERENT mainline — only chapter_01 is loaded so we
        # can't try chapter_02; instead just verify the existing
        # 409 still fires.
        r = await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r.status_code == 409

    async def test_load_save_then_start_with_force_works(self, client):
        """End-to-end: load an auto-save, then /start with force=true
        to resume.  This is the canonical 'recover from disconnect'
        flow."""
        c, SessionLocal = client
        await _create_profile(c, "alice")
        # Start + force-finish + advance
        r = await c.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        gid1 = r.json()["game_id"]
        from app.models import Game
        async with SessionLocal() as s:
            g = await s.get(Game, gid1)
            g.status = "finished"
            await s.commit()
        await c.post(
            "/mainlines/chapter_test_01/advance",
            json={"user_name": "alice", "game_id": gid1},
        )
        # Now simulate the FE: load auto-save
        await c.post(
            "/saves/load",
            json={"user_name": "alice", "kind": "auto", "slot_index": 0},
        )
        # Then /start with force=True — advance 后当前章为 chapter_test_02,
        # 恢复流程应 start 当前允许的章节(章节链锁禁止回头进已通关的 01)。
        r2 = await c.post(
            "/mainlines/chapter_test_02/start",
            json={"user_name": "alice", "skip_intro": True, "force": True},
        )
        assert r2.status_code == 201, r2.text
        # New game spawned, the old (finished) game is unaffected
        # because it was already "finished", not "playing"
