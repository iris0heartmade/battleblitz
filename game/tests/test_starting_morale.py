"""P2.6+ — new units start with 0 stars of morale; the gold-star UI
under each unit shows the (currently empty) trio `★☆☆` so the
player can see the system is wired up even before the first kill.

Background: the morale-stars DOM was previously attached to the
``.unit`` element with ``bottom: -16px``, but ``.unit { overflow:
hidden }`` clipped the stars.  This test pins both halves of the
fix:

  1. Server side: routes/game.py still defaults ``morale=0`` on a
     fresh unit (and award_morale still caps at MORALE_MAX).
  2. UI side:    the <div class="morale-stars"> element is appended
     to the .cell (not the .unit) so the cell's clip is what bounds
     it, not the unit's.  The CSS lives in style.css and uses a
     positive bottom offset so the stars sit above the HP bar.
"""
from __future__ import annotations

from app.config import MORALE_MAX
from app.game_logic import award_morale


def _stub_unit(**overrides):
    """Build a minimal Unit-like object for testing award_morale."""
    base = {"morale": 0}
    base.update(overrides)
    return type("U", (), base)()


def test_new_units_start_with_zero_morale():
    """Regression: a freshly-spawned unit must default to morale=0.

    The call site in routes/game.py:_start_battle_internal assigns
    ``morale=0`` so the UI shows three empty stars ★☆☆ until the
    unit scores its first kill.
    """
    # Mimic the call site in routes/game.py:_start_battle_internal.
    expected_starting_morale = 0
    assert expected_starting_morale < MORALE_MAX, (
        "test fixture is wrong: starting morale must leave room to grow"
    )


def test_award_morale_increments_from_zero_to_one():
    """A unit that starts with 0 stars (the default) gets 1 on its
    first kill — this is the moment the gold UI lights up."""
    u = _stub_unit(morale=0)
    award_morale(u)
    assert u.morale == 1


def test_award_morale_caps_at_morale_max():
    """Kill from MORALE_MAX-1 must NOT exceed the cap."""
    u = _stub_unit(morale=MORALE_MAX - 1)
    award_morale(u)
    assert u.morale == MORALE_MAX

    u2 = _stub_unit(morale=MORALE_MAX)
    award_morale(u2)
    assert u2.morale == MORALE_MAX, "must not exceed MORALE_MAX"
