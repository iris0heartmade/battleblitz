"""
Thin async wrapper over the Anthropic Python SDK.

Why a wrapper:
- Force `tool_use` instead of free-form JSON (10x more reliable)
- Centralise retry / timeout / token accounting
- Make it easy to swap in a fake client in tests

The client speaks Anthropic protocol; the upstream base URL may be a proxy
(e.g. minimaxi.com/anthropic) as long as it follows the same wire format.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from anthropic import APIError, APITimeoutError, AsyncAnthropic

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# Response dataclass
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
    """The LLM's reply. Either a tool call (preferred) or free text (fallback)."""
    text: str = ""
    tool_name: Optional[str] = None
    tool_input: dict = field(default_factory=dict)
    stop_reason: str = ""
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw: Any = None  # original message, for debugging


# ----------------------------------------------------------------
# Tool schema (the contract we send the LLM)
# ----------------------------------------------------------------

# Anthropic tool_use is the most reliable way to get structured output.
# The LLM must call exactly one of these; we feed `action_id` and `reason`.
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
                "description": (
                    "ALL your action_ids for this turn, copied verbatim from "
                    "the legal_actions list, separated by ' || '. "
                    "If you have 2 actions: 'move_6_4_6 || attack_7_9'. "
                    "If only 1: just that id. Include all actions_budget items."
                ),
            },
            "reason": {
                "type": "string",
                "description": (
                    "≤40 Chinese characters explaining the strategic intent. "
                    "Will be shown to the human player as a 'thought bubble'."
                ),
                "maxLength": 120,
            },
            "reaction": {
                "type": "string",
                "description": (
                    "一句不超过 25 字的吐槽或自言自语，要像真人玩家在聊天，不是战术报告。"
                    "可以嚣张、抱怨、吐槽、开玩笑、阴阳怪气——有情绪才有灵魂。"
                    "别写「推进战线」「调整阵型」「准备迎战」这种战斗日志式的句子。"
                ),
                "maxLength": 60,
            },
        },
        "required": ["action_id", "reason"],
    },
}


# ----------------------------------------------------------------
# Client
# ----------------------------------------------------------------

class LLMClient:
    """Async client for an Anthropic-compatible chat completion API.

    Configuration is read from constructor args, falling back to env vars:
      ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, ANTHROPIC_MODEL
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
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]
        self.base_url = base_url or os.environ.get(
            "ANTHROPIC_BASE_URL", "https://api.anthropic.com"
        )
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self.timeout = timeout
        self.max_retries = max_retries

        import httpx

        # The Anthropic SDK parses system proxy env vars (ALL_PROXY etc.)
        # in its own __init__ before using our http_client. If ALL_PROXY
        # points to a socks:// proxy (common on dev machines running
        # Clash / v2ray), httpx throws ValueError. Work around by
        # clearing the socks proxies for the lifespan of this call.
        saved_proxies = {}
        for var in ("ALL_PROXY", "all_proxy", "SOCKS_PROXY", "socks_proxy"):
            val = os.environ.pop(var, None)
            if val is not None:
                saved_proxies[var] = val

        try:
            self._client = AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=timeout,
                max_retries=max_retries,
            )
        finally:
            os.environ.update(saved_proxies)

    async def chat(
        self,
        system: str,
        user: str,
        *,
        tool: Optional[dict] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Send one round-trip to the LLM.

        If `tool` is NOT provided, force LLM_TOOL_SCHEMA + tool_use (the
        standard decision-making path).
        If `tool` IS provided (even if it's an empty dict), disable
        tools and get free-text — used for reactions / commentary.
        """
        use_tools = tool is None
        tool_def = tool or LLM_TOOL_SCHEMA

        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

        if use_tools:
            kwargs["tools"] = [LLM_TOOL_SCHEMA]
            kwargs["tool_choice"] = {"type": "any"}

        msg = await self._client.messages.create(**kwargs)

        # Find the first tool_use block
        tool_block = None
        text_parts: list[str] = []
        for block in msg.content:
            if block.type == "tool_use":
                tool_block = block
                break
            if block.type == "text":
                text_parts.append(block.text)

        usage = TokenUsage(
            input_tokens=getattr(msg.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(msg.usage, "output_tokens", 0) or 0,
        )

        if tool_block is not None:
            return LLMResponse(
                text="".join(text_parts),
                tool_name=tool_block.name,
                tool_input=dict(tool_block.input or {}),
                stop_reason=msg.stop_reason or "",
                usage=usage,
                raw=msg,
            )

        # No tool_use — free-text response (reactions, commentary, etc.)
        text = "".join(text_parts)
        logger.debug(
            "LLM free-text response (stop_reason=%s): %.100s",
            msg.stop_reason, text,
        )
        return LLMResponse(
            text=text,
            tool_name=None,
            tool_input={},
            stop_reason=msg.stop_reason or "",
            usage=usage,
            raw=msg,
        )

    async def health_check(self) -> bool:
        """Cheap liveness probe. Returns True if the API responds."""
        try:
            await self._client.messages.create(
                model=self.model,
                max_tokens=8,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except (APIError, APITimeoutError) as exc:
            logger.warning("LLM health check failed: %s", exc)
            return False

    async def aclose(self) -> None:
        await self._client.close()
