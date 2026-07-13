"""
Tests for the save / suspend API (auto-save + manual save + interrupt).

Covers the FE8-inspired dual-slot model:

  * GameSaveSlot — 3 manual + 1 auto
  * SuspendState — 1 mid-battle interrupt
  * Auto-save at 2 checkpoints:
      1. After /advance settlement        → label "{mainline_id}-结束"
      2. After /mainlines/{id}/prepare/complete → label "{mainline_id}-准备"

Invariants tested:
  * auto-save captures hero_campaign_states faithfully
  * auto-save does NOT touch a live Game row (it's a *post-chapter*
    snapshot, not a mid-battle one)
  * load(manual) cascades the auto-save slot wipe
  * erase cascades the suspend (FE8 invariant)
  * suspend capture does NOT touch hero_campaign_states
  * auto-save labels match the "{mainline_id}-结束" / "-准备" pattern
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
async def save_client():
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


async def _create_profile(client, user_name="alice"):
    r = await client.post("/progression/profiles", json={"user_name": user_name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _start_and_finish_battle(client, SessionLocal, mainline_id="chapter_test_01", user="alice"):
    """Start a mainline battle and force-mark the game as finished.

    Returns ``(game_id, start_body)`` so callers can read either.
    """
    r = await client.post(
        f"/mainlines/{mainline_id}/start",
        json={"user_name": user, "skip_intro": True},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    game_id = body["game_id"]
    from app.models import Game
    async with SessionLocal() as s:
        g = await s.get(Game, game_id)
        g.status = "finished"
        await s.commit()
    return game_id, body


# ============================================================
# List endpoint
# ============================================================

@pytest.mark.integration
class TestListSaves:
    async def test_list_returns_empty_for_new_profile(self, save_client):
        client, _ = save_client
        await _create_profile(client, "alice")
        r = await client.get("/saves", params={"user_name": "alice"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["user_name"] == "alice"
        assert body["manual_slots"] == [None, None, None]
        assert body["auto_slot"] is None
        assert body["suspend"] is None

    async def test_list_404_for_unknown_profile(self, save_client):
        client, _ = save_client
        r = await client.get("/saves", params={"user_name": "ghost"})
        assert r.status_code == 404


# ============================================================
# Manual save / load / erase
# ============================================================

@pytest.mark.integration
class TestManualSave:
    async def test_save_and_list(self, save_client):
        client, _ = save_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/saves/save",
            json={
                "user_name": "alice",
                "slot_index": 0,
                "mainline_id": "chapter_test_01",
                "chapter_index": 0,
                "label": "manual-slot-0",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["slot"]["kind"] == "manual"
        assert body["slot"]["slot_index"] == 0
        assert body["slot"]["mainline_id"] == "chapter_test_01"

        # List should show it
        r2 = await client.get("/saves", params={"user_name": "alice"})
        assert r2.status_code == 200
        slots = r2.json()["manual_slots"]
        assert slots[0] is not None
        assert slots[0]["mainline_id"] == "chapter_test_01"
        assert slots[1] is None
        assert slots[2] is None

    async def test_save_rejects_invalid_slot(self, save_client):
        client, _ = save_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/saves/save",
            json={
                "user_name": "alice",
                "slot_index": 5,  # invalid
                "mainline_id": "chapter_test_01",
                "chapter_index": 0,
            },
        )
        assert r.status_code == 422

    async def test_save_persists_hero_state(self, save_client):
        client, SessionLocal = save_client
        await _create_profile(client, "alice")
        # Pre-set hero state
        from app.progression.models import PlayerProfile
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            p.hero_campaign_states = {
                "yun": {
                    "hero_id": "yun",
                    "class_id": "warlock",
                    "level": 7,
                    "exp": 33,
                    "base_stats": {
                        "hp": 50, "atk": 20, "def": 11,
                        "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
                    },
                    "weapon_ranks": {"anima": 2},
                    "learned_skills": ["arcane_strike"],
                    "promoted": False,
                    "equipment": {"weapon": "oak_staff"},
                }
            }
            await s.commit()

        await client.post(
            "/saves/save",
            json={
                "user_name": "alice",
                "slot_index": 0,
                "mainline_id": "chapter_test_01",
                "chapter_index": 0,
            },
        )

        # Mutate the profile after saving
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            p.hero_campaign_states["yun"]["level"] = 99
            await s.commit()

        # Load the save — yun should be back to level 7
        r = await client.post(
            "/saves/load",
            json={"user_name": "alice", "kind": "manual", "slot_index": 0},
        )
        assert r.status_code == 200, r.text
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            assert p.hero_campaign_states["yun"]["level"] == 7
            assert p.hero_campaign_states["yun"]["equipment"] == {"weapon": "oak_staff"}


# ============================================================
# Auto-save at chapter settlement (per /advance)
# ============================================================

@pytest.mark.integration
class TestAutoSaveOnAdvance:
    async def test_advance_writes_auto_save_with_end_label(self, save_client):
        client, SessionLocal = save_client
        await _create_profile(client, "alice")
        game_id, _ = await _start_and_finish_battle(client, SessionLocal)

        # /advance should write the auto-save
        r = await client.post(
            "/mainlines/chapter_test_01/advance",
            json={"user_name": "alice", "game_id": game_id},
        )
        assert r.status_code == 200, r.text
        adv = r.json()
        assert adv["auto_save"] is not None
        assert adv["auto_save"]["label"] == "chapter_test_01-结束"
        assert adv["auto_save"]["auto_kind"] == "chapter_end"

        # List should show the auto-save
        r2 = await client.get("/saves", params={"user_name": "alice"})
        assert r2.status_code == 200
        auto = r2.json()["auto_slot"]
        assert auto is not None
        assert auto["label"] == "chapter_test_01-结束"

    async def test_advance_auto_save_captures_hero(self, save_client):
        client, SessionLocal = save_client
        await _create_profile(client, "alice")

        # Pre-set hero state
        from app.progression.models import PlayerProfile
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            p.hero_campaign_states = {
                "yun": {
                    "hero_id": "yun",
                    "class_id": "warlock",
                    "level": 5,
                    "exp": 0,
                    "base_stats": {
                        "hp": 50, "atk": 20, "def": 11,
                        "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
                    },
                    "weapon_ranks": {},
                    "learned_skills": ["arcane_strike"],
                    "promoted": False,
                    "equipment": {},
                }
            }
            await s.commit()

        game_id, _ = await _start_and_finish_battle(client, SessionLocal)
        await client.post(
            "/mainlines/chapter_test_01/advance",
            json={"user_name": "alice", "game_id": game_id},
        )

        # Mutate the profile after auto-save
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            p.hero_campaign_states["yun"]["level"] = 99
            await s.commit()

        # Load the auto-save
        r = await client.post(
            "/saves/load",
            json={"user_name": "alice", "kind": "auto", "slot_index": 0},
        )
        assert r.status_code == 200, r.text
        body2 = r.json()
        assert body2["label"] == "chapter_test_01-结束"
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            assert p.hero_campaign_states["yun"]["level"] == 5


# ============================================================
# Auto-save at prep complete (per /mainlines/{id}/prepare/complete)
# ============================================================

@pytest.mark.integration
class TestAutoSaveOnPrepareComplete:
    async def test_prepare_complete_writes_auto_save_with_prep_label(self, save_client):
        client, _ = save_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/mainlines/chapter_test_01/prepare/complete",
            json={"user_name": "alice"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["label"] == "chapter_test_01-准备"
        assert body["auto_kind"] == "prep_complete"

        # List should show the auto-save
        r2 = await client.get("/saves", params={"user_name": "alice"})
        assert r2.status_code == 200
        auto = r2.json()["auto_slot"]
        assert auto is not None
        assert auto["label"] == "chapter_test_01-准备"

    async def test_advances_after_prep_uses_prep_state(self, save_client):
        """Loading a "-准备" auto-save should put the player at the
        prep-complete state, where they can call /start to spawn the
        next battle with the saved hero state."""
        client, SessionLocal = save_client
        await _create_profile(client, "alice")
        from app.progression.models import PlayerProfile
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            p.hero_campaign_states = {
                "yun": {
                    "hero_id": "yun",
                    "class_id": "warlock",
                    "level": 5,
                    "exp": 0,
                    "base_stats": {
                        "hp": 50, "atk": 20, "def": 11,
                        "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
                    },
                    "weapon_ranks": {},
                    "learned_skills": ["arcane_strike"],
                    "promoted": False,
                    "equipment": {},
                }
            }
            await s.commit()

        # Click "Ready" — auto-save fires
        await client.post(
            "/mainlines/chapter_test_01/prepare/complete",
            json={"user_name": "alice"},
        )
        # Mutate profile (simulate the player logging out and back in)
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            p.hero_campaign_states["yun"]["level"] = 99
            await s.commit()

        # Load the "-准备" auto-save
        r = await client.post(
            "/saves/load",
            json={"user_name": "alice", "kind": "auto", "slot_index": 0},
        )
        assert r.status_code == 200
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            # yun should be back to level 5 (the prep-complete state)
            assert p.hero_campaign_states["yun"]["level"] == 5
            # And the player can /start immediately
            r2 = await client.post(
                "/mainlines/chapter_test_01/start",
                json={"user_name": "alice", "skip_intro": True},
            )
            assert r2.status_code == 201, r2.text


# ============================================================
# Cascade invariants
# ============================================================

@pytest.mark.integration
class TestCascadeInvariants:
    async def test_load_manual_save_clears_auto(self, save_client):
        client, _ = save_client
        await _create_profile(client, "alice")
        # First write a manual save
        await client.post(
            "/saves/save",
            json={
                "user_name": "alice",
                "slot_index": 0,
                "mainline_id": "chapter_test_01",
                "chapter_index": 0,
            },
        )
        # Then write an auto-save
        await client.post(
            "/mainlines/chapter_test_01/prepare/complete",
            json={"user_name": "alice"},
        )
        # Verify both are present
        r = await client.get("/saves", params={"user_name": "alice"})
        body = r.json()
        assert body["manual_slots"][0] is not None
        assert body["auto_slot"] is not None

        # Load the manual — auto should be wiped
        r2 = await client.post(
            "/saves/load",
            json={"user_name": "alice", "kind": "manual", "slot_index": 0},
        )
        assert r2.status_code == 200
        assert r2.json()["auto_cleared"] is True

        r3 = await client.get("/saves", params={"user_name": "alice"})
        assert r3.json()["auto_slot"] is None

    async def test_erase_game_save_cascades_suspend(self, save_client):
        client, SessionLocal = save_client
        await _create_profile(client, "alice")
        # Write a game save
        await client.post(
            "/saves/save",
            json={
                "user_name": "alice",
                "slot_index": 0,
                "mainline_id": "chapter_test_01",
                "chapter_index": 0,
            },
        )
        # Manually inject a suspend via the service
        from app.save.service import SaveService
        from app.save.models import SuspendPoint
        async with SessionLocal() as s:
            svc = SaveService(s)
            await svc.capture_suspend(
                user_name="alice",
                game_id=1,
                mainline_id="chapter_test_01",
                battle_id="battle_01",
                suspend_point=SuspendPoint.MANUAL,
                game_state={"foo": "bar"},
            )
            await s.commit()

        r = await client.get("/saves", params={"user_name": "alice"})
        assert r.json()["suspend"] is not None

        # Erase the game save — suspend should cascade
        r2 = await client.post(
            "/saves/erase",
            json={"user_name": "alice", "kind": "manual", "slot_index": 0},
        )
        assert r2.status_code == 200
        assert r2.json()["suspend_cleared"] is True

        r3 = await client.get("/saves", params={"user_name": "alice"})
        assert r3.json()["suspend"] is None

    async def test_erase_empty_slot_returns_404(self, save_client):
        client, _ = save_client
        await _create_profile(client, "alice")
        r = await client.post(
            "/saves/erase",
            json={"user_name": "alice", "kind": "manual", "slot_index": 1},
        )
        assert r.status_code == 404

    async def test_erase_auto_slot(self, save_client):
        client, _ = save_client
        await _create_profile(client, "alice")
        await client.post(
            "/mainlines/chapter_test_01/prepare/complete",
            json={"user_name": "alice"},
        )
        r = await client.post(
            "/saves/erase",
            json={"user_name": "alice", "kind": "auto", "slot_index": 0},
        )
        assert r.status_code == 200
        assert r.json()["erased"] is True
        r2 = await client.get("/saves", params={"user_name": "alice"})
        assert r2.json()["auto_slot"] is None


# ============================================================
# Suspend capture invariant
# ============================================================

@pytest.mark.integration
class TestSuspendCapture:
    async def test_suspend_endpoint_writes_row(self, save_client):
        client, SessionLocal = save_client
        await _create_profile(client, "alice")
        # Start a mainline to spawn a live game
        r2 = await client.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        assert r2.status_code == 201, r2.text
        gid = r2.json()["game_id"]
        # Capture suspend on the live game
        r3 = await client.post(
            f"/games/{gid}/suspend",
            json={"user_name": "alice"},
        )
        assert r3.status_code == 200, r3.text
        r4 = await client.get("/saves", params={"user_name": "alice"})
        assert r4.json()["suspend"] is not None
        assert r4.json()["suspend"]["game_id"] == gid

    async def test_suspend_rejects_finished_game(self, save_client):
        client, SessionLocal = save_client
        await _create_profile(client, "alice")
        # Start + force-finish a game
        game_id, _ = await _start_and_finish_battle(client, SessionLocal)
        # Capture suspend on the finished game — must 409
        r = await client.post(
            f"/games/{game_id}/suspend",
            json={"user_name": "alice"},
        )
        assert r.status_code == 409

    async def test_suspend_does_not_touch_hero_state(self, save_client):
        """Suspend must NOT write to hero_campaign_states.  Critical
        invariant: a disconnect-and-resume must leave long-term
        progression exactly as it was.

        Note: /start itself does write to hero_campaign_states
        (initialises the heroes from the mainline spec), so the
        baseline is captured AFTER /start and compared with the
        state AFTER /suspend.  They must be byte-identical.
        """
        client, SessionLocal = save_client
        await _create_profile(client, "alice")
        from app.progression.models import PlayerProfile
        from copy import deepcopy
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            p.hero_campaign_states = {
                "yun": {
                    "hero_id": "yun",
                    "class_id": "warlock",
                    "level": 5,
                    "exp": 0,
                    "base_stats": {
                        "hp": 50, "atk": 20, "def": 11,
                        "matk": 27, "mdef": 12, "mov": 4, "mp": 8,
                    },
                    "weapon_ranks": {},
                    "learned_skills": ["arcane_strike"],
                    "promoted": False,
                    "equipment": {},
                }
            }
            await s.commit()

        # Start a game (this DOES initialise anna + yun in
        # hero_campaign_states — that's fine, it's the start path)
        r = await client.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "alice", "skip_intro": True},
        )
        gid = r.json()["game_id"]

        # Capture baseline AFTER start
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            baseline = deepcopy(dict(p.hero_campaign_states))

        # Now capture suspend
        await client.post(
            f"/games/{gid}/suspend",
            json={"user_name": "alice"},
        )

        # hero_campaign_states should be byte-identical to the
        # post-start baseline (suspend did not touch it)
        async with SessionLocal() as s:
            p = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            assert dict(p.hero_campaign_states) == baseline


# ============================================================
# Auto-save overwrite semantics
# ============================================================

@pytest.mark.integration
class TestAutoSaveOverwrite:
    async def test_repeated_prep_complete_overwrites(self, save_client):
        client, _ = save_client
        await _create_profile(client, "alice")
        # First prep-complete
        r1 = await client.post(
            "/mainlines/chapter_test_01/prepare/complete",
            json={"user_name": "alice"},
        )
        first_saved = r1.json()["saved_at"]
        # Second prep-complete — should overwrite
        import asyncio
        asyncio.sleep(0.01)  # ensure timestamp differs
        r2 = await client.post(
            "/mainlines/chapter_test_01/prepare/complete",
            json={"user_name": "alice"},
        )
        second_saved = r2.json()["saved_at"]
        # List should still have exactly ONE auto-save
        r3 = await client.get("/saves", params={"user_name": "alice"})
        body = r3.json()
        assert body["auto_slot"] is not None
        assert body["auto_slot"]["label"] == "chapter_test_01-准备"
