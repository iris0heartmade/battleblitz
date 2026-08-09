"""Unit tests for spawn_generic_stats deterministic rolling under growth_seed."""
from __future__ import annotations

from app.modes import spawn_generic_stats


def test_spawn_l1_returns_class_base() -> None:
    stats = spawn_generic_stats("swordsman", start_level=1)
    assert stats == {
        "hp": 45, "atk": 18, "def": 12, "matk": 4, "mdef": 4,
        "mov": 5, "attack_range": 1,
    }


def test_spawn_with_same_seed_is_deterministic() -> None:
    a = spawn_generic_stats("warlock", start_level=10, growth_seed=42)
    b = spawn_generic_stats("warlock", start_level=10, growth_seed=42)
    assert a == b


def test_spawn_with_different_seeds_diverges() -> None:
    a = spawn_generic_stats("warlock", start_level=10, growth_seed=1)
    b = spawn_generic_stats("warlock", start_level=10, growth_seed=2)
    # Both will roll >0 for some stat; the deltas should differ.
    assert a != b


def test_spawn_growth_seed_drives_rng_directly() -> None:
    """The same seed gives the same result whether via growth_seed or via rng injection."""
    import random
    from app.modes import spawn_generic_stats
    a = spawn_generic_stats("swordsman", start_level=15, growth_seed=99)
    rng = random.Random(99)
    b = spawn_generic_stats("swordsman", start_level=15, rng=rng)
    assert a == b


def test_spawn_at_higher_level_grows_some_stats() -> None:
    """Going from L1 to L10, at least one stat should grow for most classes."""
    l1 = spawn_generic_stats("knight", start_level=1, growth_seed=7)
    l10 = spawn_generic_stats("knight", start_level=10, growth_seed=7)
    grown = sum(1 for k in ("hp", "atk", "def", "matk", "mdef") if l10[k] > l1[k])
    # Knight: hp 80, atk 45, def 35 — all ≥35% — over 9 rolls, at
    # least one of these will almost surely hit.  Allow a 1/100 flake.
    assert grown >= 1, f"L10 - L1 deltas: {l1} -> {l10}"


def test_spawn_caps_respected() -> None:
    """After 100 level-ups, no stat exceeds STAT_CAPS."""
    from app.progression.policies import STAT_CAPS
    s = spawn_generic_stats("berserker", start_level=100, growth_seed=1234)
    for k, cap in STAT_CAPS.items():
        if k == "mov":
            continue  # mov growth is 0 for most classes
        assert s[k] <= cap, f"{k} = {s[k]} > cap {cap}"
