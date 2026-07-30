"""Post-battle shop endpoints.

Endpoints owned here:
  * GET  /mainlines/{mainline_id}/shop                  — :func:`get_post_battle_shop`
  * POST /mainlines/{mainline_id}/shop/purchase        — :func:`purchase_post_battle_shop_item`
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.item_catalog import get_item, load_shop
from app.mainline import MainlineNotFound
from app.mainline.schemas import (
    MainlineShopOut,
    MainlineShopPurchaseOut,
    MainlineShopPurchaseRequest,
)
from app.progression import ProgressionService

from ._common import _load_profile

logger = logging.getLogger(__name__)

# Each submodule carries the full ``/mainlines`` prefix.
router = APIRouter(prefix="/mainlines", tags=["mainline"])


@router.get("/{mainline_id}/shop", response_model=MainlineShopOut)
async def get_post_battle_shop(
    mainline_id: str,
    user_name: str = Query(..., min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
) -> MainlineShopOut:
    """Return the JSON-authored post-battle stock and campaign gold."""
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    try:
        mainline_pkg.load_mainline(mainline_id)
        items = load_shop("post_battle")
    except (MainlineNotFound, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    profile = await _load_profile(session, user_name)
    return MainlineShopOut(
        mainline_id=mainline_id,
        gold=int(profile.gold),
        items=[item.payload() for item in items],
    )


@router.post(
    "/{mainline_id}/shop/purchase",
    response_model=MainlineShopPurchaseOut,
)
async def purchase_post_battle_shop_item(
    mainline_id: str,
    body: MainlineShopPurchaseRequest,
    session: AsyncSession = Depends(get_session),
) -> MainlineShopPurchaseOut:
    import app.routes.mainline as mainline_pkg  # late-bound load_mainline

    try:
        mainline_pkg.load_mainline(mainline_id)
        stock_ids = {item.item_id for item in load_shop("post_battle")}
    except (MainlineNotFound, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    item = get_item(body.item_id)
    if item is None or item.item_id not in stock_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item is not sold by this shop")
    svc = ProgressionService(session)
    try:
        result = await svc.purchase_hero_inventory_item(
            body.user_name, item.item_id, unit_price=item.price, quantity=body.quantity,
        )
    except ValueError:
        raise HTTPException(status.HTTP_409_CONFLICT, "not enough campaign gold")
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    gold_remaining, inventory_count = result
    return MainlineShopPurchaseOut(
        item_id=item.item_id,
        quantity=body.quantity,
        inventory_count=inventory_count,
        gold_remaining=gold_remaining,
    )
