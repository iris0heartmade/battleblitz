"""Commander decisions used by automated players."""

from app.commanders.effects import can_fire_co_power


def ai_should_fire_co_power(ai_player) -> bool:
    """Return whether the current AI should immediately use its power."""
    return can_fire_co_power(ai_player)
