"""In-process serialization for writes to one game."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator

from fastapi import Path


@dataclass
class _Entry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


_entries: dict[int, _Entry] = {}
_registry_lock = asyncio.Lock()


@asynccontextmanager
async def game_write_lock(game_id: int) -> AsyncIterator[None]:
    """Serialize one game's writes and discard its lock when no longer used."""
    async with _registry_lock:
        entry = _entries.setdefault(game_id, _Entry())
        entry.users += 1
    try:
        async with entry.lock:
            yield
    finally:
        async with _registry_lock:
            entry.users -= 1
            if entry.users == 0 and not entry.lock.locked():
                _entries.pop(game_id, None)


async def game_write_guard(game_id: int = Path()) -> AsyncIterator[None]:
    async with game_write_lock(game_id):
        yield
