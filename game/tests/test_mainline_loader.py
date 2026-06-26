"""
Unit tests for app.mainline.loader.

These are pure-stdlib tests — no DB, no FastAPI, no network. They
verify:
  * Happy-path loading of the sample mainline
  * In-process caching
  * Missing-file -> MainlineNotFound
  * Schema validation errors -> MainlineValidationError
  * list_mainlines() skips invalid files but lists valid ones
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.mainline import (
    MainlineNotFound,
    MainlineValidationError,
    clear_cache,
    list_mainlines,
    load_mainline,
)
from app.mainline.loader import mainlines_dir


SAMPLE_ID = "chapter_01_steel_rebellion"


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def _reset_cache():
    """Each test starts with a clean loader cache."""
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def tmp_mainlines(tmp_path, monkeypatch):
    """Redirect the loader's mainlines_dir to a tmp directory.

    Returns the tmp Path so individual tests can drop JSON files.
    """
    import app.mainline.loader as loader_mod

    monkeypatch.setattr(loader_mod, "_MAINLINES_DIR", tmp_path)
    return tmp_path


# ============================================================
# Happy path — uses the real file shipped in repo
# ============================================================

class TestLoadSample:
    def test_mainlines_dir_exists(self):
        d = mainlines_dir()
        assert d.exists(), f"mainlines dir missing: {d}"
        assert d.is_dir()

    def test_load_chapter_01(self):
        m = load_mainline(SAMPLE_ID)
        assert m.id == SAMPLE_ID
        assert m.title == "钢铁起义"
        assert m.battle_count == 0  # not on Mainline; check below

    def test_battles_have_expected_shape(self):
        m = load_mainline(SAMPLE_ID)
        assert len(m.battles) == 2
        b1, b2 = m.battles
        assert b1.id == "battle_01"
        assert b1.map_preset == "mountain_pass"
        assert b1.win_condition == "rout"
        assert b1.ally_composition == {"swordsman": 3, "archer": 1}
        assert b1.enemy_composition == {"knight": 4}
        assert b1.pre_battle_dialogue == "intro"
        assert b1.post_battle_dialogue == "battle_01_after"
        assert b2.pre_battle_dialogue is None
        assert b2.win_condition == "seize"

    def test_starting_units_and_required_classes(self):
        m = load_mainline(SAMPLE_ID)
        assert m.required_classes == ["swordsman", "archer"]
        assert len(m.starting_units) == 2
        assert m.starting_units[0].class_id == "swordsman"
        assert m.starting_units[0].name == "云"

    def test_rewards_on_clear(self):
        m = load_mainline(SAMPLE_ID)
        assert m.rewards_on_clear.gold == 500
        assert m.rewards_on_clear.unlock_class == "knight"
        assert m.rewards_on_clear.exp_per_unit == 120

    def test_dialogue_keys_resolve(self):
        m = load_mainline(SAMPLE_ID)
        assert "intro" in m.dialogues
        assert m.dialogues["intro"].endswith("intro.json")


# ============================================================
# Caching
# ============================================================

class TestCache:
    def test_cache_returns_same_object(self):
        a = load_mainline(SAMPLE_ID)
        b = load_mainline(SAMPLE_ID)
        assert a is b

    def test_clear_cache_forces_reload(self, tmp_mainlines):
        # First, write a custom file
        (tmp_mainlines / "tmp_mainline.json").write_text(json.dumps({
            "id": "tmp_mainline",
            "title": "Tmp",
            "required_classes": ["swordsman"],
            "starting_units": [{"class_id": "swordsman"}],
            "battles": [{
                "id": "b1",
                "title": "B1",
                "map_preset": "classic",
                "ally_composition": {"swordsman": 1},
                "enemy_composition": {"knight": 1},
            }],
        }), encoding="utf-8")
        m = load_mainline("tmp_mainline")
        assert m.title == "Tmp"

        # Mutate file on disk; cache should still serve the old version
        (tmp_mainlines / "tmp_mainline.json").write_text(json.dumps({
            "id": "tmp_mainline",
            "title": "Tmp v2",
            "required_classes": ["swordsman"],
            "starting_units": [{"class_id": "swordsman"}],
            "battles": [{
                "id": "b1",
                "title": "B1",
                "map_preset": "classic",
                "ally_composition": {"swordsman": 1},
                "enemy_composition": {"knight": 1},
            }],
        }), encoding="utf-8")
        cached = load_mainline("tmp_mainline")
        assert cached.title == "Tmp"  # cache hit

        clear_cache()
        fresh = load_mainline("tmp_mainline")
        assert fresh.title == "Tmp v2"


# ============================================================
# Error paths
# ============================================================

class TestErrors:
    def test_missing_raises_not_found(self, tmp_mainlines):
        # tmp_mainlines is empty
        with pytest.raises(MainlineNotFound):
            load_mainline("does_not_exist")

    def test_unknown_class_id_raises_validation(self, tmp_mainlines):
        (tmp_mainlines / "bad.json").write_text(json.dumps({
            "id": "bad",
            "title": "Bad",
            "required_classes": ["wizard"],  # not in VALID_CLASS_IDS
            "starting_units": [{"class_id": "swordsman"}],
            "battles": [{
                "id": "b1",
                "title": "B1",
                "map_preset": "classic",
                "ally_composition": {"swordsman": 1},
                "enemy_composition": {"knight": 1},
            }],
        }), encoding="utf-8")
        with pytest.raises(MainlineValidationError) as ei:
            load_mainline("bad")
        assert ei.value.mainline_id == "bad"

    def test_dangling_dialogue_reference_raises(self, tmp_mainlines):
        (tmp_mainlines / "dangling.json").write_text(json.dumps({
            "id": "dangling",
            "title": "D",
            "required_classes": ["swordsman"],
            "starting_units": [{"class_id": "swordsman"}],
            "dialogues": {"intro": "stories/x.json"},
            "battles": [{
                "id": "b1",
                "title": "B1",
                "map_preset": "classic",
                "ally_composition": {"swordsman": 1},
                "enemy_composition": {"knight": 1},
                "pre_battle_dialogue": "missing_key",  # not in dialogues
            }],
        }), encoding="utf-8")
        with pytest.raises(MainlineValidationError):
            load_mainline("dangling")

    def test_duplicate_battle_ids_raises(self, tmp_mainlines):
        (tmp_mainlines / "dup.json").write_text(json.dumps({
            "id": "dup",
            "title": "D",
            "required_classes": ["swordsman"],
            "starting_units": [{"class_id": "swordsman"}],
            "battles": [
                {"id": "b1", "title": "B1", "map_preset": "classic",
                 "ally_composition": {"swordsman": 1}, "enemy_composition": {"knight": 1}},
                {"id": "b1", "title": "B1 dup", "map_preset": "classic",
                 "ally_composition": {"swordsman": 1}, "enemy_composition": {"knight": 1}},
            ],
        }), encoding="utf-8")
        with pytest.raises(MainlineValidationError):
            load_mainline("dup")

    def test_invalid_json_raises_mainline_error(self, tmp_mainlines):
        (tmp_mainlines / "broken.json").write_text("{not json", encoding="utf-8")
        from app.mainline.loader import MainlineError
        with pytest.raises(MainlineError):
            load_mainline("broken")


# ============================================================
# list_mainlines
# ============================================================

class TestList:
    def test_list_includes_sample(self):
        items = list_mainlines()
        ids = [m.id for m in items]
        assert SAMPLE_ID in ids

    def test_list_summaries_have_battle_count(self):
        items = list_mainlines()
        for m in items:
            assert isinstance(m.battle_count, int)
            assert m.battle_count >= 1

    def test_list_skips_invalid_files(self, tmp_mainlines):
        # Real sample still loads (file unchanged in repo)
        # Plus one invalid file we just dropped
        (tmp_mainlines / "invalid.json").write_text(json.dumps({
            "id": "invalid",
            "title": "I",
            # missing required_classes, starting_units, battles -> invalid
        }), encoding="utf-8")
        items = list_mainlines()
        ids = [m.id for m in items]
        # invalid.json should be silently skipped
        assert "invalid" not in ids
