"""
Save-slot independence / no-cross-contamination regression (FE8 三槽独立).

验证核心需求(用户 7/8/9 存档场景):
  * 多个槽各停不同章节进度,彼此完全独立;
  * 读某槽 → 所有【养成态】(gold / hero 等级+装备 / mercenary /
    hero_inventory / unlock_points / mainline_commanders / cursor)
    完整回到该槽时刻;
  * 后续推进(改活动态)绝不污染其它槽的 snapshot;
  * 【账户态】(unlocked_classes/commanders / rating / current_season)
    不随读档回滚 —— 账户级永久解锁(避免读旧档打不开需要新解锁的后续章节)。
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest.fixture
async def slot_env():
    from app.main import app
    from app.database import (
        AsyncSessionLocal, Base, dispose_db, engine, init_db,
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


async def _get_profile(SessionLocal, user_name):
    from app.progression.models import PlayerProfile
    async with SessionLocal() as s:
        return (await s.execute(
            select(PlayerProfile).where(PlayerProfile.user_name == user_name)
        )).scalar_one()


async def _set_state(SessionLocal, user_name, **fields):
    """直接改 DB profile 字段,模拟章节推进后的养成/账户变化。"""
    from app.progression.models import PlayerProfile
    async with SessionLocal() as s:
        p = (await s.execute(
            select(PlayerProfile).where(PlayerProfile.user_name == user_name)
        )).scalar_one()
        for k, v in fields.items():
            setattr(p, k, v)
        await s.commit()


async def _save_slot(SessionLocal, user_name, slot_index, mainline_id, chapter_index):
    from app.progression.models import PlayerProfile
    from app.save import SaveService
    async with SessionLocal() as s:
        p = (await s.execute(
            select(PlayerProfile).where(PlayerProfile.user_name == user_name)
        )).scalar_one()
        await SaveService(s).save_manual(
            p, slot_index=slot_index, mainline_id=mainline_id,
            chapter_index=chapter_index, label=mainline_id,
        )
        await s.commit()


async def _load_slot(SessionLocal, user_name, slot_index):
    from app.progression.models import PlayerProfile
    from app.save import SaveService
    from app.save.models import SaveSlotKind
    async with SessionLocal() as s:
        p = (await s.execute(
            select(PlayerProfile).where(PlayerProfile.user_name == user_name)
        )).scalar_one()
        await SaveService(s).load(p, kind=SaveSlotKind.MANUAL, slot_index=slot_index)
        await s.commit()


def _hero_state(level, weapon, skills=None):
    return {"yun": {
        "hero_id": "yun", "class_id": "swordsman", "level": level, "exp": 0,
        "base_stats": {}, "weapon_ranks": {}, "learned_skills": skills or [],
        "promoted": False, "equipment": {"weapon": weapon},
        "equipment_initialized": True,
    }}


@pytest.mark.integration
class TestSaveSlotIndependence:
    async def test_three_slots_no_cross_contamination(self, slot_env):
        client, SessionLocal = slot_env
        await client.post("/progression/profiles", json={"user_name": "hero"})

        # ── 槽0 = "第7章"养成态 A ──
        await _set_state(
            SessionLocal, "hero",
            gold=700, unlock_points=70,
            hero_campaign_states=_hero_state(7, "iron_sword"),
            hero_inventory={"hero_crest": 1},
            mercenary_roster_state={"allocation": {"total_points": 7}},
            mainline_commanders={"chapter_test_07": "yun"},
            active_mainline="chapter_test_07",
            mainline_progress={"battle_index": 3, "scene_id": "s7", "started_at": None},
            # 账户态
            unlocked_classes=["swordsman", "archer"],
            rating=1000, current_season=1,
        )
        await _save_slot(SessionLocal, "hero", 0, "chapter_test_07", 3)

        # ── 槽1 = "第8章"养成态 B(等级/gold 涨 + 账户解锁新职业 knight)──
        await _set_state(
            SessionLocal, "hero",
            gold=800, unlock_points=80,
            hero_campaign_states=_hero_state(8, "steel_sword", ["sk1"]),
            hero_inventory={"hero_crest": 2},
            mainline_commanders={"chapter_test_07": "yun", "chapter_test_08": "anna"},
            active_mainline="chapter_test_08",
            mainline_progress={"battle_index": 3, "scene_id": "s8", "started_at": None},
            unlocked_classes=["swordsman", "archer", "knight"],  # 账户新解锁
            rating=1100, current_season=2,
        )
        await _save_slot(SessionLocal, "hero", 1, "chapter_test_08", 3)

        # ── 槽2 = "第9章" ──
        await _set_state(
            SessionLocal, "hero", gold=900,
            active_mainline="chapter_test_09",
            mainline_progress={"battle_index": 3, "scene_id": "s9", "started_at": None},
        )
        await _save_slot(SessionLocal, "hero", 2, "chapter_test_09", 3)

        # ── 当前活动态 = C(gold 900). 读槽0(第7章) → 养成态全部回到 A ──
        await _load_slot(SessionLocal, "hero", 0)
        p = await _get_profile(SessionLocal, "hero")
        assert p.gold == 700
        assert p.unlock_points == 70
        assert p.hero_campaign_states["yun"]["level"] == 7
        assert p.hero_campaign_states["yun"]["equipment"]["weapon"] == "iron_sword"
        assert p.hero_inventory == {"hero_crest": 1}
        assert p.mercenary_roster_state == {"allocation": {"total_points": 7}}
        assert p.mainline_commanders == {"chapter_test_07": "yun"}
        assert p.active_mainline == "chapter_test_07"
        assert p.mainline_progress["scene_id"] == "s7"
        # 账户态不回滚:第8章解锁的 knight + rating/season 保留
        assert "knight" in p.unlocked_classes
        assert p.rating == 1100
        assert p.current_season == 2

    async def test_advance_after_load_does_not_pollute_slots(self, slot_env):
        client, SessionLocal = slot_env
        await client.post("/progression/profiles", json={"user_name": "hero"})

        # 槽0 = 第7章
        await _set_state(
            SessionLocal, "hero", gold=700,
            hero_campaign_states=_hero_state(7, "iron_sword"),
        )
        await _save_slot(SessionLocal, "hero", 0, "chapter_test_07", 3)
        # 槽1 = 第8章
        await _set_state(
            SessionLocal, "hero", gold=800,
            hero_campaign_states=_hero_state(8, "steel_sword"),
        )
        await _save_slot(SessionLocal, "hero", 1, "chapter_test_08", 3)

        # 读槽0,然后大幅推进活动态(模拟又打了几章)
        await _load_slot(SessionLocal, "hero", 0)
        await _set_state(
            SessionLocal, "hero", gold=99999,
            hero_campaign_states=_hero_state(99, "legendary"),
        )

        # 再读槽0 → 仍是第7章原值(推进没污染 slot0 snapshot)
        await _load_slot(SessionLocal, "hero", 0)
        p = await _get_profile(SessionLocal, "hero")
        assert p.gold == 700
        assert p.hero_campaign_states["yun"]["level"] == 7

        # 读槽1 → 第8章原值(不受 slot0 载入/推进影响)
        await _load_slot(SessionLocal, "hero", 1)
        p = await _get_profile(SessionLocal, "hero")
        assert p.gold == 800
        assert p.hero_campaign_states["yun"]["level"] == 8

    async def test_reclear_overwrites_target_slot_only(self, slot_env):
        """再次通关第7章后,新档覆盖任意槽,不受老档影响,也不动其它槽。"""
        client, SessionLocal = slot_env
        await client.post("/progression/profiles", json={"user_name": "hero"})

        # 三槽初始各不同
        for slot, gold, ch in ((0, 700, "chapter_test_07"),
                               (1, 800, "chapter_test_08"),
                               (2, 900, "chapter_test_09")):
            await _set_state(SessionLocal, "hero", gold=gold)
            await _save_slot(SessionLocal, "hero", slot, ch, 3)

        # 重打第7章,拿到新养成态,覆盖槽2
        await _set_state(SessionLocal, "hero", gold=750,
                         hero_campaign_states=_hero_state(10, "silver_sword"))
        await _save_slot(SessionLocal, "hero", 2, "chapter_test_07", 3)

        # 槽2 = 新的第7章存档
        await _load_slot(SessionLocal, "hero", 2)
        p = await _get_profile(SessionLocal, "hero")
        assert p.gold == 750
        assert p.hero_campaign_states["yun"]["equipment"]["weapon"] == "silver_sword"

        # 槽0/槽1 完全不受影响
        await _load_slot(SessionLocal, "hero", 0)
        assert (await _get_profile(SessionLocal, "hero")).gold == 700
        await _load_slot(SessionLocal, "hero", 1)
        assert (await _get_profile(SessionLocal, "hero")).gold == 800
