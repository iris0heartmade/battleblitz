"""
Mainline (campaign) routes package — Step 3 of the BattleBlitz plan.

Reorganized from the original ``routes/mainline.py`` (1979 lines) into
per-domain submodules.  Public URL contract is unchanged: all 15
endpoints under ``/mainlines`` keep their existing paths and response
shapes (no schema or behavior changes; this is a pure structural
refactor).

Sub-modules:
  * :mod:`chapters`         — GET /mainlines, /dialogue, /{id}
  * :mod:`prepare`          — GET /{id}/prepare, POST promote/equipment/complete
  * :mod:`shop`             — GET /{id}/shop, POST shop/purchase
  * :mod:`battle_lifecycle` — POST /{id}/start, /advance, /next-battle, /abandon
  * :mod:`mercenary`        — GET /{id}/mercenary/config, POST /allocate

Test fixture compatibility
--------------------------
Tests patch :data:`load_mainline` on ``app.routes.mainline`` via
``monkeypatch.setattr``.  To make those patches actually take effect in
the new submodules, the binding lives at this package level (where the
patch is targeted) and submodules look it up late at call time:

.. code-block:: python

    # app/routes/mainline/battle_lifecycle.py
    import app.routes.mainline as mainline_pkg

    async def start_mainline(...):
        ml = mainline_pkg.load_mainline(mainline_id)  # late-bound, sees monkeypatch

This is the only reason this single import sits at module top in
``__init__.py``: it must execute before the submodule imports below.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

# Bind load_mainline at the package level FIRST so that:
#   1) ``monkeypatch.setattr("app.routes.mainline.load_mainline", ...)``
#      (used by test_commanders_e2e + test_commanders_integration)
#      targets a real attribute.
#   2) Submodules can resolve it at call time via
#      ``import app.routes.mainline as mainline_pkg;
#       mainline_pkg.load_mainline(...)`` for late-bound lookup.
# Do not move this import below the submodule imports below.
from app.mainline import load_mainline  # noqa: F401  (re-exported)

from . import (
    battle_lifecycle,
    chapters,
    mercenary,
    prepare,
    shop,
)

logger = logging.getLogger(__name__)
audit = logging.getLogger("audit.mainline")
# Engine-level logger exposed for submodules if they ever need to mirror
# the original mainline.py's helper loggers.
engine_logger = logging.getLogger("app.mainline.engine")

# Single aggregated router.  Each submodule already carries the
# ``/mainlines`` prefix on its own APIRouter (see the comment in each
# submodule file).  We do NOT use ``include_router`` here because
# nesting include_router objects causes FastAPI to register the parent
# as a single lazy ``_IncludedRouter`` on the app without flattening
# its children; instead we copy the underlying routes directly.  This
# matches what the original monolithic ``routes/mainline.py`` exposed
# to ``app.main``.
router = APIRouter()
for _mod in (chapters, prepare, shop, battle_lifecycle, mercenary):
    router.routes.extend(_mod.router.routes)

# Back-compat re-exports — used by tests that import from
# ``app.routes.mainline`` (test_mainline_chain_gates,
# test_commanders_integration, etc.).  Preserving these symbols keeps
# the refactor invisible to test code and to any code that imports
# helpers from the original monolith.
from ._common import (  # noqa: E402  (after submodule imports)
    CAMPAIGN_CHAINS,  # noqa: F401
    TEST_MAINLINE_CHAIN,  # noqa: F401
    _campaign_chain_name,  # noqa: F401
    _chain_for,  # noqa: F401
)
from .battle_lifecycle import (  # noqa: E402  (after submodule imports)
    _spawn_battle_for_index,  # noqa: F401
)

__all__ = [
    "router",
    "load_mainline",
    "CAMPAIGN_CHAINS",
    "TEST_MAINLINE_CHAIN",
    "_chain_for",
    "_campaign_chain_name",
    "_spawn_battle_for_index",
]
