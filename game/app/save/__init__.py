"""
Save / suspend package for BattleBlitz.

Implements FE8-inspired dual-slot save model:

  * ``GameSaveSlot``  — formal mainline save. Two kinds:
                        - manual: 3 slots per user, player-driven
                        - auto:   1 slot per user, written by the
                                  system at two checkpoints:
                                    1. After chapter settlement
                                       (label "xx章-结束")
                                    2. After pre-battle prep completes
                                       (label "xx章-准备")
  * ``SuspendState``  — single mid-battle interrupt slot. Captures
                        the live Game state at one of the
                        SUSPEND_POINT_* checkpoints (phase change,
                        player idle, during action, manual).

Cross-references:
  * Spec:    docs/superpowers/specs/2026-07-13-dual-track-...md
  * Design:  docs/superpowers/plans/2026-07-13-save-design-v2.md
  * Source:  refs/fireemblem8u/include/bmsave.h  (SAVEBLOCK_KIND_*)
             refs/fireblem8u/src/savemenu.c      (SaveMenuInit / RESUME)
"""
from app.save.models import (
    GameSaveSlot,
    SuspendState,
    SaveSlotKind,
    SuspendPoint,
)
from app.save.service import SaveService
from app.save.schemas import (
    AutoSaveCheckpointOut,
    GameSaveSlotOut,
    LoadSuspendOut,
    LoadSuspendRequest,
    PrepCompleteRequest,
    SaveEraseOut,
    SaveEraseRequest,
    SaveListOut,
    SaveLoadOut,
    SaveLoadRequest,
    SaveManualOut,
    SaveManualRequest,
    SuspendOut,
    SuspendRequest,
    SuspendStateOut,
)

__all__ = [
    # models
    "GameSaveSlot",
    "SuspendState",
    "SaveSlotKind",
    "SuspendPoint",
    "SaveService",
    # wire formats
    "AutoSaveCheckpointOut",
    "GameSaveSlotOut",
    "LoadSuspendOut",
    "LoadSuspendRequest",
    "PrepCompleteRequest",
    "SaveEraseOut",
    "SaveEraseRequest",
    "SaveListOut",
    "SaveLoadOut",
    "SaveLoadRequest",
    "SaveManualOut",
    "SaveManualRequest",
    "SuspendOut",
    "SuspendRequest",
    "SuspendStateOut",
]
