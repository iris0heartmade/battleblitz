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
