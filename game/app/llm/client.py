"""
LLM client abstraction.

Defines the *interface* (LLMClient Protocol) and the *safety wrapper*
(safe_complete). The actual Claude / OpenAI / local-Llama implementations
are intentionally NOT included here — see doc/battleblitz-llm-agent.md
for the spec; the implementation is owned by the project owner.

Why a Protocol? Two reasons:
  1. Tests can supply a fake LLMClient without monkey-patching.
  2. Swapping providers (Claude → OpenAI → local) is one line.

Why safe_complete? LLM calls are slow (500-2000ms) and unreliable
(timeouts, rate limits). Every call site needs a timeout + fallback
to a non-LLM path. Putting that logic in one place avoids the
"forgot to wrap it" bug.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ============================================================
# LLMClient Protocol (the contract)
# ============================================================

@runtime_checkable
class LLMClient(Protocol):
    """Anyone implementing this can be plugged into safe_complete().

    Implementations must be async and must NOT raise on transient errors
    (rate limit, network); instead, return None and let the caller fall
    back. (safe_complete handles the asyncio.TimeoutError case.)
    """

    async def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        model: str | None = None,
        temperature: float = 0.7,
    ) -> str | None:
        """Return the model's text response, or None on transient failure."""
        ...


# ============================================================
# safe_complete — the one wrapper every call site should use
# ============================================================

async def safe_complete(
    prompt: str,
    *,
    max_tokens: int,
    client: LLMClient | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    timeout: float = 1.5,
) -> str | None:
    """LLM call with timeout + None-on-failure semantics.

    Usage:
        text = await safe_complete(prompt, max_tokens=200, timeout=1.5)
        if text is None:
            # fall back to template / rule
            ...

    Design notes:
      - `timeout` defaults to 1.5s, which is "user won't notice" territory
        for live UI commentary and acceptable for AI turn planning.
      - We never raise — any exception becomes None + a log line. Callers
        can check `if text is None` to trigger the fallback path.
      - `client` defaults to whatever get_llm_client() returns at call
        time, so tests can monkey-patch the factory.
    """
    if client is None:
        client = get_llm_client()
    if client is None:
        # No implementation registered yet (this project hasn't picked one).
        # Return None so call sites fall back gracefully.
        logger.debug("safe_complete: no LLM client registered, returning None")
        return None

    try:
        return await asyncio.wait_for(
            client.complete(
                prompt,
                max_tokens=max_tokens,
                model=model,
                temperature=temperature,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("LLM call timed out after %.2fs (max_tokens=%d)",
                       timeout, max_tokens)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM call failed: %s", exc)
        return None


# ============================================================
# Client registry (so the project owner can plug their impl in)
# ============================================================

# Module-level handle; project owner sets this in their bootstrap code:
#
#     from app.llm import set_llm_client
#     from my_impl import ClaudeClient
#     set_llm_client(ClaudeClient())
#
# Until then, safe_complete() returns None and call sites fall back.

_llm_client: LLMClient | None = None


def set_llm_client(client: LLMClient) -> None:
    """Register the LLM implementation. Idempotent (replaces previous)."""
    global _llm_client
    _llm_client = client
    logger.info("LLM client registered: %s", type(client).__name__)


def get_llm_client() -> LLMClient | None:
    """Return the currently-registered LLM client (or None)."""
    return _llm_client


__all__ = [
    "LLMClient",
    "safe_complete",
    "set_llm_client",
    "get_llm_client",
]
