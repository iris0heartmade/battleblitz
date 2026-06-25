"""
Unit tests for the wire protocol v1.

Covers:
  - WSMessage envelope serialization
  - Payload models
  - Error code constants
  - Protocol version consistency
"""
from __future__ import annotations

import time

import pytest

from app.protocol import (
    ACTION_ATTACK,
    ACTION_END_TURN,
    ACTION_MOVE,
    CLIENT_PING,
    ERROR,
    EVENT_DELTA,
    PROTOCOL_VERSION,
    SERVER_HELLO,
    STATE_SNAPSHOT,
    WSMessage,
    ErrorCode,
    EventDeltaPayload,
    ServerHelloPayload,
    TurnAdvancePayload,
)


@pytest.mark.unit
class TestWSMessage:
    def test_default_version_is_1(self):
        m = WSMessage(type=EVENT_DELTA)
        assert m.v == 1
        assert m.v == PROTOCOL_VERSION

    def test_to_wire_omits_none(self):
        m = WSMessage(type=EVENT_DELTA, payload={"k": "v"})
        wire = m.to_wire()
        assert "seq" not in wire  # None values dropped
        assert wire["type"] == EVENT_DELTA
        assert wire["payload"] == {"k": "v"}

    def test_to_wire_includes_timestamp(self):
        before = int(time.time() * 1000)
        m = WSMessage(type=EVENT_DELTA)
        after = int(time.time() * 1000)
        wire = m.to_wire()
        assert before <= wire["sent_at_ms"] <= after

    def test_seq_preserved(self):
        m = WSMessage(type=EVENT_DELTA, seq=42)
        assert m.to_wire()["seq"] == 42

    def test_round_trip_via_model_validate(self):
        """A message serialized then re-parsed keeps its key fields."""
        original = WSMessage(type=SERVER_HELLO, seq=7, payload={"x": 1})
        wire = original.to_wire()
        restored = WSMessage.model_validate(wire)
        assert restored.type == SERVER_HELLO
        assert restored.seq == 7
        assert restored.payload == {"x": 1}


@pytest.mark.unit
class TestPayloadModels:
    def test_server_hello(self):
        p = ServerHelloPayload(
            server_version="0.1.0",
            session_id="abc",
            features=["live2d", "tts"],
        )
        d = p.model_dump()
        assert d["server_version"] == "0.1.0"
        assert d["protocol_version"] == 1
        assert "live2d" in d["features"]

    def test_event_delta(self):
        p = EventDeltaPayload(
            game_id=10, turn=5, event_type="kill",
            actor_unit_id=42, target_unit_id=56,
            context={"dmg": 18},
        )
        d = p.model_dump()
        assert d["game_id"] == 10
        assert d["event_type"] == "kill"
        assert d["context"]["dmg"] == 18

    def test_turn_advance(self):
        p = TurnAdvancePayload(
            game_id=1, turn=3, next_player_id=7,
            next_player_name="alice", is_new_round=False,
        )
        assert p.turn == 3
        assert p.next_player_name == "alice"
        assert p.is_new_round is False


@pytest.mark.unit
class TestConstants:
    def test_type_strings_are_unique(self):
        types = [
            SERVER_HELLO, STATE_SNAPSHOT, EVENT_DELTA, ERROR,
            CLIENT_PING,
            ACTION_MOVE, ACTION_ATTACK, ACTION_END_TURN,
        ]
        assert len(types) == len(set(types))

    def test_error_codes_are_strings(self):
        for name in dir(ErrorCode):
            if name.startswith("_"):
                continue
            value = getattr(ErrorCode, name)
            assert isinstance(value, str)
            assert value.isupper() or "_" in value

    def test_protocol_version_is_int(self):
        assert isinstance(PROTOCOL_VERSION, int)
        assert PROTOCOL_VERSION >= 1
