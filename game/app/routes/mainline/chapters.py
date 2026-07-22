"""Chapter listing + detail + dialogue endpoints.

Endpoints owned here:
  * GET /mainlines                        — :func:`list_mainlines_endpoint`
  * GET /mainlines/dialogue               — :func:`get_dialogue`
  * GET /mainlines/{mainline_id}          — :func:`get_mainline_detail`

Helper modules used:
  * :func:`_chain_for`, :func:`_current_mainline_for_user`,
    :func:`_game_root` from ``_common``
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.battle_config import battle_bgm_meta
from app.mainline import (
    MainlineNotFound,
    MainlineValidationError,
    list_mainlines,
)
from app.mainline.schemas import (
    BattleBgmMeta,
    BattlePreview,
    MainlineDetailOut,
)

from ._common import (
    _GAME_ROOT,
    _battle_track_id,
    _chain_for,
    _current_mainline_for_user,
)

logger = logging.getLogger(__name__)

# Each submodule carries the full ``/mainlines`` prefix so that
# ``router.include_router(...)`` in ``__init__.py`` does not stack
# another prefix on top — that combination trips FastAPI's
# "Prefix and path cannot be both empty" check.  The parent
# ``__init__.py`` exposes a no-prefix aggregator that just
# collects these sub-routers.
router = APIRouter(prefix="/mainlines", tags=["mainline"])


# ============================================================
# GET /mainlines — list
# ============================================================


@router.get("", response_model=List)
async def list_mainlines_endpoint(
    user_name: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Return mainlines for the lobby view.

    Without ``user_name`` this remains a pure all-chapter listing for
    tools and tests. With ``user_name`` the temporary test campaign is
    exposed as a Fire Emblem-style current chapter: only the first
    uncleared test chapter appears.
    """
    logger.debug("list_mainlines entry")
    items = list_mainlines()
    if user_name:
        # For every declared campaign chain, only the first uncleared
        # chapter is visible. Chains with no progress show their first
        # chapter; chains the user has finished collapse to the final
        # chapter (current chapter semantics).
        filtered: list = []
        for item in items:
            chain = _chain_for(item.id)
            if chain is None:
                filtered.append(item)
                continue
            allowed = await _current_mainline_for_user(session, user_name, chain)
            if item.id == allowed:
                filtered.append(item)
        items = filtered
    logger.info("list_mainlines ok: count=%d", len(items))
    return items


# ============================================================
# GET /mainlines/dialogue?path=...
# ============================================================


@router.get("/dialogue")
async def get_dialogue(path: str = Query(...)):
    """Serve a dialogue JSON file by relative path.

    Security:
      * Rejects any path containing ``..`` segments.
      * Resolves the path and verifies it stays inside ``game/``.

    Returns the raw JSON content of the file (a ``{"scenes": [...]}``
    object or whatever the designer authored).
    """
    logger.debug("get_dialogue entry: path=%s", path)
    if ".." in path.split("/"):
        logger.warning("get_dialogue rejected: path=%s reason=traversal", path)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "invalid path"
        )
    base = _GAME_ROOT.resolve()
    candidate = (base / path).resolve()
    # Ensure the resolved path is still under game/.
    try:
        candidate.relative_to(base)
    except ValueError:
        logger.warning("get_dialogue rejected: path=%s reason=escape", path)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "invalid path"
        )
    if not candidate.exists() or not candidate.is_file():
        logger.warning("get_dialogue not found: path=%s", path)
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"dialogue not found: {path}"
        )
    try:
        raw = candidate.read_text(encoding="utf-8")
    except OSError as exc:
        logger.exception("get_dialogue read failed: path=%s", path)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"cannot read {path}: {exc}",
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.exception("get_dialogue parse failed: path=%s", path)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"{path} is not valid JSON: {exc}",
        )
    scene_n = 0
    if isinstance(payload, dict) and isinstance(payload.get("scenes"), list):
        scene_n = len(payload["scenes"])
    elif isinstance(payload, list):
        scene_n = len(payload)
    logger.info("get_dialogue ok: path=%s scenes=%d", path, scene_n)
    return payload


# ============================================================
# GET /mainlines/{mainline_id}
# ============================================================


@router.get("/{mainline_id}", response_model=MainlineDetailOut)
async def get_mainline_detail(mainline_id: str) -> MainlineDetailOut:
    """Return full mainline detail (for the lobby detail panel)."""
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    logger.debug("get_mainline_detail entry: mainline=%s", mainline_id)
    try:
        ml = mainline_pkg.load_mainline(mainline_id)
    except MainlineNotFound as exc:
        logger.warning("get_mainline_detail not found: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except MainlineValidationError as exc:
        logger.exception("get_mainline_detail invalid: mainline=%s", mainline_id)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    out = MainlineDetailOut(
        id=ml.id,
        title=ml.title,
        synopsis=ml.synopsis,
        cover_art=ml.cover_art,
        required_classes=list(ml.required_classes),
        battle_count=len(ml.battles),
        battles=[
            BattlePreview(
                id=b.id,
                title=b.title,
                win_condition=b.win_condition,
                map_id=b.map_id,
                # P2.9 — surface catalogue metadata per battle so the
                # front-end can render "BGM: <title>" in the lobby
                # detail panel. None when the battle has no BGM or
                # the track_id isn't registered. We deliberately use
                # the battle's track_id (not the registry default) so
                # per-battle overrides show through.
                bgm=(
                    BattleBgmMeta.model_validate(
                        battle_bgm_meta(_battle_track_id(b))
                    )
                    if _battle_track_id(b) else None
                ),
            )
            for b in ml.battles
        ],
        dialogue_keys=list(ml.dialogues.keys()),
    )
    logger.info(
        "get_mainline_detail ok: mainline=%s battles=%d dialogues=%d",
        mainline_id, len(ml.battles), len(ml.dialogues),
    )
    return out
