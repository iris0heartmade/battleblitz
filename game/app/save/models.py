"""
ORM models for the save / suspend system.

Two tables, both keyed on ``user_name``:

  * ``game_save_slots`` — formal mainline saves. Up to 4 rows per
    user: 3 manual (slot_index 0/1/2) + 1 auto (slot_index 0, kind=auto).
  * ``suspend_states``  — single mid-battle interrupt. One row per user.

Why not one combined table?  Manual and auto saves are functionally
identical except for the *kind* tag and the *slot index* range.  We
keep them in the same table to avoid duplicating the snapshot
column.  The ``kind`` column discriminates them.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SAEnum,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models import _utcnow  # reuse existing tz-aware helper


# ============================================================
# Enums
# ============================================================


class SaveSlotKind(str, enum.Enum):
    """Distinguishes player-driven vs system-driven Game saves.

    * ``manual`` — written via POST /saves/save (3 slots per user).
    * ``auto``   — written by the engine at chapter-end and after
                   pre-battle prep (1 slot per user, overwritten).
    """
    MANUAL = "manual"
    AUTO = "auto"


class SuspendPoint(str, enum.Enum):
    """Where in the game loop the suspend was written.

    Mirrors FE8's ``SUSPEND_POINT_*`` constants but trimmed to the
    points BattleBlitz actually uses.  See save-design-v2.md §2.3.
    """
    PHASE_CHANGE = "phase_change"     # player → enemy / enemy → ally
    PLAYER_IDLE = "player_idle"       # player's turn, waiting for input
    DURING_ACTION = "during_action"   # mid-action (move/attack/...)
    MANUAL = "manual"                 # player pressed "暂离"
    DISCONNECT = "disconnect"         # WS onclose / beforeunload
    CHAPTER_END = "chapter_end"       # written when /advance returns victory


# ============================================================
# GameSaveSlot
# ============================================================


class GameSaveSlot(Base):
    """A formal mainline save snapshot.

    ``snapshot`` is a JSON blob with everything needed to restore the
    profile and mainline cursor:

      * ``hero_campaign_states``
      * ``mercenary_roster_state``
      * ``hero_inventory``
      * ``gold``, ``rating``, ``unlocked_classes``
      * ``unlocked_commanders``, ``mainline_commanders``
      * ``active_mainline``, ``mainline_progress`` (cursor)
      * ``mainline_id``, ``chapter_index`` (denormalised for UI)
      * ``label`` (e.g. "chapter_01-结束", "chapter_01-准备")

    Note: ``snapshot`` does NOT include any live ``Game`` row, so
    loading a save drops the player at the "ready to start" state —
    no in-flight battle.  This is by design: a Save is a *post-chapter*
    checkpoint, not a *mid-battle* snapshot (the latter is what
    ``SuspendState`` is for).
    """
    __tablename__ = "game_save_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[SaveSlotKind] = mapped_column(
        SAEnum(SaveSlotKind, name="save_slot_kind"),
        nullable=False, default=SaveSlotKind.MANUAL,
    )
    # 0/1/2 for manual; 0 for auto.  Unique per (user, kind).
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Which mainline the save is for (e.g. "chapter_01_steel_rebellion").
    mainline_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Battle index within the mainline (0-based, == len(battles) if cleared).
    chapter_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Human-readable label, e.g. "chapter_01-结束" or "chapter_01-准备".
    label: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    saved_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow,
    )
    # Full JSON snapshot of profile + mainline cursor.
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "user_name", "kind", "slot_index",
            name="uq_save_slot_per_user_kind",
        ),
        Index("ix_save_user_kind", "user_name", "kind"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<GameSaveSlot id={self.id} user={self.user_name!r} "
            f"kind={self.kind.value} slot={self.slot_index} "
            f"mainline={self.mainline_id!r} chapter_index={self.chapter_index}>"
        )


# ============================================================
# SuspendState
# ============================================================


class SuspendState(Base):
    """Single mid-battle interrupt slot.  One row per user.

    ``snapshot`` is a JSON blob with the live Game state captured at
    the ``suspend_point``:

      * ``game_id``  — the live Game row (status="playing")
      * ``battle_id`` — e.g. "battle_01"
      * full game state — see ``SaveService.capture_suspend``

    Critical invariant: the snapshot does **NOT** include
    ``hero_campaign_states`` or any other long-term hero data.  A
    Suspend captures *the battle as it stands*, not *the campaign*.
    Loading a Suspend drops the player back into the same battle
    state but does not write back any long-term progression.
    """
    __tablename__ = "suspend_states"

    # user_name is the primary key — at most one suspend per user.
    user_name: Mapped[str] = mapped_column(
        String(64), primary_key=True,
    )
    # The Game row this suspend belongs to.  May go stale (e.g. if
    # the underlying game is force-ended); the loader should
    # re-validate before resuming.
    game_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    battle_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mainline_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    suspend_point: Mapped[SuspendPoint] = mapped_column(
        SAEnum(SuspendPoint, name="suspend_point"),
        nullable=False, default=SuspendPoint.MANUAL,
    )
    saved_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow,
    )
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SuspendState user={self.user_name!r} game_id={self.game_id} "
            f"battle_id={self.battle_id!r} point={self.suspend_point.value}>"
        )


__all__ = [
    "SaveSlotKind",
    "SuspendPoint",
    "GameSaveSlot",
    "SuspendState",
]
