"""Lock the public numeric configuration for the built-in commanders."""

from dataclasses import asdict

from app.classes.heroes import get as get_hero


YUN_EXPECTED = {
    "is_commander": True,
    "commander_passive": {
        "id": "yun_passive",
        "atk_pct": 0.10, "def_pct": 0.0, "matk_pct": 0.0,
        "mdef_pct": 0.0, "hp_pct": 0.0, "mov_delta": 0,
        "range_delta": 1,
    },
    "commander_power": {
        "id": "yun_power",
        "atk_pct": 0.30, "def_pct": 0.0, "matk_pct": 0.0,
        "mdef_pct": 0.0, "heal_pct": 0.50, "extra_mov": 0,
        "range_delta": 0,
        "cost": 6,  # CommanderPower 新增 cost 字段,默认 6
    },
    # 新机制:全队累计士气星上限
    "power_threshold": 18,
}

ANNA_EXPECTED = {
    "is_commander": True,
    "commander_passive": {
        "id": "anna_passive",
        "atk_pct": 0.0, "def_pct": 0.15, "matk_pct": 0.0,
        "mdef_pct": 0.10, "hp_pct": 0.0, "mov_delta": 0,
        "range_delta": 0,
    },
    "commander_power": {
        "id": "anna_power",
        "atk_pct": 0.0, "def_pct": 0.30, "matk_pct": 0.0,
        "mdef_pct": 0.30, "heal_pct": 0.80, "extra_mov": 0,
        "range_delta": 0,
        "cost": 6,
    },
    "power_threshold": 14,
}


def _assert_snapshot(hero_id, expected):
    hero = get_hero(hero_id)
    assert hero.is_commander == expected["is_commander"]
    assert asdict(hero.commander_passive) == expected["commander_passive"]
    assert asdict(hero.commander_power) == expected["commander_power"]
    assert hero.power_threshold == expected["power_threshold"]


def test_yun_snapshot():
    _assert_snapshot("yun", YUN_EXPECTED)


def test_anna_snapshot():
    _assert_snapshot("anna", ANNA_EXPECTED)
