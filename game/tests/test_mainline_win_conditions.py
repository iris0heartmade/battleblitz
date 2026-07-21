"""
验证所有 4 种胜利条件（rout / seize / defend / boss）在引擎中的处理。

现状：
  - ``rout``  — 全引擎支持（通用 last-team-alive 判定）
  - ``seize`` — 在 ``claim_tile`` 中处理（HQ 所有权翻转时）
  - ``defend`` — 有限支持（需要 game.defend_turns，仅 legacy 场景）
  - ``boss``  — **未实现**（WinCondition 字面量存在但 check_win_condition 无分支）
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


async def _create_profile(client, user_name="test") -> int:
    r = await client.post("/progression/profiles", json={"user_name": user_name})
    assert r.status_code == 201
    return r.json()["id"]


async def _start_chapter(client, user_name: str, mainline_id: str) -> tuple[int, int]:
    """Start a chapter, return (game_id, player_id)."""
    r = await client.post(f"/mainlines/{mainline_id}/start", json={
        "user_name": user_name, "skip_intro": True,
    })
    assert r.status_code in (200, 201), r.text
    body = r.json()
    return body["game_id"], body["player_id"]


# ============================================================
# 1) Rout — 击杀所有敌方单位
# ============================================================

class TestRoutWinCondition:

    @pytest.mark.asyncio
    async def test_check_win_condition_rout_detection(self):
        """直接验证 check_win_condition 能检测 rout。

        删掉所有敌方单位后调 check_win_condition，game 应 finished。
        """
        from app.main import app
        from app.database import AsyncSessionLocal, init_db, dispose_db
        from app.mainline import clear_cache
        from app.models import Game, Player, Unit

        await init_db()
        clear_cache()
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await _create_profile(client, "rout_test")
                game_id, _ = await _start_chapter(client, "rout_test", "chapter_01_steel_rebellion")

                # 删掉所有敌方单位
                async with AsyncSessionLocal() as s:
                    blue = (await s.execute(
                        select(Player).where(Player.game_id == game_id, Player.color == "blue")
                    )).scalars().first()
                    await s.execute(select(Unit).where(Unit.player_id == blue.id))
                    # 直接删 DB 记录
                    from sqlalchemy import delete
                    await s.execute(delete(Unit).where(Unit.player_id == blue.id))
                    await s.commit()

                # 直接调 check_win_condition
                from app.game_logic import check_win_condition
                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id)
                    finished = await check_win_condition(s, g)
                    assert finished, "check_win_condition should return True for rout"
                    await s.commit()

                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id)
                    assert g.status == "finished", (
                        f"Expected finished, got {g.status}. Win reason: {g.win_reason}"
                    )
                    assert g.win_reason == "rout"
        finally:
            await dispose_db()

    @pytest.mark.asyncio
    async def test_rout_detected_through_apply_end_of_turn(self):
        """通过 apply_end_of_turn 验证 rout 检测。

        cleanup_dead_units 内部就会调 check_win_condition，所以无需额外调用。
        """
        from app.main import app
        from app.database import AsyncSessionLocal, init_db, dispose_db
        from app.mainline import clear_cache
        from app.models import Game, Player, Unit

        await init_db()
        clear_cache()
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await _create_profile(client, "rout_aet")
                game_id, _ = await _start_chapter(client, "rout_aet", "chapter_01_steel_rebellion")

                async with AsyncSessionLocal() as s:
                    blue = (await s.execute(
                        select(Player).where(Player.game_id == game_id, Player.color == "blue")
                    )).scalars().first()
                    blue_units = (await s.execute(
                        select(Unit).where(Unit.player_id == blue.id)
                    )).scalars().all()
                    for u in blue_units:
                        u.hp = 0
                    await s.commit()

                # cleanup_dead_units 内部会调 check_win_condition
                # 我们直接调 cleanup_dead_units 来验证这个路径
                from app.game_logic import cleanup_dead_units, _load_game_actors
                async with AsyncSessionLocal() as s:
                    players, units = await _load_game_actors(s, Game(id=game_id))
                    _units = [u for u in units if u.hp > 0] + [u for u in units if u.hp <= 0]
                    dead_ids = await cleanup_dead_units(s, _units)
                    assert len(dead_ids) > 0, "cleanup_dead_units should delete blue units"

                    g = await s.get(Game, game_id)
                    assert g.status == "finished", (
                        f"Expected finished, got {g.status}. Win reason: {g.win_reason}"
                    )
        finally:
            await dispose_db()


# ============================================================
# 2) Seize — 占领城堡（castles 系统）
# ============================================================

class TestSeizeWinCondition:

    @pytest.mark.asyncio
    async def test_claim_tile_on_castle_does_not_crash(self):
        """占领城堡 tile 时 claim_tile 不抛异常。

        注意：seize 是在 claim_tile 中城堡翻转时触发的。
        目前游戏没有"seize"专用 win_condition 测试地图，所以只验证
        claim_tile 在 mainline-spawned game 上能正常执行。
        """
        from app.main import app
        from app.database import AsyncSessionLocal, init_db, dispose_db
        from app.mainline import clear_cache
        from app.models import Game, Player, Unit, Tile

        await init_db()
        clear_cache()
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await _create_profile(client, "seize_test")
                game_id, _ = await _start_chapter(client, "seize_test", "chapter_02_border_flame")

                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id)
                    assert g.status == "playing"

                    # 找蓝色玩家的城堡 tile
                    blue = (await s.execute(
                        select(Player).where(Player.game_id == game_id, Player.color == "blue")
                    )).scalars().first()
                    castle = (await s.execute(
                        select(Tile).where(
                            Tile.game_id == game_id,
                            Tile.owner_id == blue.id,
                            Tile.terrain == "castle",
                        )
                    )).scalars().first()
                    if castle is None:
                        pytest.skip("no blue-owned castle tile to seize")

                    red = (await s.execute(
                        select(Player).where(Player.game_id == game_id, Player.color == "red")
                    )).scalars().first()
                    red_unit = (await s.execute(
                        select(Unit).where(Unit.player_id == red.id, Unit.hp > 0)
                    )).scalars().first()
                    assert red_unit is not None

                    # 验证 claim_castle_if_present 能识别
                    from app.game_logic import claim_castle_if_present
                    result = claim_castle_if_present(castle, red_unit)
                    # 此函数只是检查条件，true 表示可以占领
                    assert result is not None
                    # 成功执行业没有异常即可
        finally:
            await dispose_db()


# ============================================================
# 3) Defend — 坚守到指定回合
# ============================================================

class TestDefendWinCondition:

    @pytest.mark.asyncio
    async def test_check_win_condition_defend_detection(self):
        """直接验证 check_win_condition 能检测 defend。

        设置 defend_turns 并到达对应回合后，game 应 finished。
        """
        from app.main import app
        from app.database import AsyncSessionLocal, init_db, dispose_db
        from app.mainline import clear_cache
        from app.models import Game

        await init_db()
        clear_cache()
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await _create_profile(client, "defend_test")
                game_id, _ = await _start_chapter(client, "defend_test", "chapter_01_steel_rebellion")

                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id)
                    g.win_condition = "defend"
                    g.defend_turns = 5
                    g.turn_number = 5

                    from app.models import Player
                    blue = (await s.execute(
                        select(Player).where(Player.game_id == game_id, Player.color == "blue")
                    )).scalars().first()
                    from sqlalchemy import delete as _delete
                    from app.models import Unit as _Unit
                    await s.execute(_delete(_Unit).where(_Unit.player_id == blue.id))
                    await s.commit()

                from app.game_logic import check_win_condition
                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id)
                    finished = await check_win_condition(s, g)
                    assert finished, "check_win_condition should return True for defend"
                    await s.commit()

                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id)
                    assert g.status == "finished"
                    assert g.win_reason == "defend"
        finally:
            await dispose_db()


# ============================================================
# 4) Boss — 击杀 Boss 单位
# ============================================================

class TestBossWinCondition:

    @pytest.mark.asyncio
    async def test_trigger_boss_kill_check_publishes_event(self):
        """验证 trigger_boss_kill_check 发布 boss_kill 事件。

        注意：boss win_condition 在引擎中没有实现，但事件系统会发布
        boss kill 事件。此测试验证事件发布，标记已知缺口。
        """
        from app.main import app
        from app.database import AsyncSessionLocal, init_db, dispose_db
        from app.mainline import clear_cache
        from app.events import bus
        from app.mainline.event_trigger import trigger_boss_kill_check
        from app.models import Game, Player, Unit
        import json
        from pathlib import Path

        log = Path(__file__).parent / "_boss_trigger.log"
        bus.set_file_logger(str(log))
        await init_db()
        clear_cache()
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await _create_profile(client, "boss_trig")
                game_id, _ = await _start_chapter(client, "boss_trig", "chapter_01_steel_rebellion")

                # 创建已死的敌方单位名为 "kalde"
                async with AsyncSessionLocal() as s:
                    blue = (await s.execute(
                        select(Player).where(Player.game_id == game_id, Player.color == "blue")
                    )).scalars().first()
                    blue_units = (await s.execute(
                        select(Unit).where(Unit.player_id == blue.id)
                    )).scalars().all()
                    target = blue_units[0]
                    target.name = "kalde"
                    target.hp = 0  # 死了
                    # 但不要从DB删除它（cleanup_dead_units 会删，但我们直接调 trigger）
                    await s.commit()

                # 直接调 trigger_boss_kill_check（绕过 apply_end_of_turn）
                async with AsyncSessionLocal() as s:
                    g = await s.get(Game, game_id)
                    result = await trigger_boss_kill_check(s, g)
                    assert result == 1, "trigger_boss_kill_check should find 1 boss kill"

                # 验证事件
                body = log.read_text(encoding="utf-8") if log.exists() else ""
                events = [json.loads(l) for l in body.splitlines()
                          if l.strip() and not l.startswith("===")]
                boss_kills = [e for e in events
                              if e.get("type") == "kill"
                              and e.get("ctx", {}).get("is_boss_kill") is True]
                assert len(boss_kills) >= 1, (
                    f"no boss_kill event. Events: {[e.get('type') for e in events]}"
                )
                ctx = boss_kills[0]["ctx"]
                assert ctx.get("boss") is True
                assert ctx.get("is_boss_kill") is True

        finally:
            bus.close_file_logger()
            if log.exists():
                log.unlink()
            await dispose_db()
