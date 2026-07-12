from pathlib import Path


def test_hud_filters_fire_button_to_local_player_and_sends_identity():
    source = (Path(__file__).parents[1] / "app" / "web" / "app.js").read_text(encoding="utf-8")
    assert "co.player_id === localPlayerId" in source
    assert "{ player_id: localPlayerId }" in source
