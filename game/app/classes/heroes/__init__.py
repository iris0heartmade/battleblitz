"""
Hero registry — the source of truth for all named characters.

Usage::

    from app.classes.heroes import get, list_all, get_by_dialogue_name

    yun = get("yun")
    yun.base_class_id           # "swordsman"
    yun.atk_override            # 20 (or None to inherit from base)

    by_name = get_by_dialogue_name("云")  # HeroProfile or None

Adding a new hero is a one-file change:
    1. Create ``game/app/classes/heroes/<hero_id>.py``.
    2. Subclass ``BaseHero`` and fill in every attribute.
    3. Drop the asset PNGs into ``game/app/web/assets/heroes/``.
    4. Restart — auto-discovered.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

from app.classes.heroes.base import BaseHero, HeroProfile

# ----------------------------------------------------------------
# Auto-discovery
# ----------------------------------------------------------------

_registry: Dict[str, type[BaseHero]] = {}
_profiles: Dict[str, HeroProfile] = {}
# Secondary index: dialogue_name -> hero_id.  Used by the dialog
# system to resolve ``scene.speaker`` to a hero's portrait/crest.
_dialogue_index: Dict[str, str] = {}
_initialized: bool = False


def _is_known_skill(skill_id: str) -> bool:
    """Return True if ``skill_id`` is registered in the skill package.

    The skills package is itself auto-discovered, so we trigger its
    init here.  Failures (skill package not importable for some
    reason) return False — we'd rather warn about a missing skill
    than crash during hero discovery.
    """
    try:
        from app.classes.units.skills import get_or_none as _get_skill

        return _get_skill(skill_id) is not None
    except Exception:
        return False


def _discover() -> None:
    """Walk ``classes/heroes/`` and register every ``BaseHero`` subclass."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    pkg_path = Path(__file__).resolve().parent
    for _, module_name, _is_pkg in pkgutil.iter_modules([str(pkg_path)]):
        if module_name.startswith("_") or module_name in ("base",):
            continue
        try:
            mod = importlib.import_module(f"app.classes.heroes.{module_name}")
        except ImportError:
            continue

        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if not isinstance(attr, type):
                continue
            if not issubclass(attr, BaseHero):
                continue
            if attr is BaseHero:
                continue

            profile = attr.compile()
            _registry[profile.hero_id] = attr
            _profiles[profile.hero_id] = profile

            # Validate skill references.  We log a WARNING (rather
            # than raise) so a mistyped skill ID can't lock the
            # server out of a running mainline.  Unknown skills
            # just won't fire at combat time.
            for bucket_name, bucket in (
                ("active_skills", profile.active_skills),
                ("passive_skills", profile.passive_skills),
            ):
                for sid in bucket:
                    if not _is_known_skill(sid):
                        logger.warning(
                            "hero %r declares unknown %s entry %r; "
                            "skill won't fire at runtime",
                            profile.hero_id, bucket_name, sid,
                        )

            # Index by dialogue_name (preferred) and display_cn
            # (fallback) so the dialog system can resolve a speaker
            # written in either form.
            for key in (profile.dialogue_name, profile.display_cn):
                if key and key not in _dialogue_index:
                    _dialogue_index[key] = profile.hero_id


# ── Public API ──────────────────────────────────────────────


def get(hero_id: str) -> HeroProfile:
    """Return the immutable profile for a hero.  Raises KeyError if unknown."""
    _discover()
    return _profiles[hero_id]


def get_or_none(hero_id: str) -> Optional[HeroProfile]:
    _discover()
    return _profiles.get(hero_id)


def list_all() -> List[HeroProfile]:
    """All registered hero profiles."""
    _discover()
    return list(_profiles.values())


def hero_ids() -> List[str]:
    _discover()
    return list(_profiles.keys())


def get_by_dialogue_name(name: str) -> Optional[HeroProfile]:
    """Resolve a dialog ``speaker`` string to a hero profile.

    Looks up ``dialogue_name`` first, then falls back to
    ``display_cn``.  Returns ``None`` if the speaker isn't a hero
    (the dialog system then falls back to its default behavior).
    """
    _discover()
    hero_id = _dialogue_index.get(name)
    if hero_id is None:
        return None
    return _profiles.get(hero_id)


__all__ = [
    "BaseHero",
    "HeroProfile",
    "get",
    "get_or_none",
    "list_all",
    "hero_ids",
    "get_by_dialogue_name",
]
