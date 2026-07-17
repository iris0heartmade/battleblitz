"""Data-driven starter equipment for campaign heroes.

The catalogue deliberately uses stable string ids.  A campaign save stores
those ids in ``HeroCampaignState.equipment`` and counts in
``PlayerProfile.hero_inventory``; no database migration is required.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


EQUIPMENT_SLOTS = ("weapon", "armor", "accessory")


@dataclass(frozen=True)
class EquipmentDefinition:
    equipment_id: str
    name: str
    slot: str
    rarity: int
    stat_bonuses: Mapping[str, int]
    description: str
    icon_path: str


CATALOG: dict[str, EquipmentDefinition] = {
    "iron_sword": EquipmentDefinition(
        "iron_sword", "铁剑", "weapon", 1, {"atk": 2},
        "制式单手剑，攻击 +2。", "/ui/assets/equipment/iron_sword.png",
    ),
    "oak_staff": EquipmentDefinition(
        "oak_staff", "橡木法杖", "weapon", 1, {"matk": 2},
        "朴素但可靠的法杖，魔攻 +2。", "/ui/assets/equipment/oak_staff.png",
    ),
    "guard_shield": EquipmentDefinition(
        "guard_shield", "守卫圆盾", "armor", 1, {"def": 2},
        "结实的圆盾，物防 +2。", "/ui/assets/equipment/guard_shield.png",
    ),
    "ruby_ring": EquipmentDefinition(
        "ruby_ring", "赤玉戒", "accessory", 1, {"mdef": 1, "hp": 3},
        "镶有赤玉的戒指，魔防 +1、HP +3。", "/ui/assets/equipment/ruby_ring.png",
    ),
}

STARTER_INVENTORY = {
    "iron_sword": 1,
    "oak_staff": 2,  # Yun and Anna are both spell users in chapter one.
    "guard_shield": 1,
    "ruby_ring": 1,
}

DEFAULT_EQUIPMENT_BY_CLASS = {
    "swordsman": {"weapon": "iron_sword", "armor": "guard_shield"},
    "warlock": {"weapon": "oak_staff", "accessory": "ruby_ring"},
    "healer": {"weapon": "oak_staff"},
}


def get_equipment(equipment_id: str | None) -> EquipmentDefinition | None:
    return CATALOG.get(equipment_id or "")


def default_equipment_for_class(class_id: str) -> dict[str, str]:
    return dict(DEFAULT_EQUIPMENT_BY_CLASS.get(class_id, {}))


def equipped_stat_bonuses(equipment: Mapping[str, str | None]) -> dict[str, int]:
    """Return the combined stats for valid, slot-correct equipment only."""
    bonuses: dict[str, int] = {}
    for slot, equipment_id in equipment.items():
        definition = get_equipment(equipment_id)
        if definition is None or definition.slot != slot:
            continue
        for stat, value in definition.stat_bonuses.items():
            bonuses[stat] = bonuses.get(stat, 0) + int(value)
    return bonuses


def catalog_payload() -> list[dict]:
    return [
        {
            "equipment_id": item.equipment_id,
            "name": item.name,
            "slot": item.slot,
            "rarity": item.rarity,
            "stat_bonuses": dict(item.stat_bonuses),
            "description": item.description,
            "icon_path": item.icon_path,
        }
        for item in CATALOG.values()
    ]
