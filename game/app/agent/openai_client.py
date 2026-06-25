"""
OpenAI SDK-compatible LLM client for providers like DeepSeek.

Mirrors the `LLMClient` interface (same `chat()` signature, same `LLMResponse`
return type) so `LLMAgent` doesn't need to know which backend is in use.

Key differences from `AnthropicClient`:
  - Uses `openai.AsyncOpenAI` instead of `anthropic.AsyncAnthropic`.
  - Translates the Anthropic `tool_use` schema to OpenAI `function` calling.
  - Parses `tool_calls` from the response into the same `LLMResponse` shape.

Environment variables (prefixed `OPENAI_` so a single process can host both):
  `OPENAI_API_KEY`   (fallback: `ANTHROPIC_API_KEY`)
  `OPENAI_BASE_URL`  (fallback: `https://api.deepseek.com`)
  `OPENAI_MODEL`     (fallback: `deepseek-v4-pro`)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# Response dataclass (same shape as LLMClient's LLMResponse)
# ----------------------------------------------------------------

@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


@dataclass
class LLMResponse:
    text: str = ""
    tool_name: Optional[str] = None
    tool_input: dict = field(default_factory=dict)
    stop_reason: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw: Any = None


# ----------------------------------------------------------------
# Anthropic → OpenAI tool schema translation
# ----------------------------------------------------------------

def _anthropic_to_openai_tool(anthropic_tool: dict) -> dict:
    """Convert an Anthropic tool_use schema to OpenAI function calling format.

    Anthropic:
      {"name": "choose_action", "description": "...",
       "input_schema": {"type": "object", "properties": {...}, "required": [...]}}

    OpenAI:
      {"type": "function",
       "function": {"name": "choose_action", "description": "...",
                     "parameters": {"type": "object", "properties": {...},
                                    "required": [...]}}}
    """
    return {
        "type": "function",
        "function": {
            "name": anthropic_tool["name"],
            "description": anthropic_tool.get("description", ""),
            "parameters": anthropic_tool.get("input_schema", {"type": "object"}),
        },
    }


# ----------------------------------------------------------------
# OpenAI-compatible client
# ----------------------------------------------------------------

# Same tool schema as LLMClient (kept in sync manually for now).
LLM_TOOL_SCHEMA = {
    "name": "choose_action",
    "description": (
        "Pick exactly one action for the AI player to execute this turn. "
        "The `action_id` MUST be copied verbatim from the legal_actions list "
        "in the user message; we will reject any other value."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action_id": {
                "type": "string",
                "description": "The id of the legal action to execute, copied verbatim.",
            },
            "reason": {
                "type": "string",
                "description": "≤40 Chinese characters explaining the strategic intent.",
                "maxLength": 120,
            },
        },
        "required": ["action_id", "reason"],
    },
}


class OpenAIClient:
    """Async LLM client for OpenAI-compatible APIs (DeepSeek, GPT, etc.).

    Implements the same `chat(system, user, *, tool, ...)` signature as
    `LLMClient` so it's a drop-in replacement in `LLMAgent`.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        *,
        timeout: float = 30.0,
        max_retries: int = 2,
    ):
        self.api_key = (
            api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        self.base_url = base_url or os.environ.get(
            "OPENAI_BASE_URL", "https://api.deepseek.com"
        )
        self.model = model or os.environ.get("OPENAI_MODEL", "deepseek-v4-pro")
        self.timeout = timeout
        self.max_retries = max_retries

        import httpx

        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            max_retries=max_retries,
            http_client=httpx.AsyncClient(proxy=None),
        )

    async def chat(
        self,
        system: str,
        user: str,
        *,
        tool: Optional[dict] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """One round-trip to the LLM, expect a function call reply."""
        tool_def = tool or LLM_TOOL_SCHEMA
        openai_tool = _anthropic_to_openai_tool(tool_def)

        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[openai_tool],
                tool_choice={
                    "type": "function",
                    "function": {"name": tool_def["name"]},
                },
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except RateLimitError:
            logger.warning("OpenAI rate limited; will be retried by caller")
            raise
        except (APITimeoutError, APIConnectionError):
            logger.warning("OpenAI API timed out / connection error")
            raise
        except APIError as exc:
            logger.warning("OpenAI API error: %s", exc)
            raise

        choice = resp.choices[0] if resp.choices else None
        if choice is None:
            return LLMResponse(
                text="", tool_name=None, tool_input={},
                stop_reason="empty", usage=TokenUsage(),
            )

        msg = choice.message
        usage = TokenUsage(
            input_tokens=getattr(resp.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "completion_tokens", 0) or 0,
        )
        stop = choice.finish_reason or ""

        # Parse function call
        tool_calls = getattr(msg, "tool_calls", None) or []
        if tool_calls:
            tc = tool_calls[0]
            func = tc.function
            try:
                tool_input = json.loads(func.arguments)
            except json.JSONDecodeError:
                logger.warning("Failed to parse tool arguments: %s", func.arguments[:200])
                tool_input = {}
            return LLMResponse(
                text=msg.content or "",
                tool_name=func.name,
                tool_input=tool_input,
                stop_reason=stop,
                usage=usage,
                raw=resp,
            )

        # No tool call — fallback (try to extract action_id from text)
        text = msg.content or ""
        if text:
            logger.warning(
                "LLM returned text instead of tool_call (finish=%s): %.200s",
                stop, text,
            )
        return LLMResponse(
            text=text, tool_name=None, tool_input={},
            stop_reason=stop, usage=usage, raw=resp,
        )

    async def health_check(self) -> bool:
        """Cheap liveness probe."""
        try:
            await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.model,
                    max_tokens=4,
                    messages=[{"role": "user", "content": "ping"}],
                ),
                timeout=5.0,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI health check failed: %s", exc)
            return False

    async def aclose(self) -> None:
        await self._client.close()
