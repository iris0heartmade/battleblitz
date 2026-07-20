from app.hero_domain.equipment import (
    CATALOG,
    EQUIPMENT_SLOTS,
    STARTER_INVENTORY,
    equipped_stat_bonuses,
    default_equipment_for_class,
)
from app.hero_domain.legacy_bridge import (
    hero_campaign_state_from_dict,
    hero_campaign_state_to_dict,
)
from app.item_catalog import load_items, load_shop


def test_starter_equipment_has_one_copy_per_catalog_item():
    assert set(STARTER_INVENTORY) == set(CATALOG)
    assert STARTER_INVENTORY["oak_staff"] == 2
    assert {item.slot for item in CATALOG.values()} == set(EQUIPMENT_SLOTS)


def test_default_loadouts_cover_chapter_one_spell_heroes():
    assert default_equipment_for_class("warlock") == {
        "weapon": "oak_staff", "accessory": "ruby_ring"
    }
    assert default_equipment_for_class("healer") == {"weapon": "oak_staff"}


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


def test_post_battle_shop_references_individual_json_defined_items():
    items = load_items()
    stock = load_shop("post_battle")
    assert {item.item_id for item in stock} == {
        "iron_sword", "oak_staff", "guard_shield", "ruby_ring", "hero_crest"
    }
    assert items["hero_crest"].price == 300
    assert items["iron_sword"].icon_path.endswith("iron_sword.png")
