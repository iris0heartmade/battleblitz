from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any


_AUDIO_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "battle_audio.json"


def battle_audio_config_path() -> Path:
    return _AUDIO_CONFIG_PATH


@lru_cache(maxsize=1)
def load_battle_audio_config() -> dict[str, Any]:
    """Read the battle-audio registry from disk.

    Returns a normalised dict with at least ``bgm_defaults`` and
    ``tracks`` keys. The on-disk shape may include arbitrary extra
    fields per track (e.g. ``title`` / ``category`` / ``notes``); the
    loader is intentionally permissive so future additions don't
    require code changes here.

    If the config file is missing or unparseable, returns an empty
    registry rather than raising — callers that need to *fail fast*
    on a missing config should call this and check the result. The
    expand path below will treat an empty registry as "no tracks
    registered", which is the safe-fail default for strict mode.
    """
    if not _AUDIO_CONFIG_PATH.exists():
        return {"bgm_defaults": {}, "tracks": {}}
    with _AUDIO_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        return {"bgm_defaults": {}, "tracks": {}}
    # Coerce to expected shape — keep extra fields (title/category/...)
    # on track entries so downstream code can read them.
    data.setdefault("bgm_defaults", {})
    data.setdefault("tracks", {})
    return data


class UnknownBattleTrackError(KeyError):
    """Raised when a track_id is supplied that is not registered in the
    battle-audio config. Used by ``expand_battle_config(strict=True)``
    and by the BattleSpec pydantic validator so route handlers can
    translate this to HTTP 400 / 422 uniformly.
    """

    def __init__(self, track_id: str, available: list[str] | None = None):
        self.track_id = track_id
        self.available = list(available or [])
        super().__init__(track_id)


def expand_battle_config(
    raw_config: dict[str, Any] | None,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """Merge a minimal battle_config with the audio registry defaults.

    Args:
        raw_config: Caller-supplied battle config dict (e.g. from a
            Pydantic ``model_dump(exclude_none=True)``). May be None
            or empty — the function is a no-op then.
        strict: When True, an unknown ``audio.bgm.track_id`` raises
            :class:`UnknownBattleTrackError` instead of being
            silently passed through. Default False for backwards
            compatibility with internal callers that already validate
            upstream (e.g. mainline loaders, which use a Pydantic
            validator). Free-build routes should pass ``strict=True``
            so user-submitted track_ids are rejected at create-time.

    The merge precedence is (highest priority wins):
      1. Caller-supplied bgm keys (e.g. an explicit volume override)
      2. Per-track overrides in the registry
      3. Global ``bgm_defaults`` in the registry
    """
    config = deepcopy(raw_config or {})
    audio = config.get("audio")
    if not isinstance(audio, dict):
        return config
    bgm = audio.get("bgm")
    if not isinstance(bgm, dict):
        return config
    track_id = bgm.get("track_id")
    if not track_id:
        return config

    data = load_battle_audio_config()
    defaults = data.get("bgm_defaults") or {}
    tracks = data.get("tracks") or {}
    track_overrides = tracks.get(track_id)
    if strict and track_overrides is None:
        raise UnknownBattleTrackError(
            track_id, available=sorted(tracks.keys())
        )
    merged = {**defaults, **(track_overrides or {}), **bgm}
    audio["bgm"] = merged
    config["audio"] = audio
    return config


__all__ = [
    "UnknownBattleTrackError",
    "battle_audio_config_path",
    "expand_battle_config",
    "load_battle_audio_config",
]