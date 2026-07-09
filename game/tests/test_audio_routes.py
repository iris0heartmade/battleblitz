"""
Tests for the BGM-catalog route (GET /audio/tracks).

The route is a thin read of battle_audio.json with metadata split
out from parameter overrides. The point of these tests is to lock
the response shape so the front-end picker can rely on it.
"""
from __future__ import annotations

import pytest


@pytest.mark.integration
class TestAudioTracks:
    async def test_returns_defaults_and_tracks(self, client):
        r = await client.get("/audio/tracks")
        assert r.status_code == 200
        body = r.json()
        # Top-level shape — both keys present even if one is empty.
        assert "defaults" in body
        assert "tracks" in body
        # The shipped sample track must be registered.
        ids = [t["track_id"] for t in body["tracks"]]
        assert "sample_battle_01" in ids

    async def test_track_payload_has_metadata_and_params(self, client):
        r = await client.get("/audio/tracks")
        body = r.json()
        sample = next(
            t for t in body["tracks"] if t["track_id"] == "sample_battle_01"
        )
        # Stage A metadata fields surface on the track entry.
        assert sample["title"] == "示例战斗曲 01"
        assert sample["category"] == "battle"
        assert sample["file"] == "sample_battle_01.mp3"
        assert "notes" in sample and sample["notes"]
        # The resolved params dict carries the merged defaults +
        # per-track overrides — useful for the picker to render
        # a hint like "fade-in 1.2s".
        params = sample["params"]
        assert params["volume"] == 0.8
        assert params["fade_in_ms"] == 1200
        assert params["fade_out_ms"] == 800
        assert params["loop"] is True

    async def test_tracks_are_sorted(self, client):
        r = await client.get("/audio/tracks")
        ids = [t["track_id"] for t in r.json()["tracks"]]
        assert ids == sorted(ids)

    async def test_defaults_match_battle_audio_json(self, client):
        """The defaults dict must mirror the registry's bgm_defaults
        so the front-end doesn't have to guess (loop default, volume
        default, etc.)."""
        from app.battle_config import load_battle_audio_config
        r = await client.get("/audio/tracks")
        body = r.json()
        # Note: dict comparison is order-insensitive in JSON but
        # Python's == checks values only — fine for our case.
        assert body["defaults"] == load_battle_audio_config().get("bgm_defaults", {})

    async def test_unknown_metadata_keys_go_into_params(self, client):
        """If a track declares an unknown key (not in
        {title,category,file,notes}), it must land in ``params`` —
        that's the only way the picker can show it without us
        having to update the route every time someone adds a new
        metadata field. We can't ship a config that has such a key
        today, so we check the structural invariant on the existing
        track: every entry param is either a default key or a
        per-track key, and the meta keys do NOT appear in params."""
        r = await client.get("/audio/tracks")
        body = r.json()
        meta_keys = {"title", "category", "file", "notes"}
        defaults = body["defaults"]
        for t in body["tracks"]:
            for mk in meta_keys & t["params"].keys():
                # If a meta key accidentally leaked into params, the
                # picker would render it twice. Catch that here.
                assert mk not in t["params"], (
                    f"track {t['track_id']!r} has meta key {mk!r} in params"
                )
            # And conversely the resolved params must include every
            # default key.
            for dk in defaults:
                assert dk in t["params"]