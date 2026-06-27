"""
Unit tests for ``app.mainline.engine.MainlineEngine``.

These cover the *pure* side of the engine — state derivation,
``next_step()`` logic, and Game-name naming convention — without
spinning up the FastAPI app or DB.  DB-coupled paths (spawn / apply_victory)
are exercised in ``test_mainline_api.py``.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.mainline.engine import (
    MainlineEngine,
    MainlineState,
    mainline_game_name,
    parse_mainline_game_name,
)
from app.mainline.loader import load_mainline, clear_cache
from app.mainline.schemas import BattleSpec, MainlineRewards


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def sample_mainline():
    return load_mainline("chapter_01_steel_rebellion")


def _profile(
    *,
    active_mainline=None,
    battle_index=0,
    scene_id="intro",
    started_at=None,
    user_name="alice",
    unlocked=None,
    gold=0,
):
    """Build a duck-typed profile-like object for engine tests.

    Avoids needing a real DB session — the engine only reads attributes
    via ``getattr``.
    """
    return SimpleNamespace(
        user_name=user_name,
        active_mainline=active_mainline,
        mainline_progress={
            "battle_index": battle_index,
            "scene_id": scene_id,
            "started_at": started_at,
        },
        unlocked_classes=unlocked if unlocked is not None
            else ["swordsman", "archer", "knight", "healer"],
        gold=gold,
        units=[],
    )


# ============================================================
# Naming convention
# ============================================================

class TestGameName:
    def test_mainline_game_name_format(self):
        assert mainline_game_name("ch01", "b1") == "mainline:ch01:b1"

    def test_mainline_game_name_roundtrip(self):
        name = mainline_game_name("chapter_01_steel_rebellion", "battle_01")
        assert parse_mainline_game_name(name) == ("chapter_01_steel_rebellion", "battle_01")

    def test_parse_mainline_game_name_rejects_normal_game(self):
        assert parse_mainline_game_name("Some Lobby") is None
        assert parse_mainline_game_name("mainline:") is None
        assert parse_mainline_game_name("mainline::battle") is None
        assert parse_mainline_game_name("mainline:ch01:") is None


# ============================================================
# State derivation
# ============================================================

class TestStateDerivation:
    def test_no_active_mainline_is_menu(self, sample_mainline):
        eng = MainlineEngine(session=None, profile=_profile(), mainline=sample_mainline)
        assert eng.state == MainlineState.MENU

    def test_different_active_mainline_is_menu(self, sample_mainline):
        eng = MainlineEngine(
            session=None,
            profile=_profile(active_mainline="other_campaign"),
            mainline=sample_mainline,
        )
        assert eng.state == MainlineState.MENU

    def test_matching_active_mainline_is_dialogue(self, sample_mainline):
        eng = MainlineEngine(
            session=None,
            profile=_profile(active_mainline=sample_mainline.id),
            mainline=sample_mainline,
        )
        assert eng.state == MainlineState.DIALOGUE


# ============================================================
# Battle index / current battle
# ============================================================

class TestCurrentBattle:
    def test_default_index_is_zero(self, sample_mainline):
        eng = MainlineEngine(session=None, profile=_profile(), mainline=sample_mainline)
        assert eng.current_battle_index == 0
        assert eng.current_battle is not None
        assert eng.current_battle.id == "battle_01"

    def test_index_1_returns_battle_2(self, sample_mainline):
        eng = MainlineEngine(
            session=None,
            profile=_profile(battle_index=1),
            mainline=sample_mainline,
        )
        assert eng.current_battle_index == 1
        assert eng.current_battle.id == "battle_02"

    def test_index_past_end_returns_none(self, sample_mainline):
        eng = MainlineEngine(
            session=None,
            profile=_profile(battle_index=99),
            mainline=sample_mainline,
        )
        assert eng.current_battle is None

    def test_negative_index_clamped_to_zero(self, sample_mainline):
        eng = MainlineEngine(
            session=None,
            profile=_profile(battle_index=-5),
            mainline=sample_mainline,
        )
        assert eng.current_battle_index == 0

    def test_missing_mainline_progress_uses_default(self, sample_mainline):
        # A pre-Step-2 profile has no mainline_progress attr at all.
        p = SimpleNamespace(user_name="alice", active_mainline=None)
        eng = MainlineEngine(session=None, profile=p, mainline=sample_mainline)
        assert eng.current_battle_index == 0
        assert eng.current_scene_id == "intro"


# ============================================================
# next_step (pure query)
# ============================================================

class TestNextStep:
    def test_first_time_player_gets_pre_battle_dialogue(self, sample_mainline):
        eng = MainlineEngine(session=None, profile=_profile(), mainline=sample_mainline)
        step = eng.next_step()
        # chapter_01 battle_01 has pre_battle_dialogue="intro"
        assert step.state == MainlineState.DIALOGUE.value
        assert step.dialogue_key == "intro"
        assert step.dialogue_url and step.dialogue_url.endswith("intro.json")
        assert step.battle_id == "battle_01"
        assert step.battle_index == 0
        assert step.total_battles == 2

    def test_battle_2_with_orphan_scene_id_returns_battle_state(self, sample_mainline):
        eng = MainlineEngine(
            session=None,
            profile=_profile(
                active_mainline=sample_mainline.id,
                battle_index=1,
                scene_id="battle_01_after",
            ),
            mainline=sample_mainline,
        )
        # Cursor is at index 1 (battle_02). battle_02's pre_battle_dialogue
        # is None and battle_01_after is not one of battle_02's scenes,
        # so the engine returns BATTLE state with battle_02's id.
        step = eng.next_step()
        assert step.state == MainlineState.BATTLE.value
        assert step.battle_id == "battle_02"
        assert step.battle_index == 1

    def test_mid_battle_state(self, sample_mainline):
        # Cursor sits on a non-dialogue scene_id -> the engine points
        # the player at the current battle board.
        eng = MainlineEngine(
            session=None,
            profile=_profile(
                active_mainline=sample_mainline.id,
                battle_index=0,
                scene_id="in_battle_marker",
            ),
            mainline=sample_mainline,
        )
        step = eng.next_step()
        assert step.state == MainlineState.BATTLE.value
        assert step.battle_id == "battle_01"

    def test_past_last_battle_is_victory(self, sample_mainline):
        eng = MainlineEngine(
            session=None,
            profile=_profile(battle_index=2),
            mainline=sample_mainline,
        )
        step = eng.next_step()
        assert step.state == MainlineState.VICTORY.value
        assert step.total_battles == 2

    def test_next_step_does_not_mutate_profile(self, sample_mainline):
        p = _profile(active_mainline=sample_mainline.id, battle_index=0)
        before = dict(p.mainline_progress)
        eng = MainlineEngine(session=None, profile=p, mainline=sample_mainline)
        eng.next_step()
        eng.next_step()
        # The profile's progress dict is identical — engine is pure.
        assert p.mainline_progress == before


# ============================================================
# Dialogue helpers
# ============================================================

class TestDialogueHelpers:
    def test_get_dialogue_path_known_key(self, sample_mainline):
        eng = MainlineEngine(session=None, profile=_profile(), mainline=sample_mainline)
        assert eng.get_dialogue_path("intro") and eng.get_dialogue_path("intro").endswith("intro.json")

    def test_get_dialogue_path_unknown_key_returns_none(self, sample_mainline):
        eng = MainlineEngine(session=None, profile=_profile(), mainline=sample_mainline)
        assert eng.get_dialogue_path("nonexistent_scene") is None

    def test_pre_post_dialogue_per_battle(self, sample_mainline):
        eng = MainlineEngine(session=None, profile=_profile(), mainline=sample_mainline)
        assert eng.pre_battle_dialogue_for(0) == "intro"
        assert eng.pre_battle_dialogue_for(1) is None  # battle_02 has none
        assert eng.post_battle_dialogue_for(0) == "battle_01_after"
        assert eng.post_battle_dialogue_for(1) == "battle_02_after"


# ============================================================
# Scene helpers / scene_id
# ============================================================

class TestSceneId:
    def test_default_scene_id_is_intro(self, sample_mainline):
        eng = MainlineEngine(session=None, profile=_profile(), mainline=sample_mainline)
        assert eng.current_scene_id == "intro"

    def test_scene_id_from_progress(self, sample_mainline):
        eng = MainlineEngine(
            session=None,
            profile=_profile(scene_id="battle_01_after"),
            mainline=sample_mainline,
        )
        assert eng.current_scene_id == "battle_01_after"

    def test_total_battles_property(self, sample_mainline):
        eng = MainlineEngine(session=None, profile=_profile(), mainline=sample_mainline)
        assert eng.total_battles == 2
