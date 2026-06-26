"""Mainline (campaign) data subsystem.

A mainline is a JSON-described sequence of battles interleaved with
dialogue scripts. The loader validates against `schemas.Mainline`
and caches parsed objects in-process.

Pure-JSON loader for V1 — no Python hooks. A `loader_hook` field may
be reserved for V2 (post-launch extensibility) but is ignored now.
"""
from app.mainline.loader import (
    MainlineNotFound,
    MainlineValidationError,
    clear_cache,
    list_mainlines,
    load_mainline,
)

__all__ = [
    "MainlineNotFound",
    "MainlineValidationError",
    "clear_cache",
    "list_mainlines",
    "load_mainline",
]
