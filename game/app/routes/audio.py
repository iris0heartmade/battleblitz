"""
Audio metadata routes.

Currently exposes ONE endpoint:

  GET /audio/tracks   — list every registered battle BGM track, with
                        metadata (title / category / file / notes)
                        and parameter overrides, for the front-end
                        picker.

The track catalog itself lives in ``game/config/battle_audio.json``
and is read by :func:`app.battle_config.load_battle_audio_config`.
This route is a thin presentation layer; it does NOT validate or
expand anything — that's the job of ``expand_battle_config``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter

from app.battle_config import load_battle_audio_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audio", tags=["audio"])


@router.get("/tracks")
async def list_audio_tracks() -> Dict[str, Any]:
    """Return the registered BGM catalog for the front-end picker.

    Response shape::

        {
          "defaults": {"loop": true, "volume": 0.8, ...},   // global fallback
          "tracks": [                                      // sorted by track_id
            {
              "track_id": "sample_battle_01",
              "title":    "示例战斗曲 01",
              "category": "battle",
              "file":     "sample_battle_01.mp3",
              "notes":    "默认 demo 曲目 ...",
              "params":   {"volume": 0.8, ...}             // resolved = defaults + per-track overrides
            },
            ...
          ]
        }

    The ``params`` block is the *resolved* parameter set the
    front-end would see after the engine merges defaults with
    per-track overrides. The client never sends these back; it just
    uses them to render the picker hint (e.g. "fade-in 1.2s").
    """
    data = load_battle_audio_config()
    defaults: Dict[str, Any] = dict(data.get("bgm_defaults") or {})
    tracks_raw: Dict[str, Any] = data.get("tracks") or {}

    resolved: List[Dict[str, Any]] = []
    for track_id in sorted(tracks_raw.keys()):
        entry = tracks_raw[track_id] or {}
        # Track-level fields surface directly. Anything we don't
        # recognise goes into ``params`` so the picker can show the
        # resolved numbers without us having to hardcode field names.
        meta_keys = {"title", "category", "file", "notes"}
        meta = {k: entry[k] for k in meta_keys if k in entry}
        # Resolve params: defaults first, per-track overrides next.
        params = {**defaults, **{k: v for k, v in entry.items() if k not in meta_keys}}
        resolved.append({
            "track_id": track_id,
            **meta,
            "params": params,
        })

    logger.debug("list_audio_tracks ok: count=%d", len(resolved))
    return {"defaults": defaults, "tracks": resolved}


__all__ = ["router"]