from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.mercenary_domain.rules import (
    InvalidMercenaryStatError,
    MercenaryAllocationRules,
    MercenaryPointBudgetError,
    MercenaryUpgradeLimitError,
    UnknownMercenaryTypeError,
    UpgradeRule,
    apply_commander_upgrade,
    apply_allocation_to_unit,
)
from app.mercenary_domain.state import CommanderAllocation
from app.mercenary_domain.templates import ChapterBalanceConfig


def test_commander_allocation_tracks_spent_points():
    allocation = CommanderAllocation(total_points=100)
    allocation.add_upgrade("infantry", "atk", 1, 10)
    assert allocation.spent_points == 10
    assert allocation.unit_type_upgrades["infantry"]["atk"] == 1


def test_chapter_balance_config_defaults_enemy_modifiers():
    cfg = ChapterBalanceConfig()
    assert cfg.enemy_modifiers["attack"] == 0
    assert cfg.enemy_modifiers["defense"] == 0


def test_allocation_calculates_cost_on_the_server():
    allocation = CommanderAllocation(total_points=100)

    receipt = apply_commander_upgrade(
        allocation, unit_type="swordsman", stat="atk", value=2,
    )

    assert receipt.cost == 20
    assert receipt.spent_points == 20
    assert receipt.remaining_points == 80
    assert allocation.unit_type_upgrades == {"swordsman": {"atk": 2}}


@pytest.mark.parametrize(
    ("unit_type", "stat", "error"),
    [
        ("not_a_unit", "atk", UnknownMercenaryTypeError),
        ("swordsman", "luck", InvalidMercenaryStatError),
    ],
)
def test_allocation_rejects_unknown_types_and_stats(unit_type, stat, error):
    with pytest.raises(error):
        apply_commander_upgrade(
            CommanderAllocation(), unit_type=unit_type, stat=stat, value=1,
        )


def test_allocation_enforces_stat_cap_and_point_budget():
    allocation = CommanderAllocation(total_points=80)
    apply_commander_upgrade(allocation, unit_type="swordsman", stat="mov", value=2)

    with pytest.raises(MercenaryUpgradeLimitError):
        apply_commander_upgrade(allocation, unit_type="swordsman", stat="mov", value=1)

    with pytest.raises(MercenaryPointBudgetError):
        apply_commander_upgrade(
            allocation, unit_type="swordsman", stat="hp", value=20,
        )


def test_chapter_rule_can_limit_available_types_and_override_costs():
    rules = MercenaryAllocationRules(
        allowed_unit_types={"healer"},
        stat_rules={"matk": UpgradeRule(point_cost=3, max_bonus=3)},
    )
    allocation = CommanderAllocation(total_points=10)

    receipt = apply_commander_upgrade(
        allocation, unit_type="healer", stat="matk", value=3, rules=rules,
    )
    assert receipt.cost == 9

    with pytest.raises(UnknownMercenaryTypeError):
        apply_commander_upgrade(
            allocation, unit_type="swordsman", stat="matk", value=1, rules=rules,
        )


def test_allocation_applies_to_generic_battle_unit_without_rounding():
    unit = SimpleNamespace(
        unit_type="swordsman", hp=40, max_hp=40, atk=10, def_=8,
        matk=0, mdef=2, mov=3, mp=3,
    )

    applied = apply_allocation_to_unit(unit, {
        "swordsman": {"hp": 4, "atk": 2, "def": 1, "mov": 1},
    })

    assert applied == {"hp": 4, "atk": 2, "def": 1, "mov": 1}
    assert (unit.hp, unit.max_hp, unit.atk, unit.def_, unit.mov, unit.mp) == (
        44, 44, 12, 9, 4, 4,
    )
