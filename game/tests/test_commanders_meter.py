from __future__ import annotations

from types import SimpleNamespace

from app.commanders import DEATH_PENALTY, UNIT_DESTROY_SCORES, on_death, on_kill


def test_commander_meter_scores_and_initializes_state():
    attacker = SimpleNamespace(co_state=None)
    dead_player = SimpleNamespace(co_state=None)

    assert UNIT_DESTROY_SCORES["swordsman"] == 2
    assert UNIT_DESTROY_SCORES["archer"] == 3
    assert UNIT_DESTROY_SCORES["lancer"] == 2
    assert UNIT_DESTROY_SCORES["knight"] == 4
    assert UNIT_DESTROY_SCORES["warlock"] == 4
    assert UNIT_DESTROY_SCORES["healer"] == 3

    assert on_kill(attacker, "unknown") == 2
    assert attacker.co_state == {"meter": 2, "threshold": 20}

    assert on_kill(attacker, "archer") == 3
    assert attacker.co_state == {"meter": 5, "threshold": 20}

    assert on_death(dead_player) == DEATH_PENALTY
    assert dead_player.co_state == {"meter": DEATH_PENALTY, "threshold": 20}
