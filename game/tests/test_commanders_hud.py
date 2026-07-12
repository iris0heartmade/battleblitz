from pathlib import Path


WEB_DIR = Path(__file__).parents[1] / "app" / "web"


def test_hud_filters_fire_button_to_local_player_and_sends_identity():
    source = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    assert "co.player_id === localPlayerId" in source
    assert "{ player_id: localPlayerId }" in source


def test_free_mode_create_form_has_commander_picker():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    source = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="new-commander"' in html
    assert '<option value="">无指挥官</option>' in html
    assert '<option value="yun">云</option>' in html
    assert '<option value="anna">安娜</option>' in html
    assert 'document.getElementById("new-commander").value' in source
    assert "body.battle_config.commander = commanderId" in source


def test_mainline_list_renders_commander_selection_and_posts_choice():
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    source = (WEB_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="mainline-commander-panel"' in html
    assert 'id="mainline-commander-list"' in html
    assert "renderCommanderSelection" in source
    assert "/players/me/commanders" in source
    assert "/select-commander" in source
    assert 'data-action="mainline-select-commander"' in source
    assert "commander selection is closed after mainline start" in source
