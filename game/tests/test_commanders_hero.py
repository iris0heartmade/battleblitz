from app.classes.heroes import get


def test_yun_compiled_profile_includes_commander_metadata():
    yun = get("yun")

    assert yun.is_commander is True
    # 新机制阈值(全队累计士气星上限)
    assert yun.power_threshold == 18
    assert yun.commander_passive is not None
    assert yun.commander_passive.atk_pct == 0.10
    assert yun.commander_passive.range_delta == 1
    assert yun.commander_power is not None
    assert yun.commander_power.atk_pct == 0.30
    assert yun.commander_power.heal_pct == 0.50


def test_anna_compiled_profile_includes_commander_metadata():
    anna = get("anna")

    assert anna.is_commander is True
    # 新机制阈值(全队累计士气星上限)
    assert anna.power_threshold == 14
    assert anna.commander_passive is not None
    assert anna.commander_passive.def_pct == 0.15
    assert anna.commander_passive.mdef_pct == 0.10
    assert anna.commander_power is not None
    assert anna.commander_power.def_pct == 0.30
    assert anna.commander_power.mdef_pct == 0.30
    assert anna.commander_power.heal_pct == 0.80


def test_yuanying_compiled_profile_includes_silence_metadata():
    """鸢影:沉默领域 CO,warlock base,沉默半径 2(5×5)持续 1 大回合。

    沉默状态持久化层尚未实现,本测试只锁定数据形状与数值参数。
    """
    yuanying = get("yuanying")

    assert yuanying.is_commander is True
    assert yuanying.base_class_id == "warlock"
    assert yuanying.display_cn == "鸢影"
    assert yuanying.power_threshold == 16

    # stat overrides(基于 warlock base)
    assert yuanying.hp_override == 48
    assert yuanying.atk_override == 9
    assert yuanying.def_override == 11
    assert yuanying.matk_override == 28
    assert yuanying.mdef_override == 14

    # 资产路径
    assert yuanying.portrait_path == "portrait_yuanying.png"

    # passive: 全队 MATK +10% + 射程 +1
    assert yuanying.commander_passive is not None
    assert yuanying.commander_passive.matk_pct == 0.10
    assert yuanying.commander_passive.range_delta == 1

    # power: 沉默领域 5×5 + MATK +20%
    assert yuanying.commander_power is not None
    assert yuanying.commander_power.matk_pct == 0.20
    assert yuanying.commander_power.silence_radius == 2          # 5×5 方形
    assert yuanying.commander_power.silence_duration_turns == 1  # 1 大回合
    assert yuanying.commander_power.cost == 6                    # 默认 power_cost
