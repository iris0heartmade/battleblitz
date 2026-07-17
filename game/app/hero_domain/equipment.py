"""Data-driven starter equipment for campaign heroes.

The catalogue deliberately uses stable string ids.  A campaign save stores
those ids in ``HeroCampaignState.equipment`` and counts in
``PlayerProfile.hero_inventory``; no database migration is required.
"""
from __future__ import annotations

from typing import Mapping
from app.item_catalog import ItemDefinition, get_item, load_items


EQUIPMENT_SLOTS = ("weapon", "armor", "accessory")


EquipmentDefinition = ItemDefinition
CATALOG: dict[str, ItemDefinition] = {
    item_id: item for item_id, item in load_items().items() if item.kind == "equipment"
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
    item = get_item(equipment_id)
    return item if item and item.kind == "equipment" else None


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
            "equipment_id": item.item_id,
            "name": item.name,
            "slot": item.slot,
            "rarity": item.rarity,
            "stat_bonuses": dict(item.stat_bonuses),
            "description": item.description,
            "icon_path": item.icon_path,
        }
        for item in CATALOG.values()
    ]
