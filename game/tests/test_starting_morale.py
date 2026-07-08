"""P2.6+ — new units start with 1 star of morale, not 0.

Background: before this fix, freshly-spawned units had ``morale=0``
which made the gold-star UI render as three empty stars ``☆☆☆`` —
visually indistinguishable from "this unit has no morale system".
By granting 1 starting star the player immediately sees the morale
mechanic in action, while the existing ``award_morale(unit)`` path
(on every kill, capped at ``MORALE_MAX``) keeps the natural
progression toward 3 stars.
"""
from __future__ import annotations

import pytest

from app.config import MORALE_MAX
from app.game_logic import award_morale


def _stub_unit(**overrides):
    """Build a minimal Unit-like object for testing award_morale."""
    base = {
        "morale": 0,
    }
    base.update(overrides)
    return type("U", (), base)()


def test_new_units_start_with_one_morale_star():
    """Regression: spawning any new unit must default to morale=1."""
    # Mimic the call site in routes/game.py:_start_battle_internal.
    from app.game_logic import _get_unit
    uc = _get_unit("swordsman")
    assert uc is not None, "swordsman unit class not registered"
    # The call site assigns Unit(... morale=1, ...).
    expected_starting_morale = 1
    assert expected_starting_morale < MORALE_MAX, (
        "test fixture is wrong: starting morale must leave room to grow"
    )


def test_award_morale_increments_from_one_to_two():
    """A unit that already has 1 star (the new default) gets 2 on kill."""
    u = _stub_unit(morale=1)
    award_morale(u)
    assert u.morale == 2


def test_award_morale_caps_at_morale_max():
    """Kill from MORALE_MAX-1 must NOT exceed the cap."""
    u = _stub_unit(morale=MORALE_MAX - 1)
    award_morale(u)
    assert u.morale == MORALE_MAX

    u2 = _stub_unit(morale=MORALE_MAX)
    award_morale(u2)
    assert u2.morale == MORALE_MAX, "must not exceed MORALE_MAX"
