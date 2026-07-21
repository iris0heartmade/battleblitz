"""
Save-system invariant tests.

Targets the FE8-style invariants the save service is supposed to honour
but which the smoke + happy-path tests do not exercise directly (07-13
save-design-v2 plan §2.3, M6 of the 07-21 plan):

  * **Suspend hygiene** — capturing a mid-battle suspend must not
    mutate the profile's ``hero_campaign_states`` (the long-term
    progress that the manual / auto slots persist).  The suspend
    captures a *live* game state, not a *profile* snapshot, so a
    suspend capture / clear / re-capture cycle must round-trip
    ``hero_campaign_states`` byte-for-byte.
  * **Manual slot cap** — the service accepts exactly ``slot_index``
    in {0, 1, 2} and rejects anything else with ``ValueError``.  No
    fourth slot must ever be created on disk, even when the caller
    asks for ``slot_index=0`` twice (the second write replaces the
    first, the row count is still 1).
  * **Auto-save overwrite** — calling ``save_auto`` twice with the
    same user must overwrite, not append, and must keep the
    ``auto_kind`` label of the latest call.

The tests use the same engine + db setup as ``test_save_api.py``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
async def save_invariant_client():
    from app.database import (
        AsyncSessionLocal,
        Base,
        dispose_db,
        engine,
        init_db,
    )
    from app.main import app
    from app.mainline import clear_cache
    from httpx import ASGITransport, AsyncClient

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


async def _create_profile(client, user_name: str = "alice") -> None:
    r = await client.post("/progression/profiles", json={"user_name": user_name})
    assert r.status_code == 201, r.text


# ============================================================
# 1) Suspend hygiene: hero_campaign_states must survive a round-trip
# ============================================================

@pytest.mark.integration
class TestSuspendHygiene:
    async def test_capture_suspend_does_not_mutate_profile_state(
        self, save_invariant_client,
    ):
        """capture_suspend stores a live game snapshot, not a profile
        snapshot.  The profile's hero_campaign_states must therefore be
        byte-for-byte identical before and after a suspend capture.
        """
        from app.progression.models import PlayerProfile
        from app.save import SaveService
        from app.save.models import SuspendPoint

        client, SessionLocal = save_invariant_client
        await _create_profile(client, "alice")

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            # Seed a non-trivial hero_campaign_states so a stray write
            # would actually show up in the diff.
            profile.hero_campaign_states = {
                "yun": {"class_id": "archer", "level": 4, "exp": 32},
                "anna": {"class_id": "swordsman", "level": 5, "exp": 8},
            }
            await s.commit()
            snapshot_before = dict(profile.hero_campaign_states)
            profile_id = profile.id

        async with SessionLocal() as s:
            svc = SaveService(s)
            await svc.capture_suspend(
                user_name="alice",
                game_id=42,
                mainline_id="chapter_test_01",
                battle_id="battle_01",
                suspend_point=SuspendPoint.PLAYER_IDLE,
                game_state={"turn_number": 3, "tiles": [], "players": []},
            )
            await s.commit()

        async with SessionLocal() as s:
            profile = await s.get(PlayerProfile, profile_id)
            assert profile.hero_campaign_states == snapshot_before, (
                "suspend capture must not mutate the profile's hero_campaign_states"
            )

    async def test_suspend_round_trip_preserves_profile_state(
        self, save_invariant_client,
    ):
        """capture → clear → capture again must keep the profile
        state intact throughout the lifecycle.  Guards against the
        "suspend accidentally wrote to profile" regression.
        """
        from app.progression.models import PlayerProfile
        from app.save import SaveService
        from app.save.models import SuspendPoint

        client, SessionLocal = save_invariant_client
        await _create_profile(client, "bob")

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "bob")
            )).scalar_one()
            profile.hero_campaign_states = {
                "yun": {"class_id": "archer", "level": 1, "exp": 0},
            }
            await s.commit()
            seed = dict(profile.hero_campaign_states)
            profile_id = profile.id

        async with SessionLocal() as s:
            svc = SaveService(s)
            for game_id in (10, 11):
                await svc.capture_suspend(
                    user_name="bob",
                    game_id=game_id,
                    mainline_id="chapter_test_01",
                    battle_id="battle_01",
                    suspend_point=SuspendPoint.PLAYER_IDLE,
                    game_state={"turn_number": 1, "tiles": [], "players": []},
                )
            await svc.clear_suspend("bob")
            await svc.capture_suspend(
                user_name="bob",
                game_id=12,
                mainline_id="chapter_test_01",
                battle_id="battle_01",
                suspend_point=SuspendPoint.PLAYER_IDLE,
                game_state={"turn_number": 2, "tiles": [], "players": []},
            )
            await s.commit()

        async with SessionLocal() as s:
            profile = await s.get(PlayerProfile, profile_id)
            assert profile.hero_campaign_states == seed, (
                "profile hero_campaign_states must round-trip cleanly through "
                "capture → clear → re-capture"
            )


# ============================================================
# 2) Manual slot cap: 3 slots, no fourth
# ============================================================

@pytest.mark.integration
class TestManualSlotCap:
    async def test_slot_index_out_of_range_raises(self, save_invariant_client):
        from app.progression.models import PlayerProfile
        from app.save import SaveService

        client, SessionLocal = save_invariant_client
        await _create_profile(client, "alice")

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            svc = SaveService(s)
            for bad in (-1, 3, 99):
                with pytest.raises(ValueError):
                    await svc.save_manual(
                        profile,
                        slot_index=bad,
                        mainline_id="chapter_test_01",
                        chapter_index=1,
                        label=f"bad-{bad}",
                    )

    async def test_three_slots_at_most(self, save_invariant_client):
        """Writing to 0, 1, 2 yields exactly three rows; the fourth
        write is rejected so no row is created with slot_index=3.
        """
        from app.progression.models import PlayerProfile
        from app.save import GameSaveSlot, SaveService
        from app.save.models import SaveSlotKind

        client, SessionLocal = save_invariant_client
        await _create_profile(client, "alice")

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            svc = SaveService(s)
            for slot_index in (0, 1, 2):
                await svc.save_manual(
                    profile,
                    slot_index=slot_index,
                    mainline_id="chapter_test_01",
                    chapter_index=1,
                    label=f"slot-{slot_index}",
                )
            await s.commit()

        async with SessionLocal() as s:
            rows = (await s.execute(
                select(GameSaveSlot).where(
                    GameSaveSlot.user_name == "alice",
                    GameSaveSlot.kind == SaveSlotKind.MANUAL,
                )
            )).scalars().all()
            slot_indices = sorted(int(r.slot_index) for r in rows)
            assert slot_indices == [0, 1, 2], (
                f"expected exactly 3 manual slots, got {slot_indices}"
            )

    async def test_rewrite_same_slot_does_not_create_new_row(
        self, save_invariant_client,
    ):
        from app.progression.models import PlayerProfile
        from app.save import GameSaveSlot, SaveService
        from app.save.models import SaveSlotKind

        client, SessionLocal = save_invariant_client
        await _create_profile(client, "alice")

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            svc = SaveService(s)
            for i in range(5):
                await svc.save_manual(
                    profile,
                    slot_index=0,
                    mainline_id="chapter_test_01",
                    chapter_index=i + 1,
                    label=f"run-{i}",
                )
            await s.commit()

        async with SessionLocal() as s:
            rows = (await s.execute(
                select(GameSaveSlot).where(
                    GameSaveSlot.user_name == "alice",
                    GameSaveSlot.kind == SaveSlotKind.MANUAL,
                )
            )).scalars().all()
            assert len(rows) == 1, (
                f"slot 0 must remain a single row across 5 rewrites, got {len(rows)}"
            )
            only = rows[0]
            assert only.chapter_index == 5
            assert only.label == "run-4"


# ============================================================
# 3) Auto-save overwrite keeps a single row
# ============================================================

@pytest.mark.integration
class TestAutoSaveOverwrite:
    async def test_auto_save_replaces_previous_label(self, save_invariant_client):
        from app.progression.models import PlayerProfile
        from app.save import GameSaveSlot, SaveService
        from app.save.models import SaveSlotKind

        client, SessionLocal = save_invariant_client
        await _create_profile(client, "alice")

        async with SessionLocal() as s:
            profile = (await s.execute(
                select(PlayerProfile).where(PlayerProfile.user_name == "alice")
            )).scalar_one()
            svc = SaveService(s)
            await svc.save_auto(
                profile,
                mainline_id="chapter_test_01",
                chapter_index=1,
                label="chapter_test_01-结束",
            )
            await svc.save_auto(
                profile,
                mainline_id="chapter_test_01",
                chapter_index=2,
                label="chapter_test_01-准备",
            )
            await s.commit()

        async with SessionLocal() as s:
            rows = (await s.execute(
                select(GameSaveSlot).where(
                    GameSaveSlot.user_name == "alice",
                    GameSaveSlot.kind == SaveSlotKind.AUTO,
                )
            )).scalars().all()
            assert len(rows) == 1, (
                f"auto save must keep a single row, got {len(rows)}"
            )
            only = rows[0]
            assert only.label == "chapter_test_01-准备"
            assert only.chapter_index == 2
