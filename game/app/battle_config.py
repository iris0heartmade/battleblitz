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
    if not _AUDIO_CONFIG_PATH.exists():
        return {"bgm_defaults": {}, "tracks": {}}
    with _AUDIO_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        return {"bgm_defaults": {}, "tracks": {}}
    return data


def expand_battle_config(raw_config: dict[str, Any] | None) -> dict[str, Any]:
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
    track_overrides = (data.get("tracks") or {}).get(track_id) or {}
    merged = {**defaults, **track_overrides, **bgm}
    audio["bgm"] = merged
    config["audio"] = audio
    return config


__all__ = [
    "battle_audio_config_path",
    "expand_battle_config",
    "load_battle_audio_config",
]
