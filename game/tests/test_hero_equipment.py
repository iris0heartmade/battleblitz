from app.hero_domain.equipment import (
    CATALOG,
    EQUIPMENT_SLOTS,
    STARTER_INVENTORY,
    equipped_stat_bonuses,
)
from app.hero_domain.legacy_bridge import (
    hero_campaign_state_from_dict,
    hero_campaign_state_to_dict,
)


def test_starter_equipment_has_one_copy_per_catalog_item():
    assert set(STARTER_INVENTORY) == set(CATALOG)
    assert all(count == 1 for count in STARTER_INVENTORY.values())
    assert {item.slot for item in CATALOG.values()} == set(EQUIPMENT_SLOTS)


def test_equipment_bonuses_only_accept_the_correct_slot():
    assert equipped_stat_bonuses({
        "weapon": "iron_sword",
        "armor": "guard_shield",
        "accessory": "ruby_ring",
    }) == {"atk": 2, "def": 2, "mdef": 1, "hp": 3}
    assert equipped_stat_bonuses({"armor": "iron_sword"}) == {}


def test_campaign_state_keeps_equipment_ids_across_save_round_trip():
    state = hero_campaign_state_from_dict({
        "hero_id": "yun",
        "class_id": "warlock",
        "level": 1,
        "exp": 0,
        "base_stats": {"hp": 40, "mp": 8},
        "equipment": {"weapon": "oak_staff", "accessory": "ruby_ring"},
    })
    assert hero_campaign_state_to_dict(state)["equipment"] == {
        "weapon": "oak_staff", "accessory": "ruby_ring"
    }
