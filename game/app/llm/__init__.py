"""
LLM client abstraction for BattleBlitz.

Public API:
    from app.llm import safe_complete, set_llm_client, LLMClient

    # At app startup, register an implementation (owned by the project
    # owner per doc/battleblitz-llm-agent.md):
    #     set_llm_client(MyClaudeClient())

    # At call sites:
    text = await safe_complete(prompt, max_tokens=200, timeout=1.5)
    if text is None:
        # fall back to template / rule
        ...

This package is intentionally implementation-agnostic. The actual
Claude / OpenAI / local-Llama client lives elsewhere; this module
defines the contract and the safety wrapper.
"""
from app.llm.client import (
    LLMClient,
    get_llm_client,
    safe_complete,
    set_llm_client,
)

__all__ = [
    "LLMClient",
    "safe_complete",
    "set_llm_client",
    "get_llm_client",
]
