"""BattleSpec commander fields and mainline victory unlock behavior."""
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.mainline.engine import MainlineEngine
from app.mainline.schemas import BattleSpec


def _battle(**overrides):
    values = {
        "id": "b1",
        "title": "test",
        "map_id": "balanced_2p_15",
        "win_condition": "rout",
        "teams": {"ally": ["red"], "enemy": ["blue"]},
    }
    values.update(overrides)
    return BattleSpec(**values)


def test_battle_spec_accepts_commander_fields():
    spec = _battle(unlocks_commander="yun", enemy_commander="anna")

    assert spec.unlocks_commander == "yun"
    assert spec.enemy_commander == "anna"


@pytest.mark.parametrize("field", ["unlocks_commander", "enemy_commander"])
def test_battle_spec_rejects_unknown_commander(field):
    with pytest.raises(ValidationError, match="not found"):
        _battle(**{field: "ghost"})


@pytest.mark.parametrize("field", ["unlocks_commander", "enemy_commander"])
def test_battle_spec_rejects_registered_non_commander(field, monkeypatch):
    monkeypatch.setattr(
        "app.classes.heroes.get_or_none",
        lambda _hero_id: SimpleNamespace(is_commander=False),
    )
    with pytest.raises(ValidationError, match="is not a commander"):
        _battle(**{field: "draven"})


class _Session:
    async def flush(self):
        pass

    async def refresh(self, _profile):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initial", "expected"),
    [([], ["anna"]), (["anna"], ["anna"]), (None, ["anna"])],
)
async def test_apply_victory_unlocks_deduplicated_and_handles_empty_values(
    monkeypatch, initial, expected
):
    class _ProgressionService:
        def __init__(self, _session):
            pass

        async def advance_mainline_progress(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        "app.progression.service.ProgressionService", _ProgressionService
    )
    profile = SimpleNamespace(
        user_name="alice",
        gold=0,
        unlocked_classes=[],
        unlocked_commanders=initial,
        units=[],
    )
    mainline = SimpleNamespace(
        id="chapter_01",
        dialogues={},
        rewards_on_clear=SimpleNamespace(
            gold=0, unlock_class=None, exp_per_unit=0
        ),
        battles=[
            SimpleNamespace(unlocks_commander="anna"),
            SimpleNamespace(unlocks_commander=None),
            SimpleNamespace(unlocks_commander="yun"),
        ],
    )
    engine = MainlineEngine(_Session(), profile, mainline)

    engine.apply_battle_victory(mainline.battles[0])

    assert profile.unlocked_commanders == expected
    assert "yun" not in profile.unlocked_commanders


@pytest.mark.asyncio
async def test_apply_victory_preserves_empty_unlock_list(monkeypatch):
    class _ProgressionService:
        def __init__(self, _session):
            pass

        async def advance_mainline_progress(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        "app.progression.service.ProgressionService", _ProgressionService
    )
    profile = SimpleNamespace(
        user_name="alice", gold=0, unlocked_classes=[],
        unlocked_commanders=[], units=[],
    )
    mainline = SimpleNamespace(
        id="chapter_01",
        dialogues={},
        rewards_on_clear=SimpleNamespace(
            gold=0, unlock_class=None, exp_per_unit=0
        ),
        battles=[SimpleNamespace(unlocks_commander=None)],
    )

    engine = MainlineEngine(_Session(), profile, mainline)
    engine.apply_battle_victory(mainline.battles[0])

    assert profile.unlocked_commanders == []


@pytest.mark.asyncio
async def test_final_victory_only_unlocks_completed_battle(monkeypatch):
    class _ProgressionService:
        def __init__(self, _session):
            pass

        async def advance_mainline_progress(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        "app.progression.service.ProgressionService", _ProgressionService
    )
    profile = SimpleNamespace(
        user_name="alice", gold=0, unlocked_classes=[],
        unlocked_commanders=None, units=[],
    )
    completed = SimpleNamespace(unlocks_commander="anna")
    future = SimpleNamespace(unlocks_commander="yun")
    mainline = SimpleNamespace(
        id="chapter_01", dialogues={}, battles=[completed, future],
        rewards_on_clear=SimpleNamespace(
            gold=0, unlock_class=None, exp_per_unit=0
        ),
    )
    engine = MainlineEngine(_Session(), profile, mainline)

    await engine.apply_victory(completed_battle=completed)

    assert profile.unlocked_commanders == ["anna"]
