"""
Wire protocol definitions for BattleBlitz (v1).

Public API:
    from app.protocol import WSMessage, ProtocolV1
    from app.protocol import PROTOCOL_VERSION, EVENT_DELTA, ERROR, ...

The actual WebSocket transport lives in app/routes/protocol_ws.py (added
separately). This package is pure data — no I/O, easy to test.
"""
from app.protocol.v1 import (
    # Constants
    PROTOCOL_VERSION,
    SERVER_HELLO, STATE_SNAPSHOT, EVENT_DELTA,
    COMMENTARY_TEXT, COMMENTARY_AUDIO, TURN_ADVANCE, ERROR,
    CLIENT_HELLO, CLIENT_PING,
    ACTION_MOVE, ACTION_ATTACK, ACTION_SKILL, ACTION_WAIT, ACTION_END_TURN,
    # Models
    WSMessage,
    ServerHelloPayload,
    EventDeltaPayload,
    TurnAdvancePayload,
    ErrorPayload,
    ActionMovePayload,
    ActionAttackPayload,
    ActionSkillPayload,
    ErrorCode,
)

__all__ = [
    "PROTOCOL_VERSION",
    "SERVER_HELLO", "STATE_SNAPSHOT", "EVENT_DELTA",
    "COMMENTARY_TEXT", "COMMENTARY_AUDIO", "TURN_ADVANCE", "ERROR",
    "CLIENT_HELLO", "CLIENT_PING",
    "ACTION_MOVE", "ACTION_ATTACK", "ACTION_SKILL", "ACTION_WAIT", "ACTION_END_TURN",
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
