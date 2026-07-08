"""
Hero metadata routes (P2.6+).

Endpoints (mounted at the root by ``app/main.py``):

  GET /heroes              — list every registered hero with their
                             base-class + stat overrides + art paths.
                             The frontend fetches this once at boot
                             to populate the dialog speaker lookup
                             and the per-tile sprite resolver.

The route is a thin passthrough over ``app.classes.heroes``.  No
DB access — heroes are code-defined content.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/heroes", tags=["heroes"])


# Public path under which hero art is served.  Kept in sync with the
# StaticFiles mount in ``app/main.py`` (which exposes
# ``game/app/web`` at ``/ui``).
HERO_ASSET_URL = "/ui/assets/heroes"


@router.get("")
async def list_heroes() -> List[dict]:
    """Return metadata for every registered hero.

    Shape per entry::

        {
            "hero_id":       "yun",
            "display_cn":    "云",
            "base_class_id": "swordsman",
            "hp":            45,   # resolved (override or base)
            "atk":           20,
            "def_":          11,
            "matk":          4,
            "mdef":          4,
            "mov":           5,
            "sprite_url":    "/ui/assets/heroes/yun.png",
            "portrait_url":  "/ui/assets/heroes/portrait_yun.png",
            "crest_url":     "/ui/assets/heroes/crest_yun.png",
            "dialogue_name": "云",
        }

    The frontend caches the response and uses ``display_cn`` /
    ``dialogue_name`` to resolve dialog ``speaker`` strings.
    """
    from app.classes.heroes import list_all
    from app.classes.units import get as _get_unit_class

    out: List[dict] = []
    for h in list_all():
        # Resolve effective stats by layering the hero's overrides
        # over the base class.  Frontend doesn't need to know about
        # the override layer — it just wants final numbers.
        base = _get_unit_class(h.base_class_id)
        eff_hp = h.hp_override if h.hp_override is not None else base.base_hp
        eff_atk = h.atk_override if h.atk_override is not None else base.base_atk
        eff_def = h.def_override if h.def_override is not None else base.base_def
        eff_matk = h.matk_override if h.matk_override is not None else base.base_matk
        eff_mdef = h.mdef_override if h.mdef_override is not None else base.base_mdef
        eff_mov = h.mov_override if h.mov_override is not None else base.base_mov
        eff_mp = (
            h.mp_pool_override
            if h.mp_pool_override is not None
            else base.mp_pool
        )
        out.append({
            "hero_id": h.hero_id,
            "display_cn": h.display_cn,
            "base_class_id": h.base_class_id,
            "hp": eff_hp,
            "atk": eff_atk,
            "def_": eff_def,
            "matk": eff_matk,
            "mdef": eff_mdef,
            "mov": eff_mov,
            "mp": eff_mp,
            "active_skills": list(h.active_skills),
            "passive_skills": list(h.passive_skills),
            "sprite_url": f"{HERO_ASSET_URL}/{h.sprite_path}",
            "portrait_url": f"{HERO_ASSET_URL}/{h.portrait_path}",
            "crest_url": f"{HERO_ASSET_URL}/{h.crest_path}",
            "dialogue_name": h.dialogue_name or h.display_cn,
        })
    logger.debug("list_heroes ok: count=%d", len(out))
    return out
