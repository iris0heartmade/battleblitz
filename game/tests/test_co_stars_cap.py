"""CO power star meter cap behavior + 单向不变式。

不变式:
- 累积到 threshold 后 record_morale_star 不再加,返回 0
- consume_power_stars 不会反向影响 unit.morale
- unit.morale 单调累加,与 stars_earned_total 单向联系
"""
from types import SimpleNamespace

from app.commanders import consume_power_stars, record_morale_star
from app.game_logic import award_morale
from app.commanders.effects import fire_co_power


def test_record_morale_star_stops_at_threshold():
    """满 threshold 后停止增加。"""
    player = SimpleNamespace(commander_id="yun", co_state={
        "threshold": 5, "stars_earned_total": 5, "power_cost": 6,
    })
    assert record_morale_star(player, 1) == 0
    assert record_morale_star(player, 100) == 0
    # 不变
    assert player.co_state["stars_earned_total"] == 5


def test_record_morale_star_partially_fills_to_cap():
    """未满 threshold 时,加 1 颗只 +1。"""
    player = SimpleNamespace(commander_id="yun", co_state={
        "threshold": 5, "stars_earned_total": 3, "power_cost": 6,
    })
    assert record_morale_star(player, 1) == 1
    assert player.co_state["stars_earned_total"] == 4
    # 累计还差 1
    assert record_morale_star(player, 5) == 1
    assert player.co_state["stars_earned_total"] == 5
    # 满 cap
    assert record_morale_star(player, 1) == 0


def test_fire_does_not_touch_unit_morale():
    """不变式:consume_power_stars 只动 stars_earned_total,unit.morale 保持不变。"""
    from app.config import MORALE_MAX
    from types import SimpleNamespace

    class FakeUnit:
        def __init__(self):
            self.atk = 10
            self.def_ = 5
            self.matk = 0
            self.mdef = 0
            self.hp = 20
            self.max_hp = 20
            self.mov = 5
            self.mp = 3
            self.morale = MORALE_MAX  # 已满星

    # 玩家有 2 个满星单位
    unit1 = FakeUnit()
    unit2 = FakeUnit()
    player = SimpleNamespace(commander_id="yun", co_state={
        "threshold": 18, "stars_earned_total": 6, "power_cost": 6,
    }, units=[unit1, unit2])

    # 放 power
    fire_co_power(player)
    # stars 扣 6
    assert player.co_state["stars_earned_total"] == 0
    # unit.morale 完全不动
    assert unit1.morale == MORALE_MAX
    assert unit2.morale == MORALE_MAX


def test_award_morale_unit_morale_independent_of_co_stars():
    """award_morale 不会让 stars 超过 cap(虽然这是间接的)。"""
    # 给一个 unit,模拟在 player 满 cap 时再 award
    unit = SimpleNamespace(morale=2)  # 还没到 3
    player = SimpleNamespace(commander_id="yun", co_state={
        "threshold": 3, "stars_earned_total": 3, "power_cost": 6,
    })

    added = award_morale(unit, player)
    # unit.morale +1
    assert unit.morale == 3
    # player stars 已 cap,不再加
    assert added == 0
    assert player.co_state["stars_earned_total"] == 3
