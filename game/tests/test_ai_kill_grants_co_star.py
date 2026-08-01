"""Regression: AI kill 现在累加 CO 累积槽(原 on_kill 缺失 bug 修复)。

旧机制:AI 攻击走 _ai_attack,只调 award_exp → award_morale(unit),
不调 on_kill(player) 给 CO 累积槽加分。人类 vs AI 时 CO 进度只有人类加。

新机制:award_morale(unit, player) 调 record_morale_star(player, 1),
AI 玩家(attacker.player)也会进星。
"""
import pytest
from sqlalchemy import select

from app.models import Game, Player, Tile, Unit
from app.game_logic import _ai_attack


async def _ai_combat(db_session):
    """建立 AI 攻击场景,attacker 玩家无人类交互。"""
    game = Game(name="ai-kill", status="playing", map_seed=1, win_condition="defend")
    db_session.add(game)
    await db_session.flush()

    ai_player = Player(
        game_id=game.id, user_name="ai-attacker", color="red", seat=0,
        is_ai=True,
        commander_id="yun",
        co_state={"stars_earned_total": 0, "threshold": 18, "power_cost": 6},
    )
    human_player = Player(
        game_id=game.id, user_name="human-defender", color="blue", seat=1,
        is_ai=False,
        # 无 commander:不会被 record_morale_star 累加
    )
    db_session.add_all([ai_player, human_player])
    await db_session.flush()

    ai_unit = Unit(
        player_id=ai_player.id, unit_type="swordsman", name="AI-A",
        hp=20, max_hp=20, atk=20, def_=1, matk=0, mdef=0,
        mov=3, mp=3, x=0, y=0, skills=[],
    )
    target = Unit(
        player_id=human_player.id, unit_type="archer", name="Human-D",
        hp=1, max_hp=20, atk=20, def_=1, matk=0, mdef=0,
        mov=3, mp=3, x=1, y=0, skills=[],
    )
    db_session.add_all([ai_unit, target])
    await db_session.flush()
    db_session.add_all([
        Tile(game_id=game.id, x=0, y=0, terrain="plain", occupied_unit_id=ai_unit.id),
        Tile(game_id=game.id, x=1, y=0, terrain="plain", occupied_unit_id=target.id),
    ])
    await db_session.flush()

    return game.id, ai_player.id, ai_unit.id, target.id, human_player.id


@pytest.mark.asyncio
async def test_ai_kill_grants_one_star_to_ai_player(db_session, monkeypatch):
    """AI 击杀目标:AI 玩家的 stars_earned_total 增 1(旧 on_kill 缺失的修复)。"""
    from app.game_logic import DamageResult

    game_id, ai_pid, ai_uid, target_id, _hp = await _ai_combat(db_session)
    monkeypatch.setattr(
        "app.game_logic.attack_with_double_strike",
        lambda *a, **k: [
            DamageResult(damage=10, is_crit=False, is_kill=True,
                         effective_atk=10, defense_total=0)
        ],
    )

    ai_unit = await db_session.get(Unit, ai_uid)
    target = await db_session.get(Unit, target_id)
    # 预先 load player 关系,避免 _ai_attack 内部 unit_attack_range 触发
    # async lazy load(在 MissingGreenlet 之前已 fail)
    from sqlalchemy.orm import selectinload
    await db_session.refresh(ai_unit, ["player"])
    await db_session.refresh(target, ["player"])
    await _ai_attack(db_session, ai_unit, target)
    await db_session.commit()
    db_session.expire_all()

    # 重新 load
    ai_player = await db_session.get(Player, ai_pid)
    # AI 玩家累加 1 颗星
    assert ai_player.co_state["stars_earned_total"] == 1
    # 目标死了
    target_after = await db_session.get(Unit, target_id)
    assert target_after is None or target_after.hp <= 0


@pytest.mark.asyncio
async def test_ai_unit_morale_increases_along_with_co_star(db_session, monkeypatch):
    """AI 单位的 morale 和玩家累积槽都增加(同步触发)。"""
    from app.game_logic import DamageResult

    game_id, ai_pid, ai_uid, target_id, _hp = await _ai_combat(db_session)
    monkeypatch.setattr(
        "app.game_logic.attack_with_double_strike",
        lambda *a, **k: [
            DamageResult(damage=10, is_crit=False, is_kill=True,
                         effective_atk=10, defense_total=0)
        ],
    )

    ai_unit = await db_session.get(Unit, ai_uid)
    target = await db_session.get(Unit, target_id)
    await db_session.refresh(ai_unit, ["player"])
    await db_session.refresh(target, ["player"])
    starting_morale = ai_unit.morale
    await _ai_attack(db_session, ai_unit, target)
    await db_session.commit()
    db_session.expire_all()

    # unit.morale +1(cap 3)
    ai_unit = await db_session.get(Unit, ai_uid)
    assert ai_unit.morale == starting_morale + 1
    # player stars +1
    ai_player = await db_session.get(Player, ai_pid)
    assert ai_player.co_state["stars_earned_total"] == 1


@pytest.mark.asyncio
async def test_ai_kill_does_not_credit_target_player_without_commander(db_session, monkeypatch):
    """AI 击杀:目标玩家无 commander,不会进星(避免脏数据)。

    目标玩家在 _ai_combat 中是 human_player(无 commander_id),
    record_morale_star 会自动跳过它。
    """
    from app.game_logic import DamageResult

    game_id, ai_pid, ai_uid, target_id, human_pid = await _ai_combat(db_session)
    monkeypatch.setattr(
        "app.game_logic.attack_with_double_strike",
        lambda *a, **k: [
            DamageResult(damage=10, is_crit=False, is_kill=True,
                         effective_atk=10, defense_total=0)
        ],
    )

    ai_unit = await db_session.get(Unit, ai_uid)
    target = await db_session.get(Unit, target_id)
    await db_session.refresh(ai_unit, ["player"])
    await db_session.refresh(target, ["player"])
    await _ai_attack(db_session, ai_unit, target)
    await db_session.commit()
    db_session.expire_all()

    # AI 玩家(attacker)累加 1 星
    ai_player = await db_session.get(Player, ai_pid)
    assert ai_player.co_state["stars_earned_total"] == 1
    # 目标玩家无 commander,没记录
    human_player = await db_session.get(Player, human_pid)
    assert human_player.co_state.get("stars_earned_total", 0) == 0
