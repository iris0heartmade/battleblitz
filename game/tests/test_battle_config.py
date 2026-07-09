from app.battle_config import expand_battle_config


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
