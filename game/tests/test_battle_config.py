from app.battle_config import (
    UnknownBattleTrackError,
    battle_bgm_meta,
    expand_battle_config,
    load_battle_audio_config,
)


# ============================================================
# Default merge behavior (existing tests)
# ============================================================

def test_expand_battle_config_applies_file_defaults():
    out = expand_battle_config({
        "audio": {
            "bgm": {
                "track_id": "sample_battle_01",
            }
        }
    })
    assert out["audio"]["bgm"]["track_id"] == "sample_battle_01"
    assert out["audio"]["bgm"]["loop"] is True
    assert out["audio"]["bgm"]["volume"] == 0.8
    assert out["audio"]["bgm"]["fade_in_ms"] == 1200
    assert out["audio"]["bgm"]["fade_out_ms"] == 800


def test_expand_battle_config_keeps_explicit_override():
    out = expand_battle_config({
        "audio": {
            "bgm": {
                "track_id": "sample_battle_01",
                "volume": 0.55,
            }
        }
    })
    assert out["audio"]["bgm"]["volume"] == 0.55


# ============================================================
# Stage A — track catalog metadata round-trips through the loader
# ============================================================

def test_load_battle_audio_config_exposes_metadata():
    """The catalog now carries title / category / file / notes per
    track; the loader must surface them so downstream code (lobby
    detail, picker UI) can read them without parsing JSON itself."""
    data = load_battle_audio_config()
    tracks = data.get("tracks") or {}
    assert "sample_battle_01" in tracks
    entry = tracks["sample_battle_01"]
    assert entry.get("title") == "示例战斗曲 01"
    assert entry.get("category") == "battle"
    assert entry.get("file") == "sample_battle_01.mp3"
    assert "notes" in entry and "兜底 BGM" in entry["notes"]
    # Parameter overrides still coexist with the new metadata.
    assert entry.get("volume") == 0.8
    assert entry.get("fade_in_ms") == 1200
    assert entry.get("fade_out_ms") == 800


def test_expand_battle_config_does_not_strip_metadata():
    """The merge step should pass track-level metadata keys through
    to the final battle_config so the frontend can show title/category
    without a second API call."""
    out = expand_battle_config({
        "audio": {
            "bgm": {
                "track_id": "sample_battle_01",
            }
        }
    })
    bgm = out["audio"]["bgm"]
    assert bgm["title"] == "示例战斗曲 01"
    assert bgm["category"] == "battle"
    assert bgm["file"] == "sample_battle_01.mp3"


# ============================================================
# Stage B — strict-mode track_id validation
# ============================================================

def test_expand_battle_config_strict_raises_for_unknown_track():
    """A free-build submission with a bad track_id should be
    rejected at create-time, not silently persisted."""
    import pytest
    with pytest.raises(UnknownBattleTrackError) as ei:
        expand_battle_config(
            {"audio": {"bgm": {"track_id": "ghost_track_42"}}},
            strict=True,
        )
    assert ei.value.track_id == "ghost_track_42"
    # The error payload exposes the available list so the route can
    # include it in the 400 response body.
    assert "sample_battle_01" in ei.value.available


def test_expand_battle_config_non_strict_passes_unknown_track():
    """Backwards compatibility: internal callers that already validate
    upstream (e.g. mainline loaders via Pydantic) keep getting the
    old "merge defaults, skip per-track overrides when unknown"
    behavior. Defaults still merge; only the per-track entry is
    skipped — that's the difference from strict mode, where the
    whole call fails."""
    out = expand_battle_config(
        {"audio": {"bgm": {"track_id": "ghost_track_42", "volume": 0.3}}},
        # strict=False by default
    )
    # track_id survives, explicit user volume still wins over the
    # global default.
    assert out["audio"]["bgm"]["track_id"] == "ghost_track_42"
    assert out["audio"]["bgm"]["volume"] == 0.3
    # Global defaults DO merge (the unknown-track branch only skips
    # the per-track override dict, not the defaults layer).
    assert out["audio"]["bgm"]["loop"] is True
    assert out["audio"]["bgm"]["fade_in_ms"] == 1200
    # Per-track-only fields (e.g. title/category) are absent because
    # the track isn't in the registry.
    assert "title" not in out["audio"]["bgm"]
    assert "category" not in out["audio"]["bgm"]


def test_expand_battle_config_strict_accepts_known_track():
    """Sanity: strict=True on a known track_id must still work end to
    end (no regression on the happy path)."""
    out = expand_battle_config(
        {"audio": {"bgm": {"track_id": "sample_battle_01"}}},
        strict=True,
    )
    assert out["audio"]["bgm"]["volume"] == 0.8
    assert out["audio"]["bgm"]["title"] == "示例战斗曲 01"


def test_expand_battle_config_no_audio_passthrough():
    """Configs without an audio block are returned untouched, even in
    strict mode (no track to validate)."""
    out = expand_battle_config({"foo": "bar"}, strict=True)
    assert out == {"foo": "bar"}


def test_expand_battle_config_none_passthrough():
    """None input is a no-op, even in strict mode."""
    assert expand_battle_config(None, strict=True) == {}


# ============================================================
# Stage D — battle_bgm_meta lookup helper
# ============================================================

def test_battle_bgm_meta_returns_metadata_for_known_track():
    """Used by mainline routes to attach a bgm_meta block to the
    start / next-battle / detail responses. Returns only the
    catalogue metadata keys (no parameter overrides)."""
    meta = battle_bgm_meta("sample_battle_01")
    assert meta is not None
    assert meta["track_id"] == "sample_battle_01"
    assert meta["title"] == "示例战斗曲 01"
    assert meta["category"] == "battle"
    assert meta["file"] == "sample_battle_01.mp3"
    # Parameter overrides must NOT leak into the meta block —
    # the front-end gets those via the full battle_config.audio.bgm.
    assert "volume" not in meta
    assert "fade_in_ms" not in meta
    assert "loop" not in meta


def test_battle_bgm_meta_returns_none_for_unknown_track():
    """Unknown / unregistered track_id resolves to None so callers
    can serialise it as JSON null. This is intentional — the
    strict validation already happened upstream (Pydantic on
    BattleSpec, expand_battle_config strict=True on /games)."""
    assert battle_bgm_meta("ghost_track_42") is None


def test_battle_bgm_meta_returns_none_for_empty_input():
    """An empty / None track_id must short-circuit to None rather
    than crashing or returning a dict with a falsy track_id."""
    assert battle_bgm_meta("") is None
    assert battle_bgm_meta(None) is None