"""
Campaign chain gate regression tests.

Targets the ``CAMPAIGN_CHAINS`` abstraction in
``app.routes.mainline`` (07-21 Task 2).  These tests cover the rules that
the rest of the test suite does not exercise directly:

  * ``CAMPAIGN_CHAINS`` exposes the test chain and nothing else.
  * A new profile can only enter the first chapter of a chain.
  * Direct ``POST /mainlines/{locked_id}/start`` returns 403 with
    ``error == "mainline_locked"`` and surfaces the available id.
  * After the first chapter is formally cleared, the listing advances
    to chapter_test_02.
  * A finished chain (all three chapters cleared) collapses to its
    final chapter ("current chapter" semantics) so the lobby still
    renders something meaningful.
  * Mainlines that do not belong to any chain are unaffected by the
    gate.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
async def chain_client():
    from app.database import (
        AsyncSessionLocal,
        Base,
        dispose_db,
        engine,
        init_db,
    )
    from app.main import app
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


async def _create_profile(client, user_name: str = "alice") -> None:
    r = await client.post("/progression/profiles", json={"user_name": user_name})
    assert r.status_code == 201, r.text


async def _mark_chapter_cleared(
    SessionLocal,
    user_name: str,
    mainline_id: str,
    slot_index: int = 0,
) -> None:
    """Persist a "cleared" formal save so the gate sees the chapter done."""
    from app.mainline import load_mainline
    from app.progression.models import PlayerProfile
    from app.save import SaveService

    chapter_index = len(load_mainline(mainline_id).battles)
    async with SessionLocal() as s:
        profile = (await s.execute(
            __import__("sqlalchemy").select(PlayerProfile).where(
                PlayerProfile.user_name == user_name
            )
        )).scalar_one()
        await SaveService(s).save_manual(
            profile,
            slot_index=slot_index,
            mainline_id=mainline_id,
            chapter_index=chapter_index,
            label=f"{mainline_id}-cleared",
        )
        await s.commit()


# ============================================================
# 1) CAMPAIGN_CHAINS surface
# ============================================================

class TestCampaignChainsConfig:
    def test_test_chain_is_declared(self):
        from app.routes.mainline import CAMPAIGN_CHAINS, TEST_MAINLINE_CHAIN

        assert "test" in CAMPAIGN_CHAINS
        assert CAMPAIGN_CHAINS["test"] == TEST_MAINLINE_CHAIN
        assert CAMPAIGN_CHAINS["test"][0] == "chapter_test_01"
        assert CAMPAIGN_CHAINS["test"][-1] == "chapter_test_03"

    def test_chain_for_resolves_known_and_unknown_ids(self):
        from app.routes.mainline import _chain_for, _campaign_chain_name

        assert _chain_for("chapter_test_02") == (
            "chapter_test_01", "chapter_test_02", "chapter_test_03"
        )
        assert _chain_for("chapter_01_steel_rebellion") is None
        assert _campaign_chain_name("chapter_test_02") == "test"
        assert _campaign_chain_name("chapter_01_steel_rebellion") is None


# ============================================================
# 2) Fresh profile: only first chapter visible / start-able
# ============================================================

class TestFreshProfileGate:
    async def test_listing_only_shows_first_test_chapter(self, chain_client):
        client, _ = chain_client
        await _create_profile(client, "fresh")
        r = await client.get("/mainlines", params={"user_name": "fresh"})
        assert r.status_code == 200, r.text
        ids = [m["id"] for m in r.json() if str(m["id"]).startswith("chapter_test_")]
        assert ids == ["chapter_test_01"], (
            "fresh profile must only see the first chapter of the chain"
        )

    async def test_starting_locked_chapter_returns_403(self, chain_client):
        client, _ = chain_client
        await _create_profile(client, "fresh")
        r = await client.post(
            "/mainlines/chapter_test_02/start",
            json={"user_name": "fresh", "skip_intro": True},
        )
        assert r.status_code == 403, r.text
        # FastAPI wraps HTTPException detail as `{"detail": ...}`; pull
        # the structured payload out before asserting the gate fields.
        detail = r.json().get("detail", {})
        if detail is None:
            detail = {}
        assert detail.get("error") == "mainline_locked", r.text
        assert detail.get("mainline_id") == "chapter_test_02"
        assert detail.get("available_mainline_id") == "chapter_test_01"
        assert detail.get("chain") == "test"

    async def test_non_chain_mainlines_are_unaffected_by_gate(
        self, chain_client,
    ):
        client, _ = chain_client
        await _create_profile(client, "fresh")
        # The standalone production chapter must not be filtered by the
        # chain gate; it is a non-chain mainline.
        r = await client.get("/mainlines", params={"user_name": "fresh"})
        assert r.status_code == 200, r.text
        ids = [m["id"] for m in r.json()]
        assert "chapter_01_steel_rebellion" in ids


# ============================================================
# 3) Cleared chapter advances the gate
# ============================================================

class TestClearedChapterAdvances:
    async def test_clearing_first_chapter_unlocks_second(
        self, chain_client,
    ):
        client, SessionLocal = chain_client
        await _create_profile(client, "advancer")
        await _mark_chapter_cleared(SessionLocal, "advancer", "chapter_test_01")

        r = await client.get("/mainlines", params={"user_name": "advancer"})
        assert r.status_code == 200, r.text
        ids = [m["id"] for m in r.json() if str(m["id"]).startswith("chapter_test_")]
        assert ids == ["chapter_test_02"], (
            "clearing the first chapter must advance the visible chapter"
        )

    async def test_clearing_chain_keeps_final_chapter_visible(
        self, chain_client,
    ):
        client, SessionLocal = chain_client
        await _create_profile(client, "finisher")
        # Use distinct save slots so the latest write does not overwrite
        # the previous one — the gate only recognises a chapter as
        # cleared when the formal save is on disk.
        await _mark_chapter_cleared(SessionLocal, "finisher", "chapter_test_01", slot_index=0)
        await _mark_chapter_cleared(SessionLocal, "finisher", "chapter_test_02", slot_index=1)
        await _mark_chapter_cleared(SessionLocal, "finisher", "chapter_test_03", slot_index=2)

        r = await client.get("/mainlines", params={"user_name": "finisher"})
        assert r.status_code == 200, r.text
        ids = [m["id"] for m in r.json() if str(m["id"]).startswith("chapter_test_")]
        # Current-chapter semantics: when the entire chain is cleared
        # the player still sees the final chapter.
        assert ids == ["chapter_test_03"], (
            "fully-cleared chain must collapse to the final chapter"
        )

    async def test_partial_chain_only_blocks_uncleared_starts(
        self, chain_client,
    ):
        client, SessionLocal = chain_client
        await _create_profile(client, "mid")
        await _mark_chapter_cleared(SessionLocal, "mid", "chapter_test_01")

        # chapter_test_02 is now allowed.
        ok = await client.post(
            "/mainlines/chapter_test_02/start",
            json={"user_name": "mid", "skip_intro": True},
        )
        assert ok.status_code in (201, 200, 409), ok.text  # 409 if a game is in-flight

        # chapter_test_03 must still be blocked, and the gate should
        # point the player at the *next available* chapter (chapter_02)
        # which is what the listing surfaces for this user.
        blocked = await client.post(
            "/mainlines/chapter_test_03/start",
            json={"user_name": "mid", "skip_intro": True},
        )
        assert blocked.status_code == 403, blocked.text
        detail = blocked.json().get("detail", {}) or {}
        assert detail.get("mainline_id") == "chapter_test_03"
        assert detail.get("available_mainline_id") == "chapter_test_02"
