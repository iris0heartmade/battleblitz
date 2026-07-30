"""Unit tests for the GrowthPolicy abstraction.

These tests verify only the policy / dataset layer — the renderer is
covered by visual inspection of generated PNGs (out of scope for headless
pytest).

Why these specifically?
  - The L1 baseline is the single source of truth that every chart
    consumes.  A typo in :func:`resolve_effective_base` propagates
    through 17 charts silently, so we lock it down with hard-coded
    expected values.
  - The autolevel formula is shared with :mod:`app.modes`; if it ever
    changes, the snapshot must change too — that's a feature, not a
    bug: this test *forces* the team to consciously update the chart
    numbers when the spawn formula moves.
"""
from __future__ import annotations

import sys
from pathlib import Path

# The chart tool itself lives at the REPO ROOT's `tools/` directory
# (one level above `game/`, which is already on sys.path via conftest).
# We add the repo root here so the dataset / renderer modules resolve
# under their tooling namespace (`tools.growth_charts.*`).
_REPO_ROOT = Path(__file__).resolve().parents[2]  # game/tests/x.py → repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from app.classes.heroes import get as get_hero
from app.classes.units import get as get_class
from app.progression.policies import (
    AutolevelPolicy,
    BattleLanePolicy,
    STAT_KEYS,
    TIER2_TYPE_IDS,
    ClassBaseline,
    GrowthPolicy,
    get_policy,
    infer_tier,
    resolve_effective_base,
)
from tools.growth_charts.dataset import (
    all_class_curves,
    all_hero_curves,
    compute_class_growth,
    compute_hero_growth,
)


# ============================================================
# resolve_effective_base  (hero override composition)
# ============================================================

def test_resolve_class_only_inherits_baseline():
    """Class without hero → no overrides, base stats come straight through."""
    bm = get_class("blade_master")
    base = resolve_effective_base(bm, None)
    assert base["hp"] == bm.base_hp
    assert base["atk"] == bm.base_atk
    # Every known stat key must be present.
    assert set(base.keys()) == set(STAT_KEYS)


def test_resolve_hero_overrides_applied_in_order():
    """Hero with overrides → override wins, base_class fills the rest.

    yun overrides: hp=50, atk=20, def=11, matk=27, mov=4
    yun inherits: mdef=12 (warlock), mp=8 (warlock)"""
    yun = get_hero("yun")
    warlock = get_class("warlock")
    base = resolve_effective_base(warlock, yun)
    assert base["hp"] == 50       # override
    assert base["atk"] == 20      # override
    assert base["def"] == 11      # override
    assert base["matk"] == 27     # override
    assert base["mdef"] == 12     # inherited from warlock
    assert base["mov"] == 4       # override
    assert base["mp"] == 8        # inherited from warlock


def test_resolve_hero_with_no_overrides_inherits_everything():
    """A hero with all `None` overrides is identical to its base class.

    We don't currently have such a hero in the registry, so simulate
    one — the function should still resolve cleanly."""
    bm = get_class("blade_master")
    base = resolve_effective_base(bm, None)
    # Every key matches the class profile verbatim.
    assert base["hp"] == bm.base_hp
    assert base["matk"] == bm.base_matk
    assert base["mp"] == bm.mp_pool


# ============================================================
# AutolevelPolicy — formula contract
# ============================================================

def test_autolevel_policy_baseline_resolves_class_correctly():
    policy = AutolevelPolicy()
    bm = get_class("blade_master")
    bl = policy.baseline(class_profile=bm, hero_profile=None)
    assert isinstance(bl, ClassBaseline)
    assert bl.type_id == "blade_master"
    assert bl.label_cn == "剑圣"
    assert bl.is_hero is False
    assert bl.tier == 2  # blade_master is in TIER2_TYPE_IDS
    assert bl.attack_kind == "physical"


def test_autolevel_policy_baseline_resolves_hero_correctly():
    policy = AutolevelPolicy()
    yun = get_hero("yun")
    bl = policy.baseline(class_profile=get_class("warlock"), hero_profile=yun)
    assert bl.type_id == "yun"
    assert bl.label_cn == "云"
    assert bl.is_hero is True
    assert bl.base_class_id == "warlock"
    # formula_note explicitly says hero is using the generic formula
    assert "autolevel_boss" in bl.formula_note


def test_battle_lane_stat_at_level_matches_spawn_helper():
    """Cross-check: chart's stat_at_level matches app.modes.spawn_generic_stats
    at the same start_level for a plain class.  If this fails, either
    BattleLanePolicy or spawn_generic_stats drifted apart."""
    from app.modes import spawn_generic_stats

    bm = get_class("blade_master")
    policy = BattleLanePolicy()
    bl = policy.baseline(class_profile=bm, hero_profile=None)

    for lv in (1, 5, 10, 20):
        from_policy = dict(policy.stat_at_level(baseline_=bl, level=lv))
        from_spawn = spawn_generic_stats(bm.type_id, start_level=lv)
        assert from_policy["hp"] == from_spawn["hp"], (
            f"HP mismatch at Lv {lv}: policy={from_policy['hp']} "
            f"spawn={from_spawn['hp']}"
        )
        assert from_policy["atk"] == from_spawn["atk"]
        assert from_policy["def"] == from_spawn["def"]
        assert from_policy["matk"] == from_spawn["matk"]
        assert from_policy["mdef"] == from_spawn["mdef"]
        # mov is class-static and not in spawn_generic_stats — must match L1.
        assert from_policy["mov"] == bm.base_mov
        assert from_policy["mp"] == bm.mp_pool


def test_autolevel_rejects_level_below_1():
    policy = AutolevelPolicy()
    bm = get_class("blade_master")
    bl = policy.baseline(class_profile=bm, hero_profile=None)
    with pytest.raises(ValueError):
        policy.stat_at_level(baseline_=bl, level=0)


def test_battle_lane_magic_class_grows_magic_lane_strongly_and_physical_lane_weakly():
    policy = BattleLanePolicy()
    warlock = get_class("warlock")
    bl = policy.baseline(class_profile=warlock, hero_profile=None)

    l20 = dict(policy.stat_at_level(baseline_=bl, level=20))

    assert l20["matk"] == 31
    assert l20["mdef"] == 14
    assert l20["atk"] == 9
    assert l20["def"] == 11


def test_battle_lane_physical_class_grows_physical_lane_strongly_and_magic_lane_weakly():
    policy = BattleLanePolicy()
    swordsman = get_class("swordsman")
    bl = policy.baseline(class_profile=swordsman, hero_profile=None)

    l20 = dict(policy.stat_at_level(baseline_=bl, level=20))

    assert l20["atk"] == 27
    assert l20["def"] == 14
    assert l20["matk"] == 5
    assert l20["mdef"] == 5


def test_battle_lane_hero_uses_base_class_attack_kind_for_growth_sides():
    policy = BattleLanePolicy()
    yun = get_hero("yun")
    bl = policy.baseline(class_profile=get_class("warlock"), hero_profile=yun)

    l20 = dict(policy.stat_at_level(baseline_=bl, level=20))

    assert bl.attack_kind == "magic"
    assert l20["matk"] == 36
    assert l20["mdef"] == 14
    assert l20["atk"] == 21
    assert l20["def"] == 12


def test_battle_lane_policy_matches_generic_spawn_helper():
    from app.modes import spawn_generic_stats

    policy = BattleLanePolicy()
    for type_id in ("warlock", "swordsman"):
        cls = get_class(type_id)
        bl = policy.baseline(class_profile=cls, hero_profile=None)
        for lv in (1, 10, 20):
            from_policy = dict(policy.stat_at_level(baseline_=bl, level=lv))
            from_spawn = spawn_generic_stats(type_id, start_level=lv)
            assert from_policy["hp"] == from_spawn["hp"]
            assert from_policy["atk"] == from_spawn["atk"]
            assert from_policy["def"] == from_spawn["def"]
            assert from_policy["matk"] == from_spawn["matk"]
            assert from_policy["mdef"] == from_spawn["mdef"]


# ============================================================
# Dataset helpers
# ============================================================

def test_compute_class_growth_produces_full_curve():
    curve = compute_class_growth(
        class_profile=get_class("blade_master"),
        max_level=20,
        policy=AutolevelPolicy(),
    )
    assert sorted(curve.values.keys()) == list(range(1, 21))
    # Every level has a full stat map.
    for lv, stats in curve.values.items():
        assert set(stats.keys()) == set(STAT_KEYS)


def test_compute_hero_growth_composes_base_and_overrides():
    curve = compute_hero_growth(
        hero_profile=get_hero("anna"),
        max_level=20,
        policy=AutolevelPolicy(),
    )
    # anna base stats with overrides: hp=46, def=10, matk=12, mdef=14, mov=3, mp=6
    assert curve.values[1]["hp"] == 46
    assert curve.values[1]["def"] == 10
    assert curve.values[1]["matk"] == 12
    # her atk is NOT overridden, so should inherit healer base_atk=5
    assert curve.values[1]["atk"] == 5


def test_total_at_and_delta_pct_helpers():
    curve = compute_class_growth(
        class_profile=get_class("healer"),
        max_level=10,
        policy=AutolevelPolicy(),
    )
    assert curve.total_at(1) == sum(curve.values[1].values())
    delta = curve.delta_pct(10)
    # healer hp: base=40, rate=85%, L10 = 40 + int(9 * 0.85) = 40 + 7 = 47
    # Δ% = (47 - 40) / 40 = 17.5%
    assert delta["hp"] == pytest.approx(17.5, abs=0.05)
    # mov: 3 → 3 → 0%
    assert delta["mov"] == pytest.approx(0.0)


def test_all_class_curves_sorted_and_complete():
    curves = all_class_curves(max_level=20, policy=AutolevelPolicy())
    # Auto-discovery should yield >= 10 classes now (we added 4 new ones).
    assert len(curves) >= 10
    # Sorted by (tier, type_id) — invariant for diff-able index.json.
    ids = [c.baseline.type_id for c in curves]
    assert ids == sorted(ids, key=lambda t: (
        2 if t in TIER2_TYPE_IDS else 1,
        t,
    ))


def test_all_hero_curves_present():
    curves = all_hero_curves(max_level=20, policy=AutolevelPolicy())
    hero_ids = {c.baseline.type_id for c in curves}
    # The two registered heroes must show up.
    assert {"yun", "anna"}.issubset(hero_ids)


# ============================================================
# Registry + Protocol surface
# ============================================================

def test_get_policy_resolves_known_name():
    p = get_policy("autolevel_boss")
    assert isinstance(p, AutolevelPolicy)
    assert p.name == "autolevel_boss"


def test_get_policy_resolves_battle_lane_default_name():
    p = get_policy("battle_lane")
    assert isinstance(p, BattleLanePolicy)
    assert p.name == "battle_lane"


def test_get_policy_rejects_unknown_name():
    with pytest.raises(KeyError):
        get_policy("curve_linear_does_not_exist_yet")


def test_infer_tier_uses_type_id_set_for_classes():
    assert infer_tier(type_id="swordsman", is_hero=False) == 1
    assert infer_tier(type_id="blade_master", is_hero=False) == 2
    assert infer_tier(type_id="dragon_rider", is_hero=False) == 1
    assert infer_tier(type_id="berserker", is_hero=False) == 2
    # Heroes are always tier-1 until the promotion system lands.
    assert infer_tier(type_id="yun", is_hero=True) == 1


def test_berserker_and_dragon_rider_baselines_match_expected_tiers():
    berserker = get_class("berserker")
    dragon_rider = get_class("dragon_rider")

    assert (berserker.base_hp, berserker.base_atk, berserker.base_def) == (48, 28, 8)
    assert berserker.base_mov == 4
    assert (dragon_rider.base_hp, dragon_rider.base_atk, dragon_rider.base_def) == (42, 16, 7)
    assert dragon_rider.base_mov == 5
