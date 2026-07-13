from __future__ import annotations

import pytest

from app.hero_domain import (
    build_hero_character_template,
    build_hero_class_template,
    build_initial_campaign_state,
    can_promote_hero,
    promote_hero,
)


def test_legacy_bridge_exposes_promotion_routes():
    char = build_hero_character_template("yun")
    hero_class = build_hero_class_template("warlock")

    assert char.promotion_routes == ["sage"]
    assert hero_class.promotion_options == ["sage"]


def test_promote_hero_applies_bonus_and_resets_level():
    state = build_initial_campaign_state("yun")
    state.level = 20
    state.exp = 88

    promoted = promote_hero(
        state,
        build_hero_class_template("warlock"),
        build_hero_class_template("sage"),
    )

    assert can_promote_hero(state, build_hero_class_template("warlock")) is True
    assert promoted.class_id == "sage"
    assert promoted.level == 1
    assert promoted.exp == 0
    assert promoted.promoted is True
    assert promoted.base_stats["hp"] == 54
    assert promoted.base_stats["matk"] == 31
    assert promoted.base_stats["mdef"] == 16
    assert promoted.base_stats["mov"] == 5
    assert promoted.base_stats["mp"] == 10


def test_promote_hero_rejects_invalid_target():
    state = build_initial_campaign_state("anna")
    state.level = 20

    with pytest.raises(ValueError):
        promote_hero(
            state,
            build_hero_class_template("healer"),
            build_hero_class_template("sage"),
        )
