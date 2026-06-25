"""
Wire protocol v1 — the language between server and (future) native client.

This module defines the data shapes; it does **not** do any I/O. The actual
WebSocket/REST serialization is done by routes/protocol_ws.py (future) and
the existing REST routes.

Design rules (see doc/ARCHITECTURE_PLAN.md §8.1 for full spec):
  - Flat JSON; no nested ORM objects
  - Every message has a `v: 1` version field
  - Type strings (not numeric enums)
  - Integer IDs only (no UUIDs/Snowflakes)
  - Timestamps are unix milliseconds
"""
from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field


# ============================================================
# Protocol version
# ============================================================

PROTOCOL_VERSION: int = 1


# ============================================================
# Message type strings
# ============================================================

# Server → client
SERVER_HELLO         = "server.hello"          # First message after WS connect
STATE_SNAPSHOT      = "state.snapshot"        # Full game state
EVENT_DELTA         = "event.delta"           # Single GameEvent
COMMENTARY_TEXT     = "commentary.text"       # Text only
COMMENTARY_AUDIO    = "commentary.audio"      # Text + base64 audio bytes
TURN_ADVANCE        = "turn.advance"          # Whose turn is it now
ERROR               = "error"

# Client → server
CLIENT_HELLO        = "client.hello"          # Auth + join
CLIENT_PING         = "client.ping"
ACTION_MOVE         = "action.move"
ACTION_ATTACK       = "action.attack"
ACTION_SKILL        = "action.skill"
ACTION_WAIT         = "action.wait"
ACTION_END_TURN     = "action.end_turn"


# ============================================================
# Envelope
# ============================================================

class WSMessage(BaseModel):
    """Universal WebSocket message wrapper.

    All messages going over the wire use this envelope so clients can
    route by `type` and validate by `v`.
    """

    v: int = Field(default=PROTOCOL_VERSION)
    type: str
    # Monotonic per-connection sequence number. Server fills this in.
    seq: int | None = None
    # Unix ms when the server emitted the message.
    sent_at_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    # Type-specific payload. Validated per `type` by the route handler.
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        """Serialise for transmission (Pydantic dump)."""
        return self.model_dump(exclude_none=True)


# ============================================================
# Specific payload schemas (for documentation + future validation)
# ============================================================

class ServerHelloPayload(BaseModel):
    server_version: str
    protocol_version: int = PROTOCOL_VERSION
    session_id: str
    features: list[str] = Field(default_factory=list)


class EventDeltaPayload(BaseModel):
    """Carries a single GameEvent (see app/events/types.py)."""
    game_id: int
    turn: int
    event_type: str
    actor_unit_id: int | None = None
    target_unit_id: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class TurnAdvancePayload(BaseModel):
    game_id: int
    turn: int
    next_player_id: int | None
    next_player_name: str | None
    is_new_round: bool = False


class ErrorPayload(BaseModel):
    code: str
    message: str
    # Optional: the offending field for INPUT_VALIDATE-style errors.
    field: str | None = None
    # Optional: trace id for log correlation.
    trace_id: str | None = None


class ActionMovePayload(BaseModel):
    unit_id: int
    to_x: int
    to_y: int


class ActionAttackPayload(BaseModel):
    attacker_id: int
    target_id: int


class ActionSkillPayload(BaseModel):
    unit_id: int
    skill: str
    target_id: int | None = None


# ============================================================
# Error codes
# ============================================================

class ErrorCode:
    OUT_OF_MP          = "OUT_OF_MP"
    OUT_OF_RANGE       = "OUT_OF_RANGE"
    NOT_YOUR_TURN      = "NOT_YOUR_TURN"
    INVALID_TARGET     = "INVALID_TARGET"
    GAME_FINISHED      = "GAME_FINISHED"
    GAME_NOT_FOUND     = "GAME_NOT_FOUND"
    INTERNAL           = "INTERNAL"
    AUTH_REQUIRED      = "AUTH_REQUIRED"
    RATE_LIMITED       = "RATE_LIMITED"
    PROTOCOL_MISMATCH  = "PROTOCOL_MISMATCH"


__all__ = [
    "PROTOCOL_VERSION",
    # Type constants
    "SERVER_HELLO", "STATE_SNAPSHOT", "EVENT_DELTA",
    "COMMENTARY_TEXT", "COMMENTARY_AUDIO", "TURN_ADVANCE", "ERROR",
    "CLIENT_HELLO", "CLIENT_PING",
    "ACTION_MOVE", "ACTION_ATTACK", "ACTION_SKILL", "ACTION_WAIT", "ACTION_END_TURN",
    # Envelope + payload models
    "WSMessage",
    "ServerHelloPayload",
    "EventDeltaPayload",
    "TurnAdvancePayload",
    "ErrorPayload",
    "ActionMovePayload",
    "ActionAttackPayload",
    "ActionSkillPayload",
    "ErrorCode",
]
