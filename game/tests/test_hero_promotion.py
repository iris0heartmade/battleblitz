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
    # yun 重做成纯法师后 mp=4,sage 转职加成 +2 → 6(MOV/MP 合并后 mp 是"当前移动力池")
    assert promoted.base_stats["mp"] == 6


def test_promote_hero_rejects_invalid_target():
    state = build_initial_campaign_state("anna")
    state.level = 20

    with pytest.raises(ValueError):
        promote_hero(
            state,
            build_hero_class_template("healer"),
            build_hero_class_template("sage"),
        )


def test_legacy_bridge_fallback_drops_plus_eight_mp():
    """Spec §9 step 12: drop the `+8 mp` legacy fallback in
    build_hero_class_template.  Classes NOT in the explicit
    _HERO_CLASS_SPECS table (e.g. `bard`, `warrior`, `dragon_rider`)
    fall through to the inline caps builder, which must NOT
    synthesize an "mp" key from `base_mov + 8`.  Caps are an
    upper-bound surface; an unwanted `mp` here would let
    promote_hero silently cap (or grow) the hero campaign mp.

    Regression guard: if the `+8 mp` branch sneaks back in,
    `t.caps` will contain "mp" and this test will fail.
    """
    for fallback_class in ("bard", "warrior", "dragon_rider", "falcon_knight"):
        t = build_hero_class_template(fallback_class)
        assert "mp" not in t.caps, (
            f"legacy '+8 mp' fallback re-emerged for {fallback_class!r}: "
            f"caps={t.caps!r}"
        )
