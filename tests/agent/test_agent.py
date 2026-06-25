"""
Unit tests for the LLMAgent orchestration logic.

The LLM client is mocked so these tests run without an API key or GPU.
They verify:
- The retry/fallback path activates when the LLM returns garbage
- The action-id validation catches hallucinated ids
- A well-formed tool_use reply is parsed into an ActionPlan
- Fallback picks attacks > skills > moves > waits > end_turn
"""
from __future__ import annotations

import asyncio
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.agent import LLMAgent, _rules_ai_pick
from app.agent.llm_client import LLMResponse, TokenUsage
from app.agent.schemas import (
    AgentAction,
    InvalidActionError,
    LegalAction,
    ParseError,
)


# ── Helpers ──────────────────────────────────────────────────

def _legal_actions() -> List[LegalAction]:
    return [
        LegalAction(
            action_id="attack_1_9", kind="attack", unit_id=1,
            params={"target_id": 9},
            description="Swordsman 攻击 Swordsman (预计 12 伤害)",
            dmg_estimate=12,
        ),
        LegalAction(
            action_id="move_1_5_5", kind="move", unit_id=1,
            params={"to": [5, 5]},
            description="Swordsman 移动到 (5,5)",
        ),
        LegalAction(
            action_id="wait_1", kind="wait", unit_id=1,
            description="Swordsman 原地待命",
        ),
        LegalAction(
            action_id="end_turn", kind="end_turn",
            description="结束本回合行动",
        ),
    ]


def _llm_response(action_id: str = "attack_1_9", reason: str = "抢先击杀") -> LLMResponse:
    return LLMResponse(
        text="",
        tool_name="choose_action",
        tool_input={"action_id": action_id, "reason": reason},
        stop_reason="tool_use",
        usage=TokenUsage(input_tokens=100, output_tokens=20),
    )


def _fake_llm_client(responses: List[LLMResponse]) -> MagicMock:
    """An LLMClient stand-in that returns `responses` in order, then loops."""
    client = MagicMock()
    iter_resp = iter(responses)

    async def _chat(*, system, user, **kwargs):
        try:
            return next(iter_resp)
        except StopIteration:
            return responses[-1]

    client.chat = AsyncMock(side_effect=_chat)
    return client


# ── Parsing + validation ────────────────────────────────────

def test_parses_well_formed_tool_use():
    agent = LLMAgent(llm_client=_fake_llm_client([_llm_response()]))
    resp = _llm_response()
    action = agent._parse_response(resp)
    assert action.action_id == "attack_1_9"
    assert action.reason == "抢先击杀"


def test_parse_rejects_wrong_tool_name():
    agent = LLMAgent(llm_client=_fake_llm_client([]))
    bad = LLMResponse(tool_name="attack", tool_input={"action_id": "x"}, stop_reason="x")
    with pytest.raises(ParseError):
        agent._parse_response(bad)


def test_parse_rejects_missing_action_id():
    agent = LLMAgent(llm_client=_fake_llm_client([]))
    bad = LLMResponse(tool_name="choose_action", tool_input={"reason": "x"}, stop_reason="x")
    with pytest.raises(ParseError):
        agent._parse_response(bad)


def test_validate_accepts_legal_action_id():
    agent = LLMAgent(llm_client=_fake_llm_client([]))
    legal = _legal_actions()
    action = AgentAction(action_id="attack_1_9", reason="x")
    agent._validate_action_id(action, legal)  # no raise


def test_validate_rejects_hallucinated_action_id():
    agent = LLMAgent(llm_client=_fake_llm_client([]))
    legal = _legal_actions()
    action = AgentAction(action_id="destroy_everything", reason="x")
    with pytest.raises(InvalidActionError):
        agent._validate_action_id(action, legal)


# ── Retry + fallback ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_retry_recovers_on_second_attempt():
    bad = LLMResponse(tool_name="choose_action", tool_input={"action_id": "fake"}, stop_reason="x")
    good = _llm_response("attack_1_9")
    client = _fake_llm_client([bad, good])

    agent = LLMAgent(llm_client=client, max_retries=2)
    plan = await agent._ask_llm_with_retry(
        system="x", user="y", legal=_legal_actions(),
    )
    assert plan.fallback is False
    assert plan.legal_action.action_id == "attack_1_9"
    assert plan.llm_retries == 1


@pytest.mark.asyncio
async def test_fallback_after_all_retries_fail():
    bad = LLMResponse(tool_name="choose_action", tool_input={"action_id": "fake"}, stop_reason="x")
    client = _fake_llm_client([bad, bad, bad, bad])

    agent = LLMAgent(llm_client=client, max_retries=2)
    plan = await agent._ask_llm_with_retry(
        system="x", user="y", legal=_legal_actions(),
    )
    assert plan.fallback is True
    # Fallback picks the highest-damage attack
    assert plan.legal_action.kind == "attack"
    assert plan.legal_action.action_id == "attack_1_9"
    assert "[兜底]" in plan.reason


# ── Rules-AI fallback picker ─────────────────────────────────

def test_rules_ai_pick_prefers_attack():
    legal = _legal_actions()
    pick = _rules_ai_pick(legal)
    assert pick.kind == "attack"


def test_rules_ai_pick_falls_back_to_wait_when_no_attack():
    legal = [
        LegalAction(action_id="wait_1", kind="wait", unit_id=1),
        LegalAction(action_id="end_turn", kind="end_turn"),
    ]
    pick = _rules_ai_pick(legal)
    assert pick.kind == "wait"


def test_rules_ai_pick_picks_end_turn_when_nothing_else():
    legal = [LegalAction(action_id="end_turn", kind="end_turn")]
    pick = _rules_ai_pick(legal)
    assert pick.kind == "end_turn"
