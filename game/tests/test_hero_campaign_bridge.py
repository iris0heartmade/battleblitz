from app.hero_domain import (
    build_campaign_spawn_payload,
    build_hero_character_template,
    build_hero_class_template,
    build_initial_campaign_state,
    hero_campaign_state_from_dict,
    hero_campaign_state_to_dict,
)


def test_build_initial_campaign_state_from_legacy_hero_profile():
    state = build_initial_campaign_state("yun")

    assert state.hero_id == "yun"
    assert state.class_id == "warlock"
    assert state.level == 1
    assert state.base_stats["hp"] == 50
    assert state.base_stats["matk"] == 27
    assert state.base_stats["mov"] == 4
    assert "arcane_strike" in state.learned_skills
    assert state.promoted is False


def test_legacy_bridge_exposes_hero_and_class_templates():
    char = build_hero_character_template("anna")
    hero_class = build_hero_class_template("healer")

    assert char.default_class_id == "healer"
    assert char.promotion_routes == ["saint"]
    assert hero_class.promotion_options == ["saint"]
    assert hero_class.tier == 1


def test_hero_campaign_state_round_trip_and_spawn_payload():
    original = build_initial_campaign_state("anna")
    original.level = 6
    original.exp = 42

    payload = hero_campaign_state_to_dict(original)
    restored = hero_campaign_state_from_dict(payload)
    spawn_payload = build_campaign_spawn_payload(restored)

    assert restored.hero_id == "anna"
    assert restored.level == 6
    assert restored.exp == 42
    assert spawn_payload["class_id"] == "healer"
    assert spawn_payload["base_stats"]["hp"] == original.base_stats["hp"]
