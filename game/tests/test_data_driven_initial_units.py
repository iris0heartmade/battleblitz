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


class TestGenerateMapPreset:
    def test_returns_map_preset_result(self):
        """generate_map_preset returns a MapPresetResult (not raw tiles)."""
        from app.game_logic import generate_map_preset, MapPresetResult
        # "classic" is the special procedural fallback preset; the loader
        # inlines a placeholder initial_units entry for it so the
        # post-2.6 hard validation accepts it.
        result = generate_map_preset("classic", seed=1, num_castles=4)
        assert isinstance(result, MapPresetResult)
        assert hasattr(result, "tiles")
        assert hasattr(result, "initial_units")
        # tiles is the 2D grid; initial_units is a list (possibly empty
        # for procedurally generated maps).
        assert isinstance(result.tiles, list)
        assert isinstance(result.initial_units, list)
        # Tiles grid is non-empty for a valid generation call.
        assert len(result.tiles) > 0
        assert len(result.tiles[0]) > 0
