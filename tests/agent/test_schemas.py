"""
Unit tests for the agent's Pydantic schemas.

No DB, no LLM. Pure validation tests.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.schemas import (
    AgentAction,
    GameSnapshot,
    InvalidActionError,
    LegalAction,
    ParseError,
    UnitView,
)


# ── UnitView ────────────────────────────────────────────────

def test_unit_view_minimal():
    u = UnitView(
        id=1, type="swordsman", name="Swordsman A",
        hp=30, max_hp=45, mp=5, x=3, y=5, terrain="plain",
    )
    assert u.skills == []
    assert u.morale == 0
    assert u.has_acted is False


def test_unit_view_rejects_bad_morale():
    with pytest.raises(ValidationError):
        UnitView(
            id=1, type="swordsman", name="x",
            hp=30, max_hp=45, mp=5, x=0, y=0, terrain="plain",
            morale=4,  # out of range
        )


def test_unit_view_rejects_bad_type():
    with pytest.raises(ValidationError):
        UnitView(
            id=1, type="dragon", name="x",  # invalid type
            hp=30, max_hp=45, mp=5, x=0, y=0, terrain="plain",
        )


# ── LegalAction ─────────────────────────────────────────────

def test_legal_action_minimal():
    a = LegalAction(action_id="end_turn", kind="end_turn")
    assert a.unit_id is None
    assert a.params == {}


def test_legal_action_attack_shape():
    a = LegalAction(
        action_id="attack_3_9",
        kind="attack",
        unit_id=3,
        params={"target_id": 9},
        description="Knight 攻击 Swordsman",
        dmg_estimate=14,
    )
    assert a.dmg_estimate == 14


# ── AgentAction ─────────────────────────────────────────────

def test_agent_action_accepts_valid():
    a = AgentAction(action_id="attack_3_9", reason="抢先击杀")
    assert a.action_id == "attack_3_9"


def test_agent_action_rejects_empty_id():
    with pytest.raises(ValidationError):
        AgentAction(action_id="", reason="x")


def test_agent_action_rejects_invalid_chars():
    with pytest.raises(ValidationError):
        AgentAction(action_id="attack 3 9", reason="x")  # spaces not allowed


def test_agent_action_truncates_long_reason():
    a = AgentAction(action_id="wait_1", reason="x" * 200)
    assert len(a.reason) == 120


# ── Error types ─────────────────────────────────────────────

def test_invalid_action_error_carries_id():
    e = InvalidActionError("attack_99_9")
    assert e.action_id == "attack_99_9"
    assert "attack_99_9" in str(e)
