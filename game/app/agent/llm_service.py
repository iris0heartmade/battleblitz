"""
Unified LLM service manager.

One entry-point (`get_client()`) gives you a working client for whatever
LLM provider is configured. Handles three concerns:

1. **Protocol selection** — Anthropic SDK or OpenAI-compatible SDK, picked
   from `LLM_PROTOCOL` env or auto-detected from `OPENAI_BASE_URL`.
2. **Provider fallback chain** — try local llama.cpp first, fall back to
   the cloud API provider. Auto-detects which is reachable at startup.
3. **Single API surface** — all LLM clients expose `chat(system, user, ...)`
   returning the same `LLMResponse` shape, so the rest of the agent
   doesn't care which backend is in use.

Auto-detection rules (applied in order):
- If `LLM_FORCE=local`   → always use the local llama.cpp (OpenAI client)
- If `LLM_FORCE=cloud`   → always use the cloud provider
- If `LLM_FORCE` unset   → at startup, try the local OpenAI base URL.
  If it responds, use it. Otherwise fall back to whatever cloud
  credentials are present in env vars (Anthropic first, then OpenAI
  pointing at the cloud).

The chosen backend is cached for the lifetime of the process; flip the
env var and restart to change.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# Backend constants
# ----------------------------------------------------------------

BACKEND_LOCAL_OPENAI = "local-openai"   # llama.cpp / vLLM / Ollama
BACKEND_CLOUD_ANTHROPIC = "cloud-anthropic"
BACKEND_CLOUD_OPENAI = "cloud-openai"


# ----------------------------------------------------------------
# Reachability probe
# ----------------------------------------------------------------

def _is_local_reachable(base_url: str, timeout: float = 0.8) -> bool:
    """Synchronous TCP probe to see if the local LLM server is up.

    Cheap — just connect the socket, no HTTP request. If the server
    is dead / wrong port / wrong host, this returns False fast.
    """
    import socket
    from urllib.parse import urlparse

    try:
        parsed = urlparse(base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


async def _async_is_local_reachable(base_url: str, timeout: float = 0.8) -> bool:
    """Async version of the reachability probe (for use inside async code)."""
    import asyncio
    import socket
    from urllib.parse import urlparse

    def _probe():
        try:
            parsed = urlparse(base_url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, ValueError):
            return False
    return await asyncio.get_event_loop().run_in_executor(None, _probe)


# ----------------------------------------------------------------
# Backend selection
# ----------------------------------------------------------------

def _choose_backend() -> str:
    """Decide which backend to use based on env + local reachability.

    Runs synchronously at startup; safe to call before the event loop runs.
    """
    force = os.environ.get("LLM_FORCE", "").strip().lower()
    if force == "local":
        logger.info("LLM_FORCE=local → using llama.cpp")
        return BACKEND_LOCAL_OPENAI
    if force == "cloud":
        # Pick whichever cloud protocol has creds
        if os.environ.get("ANTHROPIC_API_KEY"):
            return BACKEND_CLOUD_ANTHROPIC
        if os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_BASE_URL"):
            return BACKEND_CLOUD_OPENAI
        logger.warning("LLM_FORCE=cloud but no cloud credentials in env")
        return BACKEND_CLOUD_ANTHROPIC   # will likely fail at first call

    # Auto: try local first.
    local_url = os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:8080/v1")
    if _is_local_reachable(local_url):
        logger.info("Local LLM reachable at %s → using llama.cpp", local_url)
        return BACKEND_LOCAL_OPENAI
    logger.info("Local LLM not reachable at %s — falling back to cloud", local_url)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return BACKEND_CLOUD_ANTHROPIC
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_BASE_URL"):
        return BACKEND_CLOUD_OPENAI
    logger.warning("No LLM credentials at all — agent will use rules AI fallback")
    return BACKEND_CLOUD_ANTHROPIC   # will fail at first call, rules AI kicks in


# ----------------------------------------------------------------
# Client factory
# ----------------------------------------------------------------

_cached_client = None
_cached_backend: Optional[str] = None


def get_client(force_refresh: bool = False):
    """Return the singleton LLM client (auto-detects backend on first call)."""
    global _cached_client, _cached_backend

    if _cached_client is not None and not force_refresh:
        return _cached_client

    backend = _choose_backend()
    _cached_backend = backend

    if backend == BACKEND_LOCAL_OPENAI:
        from app.agent.openai_client import OpenAIClient
        # OpenAIClient reads OPENAI_BASE_URL/OPENAI_MODEL from env, which
        # the user should have set to point at llama.cpp.
        _cached_client = OpenAIClient()
    elif backend == BACKEND_CLOUD_OPENAI:
        from app.agent.openai_client import OpenAIClient
        _cached_client = OpenAIClient()
    else:  # BACKEND_CLOUD_ANTHROPIC
        from app.agent.llm_client import LLMClient
        _cached_client = LLMClient()

    logger.info(
        "LLM service ready: backend=%s url=%s model=%s",
        backend,
        getattr(_cached_client, "base_url", "?"),
        getattr(_cached_client, "model", "?"),
    )
    return _cached_client


def get_backend_name() -> str:
    """Return the active backend name (for logging / UI)."""
    return _cached_backend or "(not initialized)"


def reset() -> None:
    """Drop the cached client (testing helper)."""
    global _cached_client, _cached_backend
    _cached_client = None
    _cached_backend = None


# ----------------------------------------------------------------
# Status report
# ----------------------------------------------------------------

def status_report() -> dict:
    """Return a dict for the /healthz or debug endpoint to expose."""
    return {
        "backend": get_backend_name(),
        "model": getattr(_cached_client, "model", None) if _cached_client else None,
        "base_url": getattr(_cached_client, "base_url", None) if _cached_client else None,
        "local_target": os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:8080/v1"),
        "local_reachable": _is_local_reachable(
            os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:8080/v1")
        ),
        "has_anthropic_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "has_openai_key": bool(os.environ.get("OPENAI_API_KEY")),
    }


# Bring asyncio in for the async probe
import asyncio
