"""
Event type definitions for the in-process event bus.

Every significant game occurrence (move, attack, kill, skill, etc.) becomes a
GameEvent and is published to `app.events.bus.bus`. Subscribers (AI, commentary,
WebSocket gateway, telemetry) receive them asynchronously.

Wire format (for WebSocket, see `app.protocol.v1`):
    {
      "v": 1,
      "type": "kill",
      "game_id": 123,
      "turn": 5,
      "timestamp_ms": 1719312345678,
      "actor_player_id": 7,
      "actor_unit_id": 42,
      "target_player_id": 9,
      "target_unit_id": 56,
      "context": {"attacker_type": "swordsman", "dmg": 18, "is_crit": true}
    }
"""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field


# ============================================================
# Event type enum (frozen; add new types here when needed)
# ============================================================

EventType = Literal[
    # Per-action events (fired by app/routes/actions.py)
    "move",
    "attack",
    "kill",
    "skill",
    "wait",
    # Turn / round events (fired by app/routes/turns.py)
    "turn_end",
    "round_end",
    "match_start",
    "match_end",
    # Strategic events (fired by app/game_logic.py or app/progression/)
    "castle_captured",
    "level_up",
    "low_hp_warning",
    "comeback",
    "victory_imminent",
    # System events (fired by app/main.py or scheduler)
    "ai_step",
    "auto_skip",
    "error",
]

# Use this set when classifying events by importance in commentary / UI.
CRITICAL_EVENTS: frozenset[str] = frozenset({
    "kill", "castle_captured", "comeback",
    "victory_imminent", "match_end",
})
IMPORTANT_EVENTS: frozenset[str] = frozenset({
    "level_up", "round_end", "match_start",
    "low_hp_warning", "auto_skip",
})
# Everything else is NORMAL.


# ============================================================
# GameEvent model
# ============================================================

class GameEvent(BaseModel):
    """A single game occurrence. Immutable; pass by value, never mutate."""

    # Schema version — bump `v` on the protocol when this changes shape.
    v: int = Field(default=1, description="Protocol version")

    # Discriminator
    type: EventType

    # Routing
    game_id: int

    # When (monotonic on the server; clients should treat as informational)
    timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))

    # Turn context
    turn: int = 0

    # Who did it (None for system / non-player events)
    actor_player_id: int | None = None
    actor_unit_id: int | None = None
    actor_name: str | None = None

    # Who it happened to
    target_player_id: int | None = None
    target_unit_id: int | None = None
    target_name: str | None = None

    # Free-form per-type data (e.g. {"dmg": 18, "is_crit": true})
    context: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for the wire (same shape as the Pydantic model)."""
        return self.model_dump(exclude_none=True)

    @property
    def importance(self) -> str:
        if self.type in CRITICAL_EVENTS:
            return "critical"
        if self.type in IMPORTANT_EVENTS:
            return "important"
        return "normal"


__all__ = [
    "GameEvent",
    "EventType",
    "CRITICAL_EVENTS",
    "IMPORTANT_EVENTS",
]
