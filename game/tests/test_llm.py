"""
Unit tests for the LLM client abstraction.

Covers:
  - safe_complete timeout behavior
  - safe_complete exception swallowing
  - safe_complete returning None when no client registered
  - set_llm_client / get_llm_client round-trip
  - Mock client conforms to LLMClient Protocol
"""
from __future__ import annotations

import asyncio

import pytest

from app.llm import (
    LLMClient,
    get_llm_client,
    safe_complete,
    set_llm_client,
)


# ============================================================
# Test doubles
# ============================================================

class _SlowClient:
    """Takes too long; used to test timeout behavior."""

    def __init__(self, delay: float = 5.0, text: str = "late") -> None:
        self.delay = delay
        self.text = text
        self.calls = 0

    async def complete(self, prompt, *, max_tokens, model=None, temperature=0.7):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return self.text


class _ExplodingClient:
    """Always raises; used to test exception handling."""

    async def complete(self, prompt, *, max_tokens, model=None, temperature=0.7):
        raise RuntimeError("simulated LLM outage")


class _CountingClient:
    """Returns a fixed string; records every call."""

    def __init__(self, text: str = "mock answer") -> None:
        self.text = text
        self.calls: list[dict] = []

    async def complete(self, prompt, *, max_tokens, model=None, temperature=0.7):
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        return self.text


# ============================================================
# set / get round-trip
# ============================================================

@pytest.mark.unit
class TestRegistry:
    def setup_method(self):
        # Save and restore around each test to avoid polluting global state.
        from app.llm import client as _mod
        self._saved = _mod._llm_client
        _mod._llm_client = None

    def teardown_method(self):
        from app.llm import client as _mod
        _mod._llm_client = self._saved

    def test_get_returns_none_when_unset(self):
        assert get_llm_client() is None

    def test_set_then_get(self):
        c = _CountingClient()
        set_llm_client(c)
        assert get_llm_client() is c

    def test_set_replaces_previous(self):
        a, b = _CountingClient("a"), _CountingClient("b")
        set_llm_client(a)
        set_llm_client(b)
        assert get_llm_client() is b


# ============================================================
# safe_complete
# ============================================================

@pytest.mark.unit
class TestSafeComplete:
    def setup_method(self):
        from app.llm import client as _mod
        self._saved = _mod._llm_client
        _mod._llm_client = None

    def teardown_method(self):
        from app.llm import client as _mod
        _mod._llm_client = self._saved

    async def test_returns_none_when_no_client(self):
        result = await safe_complete("hi", max_tokens=100)
        assert result is None

    async def test_returns_text_on_success(self):
        c = _CountingClient("hello world")
        set_llm_client(c)
        result = await safe_complete("say hi", max_tokens=50, timeout=2.0)
        assert result == "hello world"
        assert len(c.calls) == 1
        assert c.calls[0]["max_tokens"] == 50

    async def test_timeout_returns_none(self):
        c = _SlowClient(delay=5.0)
        set_llm_client(c)
        result = await safe_complete("hi", max_tokens=50, timeout=0.1)
        assert result is None
        # The slow client WAS called (timeout is downstream)
        assert c.calls == 1

    async def test_exception_returns_none(self):
        c = _ExplodingClient()
        set_llm_client(c)
        result = await safe_complete("hi", max_tokens=50, timeout=1.0)
        assert result is None

    async def test_explicit_client_overrides_global(self):
        global_client = _CountingClient("global")
        local_client = _CountingClient("local")
        set_llm_client(global_client)
        result = await safe_complete(
            "hi", max_tokens=50,
            client=local_client, timeout=2.0,
        )
        assert result == "local"
        assert len(local_client.calls) == 1
        assert len(global_client.calls) == 0  # not used


# ============================================================
# Protocol conformance
# ============================================================

@pytest.mark.unit
class TestProtocolConformance:
    def test_counting_client_satisfies_protocol(self):
        c = _CountingClient()
        # runtime_checkable lets us use isinstance against LLMClient.
        assert isinstance(c, LLMClient)

    def test_slow_client_satisfies_protocol(self):
        c = _SlowClient()
        assert isinstance(c, LLMClient)

    def test_exploding_client_satisfies_protocol(self):
        c = _ExplodingClient()
        assert isinstance(c, LLMClient)
