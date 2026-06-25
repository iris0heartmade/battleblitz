"""
Unit tests for `app.game_logic` — combat math, map gen, level-up, AI helpers.

Most of `game_logic` is pure (damage calc, map gen) so we can test without
a database. The DB-touching functions (apply_end_of_turn, ai_take_turn)
need an integration test instead — see `test_integration_smoke.py`.
"""
from __future__ import annotations

import random

import pytest

from app.config import (
    ARCHER_BASE_RANGE,
    CRIT_MULTIPLIER,
    DEFAULT_MELEE_RANGE,
    MAP_SIZE,
    MORALE_MAX,
    SKILL_DOUBLE_STRIKE,
    TERRAIN_CASTLE,
    TERRAIN_PLAIN,
    UNIT_ARCHER,
    UNIT_HEALER,
    UNIT_KNIGHT,
    UNIT_SWORDSMAN,
)
from app.game_logic import (
    HEAL_AMOUNT,
    _type_multiplier,
    apply_damage,
    attack_with_double_strike,
    award_morale,
    calculate_damage,
    castle_positions,
    generate_map,
    heal_adjacent_ally,
    unit_attack_range,
)
from app.models import Unit


# ============================================================
# Helpers to construct Unit stubs without touching the DB.
# ============================================================

def _stub_unit(
    unit_type: str = UNIT_SWORDSMAN,
    *,
    atk: int = 20,
    def_: int = 10,
    hp: int = 50,
    morale: int = 0,
    skills: list | None = None,
    x: int = 0,
    y: int = 0,
) -> Unit:
    """In-memory Unit row, never persisted. Note: `id` stays None."""
    return Unit(
        player_id=1,
        unit_type=unit_type,
        name="Stub",
        level=1,
        exp=0,
        hp=hp,
        max_hp=hp,
        atk=atk,
        def_=def_,
        mov=5,
        mp=5,
        morale=morale,
        x=x,
        y=y,
        has_acted=False,
        skills=skills or [],
    )


# ============================================================
# calculate_damage
# ============================================================

@pytest.mark.unit
class TestCalculateDamage:
    def test_kill_when_damage_exceeds_hp(self):
        atk = _stub_unit(atk=100)
        df = _stub_unit(hp=10)
        r = calculate_damage(atk, df, tile_def_bonus=0,
                             crit=False, rng=random.Random(0))
        assert r.is_kill is True
        assert r.damage >= 10

    def test_minimum_damage_is_one(self):
        # Pathological: attacker weaker than defender + huge terrain
        atk = _stub_unit(atk=1)
        df = _stub_unit(def_=1000, hp=9999)
        r = calculate_damage(atk, df, tile_def_bonus=100,
                             crit=False, rng=random.Random(0))
        assert r.damage >= 1

    def test_morale_scales_attack(self):
        # morale=0 vs morale=MORALE_MAX: damage should be larger with morale.
        df = _stub_unit(hp=200, def_=20)
        a0 = _stub_unit(atk=20, morale=0)
        a3 = _stub_unit(atk=20, morale=MORALE_MAX)
        r0 = calculate_damage(a0, df, 0, crit=False, rng=random.Random(1))
        r3 = calculate_damage(a3, df, 0, crit=False, rng=random.Random(1))
        assert r3.damage > r0.damage

    def test_terrain_bonus_increases_defense(self):
        atk = _stub_unit(atk=30)
        df = _stub_unit(hp=999, def_=10)
        r_plain = calculate_damage(atk, df, tile_def_bonus=0,
                                   crit=False, rng=random.Random(2))
        r_castle = calculate_damage(atk, df, tile_def_bonus=5,
                                    crit=False, rng=random.Random(2))
        # Higher effective defense → less damage
        assert r_castle.damage < r_plain.damage

    def test_crit_multiplies_damage(self):
        atk = _stub_unit(atk=30)
        df = _stub_unit(hp=999, def_=10)
        r_no = calculate_damage(atk, df, 0, crit=False, rng=random.Random(3))
        r_yes = calculate_damage(atk, df, 0, crit=True, rng=random.Random(3))
        # The crit multiplier is applied to the *base*, not the after-defence ratio.
        # We just check that crit is strictly greater.
        assert r_yes.damage > r_no.damage
        assert r_yes.is_crit is True
        assert r_no.is_crit is False


# ============================================================
# attack_with_double_strike
# ============================================================

@pytest.mark.unit
class TestDoubleStrike:
    def test_no_double_strike_returns_single_hit(self):
        atk = _stub_unit(atk=30, skills=[])
        df = _stub_unit(hp=999, def_=10)
        hits = attack_with_double_strike(atk, df, 0, rng=random.Random(0))
        assert len(hits) == 1

    def test_double_strike_returns_two_hits(self):
        atk = _stub_unit(atk=30, skills=[SKILL_DOUBLE_STRIKE])
        df = _stub_unit(hp=999, def_=10)
        hits = attack_with_double_strike(atk, df, 0, rng=random.Random(0))
        assert len(hits) == 2

    def test_double_strike_damage_is_half_per_hit(self):
        atk = _stub_unit(atk=30, skills=[SKILL_DOUBLE_STRIKE])
        df = _stub_unit(hp=999, def_=10)
        single = attack_with_double_strike(
            _stub_unit(atk=30, skills=[]), df, 0, rng=random.Random(0)
        )[0]
        double = attack_with_double_strike(atk, df, 0, rng=random.Random(0))
        # Each double-strike hit should be ~half of the single hit.
        for h in double:
            assert h.damage == max(1, single.damage // 2)


# ============================================================
# apply_damage
# ============================================================

@pytest.mark.unit
class TestApplyDamage:
    def test_subtracts_hp(self):
        u = _stub_unit(hp=50)
        killed = apply_damage(u, 20)
        assert u.hp == 30
        assert killed is False

    def test_kill_flag(self):
        u = _stub_unit(hp=50)
        killed = apply_damage(u, 100)
        assert u.hp == 0
        assert killed is True

    def test_clamps_at_zero(self):
        u = _stub_unit(hp=10)
        apply_damage(u, 999)
        assert u.hp == 0


# ============================================================
# award_morale
# ============================================================

@pytest.mark.unit
class TestAwardMorale:
    def test_increments(self):
        u = _stub_unit(morale=1)
        award_morale(u)
        assert u.morale == 2

    def test_caps_at_max(self):
        u = _stub_unit(morale=MORALE_MAX)
        award_morale(u)
        assert u.morale == MORALE_MAX


# ============================================================
# type advantage
# ============================================================

@pytest.mark.unit
class TestTypeAdvantage:
    def test_swordsman_beats_knight(self):
        assert _type_multiplier(_stub_unit(UNIT_SWORDSMAN),
                                _stub_unit(UNIT_KNIGHT)) == 1.20

    def test_knight_beats_archer(self):
        assert _type_multiplier(_stub_unit(UNIT_KNIGHT),
                                _stub_unit(UNIT_ARCHER)) == 1.20

    def test_no_advantage_between_non_matched(self):
        assert _type_multiplier(_stub_unit(UNIT_ARCHER),
                                _stub_unit(UNIT_SWORDSMAN)) == 1.0
        assert _type_multiplier(_stub_unit(UNIT_HEALER),
                                _stub_unit(UNIT_HEALER)) == 1.0


# ============================================================
# unit_attack_range
# ============================================================

@pytest.mark.unit
class TestAttackRange:
    def test_swordsman_is_melee(self):
        assert unit_attack_range(_stub_unit(UNIT_SWORDSMAN)) == DEFAULT_MELEE_RANGE

    def test_archer_default(self):
        assert unit_attack_range(_stub_unit(UNIT_ARCHER)) == ARCHER_BASE_RANGE

    def test_archer_with_snipe(self):
        u = _stub_unit(UNIT_ARCHER, skills=["snipe"])
        assert unit_attack_range(u) == ARCHER_BASE_RANGE + 1


# ============================================================
# heal_adjacent_ally
# ============================================================

@pytest.mark.unit
class TestHeal:
    def test_heals_adjacent(self):
        h = _stub_unit(UNIT_HEALER, skills=["heal"], x=0, y=0)
        a = _stub_unit(UNIT_SWORDSMAN, hp=20, x=1, y=0)  # adjacent
        # Same player_id is required by heal_adjacent_ally
        a.player_id = h.player_id
        # Make sure there's room to heal (max_hp > hp)
        a.max_hp = 50
        restored = heal_adjacent_ally(h, a)
        assert restored == HEAL_AMOUNT
        assert a.hp == 20 + HEAL_AMOUNT

    def test_no_heal_when_not_adjacent(self):
        h = _stub_unit(UNIT_HEALER, skills=["heal"], x=0, y=0)
        a = _stub_unit(UNIT_SWORDSMAN, hp=20, x=2, y=0)
        a.player_id = h.player_id
        a.max_hp = 50
        restored = heal_adjacent_ally(h, a)
        assert restored == 0
        assert a.hp == 20

    def test_no_heal_when_full_hp(self):
        h = _stub_unit(UNIT_HEALER, skills=["heal"], x=0, y=0)
        a = _stub_unit(UNIT_SWORDSMAN, hp=50, x=1, y=0)
        a.player_id = h.player_id
        a.max_hp = 50
        restored = heal_adjacent_ally(h, a)
        assert restored == 0

    def test_no_heal_when_other_player(self):
        h = _stub_unit(UNIT_HEALER, skills=["heal"], x=0, y=0)
        a = _stub_unit(UNIT_SWORDSMAN, hp=20, x=1, y=0)
        a.player_id = 99  # different from h.player_id=1
        a.max_hp = 50
        restored = heal_adjacent_ally(h, a)
        assert restored == 0

    def test_no_heal_without_skill(self):
        h = _stub_unit(UNIT_HEALER, skills=[], x=0, y=0)
        a = _stub_unit(UNIT_SWORDSMAN, hp=20, x=1, y=0)
        a.player_id = h.player_id
        a.max_hp = 50
        restored = heal_adjacent_ally(h, a)
        assert restored == 0


# ============================================================
# Map generation
# ============================================================

@pytest.mark.unit
class TestGenerateMap:
    def test_grid_size_is_correct(self):
        grid = generate_map(seed=42, num_castles=4)
        assert len(grid) == MAP_SIZE
        assert all(len(row) == MAP_SIZE for row in grid)

    def test_seed_is_deterministic(self):
        a = generate_map(seed=999, num_castles=2)
        b = generate_map(seed=999, num_castles=2)
        # Same seed → same terrain grid
        for y in range(MAP_SIZE):
            for x in range(MAP_SIZE):
                assert a[y][x].terrain == b[y][x].terrain

    def test_castle_count_matches_players(self):
        for n in (2, 3, 4):
            grid = generate_map(seed=1, num_castles=n)
            castles = sum(
                1 for row in grid for t in row if t.terrain == TERRAIN_CASTLE
            )
            assert castles == n, f"expected {n} castles, got {castles}"

    def test_invalid_castle_count_falls_back(self):
        grid = generate_map(seed=1, num_castles=99)
        castles = sum(
            1 for row in grid for t in row if t.terrain == TERRAIN_CASTLE
        )
        # Falls back to CASTLES_PER_GAME (= 4)
        assert castles == 4

    def test_castle_positions_helper(self):
        for n in (2, 3, 4):
            pos = castle_positions(n)
            assert len(pos) == n
            for seat, (x, y) in pos.items():
                assert 0 <= x < MAP_SIZE
                assert 0 <= y < MAP_SIZE
                assert seat < n
