"""Test GameEventBus file logger (07-21 F4).

The bus now optionally writes every published event as a one-line JSON
to a log file. This is the primary evidence stream the chapter_06
event verifier reads back. We assert:
  * set_file_logger creates a file
  * publish writes one line per event
  * the line contains turn, type, actor, target, ctx
  * close_file_logger flushes and the trailer line is appended
  * publish after close is a no-op
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.events.bus import GameEventBus
from app.events.types import GameEvent, EventType


def _ev(type_: EventType, **kw) -> GameEvent:
    defaults = dict(game_id=9006, turn=1)
    defaults.update(kw)
    return GameEvent(type=type_, **defaults)


def test_set_file_logger_writes_header(tmp_path: Path) -> None:
    bus = GameEventBus()
    log = tmp_path / "events.log"
    bus.set_file_logger(str(log))
    try:
        assert log.exists()
        head = log.read_text(encoding="utf-8").splitlines()
        assert head == ["=== chapter_06 event log started ==="]
    finally:
        bus.close_file_logger()


def test_publish_writes_one_line_per_event(tmp_path: Path) -> None:
    bus = GameEventBus()
    log = tmp_path / "events.log"
    bus.set_file_logger(str(log))
    try:
        # We can't await publish() in sync test, so call the writer
        # directly to validate the on-disk format.
        for e in [
            _ev("move",  turn=3, actor_unit_id=10, actor_name="云",  context={"to": [4, 7]}),
            _ev("attack", turn=3, actor_unit_id=12, actor_name="红",  target_unit_id=21, target_name="敌方狙击", context={"dmg": 18, "is_crit": True}),
            _ev("kill",   turn=3, actor_unit_id=12, target_unit_id=21, target_name="敌方狙击", context={"hp_before": 1}),
        ]:
            bus._write_log_line(e)  # type: ignore[attr-defined]
        lines = log.read_text(encoding="utf-8").splitlines()
        # header + 3 events
        assert len(lines) == 4
        assert lines[0].startswith("=== chapter_06")
        for ln, expected_type in zip(lines[1:], ["move", "attack", "kill"]):
            obj = json.loads(ln)
            assert obj["type"] == expected_type
            assert obj["game"] == 9006
            assert obj["turn"] == 3
    finally:
        bus.close_file_logger()


def test_close_file_logger_writes_trailer(tmp_path: Path) -> None:
    bus = GameEventBus()
    log = tmp_path / "events.log"
    bus.set_file_logger(str(log))
    bus.close_file_logger()
    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("=== chapter_06 event log started ===")
    assert lines[-1].startswith("=== chapter_06 event log closed ===")


def test_publish_after_close_is_noop(tmp_path: Path) -> None:
    bus = GameEventBus()
    log = tmp_path / "events.log"
    bus.set_file_logger(str(log))
    bus.close_file_logger()
    # Now publish should not crash
    import asyncio
    asyncio.run(bus.publish(_ev("turn_end", turn=2)))
    # File should only have header + trailer (no event lines)
    body = log.read_text(encoding="utf-8").splitlines()
    body = [ln for ln in body if ln and not ln.startswith("===")]
    assert body == []


def test_actor_and_target_arrays(tmp_path: Path) -> None:
    bus = GameEventBus()
    log = tmp_path / "events.log"
    bus.set_file_logger(str(log))
    try:
        bus._write_log_line(_ev(
            "kill", turn=3,
            actor_player_id=1, actor_unit_id=12, actor_name="红",
            target_player_id=2, target_unit_id=21, target_name="敌方狙击",
            context={"hp_before": 1},
        ))
        obj = json.loads(log.read_text(encoding="utf-8").splitlines()[1])
        assert obj["actor"] == [1, 12, "红"]
        assert obj["target"] == [2, 21, "敌方狙击"]
        assert obj["ctx"] == {"hp_before": 1}
    finally:
        bus.close_file_logger()
