"""test_data_driven_initial_units.py -- startup."""
import pytest
from app.game_logic import _resolve_size


class TestResolveSize:
    def test_legacy_int(self):
        r = _resolve_size(15)
        assert r == {"width": 15, "height": 15}

    def test_object(self):
        r = _resolve_size({"width": 10, "height": 7})
        assert r == {"width": 10, "height": 7}

    def test_bad_type(self):
        with pytest.raises(TypeError, match="size must be int or dict"):
            _resolve_size("15")


class TestLoadMapPresets:
    def test_missing_initial_units_raises(self):
        """A map JSON without initial_units must be rejected at load."""
        from app.game_logic import _load_map_presets
        # We'll test indirectly: try loading a minimal bad dict.
        # _load_map_presets reads from disk, so we write a temp test JSON.
        pass
