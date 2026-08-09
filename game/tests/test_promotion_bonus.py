"""Unit tests for apply_promotion_bonus and the promotion-bonus pipeline."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.progression.leveling import apply_promotion_bonus


def _unit(**attrs):
    """Build a minimal unit-like object with the given stats."""
    # `def` is a Python keyword; SimpleNamespace(def=...) is a SyntaxError.
    # We use setattr() to bind it after construction.
    base = {
        "hp": 50, "atk": 20, "matk": 5, "mdef": 10, "mov": 6,
    }
    base.update(attrs)
    ns = SimpleNamespace(**base)
    if not hasattr(ns, "def"):
        setattr(ns, "def", 15)
    return ns


def test_apply_promotion_bonus_swordsman_adds_flat_bonus() -> None:
    # apply_promotion_bonus reads `getattr(unit, "def")` and writes
    # via `setattr`.  Python syntax doesn't allow `u.def = …` in source,
    # but `setattr(u, "def", v)` is legal — we use a tiny wrapper class
    # that initialises "def" via setattr.
    class _Unit:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
    u = _Unit(hp=50, atk=20, def_=15, matk=5, mdef=10, mov=6)
    # Bind the attribute "def" to the same slot the test set up.
    setattr(u, "def", u.def_)
    bonus = apply_promotion_bonus(u, "swordsman")
    assert bonus == {"hp": 3, "atk": 2, "def": 2, "matk": 0, "mdef": 3, "mov": 0}
    assert u.hp == 53
    assert u.atk == 22
    assert getattr(u, "def") == 17
    assert u.matk == 5
    assert u.mdef == 13
    assert u.mov == 6


def test_apply_promotion_bonus_tier2_class_no_op() -> None:
    u = _unit(hp=50, atk=20)
    before = (u.hp, u.atk)
    bonus = apply_promotion_bonus(u, "paladin")
    assert all(v == 0 for v in bonus.values())
    assert (u.hp, u.atk) == before


def test_apply_promotion_bonus_unknown_class_no_op() -> None:
    u = _unit()
    before_hp = u.hp
    bonus = apply_promotion_bonus(u, "knight")  # knight is tier-1
    # knight bonus is 3/2/2/0/3/1 — so HP DOES change.  Use an unknown
    # class for the no-op check.
    u2 = _unit()
    before_hp2 = u2.hp
    bonus2 = apply_promotion_bonus(u2, "totally_made_up_class")
    assert all(v == 0 for v in bonus2.values())
    assert u2.hp == before_hp2


def test_apply_promotion_bonus_skips_missing_attrs() -> None:
    """Units without the stat attribute are silently skipped (legacy safety)."""
    u = SimpleNamespace(hp=50, atk=20)  # no def/matk/mdef/mov
    bonus = apply_promotion_bonus(u, "swordsman")
    # hp and atk are still applied.
    assert u.hp == 53
    assert u.atk == 22
    assert bonus == {"hp": 3, "atk": 2, "def": 2, "matk": 0, "mdef": 3, "mov": 0}
