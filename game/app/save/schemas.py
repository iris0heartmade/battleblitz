"""
Pydantic v2 wire formats for the save / suspend API.

Stable across the implementation — route handlers return these, the
front-end parses them.  Internal ORM rows (``GameSaveSlot``,
``SuspendState``) are not exposed directly; the route layer projects
to these models first.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# GameSaveSlot
# ============================================================


class GameSaveSlotOut(BaseModel):
    """One row in the save slot list."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: Literal["manual", "auto"]
    slot_index: int
    mainline_id: str
    chapter_index: int
    # "chapter_01-结束" or "chapter_01-准备" for auto; "" for manual.
    label: str
    saved_at: datetime
    # Echoed for FE convenience; large JSON blobs aren't inlined.
    has_snapshot: bool = True


# ============================================================
# SuspendState
# ============================================================


class SuspendStateOut(BaseModel):
    """The single mid-battle interrupt slot, if present."""
    model_config = ConfigDict(from_attributes=True)

    user_name: str
    game_id: Optional[int] = None
    mainline_id: Optional[str] = None
    battle_id: Optional[str] = None
    suspend_point: Literal[
        "phase_change", "player_idle", "during_action",
        "manual", "disconnect", "chapter_end",
    ]
    saved_at: datetime


# ============================================================
# List endpoint
# ============================================================


class SaveListOut(BaseModel):
    """Response shape for ``GET /saves?user_name=...``.

    The 3 manual slot positions are always present (``null`` if
    empty), so the front-end can render fixed-position slot cards.
    The auto slot is also always present (one position).
    """
    user_name: str
    manual_slots: list[Optional[GameSaveSlotOut]]   # length 3
    auto_slot: Optional[GameSaveSlotOut] = None
    suspend: Optional[SuspendStateOut] = None


# ============================================================
# Manual save
# ============================================================


class SaveManualRequest(BaseModel):
    """Body for ``POST /saves/save``."""
    user_name: str = Field(min_length=1, max_length=64)
    slot_index: int = Field(ge=0, le=2)
    mainline_id: str = Field(min_length=1, max_length=64)
    chapter_index: int = Field(ge=0, le=32)
    label: str = Field(default="", max_length=64)


class SaveManualOut(BaseModel):
    ok: bool = True
    slot: GameSaveSlotOut


# ============================================================
# Load
# ============================================================


class SaveLoadRequest(BaseModel):
    """Body for ``POST /saves/load``."""
    user_name: str = Field(min_length=1, max_length=64)
    kind: Literal["manual", "auto"]
    slot_index: int = Field(ge=0, le=2)


class SaveLoadOut(BaseModel):
    """Response after restoring from a save slot.

    The profile and mainline cursor are restored server-side.  The
    front-end should refetch the mainline list and current cursor
    after a successful load — the response only echoes the meta
    fields needed for confirmation.
    """
    ok: bool = True
    mainline_id: str
    chapter_index: int
    label: str
    # If a manual save was loaded, the auto-save was cleared.
    auto_cleared: bool


# ============================================================
# Load suspend (resume from a mid-battle interrupt)
# ============================================================


class LoadSuspendRequest(BaseModel):
    """Body for ``POST /saves/load_suspend``.

    Pairs with the WS onclose auto-suspend: when the player
    reconnects, they hit this endpoint to learn the game_id of
    the suspended battle, then navigate to ``/games/{game_id}/state``
    to pick up where they left off.
    """
    user_name: str = Field(min_length=1, max_length=64)


class LoadSuspendOut(BaseModel):
    """Response after loading a suspend slot.

    The FE should:
      1. Read ``game_id`` and fetch ``/games/{id}/state`` to render
         the board at the same moment the player left it.
      2. Optionally restore the mainline cursor to ``mainline_id``
         and ``battle_id`` so subsequent ``/start`` / ``/advance``
         calls target the right chapter/battle.

    ``aborted_game_count`` is the number of in-flight games that
    were force-aborted so the suspend's game can be re-entered
    cleanly.  The FE should mention this if > 0 so the player
    knows their old battle is no longer current.
    """
    ok: bool = True
    user_name: str
    game_id: Optional[int] = None
    mainline_id: Optional[str] = None
    battle_id: Optional[str] = None
    suspend_point: str
    saved_at: datetime
    aborted_game_count: int


# ============================================================
# Erase
# ============================================================


class SaveEraseRequest(BaseModel):
    """Body for ``POST /saves/erase``."""
    user_name: str = Field(min_length=1, max_length=64)
    kind: Literal["manual", "auto"]
    slot_index: int = Field(ge=0, le=2)


class SaveEraseOut(BaseModel):
    ok: bool = True
    erased: bool
    # If a save was erased, the cascade may have wiped the suspend.
    suspend_cleared: bool


# ============================================================
# Auto-save checkpoint feedback
# ============================================================


class AutoSaveCheckpointOut(BaseModel):
    """Response from the prep-complete / chapter-end auto-save
    endpoints, with the ``label`` that the FE uses to render the
    "自动存档中…… 自动存档完毕" toast.
    """
    ok: bool = True
    # "chapter_01-结束" or "chapter_01-准备"
    label: str
    # "chapter_end" or "prep_complete"
    auto_kind: str
    saved_at: datetime


# ============================================================
# Prep complete (the "Ready" button)
# ============================================================


class PrepCompleteRequest(BaseModel):
    """Body for ``POST /mainlines/{id}/prepare/complete``."""
    user_name: str = Field(min_length=1, max_length=64)


# ============================================================
# Manual suspend
# ============================================================


class SuspendRequest(BaseModel):
    """Body for ``POST /games/{id}/suspend``."""
    user_name: str = Field(min_length=1, max_length=64)


class SuspendOut(BaseModel):
    ok: bool = True
    saved_at: datetime


# ============================================================
# Discard suspend
# ============================================================


class DiscardSuspendOut(BaseModel):
    """Response from ``DELETE /saves/suspend?user_name=...``.

    ``cleared`` distinguishes "suspend existed and was removed" from
    "no suspend existed" — the second is not an error (the operation
    is idempotent) but the client may want to surface a different
    toast for it.
    """
    ok: bool = True
    cleared: bool


__all__ = [
    "GameSaveSlotOut",
    "SuspendStateOut",
    "SaveListOut",
    "SaveManualRequest",
    "SaveManualOut",
    "SaveLoadRequest",
    "SaveLoadOut",
    "SaveEraseRequest",
    "SaveEraseOut",
    "AutoSaveCheckpointOut",
    "PrepCompleteRequest",
    "SuspendRequest",
    "SuspendOut",
    "DiscardSuspendOut",
]
