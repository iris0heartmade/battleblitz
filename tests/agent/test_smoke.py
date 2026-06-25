"""
Smoke test: import every module in the agent package to catch syntax errors,
missing dependencies, and circular imports at test time rather than runtime.
"""
from __future__ import annotations


def test_imports():
    from app.agent import LLMAgent, dispatch_ai_turn  # noqa: F401
    from app.agent.agent import LLMAgent, _rules_ai_pick  # noqa: F401
    from app.agent.integration import (  # noqa: F401
        dispatch_ai_turn,
        get_default_llm_client,
        set_default_llm_client,
    )
    from app.agent.legal_actions import enumerate_legal_actions  # noqa: F401
    from app.agent.llm_client import LLMClient, LLMResponse, TokenUsage  # noqa: F401
    from app.agent.prompt import (  # noqa: F401
        build_system_prompt,
        build_user_prompt,
        get_personality,
        PERSONALITIES,
    )
    from app.agent.schemas import (  # noqa: F401
        AgentAction,
        GameSnapshot,
        LegalAction,
        UnitView,
    )
    from app.agent.snapshot import build_snapshot  # noqa: F401


def test_personalities_defined():
    from app.agent.prompt import PERSONALITIES
    assert "aggressive" in PERSONALITIES
    assert "defensive" in PERSONALITIES
    assert "balanced" in PERSONALITIES
    assert "trickster" in PERSONALITIES


def test_unknown_personality_falls_back_to_balanced():
    from app.agent.prompt import build_system_prompt
    p = build_system_prompt("nonsense", map_size=15)
    assert "均衡" in p
