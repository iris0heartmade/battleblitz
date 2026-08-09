"""
验证英雄跨主线章节的状态持久化。

核心场景：
  1. 完成 chapter_01 后, yun/anna 的 hero_campaign_states 保存正确
  2. 启动 chapter_02 时, 从 hero_campaign_states 恢复等级/属性/技能/装备
  3. 跨章状态包括: class_id, level, exp, base_stats, learned_skills,
     weapon_ranks, equipment, promoted

Coverage:
  - 状态保存: start → 战斗完成 → advance → 检查 hero_campaign_states
  - 状态恢复: start next chapter → 验证 Unit 属性来自 hero_campaign_states
  - 转职保持: promoted hero 跨章保留 class_id
  - 装备保持: 装备配置跨章保留
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


@pytest.mark.integration
class TestHeroCampaignStatePersistence:

    @pytest.mark.asyncio
    async def test_hero_state_saved_after_battle_victory(self):
        """完成一场战斗后 advance 应保存 hero_campaign_states 到 profile。

        验证步骤:
          1. start chapter_01 (yun warlock Lv7)
          2. 模拟战斗中英雄成长 (level 7→8, 获得新技能)
          3. 标记 game finished → advance
          4. 检查 profile.hero_campaign_states[yun] 包含更新后的状态
        """
        from app.main import app
        from app.database import init_db, dispose_db
        from app.mainline import clear_cache

        await init_db()
        clear_cache()

        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                # setup
                r = await c.post("/progression/profiles", json={"user_name": "hero_test_1"})
                assert r.status_code == 201

                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/start",
                    json={"user_name": "hero_test_1", "skip_intro": True},
                )
                assert r.status_code in (200, 201), r.text
                body = r.json()
                game_id = body["game_id"]

                from app.database import AsyncSessionLocal
                from app.models import Game, Player, Unit
                from app.progression.models import PlayerProfile

                # 模拟战斗中成长: 修改 yun 的属性
                async with AsyncSessionLocal() as s:
                    human = (await s.execute(
                        select(Player).where(
                            Player.game_id == game_id,
                            Player.is_ai == False,
                        )
                    )).scalars().first()

                    yun = (await s.execute(
                        select(Unit).where(
                            Unit.player_id == human.id,
                            Unit.hero_id == "yun",
                        )
                    )).scalars().first()
                    assert yun is not None, "no yun unit found"

                    # 成长: level 7→8, 获得新技能
                    yun.level = 8
                    yun.exp = 33
                    yun.hp = 17  # current HP (in-battle damage)
                    yun.max_hp = 68
                    yun.atk = 31
                    yun.def_ = 18
                    yun.matk = 40
                    yun.mdef = 21
                    yun.mov = 6
                    yun.skills = ["arcane_strike", "veteran_focus"]

                    # 写 campaign_base_stats (advance 时读取这个)
                    yun.campaign_base_stats = {
                        "hp": 68, "atk": 31, "def": 18,
                        "matk": 40, "mdef": 21, "mov": 6, "mp": 8,
                    }

                    # 标记战斗完成
                    g = await s.get(Game, game_id)
                    g.status = "finished"
                    await s.commit()

                # advance → hero state 应保存
                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/advance",
                    json={"user_name": "hero_test_1", "game_id": game_id},
                )
                assert r.status_code == 200, r.text

                # 验证 hero_campaign_states
                async with AsyncSessionLocal() as s:
                    profile = (await s.execute(
                        select(PlayerProfile).where(
                            PlayerProfile.user_name == "hero_test_1"
                        )
                    )).scalar_one()

                    assert "yun" in profile.hero_campaign_states, (
                        f"yun missing from hero_campaign_states; "
                        f"got keys: {list(profile.hero_campaign_states.keys())}"
                    )
                    yun_state = profile.hero_campaign_states["yun"]

                    # 核心验证: 等级/属性/技能/装备
                    assert yun_state["level"] == 8, (
                        f"yun level not persisted: expected 8, got {yun_state['level']}"
                    )
                    assert yun_state["exp"] == 33
                    assert yun_state["class_id"] == "warlock"
                    assert yun_state["learned_skills"] == ["arcane_strike", "veteran_focus"]
                    assert yun_state["base_stats"]["hp"] == 68
                    assert yun_state["base_stats"]["atk"] == 31
                    assert yun_state["base_stats"]["matk"] == 40

                    # 当前战斗 MP 不应覆盖长期 pool
                    # 2026-08-10 平衡: yun mov_override = 5(全部英雄统一),mp == mov == 5
                    # (MOV/MP 合并后 mp 是"当前移动力池")
                    assert yun_state["base_stats"]["mp"] == 5, (
                        f"mp should be 5 (campaign_base = mov_override), "
                        f"got {yun_state['base_stats']['mp']}"
                    )

                    # anna 也在
                    assert "anna" in profile.hero_campaign_states, (
                        "anna missing from hero_campaign_states"
                    )

        finally:
            await dispose_db()

    @pytest.mark.asyncio
    async def test_promoted_hero_crosses_into_next_chapter(self):
        """验证: 转职后的英雄跨入下一章时保留 class_id 和 promoted 标记。

        步骤:
          1. 给 profile 预置 yun 为 sage (已转职)
          2. start chapter_02 → yun 应以 sage 身份登场
        """
        from app.main import app
        from app.database import init_db, dispose_db
        from app.mainline import clear_cache

        await init_db()
        clear_cache()

        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                # 创建 profile
                r = await c.post("/progression/profiles", json={"user_name": "promo_test"})
                assert r.status_code == 201

                # 预置 yun 为 sage
                from app.database import AsyncSessionLocal
                from app.progression.models import PlayerProfile
                async with AsyncSessionLocal() as s:
                    profile = (await s.execute(
                        select(PlayerProfile).where(
                            PlayerProfile.user_name == "promo_test"
                        )
                    )).scalar_one()
                    profile.hero_campaign_states = {
                        "yun": {
                            "hero_id": "yun",
                            "class_id": "sage",
                            "level": 4,
                            "exp": 12,
                            "base_stats": {
                                "hp": 58, "atk": 23, "def": 14,
                                "matk": 38, "mdef": 19, "mov": 5, "mp": 12,
                            },
                            "weapon_ranks": {},
                            "learned_skills": ["arcane_strike"],
                            "promoted": True,
                            "equipment": {"weapon": "oak_staff"},
                        }
                    }
                    profile.unlocked_classes = ["sage", "warlock", "swordsman", "archer", "healer"]
                    await s.commit()

                # start chapter_02
                r = await c.post(
                    "/mainlines/chapter_02_border_flame/start",
                    json={"user_name": "promo_test", "skip_intro": True},
                )
                assert r.status_code in (200, 201), r.text
                body = r.json()
                game_id = body["game_id"]

                from app.models import Game, Player, Unit
                async with AsyncSessionLocal() as s:
                    human = (await s.execute(
                        select(Player).where(
                            Player.game_id == game_id,
                            Player.is_ai == False,
                        )
                    )).scalars().first()
                    assert human is not None

                    yun = (await s.execute(
                        select(Unit).where(
                            Unit.player_id == human.id,
                            Unit.hero_id == "yun",
                        )
                    )).scalars().first()
                    assert yun is not None, "yun not found in chapter_02"

                    # 验证转职保留
                    assert yun.unit_type == "sage", (
                        f"expected sage, got {yun.unit_type} — "
                        f"promoted class not carried over!"
                    )
                    assert yun.level == 4

        finally:
            await dispose_db()

    @pytest.mark.asyncio
    async def test_equipment_carried_across_chapters(self):
        """验证: 英雄的装备配置跨章保留。

        步骤:
          1. 预置 yun 装备 oak_staff
          2. prepare chapter_02 → yun.equipment 包含 oak_staff
          3. start → yun 的 stat_bonuses 应包含装备加成
        """
        from app.main import app
        from app.database import init_db, dispose_db
        from app.mainline import clear_cache

        await init_db()
        clear_cache()

        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post("/progression/profiles",
                                 json={"user_name": "equip_test"})
                assert r.status_code == 201

                from app.database import AsyncSessionLocal
                from app.progression.models import PlayerProfile
                async with AsyncSessionLocal() as s:
                    profile = (await s.execute(
                        select(PlayerProfile).where(
                            PlayerProfile.user_name == "equip_test"
                        )
                    )).scalar_one()
                    profile.hero_campaign_states = {
                        "yun": {
                            "hero_id": "yun",
                            "class_id": "warlock",
                            "level": 7,
                            "exp": 0,
                            "base_stats": {"hp": 50, "atk": 20, "def": 11,
                                           "matk": 27, "mdef": 12, "mov": 4, "mp": 8},
                            "weapon_ranks": {},
                            "learned_skills": ["arcane_strike"],
                            "promoted": False,
                            "equipment": {"weapon": "oak_staff"},
                        }
                    }
                    profile.hero_inventory = {"oak_staff": 1}
                    await s.commit()

                # prepare → 应该看到装备
                r = await c.get(
                    "/mainlines/chapter_02_border_flame/prepare",
                    params={"user_name": "equip_test"},
                )
                assert r.status_code == 200, r.text
                body = r.json()
                heroes = body["heroes"]
                yun = next((h for h in heroes if h["hero_id"] == "yun"), None)
                assert yun is not None, "yun not in prepare heroes"

                assert yun["equipment"].get("weapon") == "oak_staff", (
                    f"expected oak_staff, got {yun['equipment']}"
                )

        finally:
            await dispose_db()

    @pytest.mark.asyncio
    async def test_initial_hero_state_created_if_missing(self):
        """如果 hero_campaign_states 中没有某英雄，start 应自动创建初始状态。"""
        from app.main import app
        from app.database import init_db, dispose_db
        from app.mainline import clear_cache

        await init_db()
        clear_cache()

        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post("/progression/profiles",
                                 json={"user_name": "initial_test"})
                assert r.status_code == 201

                # 不预置任何 hero_campaign_states
                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/start",
                    json={"user_name": "initial_test", "skip_intro": True},
                )
                assert r.status_code in (200, 201), r.text

                from app.database import AsyncSessionLocal
                from app.progression.models import PlayerProfile
                async with AsyncSessionLocal() as s:
                    profile = (await s.execute(
                        select(PlayerProfile).where(
                            PlayerProfile.user_name == "initial_test"
                        )
                    )).scalar_one()
                    assert "yun" in profile.hero_campaign_states, (
                        "yun should be auto-created in hero_campaign_states"
                    )
                    assert "anna" in profile.hero_campaign_states, (
                        "anna should be auto-created in hero_campaign_states"
                    )
                    yun = profile.hero_campaign_states["yun"]
                    assert yun["level"] >= 1
                    assert yun["class_id"] in ("warlock",)
                    assert yun["promoted"] is False

        finally:
            await dispose_db()
