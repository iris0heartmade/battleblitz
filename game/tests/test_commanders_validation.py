"""L2 — pure-function tests for `validate_center_xy`.

The route layer turns the `CenterOutOfBounds` into an HTTP 400; these tests
pin the boundary contract so a future refactor of the route doesn't silently
drop the check.
"""
from __future__ import annotations

import pytest

from app.commanders.validation import (
    CenterOutOfBounds,
    validate_center_xy,
)


# Standard 15x15 grid used by every test preset; we also test 5x5 to confirm
# the helper isn't accidentally hard-coded to MAP_SIZE.
MAP_15 = 15
MAP_5 = 5


class TestValidateCenterXy:
    def test_none_passes_through(self):
        """Stat-only CO powers (anna / yun) send no center — must be allowed."""
        assert validate_center_xy(None, map_size=MAP_15) is None

    @pytest.mark.parametrize(
        "xy",
        [(0, 0), (7, 7), (14, 14), (0, 14), (14, 0), (1, 13)],
    )
    def test_in_bounds_returns_tuple_unchanged(self, xy):
        result = validate_center_xy(xy, map_size=MAP_15)
        assert result == xy

    @pytest.mark.parametrize(
        "xy",
        [
            (-1, 0),         # x < 0
            (0, -1),         # y < 0
            (15, 0),         # x == map_size  (off-by-one trap)
            (0, 15),         # y == map_size
            (15, 15),        # both == map_size
            (100, 100),      # far OOB
            (-100, -100),    # far negative
        ],
    )
    def test_out_of_bounds_raises(self, xy):
        with pytest.raises(CenterOutOfBounds) as exc_info:
            validate_center_xy(xy, map_size=MAP_15)
        # Error message should be debuggable — include the bad coords and
        # the map size so logs / 400 responses aren't cryptic.
        msg = str(exc_info.value)
        assert str(xy[0]) in msg
        assert str(xy[1]) in msg
        assert str(MAP_15) in msg

    def test_non_tuple_raises(self):
        with pytest.raises(CenterOutOfBounds):
            validate_center_xy([3, 3], map_size=MAP_15)  # type: ignore[arg-type]

    def test_wrong_length_raises(self):
        with pytest.raises(CenterOutOfBounds):
            validate_center_xy((3,), map_size=MAP_15)  # type: ignore[arg-type]

    def test_helper_uses_injected_map_size(self):
        """MAP_SIZE is read by the caller; helper must respect what it gets,
        not hard-code 15. (3, 3) is in bounds on 15x15 but OOB on 5x5."""
        # On 15x15, (3, 3) is well inside — must pass.
        assert validate_center_xy((3, 3), map_size=MAP_15) == (3, 3)
        # On 5x5, the SAME (3, 3) is still in bounds (4 < 5), so pass too.
        assert validate_center_xy((3, 3), map_size=MAP_5) == (3, 3)
        # But (4, 4) is OOB on 5x5 (must be < 5).
        with pytest.raises(CenterOutOfBounds):
            validate_center_xy((5, 5), map_size=MAP_5)
        # And in bounds on 15x15.
        assert validate_center_xy((5, 5), map_size=MAP_15) == (5, 5)

    def test_center_out_of_bounds_is_value_error_subclass(self):
        """Route catches `except ValueError` broadly; make sure our subclass
        doesn't accidentally bypass that."""
        assert issubclass(CenterOutOfBounds, ValueError)
        with pytest.raises(ValueError):
            validate_center_xy((-1, -1), map_size=MAP_15)
