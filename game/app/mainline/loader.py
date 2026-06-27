"""
Loader for mainline JSON files.

Design points:
  * Mainline files live in `game/mainlines/*.json` (one file per campaign).
  * Parsed objects are cached in-process (`_cache`). `clear_cache()`
    exists for tests and for hot-reload scenarios.
  * All file reads happen via stdlib so the loader is safe to call
    from request handlers (no async DB / network).
  * Errors are surfaced as `MainlineNotFound` / `MainlineValidationError`
    so route handlers can translate to 404 / 422 cleanly.
"""
from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Iterable

from pydantic import ValidationError

from app.mainline.schemas import Mainline, MainlineSummary


# ============================================================
# Custom exceptions
# ============================================================

class MainlineError(Exception):
    """Base class for mainline loading errors."""


class MainlineNotFound(MainlineError):
    """No JSON file matching the requested mainline id."""


class MainlineValidationError(MainlineError):
    """JSON found but failed schema validation."""

    def __init__(self, mainline_id: str, message: str) -> None:
        super().__init__(f"mainline {mainline_id!r} invalid: {message}")
        self.mainline_id = mainline_id


# ============================================================
# Path resolution
# ============================================================

# game/app/mainline/loader.py → game/mainlines/
_MAINLINES_DIR: Path = Path(__file__).resolve().parents[2] / "mainlines"


def mainlines_dir() -> Path:
    """The directory where mainline JSON files live. Exposed for tooling."""
    return _MAINLINES_DIR


# ============================================================
# Cache
# ============================================================

_cache: dict[str, Mainline] = {}
_cache_lock = Lock()


def clear_cache() -> None:
    """Drop all cached mainlines. Used by tests + future hot-reload."""
    with _cache_lock:
        _cache.clear()


def _mainline_path(mainline_id: str) -> Path:
    return _MAINLINES_DIR / f"{mainline_id}.json"


def _read_and_parse(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MainlineNotFound(str(path)) from exc
    except OSError as exc:
        raise MainlineError(f"cannot read {path}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MainlineError(f"{path} is not valid JSON: {exc}") from exc


# ============================================================
# Public API
# ============================================================

def load_mainline(mainline_id: str) -> Mainline:
    """Load and validate a mainline by id. Cached after first parse.

    Raises:
        MainlineNotFound: no `<id>.json` under the mainlines dir.
        MainlineValidationError: file exists but fails schema validation.
        MainlineError: other I/O / JSON parsing errors.
    """
    with _cache_lock:
        cached = _cache.get(mainline_id)
    if cached is not None:
        return cached

    path = _mainline_path(mainline_id)
    data = _read_and_parse(path)

    try:
        mainline = Mainline.model_validate(data)
    except ValidationError as exc:
        # Surface a readable summary; full traceback lives in exc.errors()
        msgs = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", ()))
            msgs.append(f"{loc}: {err.get('msg', '')}")
        raise MainlineValidationError(
            mainline_id, "; ".join(msgs)
        ) from exc

    with _cache_lock:
        _cache[mainline_id] = mainline
    return mainline


def _iter_mainline_files() -> Iterable[Path]:
    if not _MAINLINES_DIR.exists():
        return []
    return sorted(_MAINLINES_DIR.glob("*.json"))


def list_mainlines() -> list[MainlineSummary]:
    """Return one MainlineSummary per mainline JSON on disk.

    Files that fail validation are *skipped* (not raised) — content
    authors should be able to save half-finished campaigns without
    breaking the lobby list. Validation errors are still raised when
    a specific mainline is loaded via `load_mainline`.
    """
    summaries: list[MainlineSummary] = []
    for path in _iter_mainline_files():
        try:
            data = _read_and_parse(path)
            mainline = Mainline.model_validate(data)
        except (MainlineError, ValidationError):
            # Skip invalid; do not raise.
            continue
        summaries.append(MainlineSummary(
            id=mainline.id,
            title=mainline.title,
            synopsis=mainline.synopsis,
            cover_art=mainline.cover_art,
            required_classes=list(mainline.required_classes),
            battle_count=len(mainline.battles),
        ))
    return summaries


__all__ = [
    "MainlineError",
    "MainlineNotFound",
    "MainlineValidationError",
    "mainlines_dir",
    "clear_cache",
    "load_mainline",
    "list_mainlines",
]
