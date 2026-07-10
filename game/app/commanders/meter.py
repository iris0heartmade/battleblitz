from __future__ import annotations

from typing import Any

UNIT_DESTROY_SCORES: dict[str, int] = {
    "swordsman": 2,
    "archer": 3,
    "lancer": 2,
    "knight": 4,
    "warlock": 4,
    "healer": 3,
}

DEATH_PENALTY = 2


def _ensure_meter_state(player: Any) -> dict[str, Any]:
    state = getattr(player, "co_state", None)
    if state is None:
        state = {"meter": 0, "threshold": 20}
        player.co_state = state
        return state
    if "meter" not in state:
        state["meter"] = 0
    if "threshold" not in state:
        state["threshold"] = 20
    return state


def on_kill(attacker_player: Any, killed_unit_type: str) -> int:
    state = _ensure_meter_state(attacker_player)
    score = UNIT_DESTROY_SCORES.get(killed_unit_type, 2)
    state["meter"] += score
    return score


def on_death(dead_player: Any) -> int:
    state = _ensure_meter_state(dead_player)
    state["meter"] += DEATH_PENALTY
    return DEATH_PENALTY
