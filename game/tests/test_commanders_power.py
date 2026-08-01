import pytest

from app.commanders.effects import (
    bake_passive_into_units, can_fire_co_power, expire_power, fire_co_power,
)


class FakeUnit:
    def __init__(self, id=1, hp=20, max_hp=20, atk=10, def_=5, matk=2, mdef=1,
                 mov=4, mp=4, attack_range=2):
        self.id = id
        self.hp, self.max_hp = hp, max_hp
        self.atk, self.def_, self.matk, self.mdef = atk, def_, matk, mdef
        self.mov, self.mp, self.attack_range = mov, mp, attack_range


class FakePlayer:
    """新机制:用 stars_earned_total 替代旧 meter。threshold=18(yun),power_cost=6。"""

    def __init__(self, commander_id, units=None, stars=0, active=False,
                 threshold=18, power_cost=6):
        self.commander_id, self.units = commander_id, units or []
        self.co_state = {
            "commander_id": commander_id,
            "stars_earned_total": stars,
            "threshold": threshold,
            "power_cost": power_cost,
            "meter": 0,  # 旧字段保留
            "is_power_active": active,
            "last_start_turn": -1,
        }


@pytest.mark.parametrize("player, expected", [
    # stars=power_cost(6) 即可放
    (FakePlayer("yun", stars=6), True),
    # stars 不足
    (FakePlayer("yun", stars=5), False),
    # 已在生效中
    (FakePlayer("yun", stars=6, active=True), False),
    # 无指挥官
    (FakePlayer(None, stars=100), False),
    # stars 多于 power_cost(累计型,放完只扣 6,继续累计)
    (FakePlayer("yun", stars=18), True),
])
def test_can_fire_conditions(player, expected):
    assert can_fire_co_power(player) is expected


def test_fire_stacks_heals_marks_and_consumes_stars():
    """放 power:stars -6 (power_cost),unit 应用 power 加成。"""
    unit = FakeUnit(hp=20, max_hp=40, atk=10)
    player = FakePlayer("yun", [unit], stars=18)
    bake_passive_into_units(player)
    fire_co_power(player)
    assert (unit.atk, unit.hp) == (14, 40)  # yun_power: +30% atk, +50% heal cap
    assert player.co_state["stars_earned_total"] == 12  # 18 - 6
    assert player.co_state["is_power_active"] is True
    assert unit._commander_power is not None


def test_fire_rejects_insufficient_stars():
    """stars_earned_total < power_cost 时 raise。"""
    with pytest.raises(ValueError, match="insufficient stars"):
        fire_co_power(FakePlayer("yun", stars=5))


def test_heal_is_capped_and_zero_extra_move_is_noop():
    unit = FakeUnit(hp=5, max_hp=20, mp=2, mov=5)
    player = FakePlayer("yun", [unit], stars=18)
    bake_passive_into_units(player)
    fire_co_power(player)
    assert (unit.hp, unit.mp) == (15, 2)


def test_expire_restores_passive_baseline_only():
    unit = FakeUnit(atk=10)
    player = FakePlayer("yun", [unit], stars=18)
    bake_passive_into_units(player)
    fire_co_power(player)
    expire_power(player)
    assert unit.atk == 11  # 还原到 passive (yun_passive +10% atk)
    assert player.co_state["is_power_active"] is False
    assert not hasattr(unit, "_commander_power")


def test_expire_when_inactive_is_noop():
    unit = FakeUnit(atk=10)
    player = FakePlayer("yun", [unit])
    bake_passive_into_units(player)
    expire_power(player)
    assert unit.atk == 11


def test_expire_restores_after_unit_reload():
    unit = FakeUnit(id=42, atk=10)
    player = FakePlayer("yun", [unit], stars=18)
    bake_passive_into_units(player)
    fire_co_power(player)
    saved_state = dict(player.co_state)

    reloaded = FakeUnit(id=42, atk=unit.atk)
    reloaded_player = FakePlayer("yun", [reloaded])
    reloaded_player.co_state = saved_state
    expire_power(reloaded_player)
    assert reloaded.atk == 11
    assert "_power_baselines" not in reloaded_player.co_state


def test_co_state_changes_use_new_dict_objects():
    player = FakePlayer("yun", [FakeUnit()], stars=18)
    bake_passive_into_units(player)
    before_fire = player.co_state
    fire_co_power(player)
    assert player.co_state is not before_fire
    before_expire = player.co_state
    expire_power(player)
    assert player.co_state is not before_expire


def test_fire_keeps_residual_stars_above_cost():
    """新机制:放 power 扣 6 后,若 stars 仍 >= 6,expire 后能再放(累计型)。"""
    unit = FakeUnit(atk=10)
    player = FakePlayer("yun", [unit], stars=12)
    bake_passive_into_units(player)
    fire_co_power(player)
    # 12 - 6 = 6,power 生效中
    assert player.co_state["stars_earned_total"] == 6
    # power 生效期间,can_fire 拒绝(避免双 power 叠加)
    assert can_fire_co_power(player) is False
    # expire 后,stars 仍 6 >= power_cost 6,可再放
    expire_power(player)
    assert player.co_state["stars_earned_total"] == 6
    assert can_fire_co_power(player) is True
