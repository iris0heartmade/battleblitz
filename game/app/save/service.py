"""
Save / Suspend service layer.

This is the only place that knows how to:

  * capture a profile + cursor into a ``GameSaveSlot.snapshot``
  * restore a profile + cursor from a ``GameSaveSlot.snapshot``
  * capture a live game state into a ``SuspendState.snapshot``
  * load a Suspend back into the live game state

Route handlers call these methods; they never touch the JSON blobs
directly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.progression.models import PlayerProfile
from app.save.models import (
    GameSaveSlot,
    SaveSlotKind,
    SuspendPoint,
    SuspendState,
)

logger = logging.getLogger(__name__)


# Profile fields that round-trip in a Game save.
#
# 分档策略(对齐 FE8「养成随档 / 解锁账户永久」):
#   - 档案态(下方元组):随读档整体回滚到存档时刻,是 per-playthrough 养成态。
#   - 账户态(NOT here):unlocked_classes / unlocked_commanders /
#     unlocked_cosmetics / rating / current_season —— 账户级永久解锁,
#     不进 snapshot、load 时不覆盖,读旧档也不丢失(避免读旧档打不开
#     需要新解锁的后续章节)。
# 注:unlock_points 是养成货币,必须随档,否则读旧档后残留新章节值 = 串档。
_PROFILE_SNAPSHOT_FIELDS = (
    "hero_campaign_states",
    "mercenary_roster_state",
    "hero_inventory",
    "gold",
    "unlock_points",
    "mainline_commanders",
)


class SaveService:
    """Capture / restore for the save / suspend system.

    Holds the AsyncSession + repos and exposes intent-named methods.
    Mirrors the role of ``ProgressionService`` in app/progression/ —
    one stop for save-system business logic.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Profile (de)hydration ───────────────────────────────

    @staticmethod
    def _snapshot_profile(profile: PlayerProfile) -> dict:
        """Copy all long-term state from a profile into a JSON dict."""
        snap: dict[str, Any] = {}
        for field_name in _PROFILE_SNAPSHOT_FIELDS:
            value = getattr(profile, field_name, None)
            if value is None:
                snap[field_name] = None
            elif hasattr(value, "items"):
                # JSON dict-like — defensive copy
                snap[field_name] = dict(value)
            elif isinstance(value, list):
                snap[field_name] = list(value)
            else:
                snap[field_name] = value
        # Cursor: which mainline + which battle we're on
        snap["active_mainline"] = getattr(profile, "active_mainline", None)
        snap["mainline_progress"] = dict(
            getattr(profile, "mainline_progress", {}) or {}
        )
        return snap

    @staticmethod
    def _restore_profile(profile: PlayerProfile, snap: dict) -> None:
        """Write a JSON dict back onto a profile.

        The profile row is the one we received — the caller is
        responsible for session.flush()/commit.
        """
        for field_name in _PROFILE_SNAPSHOT_FIELDS:
            if field_name in snap:
                value = snap[field_name]
                if value is None:
                    setattr(profile, field_name, None)
                elif isinstance(value, dict):
                    setattr(profile, field_name, dict(value))
                elif isinstance(value, list):
                    setattr(profile, field_name, list(value))
                else:
                    setattr(profile, field_name, value)
        if "active_mainline" in snap:
            profile.active_mainline = snap["active_mainline"]
        if "mainline_progress" in snap:
            profile.mainline_progress = dict(snap["mainline_progress"] or {})

    # ── Manual save (player-driven) ──────────────────────────

    async def save_manual(
        self,
        profile: PlayerProfile,
        slot_index: int,
        mainline_id: str,
        chapter_index: int,
        label: str = "",
    ) -> GameSaveSlot:
        """Write the profile's current state into a manual save slot.

        Replaces any prior save in the same (user, manual, slot_index)
        slot.  Returns the saved row.
        """
        if slot_index not in (0, 1, 2):
            raise ValueError(
                f"slot_index must be 0, 1, or 2 (got {slot_index!r})"
            )
        snap = self._snapshot_profile(profile)
        snap["mainline_id"] = mainline_id
        snap["chapter_index"] = int(chapter_index)
        snap["label"] = label
        snap["saved_at"] = datetime.now(timezone.utc).isoformat()

        existing = await self._get_slot(
            profile.user_name, SaveSlotKind.MANUAL, slot_index,
        )
        if existing is None:
            slot = GameSaveSlot(
                user_name=profile.user_name,
                kind=SaveSlotKind.MANUAL,
                slot_index=slot_index,
                mainline_id=mainline_id,
                chapter_index=chapter_index,
                label=label,
                snapshot=snap,
            )
            self.session.add(slot)
        else:
            existing.mainline_id = mainline_id
            existing.chapter_index = chapter_index
            existing.label = label
            existing.saved_at = datetime.now(timezone.utc)
            existing.snapshot = snap
            slot = existing
        await self.session.flush()
        logger.info(
            "save_manual: user=%s slot=%d mainline=%s chapter_index=%d",
            profile.user_name, slot_index, mainline_id, chapter_index,
        )
        return slot

    # ── Auto-save (system-driven) ───────────────────────────

    async def save_auto(
        self,
        profile: PlayerProfile,
        mainline_id: str,
        chapter_index: int,
        label: str,
    ) -> GameSaveSlot:
        """Write the auto-save slot (overwrite any prior auto-save).

        Called from two checkpoints (see save-design-v2.md §2.3):

          1. ``chapter_end`` — after /advance returns "victory"
             (or after a battle settlement).  Label: "{mainline_id}-结束"
          2. ``prep_complete`` — after /mainlines/{id}/prepare/complete
             (the player signals they're done prepping).  Label:
             "{mainline_id}-准备"
        """
        if not label:
            raise ValueError("label is required for auto-save")
        snap = self._snapshot_profile(profile)
        snap["mainline_id"] = mainline_id
        snap["chapter_index"] = int(chapter_index)
        snap["label"] = label
        snap["saved_at"] = datetime.now(timezone.utc).isoformat()
        snap["auto_kind"] = (
            "chapter_end" if label.endswith("-结束") else
            "prep_complete" if label.endswith("-准备") else
            "unknown"
        )

        existing = await self._get_slot(
            profile.user_name, SaveSlotKind.AUTO, 0,
        )
        if existing is None:
            slot = GameSaveSlot(
                user_name=profile.user_name,
                kind=SaveSlotKind.AUTO,
                slot_index=0,
                mainline_id=mainline_id,
                chapter_index=chapter_index,
                label=label,
                snapshot=snap,
            )
            self.session.add(slot)
        else:
            existing.mainline_id = mainline_id
            existing.chapter_index = chapter_index
            existing.label = label
            existing.saved_at = datetime.now(timezone.utc)
            existing.snapshot = snap
            slot = existing
        await self.session.flush()
        logger.info(
            "save_auto: user=%s label=%r mainline=%s chapter_index=%d",
            profile.user_name, label, mainline_id, chapter_index,
        )
        return slot

    async def clear_auto(self, profile: PlayerProfile) -> None:
        """Drop the auto-save slot.

        Called when the player advances past a checkpoint that
        already produced a newer auto-save (e.g. loading a manual
        save).  Safe to call when no auto-save exists.
        """
        existing = await self._get_slot(
            profile.user_name, SaveSlotKind.AUTO, 0,
        )
        if existing is not None:
            await self.session.delete(existing)
            await self.session.flush()
            logger.info(
                "clear_auto: user=%s (slot wiped)", profile.user_name,
            )

    # ── Load ────────────────────────────────────────────────

    async def load(
        self,
        profile: PlayerProfile,
        *,
        kind: SaveSlotKind,
        slot_index: int,
        abort_in_flight: bool = True,
    ) -> GameSaveSlot:
        """Restore profile + cursor from a Game save slot.

        Side effects:
          * profile fields overwritten from the snapshot
          * if a SuspendState exists for the user, it is invalidated
            (FE8 cascade — see bmsave.c::InvalidateGameSave)
          * the auto-save slot is cleared (the player just picked an
            explicit save, so the previous auto-checkpoint is no
            longer "the newest thing")

        The caller is responsible for committing the session.
        """
        if kind == SaveSlotKind.MANUAL and slot_index not in (0, 1, 2):
            raise ValueError(
                f"manual slot_index must be 0, 1, or 2 (got {slot_index!r})"
            )
        if kind == SaveSlotKind.AUTO and slot_index != 0:
            raise ValueError(
                f"auto slot_index must be 0 (got {slot_index!r})"
            )
        slot = await self._get_slot(profile.user_name, kind, slot_index)
        if slot is None:
            raise LookupError(
                f"no {kind.value} save slot {slot_index} for user "
                f"{profile.user_name!r}"
            )
        # 1. Abort in-flight games before mutating the cursor.
        if abort_in_flight:
            await self._abort_in_flight_games(profile.user_name)
        # 2. Restore profile.
        self._restore_profile(profile, slot.snapshot)
        # 3. FE8 cascade.
        await self._invalidate_suspend(profile.user_name)
        # 4. Manual loads supersede the auto-save slot.
        if kind == SaveSlotKind.MANUAL:
            await self.clear_auto(profile)
        await self.session.flush()
        logger.info(
            "save_load: user=%s kind=%s slot=%d mainline=%s",
            profile.user_name, kind.value, slot_index, slot.mainline_id,
        )
        return slot

    # ── Erase ───────────────────────────────────────────────

    async def erase(
        self, user_name: str, *, kind: SaveSlotKind, slot_index: int,
    ) -> bool:
        """Delete a save slot.  Returns True if anything was removed.

        Cascades:
          * If the erased slot is a Game save, the user's SuspendState
            is invalidated (FE8 invariant — see bmsave.c::InvalidateGameSave).
        """
        slot = await self._get_slot(user_name, kind, slot_index)
        if slot is None:
            return False
        # Determine the linked game slot for the cascade
        await self._invalidate_suspend(user_name)
        await self.session.delete(slot)
        await self.session.flush()
        logger.info(
            "save_erase: user=%s kind=%s slot=%d",
            user_name, kind.value, slot_index,
        )
        return True

    # ── Suspend capture / restore ───────────────────────────

    async def capture_suspend(
        self,
        user_name: str,
        game_id: int,
        mainline_id: str,
        battle_id: str,
        suspend_point: SuspendPoint,
        game_state: dict,
    ) -> SuspendState:
        """Write the live game state into the user's Suspend slot.

        Replaces any prior suspend.  ``game_state`` is whatever the
        caller wants to preserve — typically the full ``GameStateOut``
        payload (tiles, players, units, action log, action data).
        """
        snap = {
            "game_id": game_id,
            "mainline_id": mainline_id,
            "battle_id": battle_id,
            "suspend_point": suspend_point.value,
            "game_state": dict(game_state),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        existing = await self._get_suspend(user_name)
        if existing is None:
            sus = SuspendState(
                user_name=user_name,
                game_id=game_id,
                mainline_id=mainline_id,
                battle_id=battle_id,
                suspend_point=suspend_point,
                snapshot=snap,
            )
            self.session.add(sus)
        else:
            existing.game_id = game_id
            existing.mainline_id = mainline_id
            existing.battle_id = battle_id
            existing.suspend_point = suspend_point
            existing.saved_at = datetime.now(timezone.utc)
            existing.snapshot = snap
            sus = existing
        await self.session.flush()
        logger.info(
            "suspend_capture: user=%s game_id=%d point=%s",
            user_name, game_id, suspend_point.value,
        )
        return sus

    async def load_suspend(self, user_name: str) -> SuspendState:
        """Fetch the user's SuspendState.  Raises LookupError if absent."""
        sus = await self._get_suspend(user_name)
        if sus is None:
            raise LookupError(f"no suspend for user {user_name!r}")
        return sus

    async def clear_suspend(self, user_name: str) -> bool:
        """Drop the user's suspend.  Returns True if anything was removed."""
        sus = await self._get_suspend(user_name)
        if sus is None:
            return False
        await self.session.delete(sus)
        await self.session.flush()
        logger.info("suspend_clear: user=%s", user_name)
        return True

    # ── List ────────────────────────────────────────────────

    async def list_saves(
        self, user_name: str,
    ) -> tuple[list[GameSaveSlot], Optional[SuspendState]]:
        """Return (manual_slots_sorted, auto_slot_or_none, suspend).

        Manual slots are returned in slot_index order; missing slots
        appear as None in the 3-element list.
        """
        rows = (await self.session.execute(
            select(GameSaveSlot).where(GameSaveSlot.user_name == user_name)
            .order_by(GameSaveSlot.kind, GameSaveSlot.slot_index)
        )).scalars().all()
        manual = [None, None, None]
        auto: Optional[GameSaveSlot] = None
        for row in rows:
            if row.kind == SaveSlotKind.MANUAL:
                if 0 <= row.slot_index < 3:
                    manual[row.slot_index] = row
            elif row.kind == SaveSlotKind.AUTO and row.slot_index == 0:
                auto = row
        suspend = await self._get_suspend(user_name)
        return manual, auto, suspend

    # ── Internals ───────────────────────────────────────────

    async def _get_slot(
        self, user_name: str, kind: SaveSlotKind, slot_index: int,
    ) -> Optional[GameSaveSlot]:
        return (await self.session.execute(
            select(GameSaveSlot).where(
                GameSaveSlot.user_name == user_name,
                GameSaveSlot.kind == kind,
                GameSaveSlot.slot_index == slot_index,
            )
        )).scalar_one_or_none()

    async def _get_suspend(self, user_name: str) -> Optional[SuspendState]:
        return (await self.session.execute(
            select(SuspendState).where(SuspendState.user_name == user_name)
        )).scalar_one_or_none()

    async def _invalidate_suspend(self, user_name: str) -> None:
        """Drop the user's suspend, logging why (no-op if absent)."""
        sus = await self._get_suspend(user_name)
        if sus is not None:
            await self.session.delete(sus)
            await self.session.flush()
            logger.info(
                "suspend_cascade: user=%s (cleared by game save load/erase)",
                user_name,
            )

    async def _abort_in_flight_games(self, user_name: str) -> int:
        """Force-finish any in-flight (``status == "playing"``) games
        belonging to this user.

        Called by ``load()`` to prevent DB-leaking orphans when a
        player loads a save that points at a different cursor state.
        The aborted games stay in the DB so the player can still
        find them in the open-mode save list ("📚 存档管理"),
        but they no longer count as the player's "current battle".

        Returns the number of games aborted (0 if none).
        """
        # Imported here to avoid a circular import: save.models
        # references PlayerProfile, and PlayerProfile is defined
        # in progression.models.
        from app.models import Game, Player

        rows = (await self.session.execute(
            select(Game)
            .join(Player, Player.game_id == Game.id)
            .where(
                Game.status == "playing",
                Player.user_name == user_name,
                Player.is_ai == False,  # noqa: E712
                Player.is_spectator == False,  # noqa: E712
            )
        )).scalars().all()
        for game in rows:
            game.status = "aborted"
        if rows:
            await self.session.flush()
            logger.info(
                "save_load aborted in-flight games: user=%s count=%d ids=%s",
                user_name, len(rows), [g.id for g in rows],
            )
        return len(rows)


__all__ = ["SaveService"]
