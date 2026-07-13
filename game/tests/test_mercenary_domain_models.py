from __future__ import annotations

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
