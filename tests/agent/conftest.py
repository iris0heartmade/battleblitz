"""
Pytest config for the agent tests.

Marks:
  - requires_gpu: skip unless GPU + API key available
  - requires_network: skip in offline CI
"""
from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Auto-skip `requires_gpu` tests when ANTHROPIC_API_KEY isn't set."""
    skip_gpu = pytest.mark.skip(
        reason="ANTHROPIC_API_KEY not set or no network; skipping live LLM test"
    )
    for item in items:
        if "requires_gpu" in item.keywords and not os.environ.get("ANTHROPIC_API_KEY"):
            item.add_marker(skip_gpu)
