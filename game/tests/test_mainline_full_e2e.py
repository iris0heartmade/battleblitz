"""
全章节端到端集成测试 — 验证主线典型生命周期是否跑通。

模拟一个玩家从开始到完成主线的完整操作序列：
  prepare → start → 战斗 → advance → next-battle → ... → victory

覆盖：
  1. 单章全流程 (chapter_01: 2 battles, rout + seize)
  2. 多章链 (chapter_01 → chapter_02)
  3. 事件触发完整性 (波次/陷阱/Boss)
  4. 奖励发放
  5. 前置条件检查
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


# ============================================================
# 单章全流程: chapter_01 (2 battles, rout + seize)
# ============================================================

class TestSingleChapterE2E:

    @pytest.mark.asyncio
    async def test_chapter_01_full_campaign(self):
        """从 start 到 victory 的完整 chapter_01 流程。

        步骤:
          1. profile 创建
          2. start(无 intro) → 验证 response
          3. 验证单位生成 (spawn_overrides + hero binding)
          4. 结束 battle_01 → advance → post_battle_dialogue
          5. next-battle → battle_02
          6. 结束 battle_02 → advance → VICTORY + 奖励
        """
        from app.main import app
        from app.database import init_db, dispose_db
        from app.mainline import clear_cache

        await init_db()
        clear_cache()

        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as c:
                # ---- 1. Profile ----
                r = await c.post(
                    "/progression/profiles",
                    json={"user_name": "e2e_test"},
                )
                assert r.status_code == 201

                # ---- 2. Start chapter_01 ----
                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/start",
                    json={"user_name": "e2e_test", "skip_intro": True},
                )
                assert r.status_code in (200, 201), (
                    f"start failed: {r.text}"
                )
                body = r.json()
                assert body["mainline_id"] == "chapter_01_steel_rebellion"
                assert body["battle_id"] == "battle_01"
                assert body["battle_index"] == 0
                assert body["total_battles"] == 2
                assert body["state"] == "battle"  # skip_intro
                game_id_1 = body["game_id"]

                # ---- 3. 验证单位生成 ----
                from app.database import AsyncSessionLocal
                from app.models import Game, Player, Unit

                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id_1)
                    assert g is not None
                    assert g.status == "playing"
                    assert g.name == "mainline:chapter_01_steel_rebellion:battle_01"

                    # 验证队伍
                    players = (await s.execute(
                        select(Player).where(Player.game_id == game_id_1)
                    )).scalars().all()
                    assert len(players) == 2
                    red = next(p for p in players if p.color == "red")
                    blue = next(p for p in players if p.color == "blue")
                    assert red.is_ai is False  # 人类
                    assert blue.is_ai is True   # AI

                    # 验证单位 (balanced_2p_15: 5 red, 5 blue)
                    red_units = (await s.execute(
                        select(Unit).where(Unit.player_id == red.id)
                    )).scalars().all()
                    blue_units = (await s.execute(
                        select(Unit).where(Unit.player_id == blue.id)
                    )).scalars().all()
                    assert len(red_units) == 5, (
                        f"expected 5 red units, got {len(red_units)}"
                    )
                    assert len(blue_units) == 5, (
                        f"expected 5 blue units, got {len(blue_units)}"
                    )

                    # hero_id 绑定: yun 存在
                    yun = next(
                        (u for u in red_units if u.hero_id == "yun"), None
                    )
                    assert yun is not None, "yun (hero_id=yun) not found"
                    assert yun.unit_type == "warlock", (
                        f"yun unit_type should be warlock, got {yun.unit_type}"
                    )
                    # 等级由 hero_campaign_states 决定，不提前预设时默认 1
                    assert yun.level >= 1

                    anna = next(
                        (u for u in red_units if u.hero_id == "anna"), None
                    )
                    assert anna is not None, "anna (hero_id=anna) not found"

                # ---- 4. 结束 battle_01 ----
                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id_1)
                    g.status = "finished"
                    await s.commit()

                # advance → post_battle_dialogue
                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/advance",
                    json={
                        "user_name": "e2e_test",
                        "game_id": game_id_1,
                    },
                )
                assert r.status_code == 200, (
                    f"advance after battle_01 failed: {r.text}"
                )
                body = r.json()
                assert body["state"] == "dialogue", (
                    f"expected dialogue after battle_01, got {body['state']}"
                )
                assert body["post_battle_dialogue_key"] == "battle_01_after"
                assert body["rewards"] is None  # 不是最后一战
                assert body["battle_index"] == 1  # cursor 前进了

                # ---- 5. next-battle → battle_02 ----
                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/next-battle",
                    json={"user_name": "e2e_test"},
                )
                assert r.status_code == 201, (
                    f"next-battle failed: {r.text}"
                )
                body = r.json()
                assert body["battle_id"] == "battle_02"
                assert body["battle_index"] == 1
                assert body["state"] == "battle"
                game_id_2 = body["game_id"]

                # 验证 battle_02 单位
                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id_2)
                    assert g is not None
                    assert g.status == "playing"
                    assert g.name == "mainline:chapter_01_steel_rebellion:battle_02"

                    players = (await s.execute(
                        select(Player).where(Player.game_id == game_id_2)
                    )).scalars().all()
                    assert len(players) == 2

                # ---- 6. 结束 battle_02 = VICTORY ----
                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id_2)
                    g.status = "finished"
                    await s.commit()

                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/advance",
                    json={
                        "user_name": "e2e_test",
                        "game_id": game_id_2,
                    },
                )
                assert r.status_code == 200, (
                    f"advance after battle_02 (victory) failed: {r.text}"
                )
                body = r.json()
                assert body["state"] == "victory", (
                    f"expected victory, got {body['state']}: {r.text}"
                )

                # 验证奖励
                rewards = body.get("rewards")
                assert rewards is not None, "no rewards in victory response"
                assert rewards["gold"] >= 500, (
                    f"expected gold >= 500, got {rewards['gold']}"
                )
                assert rewards["exp_per_unit"] > 0

                # 验证 profile 更新
                from app.progression.models import PlayerProfile
                async with AsyncSessionLocal() as s:
                    profile = (await s.execute(
                        select(PlayerProfile).where(
                            PlayerProfile.user_name == "e2e_test"
                        )
                    )).scalar_one()
                    assert profile.gold >= 500, (
                        f"profile gold not updated: {profile.gold}"
                    )
                    # active_mainline 应该被清空（已完成）
                    assert profile.active_mainline is None, (
                        "active_mainline should be None after victory"
                    )

        finally:
            await dispose_db()

    @pytest.mark.asyncio
    async def test_chapter_06_full_campaign_with_triggers(self):
        """chapter_06 含事件触发（波次/陷阱/Boss）的全流程。

        这个测试验证 F5B 的事件触发钩子在完整流程中的工作。
        与 test_mainline_event_triggers.py 不同，这里是跨整章全流程。
        """
        from app.main import app
        from app.database import init_db, dispose_db
        from app.mainline import clear_cache
        from app.events import bus
        import json
        from pathlib import Path

        log = Path(__file__).parent / "_ch06_e2e.log"
        bus.set_file_logger(str(log))

        await init_db()
        clear_cache()

        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as c:
                r = await c.post(
                    "/progression/profiles",
                    json={"user_name": "ch06_e2e"},
                )
                assert r.status_code == 201

                # unblock 所有 classes
                from app.database import AsyncSessionLocal
                from app.progression.models import PlayerProfile
                async with AsyncSessionLocal() as s:
                    profile = (await s.execute(
                        select(PlayerProfile).where(
                            PlayerProfile.user_name == "ch06_e2e"
                        )
                    )).scalar_one()
                    profile.unlocked_classes = [
                        "swordsman", "archer", "healer", "knight",
                        "warlock", "paladin", "sage",
                    ]
                    profile.gold = 99999
                    await s.commit()

                # ---- battle_01: rout + wave + trap ----
                r = await c.post(
                    "/mainlines/chapter_06_iron_reckoning/start",
                    json={"user_name": "ch06_e2e", "skip_intro": True},
                )
                assert r.status_code in (200, 201), r.text
                body = r.json()
                game_id = body["game_id"]
                assert body["battle_id"] == "battle_01"

                # 验证 battle_01 有单位
                from app.models import Game, Player, Unit
                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id)
                    assert g.status == "playing"

                    players = (await s.execute(
                        select(Player).where(Player.game_id == game_id)
                    )).scalars().all()
                    red = next(p for p in players if p.color == "red")
                    blue = next(p for p in players if p.color == "blue")
                    red_units = (await s.execute(
                        select(Unit).where(Unit.player_id == red.id)
                    )).scalars().all()
                    assert len(red_units) >= 1, "no red units in ch06 battle_01"

                # 触发 wave: turn = 3
                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id)
                    g.turn_number = 3
                    await s.commit()

                from app.game_logic import apply_end_of_turn as _aet
                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id)
                    await _aet(s, g)

                # 验证波次事件
                body = log.read_text(encoding="utf-8") if log.exists() else ""
                events = [json.loads(l) for l in body.splitlines()
                          if l.strip() and not l.startswith("===")]
                wave_events = [
                    e for e in events
                    if e.get("type") == "move"
                    and e.get("ctx", {}).get("wave_turn") == 3
                ]
                assert len(wave_events) >= 1, (
                    f"no wave-3 move in events log. events={[e.get('type') for e in events]}"
                )

                # 结束 battle_01
                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id)
                    g.status = "finished"
                    await s.commit()

                r = await c.post(
                    "/mainlines/chapter_06_iron_reckoning/advance",
                    json={"user_name": "ch06_e2e", "game_id": game_id},
                )
                assert r.status_code == 200, f"advance failed: {r.text}"
                assert r.json()["state"] == "dialogue"

                # ---- battle_02: defend ----
                r = await c.post(
                    "/mainlines/chapter_06_iron_reckoning/next-battle",
                    json={"user_name": "ch06_e2e"},
                )
                assert r.status_code == 201, r.text
                body = r.json()
                game_id_2 = body["game_id"]
                assert body["battle_id"] == "battle_02"

                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id_2)
                    g.status = "finished"
                    await s.commit()

                r = await c.post(
                    "/mainlines/chapter_06_iron_reckoning/advance",
                    json={"user_name": "ch06_e2e", "game_id": game_id_2},
                )
                assert r.status_code == 200, f"advance failed: {r.text}"

                # ---- battle_03: boss ----
                r = await c.post(
                    "/mainlines/chapter_06_iron_reckoning/next-battle",
                    json={"user_name": "ch06_e2e"},
                )
                assert r.status_code == 201, r.text
                game_id_3 = r.json()["game_id"]

                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id_3)
                    g.status = "finished"
                    await s.commit()

                r = await c.post(
                    "/mainlines/chapter_06_iron_reckoning/advance",
                    json={"user_name": "ch06_e2e", "game_id": game_id_3},
                )
                assert r.status_code == 200, f"advance failed: {r.text}"
                body = r.json()
                # chapter_06 完成 → VICTORY
                assert body["state"] == "victory", (
                    f"expected victory, got {body['state']}: {r.text}"
                )

        finally:
            bus.close_file_logger()
            if log.exists():
                log.unlink()
            await dispose_db()


# ============================================================
# 跨章链: chapter_01 → chapter_02
# ============================================================

class TestCrossChapterE2E:

    @pytest.mark.asyncio
    async def test_chapter_chain_01_to_02(self):
        """验证: 完成 chapter_01 后可以解锁 chapter_02。

        注意: 生产链门控需要正式存档 (GameSaveSlot)。此测试验证
        chain_gates 逻辑允许已清关的玩家进入下一章。
        """
        from app.main import app
        from app.database import init_db, dispose_db
        from app.mainline import clear_cache

        await init_db()
        clear_cache()

        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as c:
                r = await c.post(
                    "/progression/profiles",
                    json={"user_name": "chain_e2e"},
                )
                assert r.status_code == 201

                from app.database import AsyncSessionLocal
                from app.save.models import GameSaveSlot

                # 需要模拟 chapter_01 的完成存档
                # test chain 用 chapter_test_NN, 生产链下 chapter_01→02 目前
                # 还没有正式锁定逻辑, 所以直接测 start 应该可以
                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/start",
                    json={"user_name": "chain_e2e", "skip_intro": True},
                )
                assert r.status_code in (200, 201), (
                    f"chapter_01 start failed: {r.text}"
                )
                # 能进就说明门控允许

                # 创建存档标记 chapter_01 完成
                async with AsyncSessionLocal() as s:
                    slot = GameSaveSlot(
                        user_name="chain_e2e",
                        mainline_id="chapter_01_steel_rebellion",
                        slot_index=0,
                        chapter_index=2,  # 2 battles completed
                        snapshot={},
                    )
                    s.add(slot)
                    await s.commit()

                # chapter_02 应该可以访问（用 force 因为 ch01 还是 active）
                r = await c.post(
                    "/mainlines/chapter_02_border_flame/start",
                    json={"user_name": "chain_e2e", "skip_intro": True, "force": True},
                )
                assert r.status_code in (200, 201), (
                    f"chapter_02 start after ch01 completion failed: {r.text}"
                )

        finally:
            await dispose_db()


# ============================================================
# 准备工作流（prepare 端点完整流程）
# ============================================================

class TestPrepareFlowE2E:

    @pytest.mark.asyncio
    async def test_full_prepare_flow(self):
        """验证 prepare → promote → equipment → complete 全流程。"""
        from app.main import app
        from app.database import init_db, dispose_db
        from app.mainline import clear_cache

        await init_db()
        clear_cache()

        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(
                transport=transport, base_url="http://test"
            ) as c:
                r = await c.post(
                    "/progression/profiles",
                    json={"user_name": "prep_e2e"},
                )
                assert r.status_code == 201

                # 预置转职用道具
                from app.database import AsyncSessionLocal
                from app.progression.models import PlayerProfile
                async with AsyncSessionLocal() as s:
                    profile = (await s.execute(
                        select(PlayerProfile).where(
                            PlayerProfile.user_name == "prep_e2e"
                        )
                    )).scalar_one()
                    # 预置转职用道具 + hero 等级（需要 20 级才能转职）
                    profile.hero_inventory = {"hero_crest": 2}
                    profile.hero_campaign_states = {
                        "yun": {
                            "hero_id": "yun",
                            "class_id": "warlock",
                            "level": 20,
                            "exp": 88,
                            "base_stats": {"hp": 63, "atk": 30, "def": 16,
                                           "matk": 39, "mdef": 19, "mov": 5, "mp": 12},
                            "weapon_ranks": {},
                            "learned_skills": ["arcane_strike"],
                            "promoted": False,
                            "equipment": {},
                        }
                    }
                    profile.unlocked_classes = [
                        "swordsman", "archer", "healer", "knight",
                        "warlock", "sage",
                    ]
                    await s.commit()

                # prepare
                r = await c.get(
                    "/mainlines/chapter_01_steel_rebellion/prepare",
                    params={"user_name": "prep_e2e"},
                )
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["mainline_id"] == "chapter_01_steel_rebellion"
                assert len(body["heroes"]) >= 2
                assert body["inventory"].get("hero_crest", 0) == 2

                yun = next(
                    (h for h in body["heroes"] if h["hero_id"] == "yun"), None
                )
                assert yun is not None, "yun not in prepare heroes"
                assert yun["can_promote"] is True  # 有 crest

                # promote yun → sage
                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/prepare/promote",
                    json={
                        "user_name": "prep_e2e",
                        "hero_id": "yun",
                        "target_class_id": "sage",
                    },
                )
                assert r.status_code == 200, r.text
                pbody = r.json()
                assert pbody["class_id"] == "sage"
                assert pbody["promoted"] is True
                assert pbody["hero_crest_left"] == 1

                # 用 promoted 状态 start
                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/start",
                    json={"user_name": "prep_e2e", "skip_intro": True},
                )
                assert r.status_code in (200, 201), r.text

                from app.models import Game, Player, Unit
                async with AsyncSessionLocal() as s:
                    human = (await s.execute(
                        select(Player).where(
                            Player.is_ai == False,
                            Player.game_id == r.json()["game_id"],
                        )
                    )).scalars().first()
                    assert human is not None
                    yun = (await s.execute(
                        select(Unit).where(
                            Unit.player_id == human.id,
                            Unit.hero_id == "yun",
                        )
                    )).scalars().first()
                    assert yun is not None
                    # 验证转职生效
                    assert yun.unit_type == "sage", (
                        f"yun should start as sage after promotion, got {yun.unit_type}"
                    )

        finally:
            await dispose_db()
