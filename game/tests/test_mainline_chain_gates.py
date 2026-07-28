"""
Campaign chain config + "no chapter lock" regression tests.

P2(FE8 对齐):章节锁(``mainline_locked`` 403)已删除。玩家可自由进入 /
重玩任意章节;章节顺序不再被门控。``CAMPAIGN_CHAINS`` 配置保留(供未来
UI 分组 + ``_has_cleared_mainline`` 只读 cleared 查询),但不再折叠列表
或阻止 start。

保留的门控(非章节锁):"单一活动态"—— profile 同时只能有一个 active
mainline,重复 start 返回 409 ``mainline_already_active``(需 abandon 或
force=true)。这是"内存活动态一份"的保护(对齐 FE8 的存档槽↔活动态模型),
不是章节顺序锁。
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
    """Persist a "cleared" formal save (chapter_index == battle count)."""
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
# 1) CAMPAIGN_CHAINS surface (retained — config + chain helpers)
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
# 2) No chapter lock — all chapters listed & start-able freely
# ============================================================

class TestNoChapterLock:
    async def test_listing_shows_all_chapters(self, chain_client):
        client, _ = chain_client
        await _create_profile(client, "fresh")
        r = await client.get("/mainlines", params={"user_name": "fresh"})
        assert r.status_code == 200, r.text
        ids = {m["id"] for m in r.json() if str(m["id"]).startswith("chapter_test_")}
        # 无锁:全部章节可见,不折叠成"当前章节"。
        assert {"chapter_test_01", "chapter_test_02", "chapter_test_03"} <= ids, (
            "chapter lock removed — listing must show all chapters"
        )

    async def test_non_chain_mainline_still_listed(self, chain_client):
        client, _ = chain_client
        await _create_profile(client, "fresh")
        r = await client.get("/mainlines", params={"user_name": "fresh"})
        assert r.status_code == 200, r.text
        ids = [m["id"] for m in r.json()]
        assert "chapter_01_steel_rebellion" in ids

    async def test_starting_later_chapter_not_locked(self, chain_client):
        client, _ = chain_client
        await _create_profile(client, "jumper")
        # fresh profile 直接 start 第二章 —— 不再返回 403 锁(可跳章)。
        r = await client.post(
            "/mainlines/chapter_test_02/start",
            json={"user_name": "jumper", "skip_intro": True},
        )
        assert r.status_code != 403, r.text
        if r.status_code >= 400:
            detail = r.json().get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error") != "mainline_locked", r.text

    async def test_replaying_cleared_chapter_allowed(self, chain_client):
        client, SessionLocal = chain_client
        await _create_profile(client, "replayer")
        await _mark_chapter_cleared(SessionLocal, "replayer", "chapter_test_01")
        # 已通关第一章后仍可重玩 —— 无锁。
        r = await client.post(
            "/mainlines/chapter_test_01/start",
            json={"user_name": "replayer", "skip_intro": True},
        )
        assert r.status_code != 403, r.text


# ============================================================
# 3) Cleared query stays available (read-only, for UI annotation)
# ============================================================

class TestClearedQuery:
    async def test_has_cleared_mainline_readonly(self, chain_client):
        client, SessionLocal = chain_client
        await _create_profile(client, "q")
        from app.routes.mainline._common import _has_cleared_mainline

        async with SessionLocal() as s:
            assert await _has_cleared_mainline(s, "q", "chapter_test_01") is False
        await _mark_chapter_cleared(SessionLocal, "q", "chapter_test_01")
        async with SessionLocal() as s:
            assert await _has_cleared_mainline(s, "q", "chapter_test_01") is True
