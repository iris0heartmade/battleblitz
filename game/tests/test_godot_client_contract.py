from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NETWORK_CLIENT = ROOT / "godot-client" / "scripts" / "autoload" / "network_client.gd"
MAIN_GD = ROOT / "godot-client" / "scripts" / "main.gd"
BOARD_GD = ROOT / "godot-client" / "scripts" / "board" / "board.gd"
UNIT_NODE_GD = ROOT / "godot-client" / "scripts" / "board" / "unit_node.gd"
PROJECT_GODOT = ROOT / "godot-client" / "project.godot"
TEXTURE_LOADER_GD = ROOT / "godot-client" / "scripts" / "core" / "texture_loader.gd"
WEB_APP_JS = ROOT / "game" / "app" / "web" / "app.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_godot_network_client_exposes_hero_backend_endpoints():
    source = _read(NETWORK_CLIENT)
    required_snippets = [
        "func get_mainline_prepare(",
        '"/mainlines/%s/prepare?user_name=%s"',
        "func promote_mainline_hero(",
        '"/mainlines/%s/prepare/promote"',
        "func equip_mainline_hero(",
        '"/mainlines/%s/prepare/equipment"',
        "func get_post_battle_shop(",
        '"/mainlines/%s/shop?user_name=%s"',
        "func purchase_post_battle_shop_item(",
        '"/mainlines/%s/shop/purchase"',
        "func get_mercenary_config(",
        '"/mainlines/%s/mercenary/config?user_name=%s"',
        "func allocate_mercenary_points(",
        '"/mainlines/%s/mercenary/allocate"',
        "func list_saves(",
        '"/saves?user_name=%s"',
        "func load_save(user_name: String, kind: String, slot_index: int",
        '"/saves/load"',
        "func erase_save(user_name: String, kind: String, slot_index: int",
        '"/saves/erase"',
        "func capture_suspend(game_id: int, user_name: String",
        '"/games/%d/suspend"',
    ]
    for snippet in required_snippets:
        assert snippet in source


def test_godot_save_views_use_save_api_not_game_delete_api():
    source = _read(MAIN_GD)
    assert 'NetworkClient.list_saves(_user_name, Callable(self, "_on_saves_response"))' in source
    assert 'NetworkClient.list_saves(_user_name, Callable(self, "_on_ml_slots_response"))' in source
    assert "NetworkClient.load_save(" in source
    assert "NetworkClient.erase_save(" in source
    assert 'NetworkClient.delete_game(_selected_save_id' not in source
    assert 'NetworkClient.list_games(Callable(self, "_on_saves_response")' not in source
    assert 'NetworkClient.list_games(Callable(self, "_on_ml_slots_response")' not in source


def test_godot_mainline_start_passes_prepare_compatible_arguments():
    source = _read(MAIN_GD)
    assert "NetworkClient.get_mainline_prepare(" in source
    assert "func _on_prepare_start_pressed() -> void:" in source
    assert 'NetworkClient.start_mainline(_selected_mainline_id, _user_name, false, [], Callable(self, "_on_mainline_start_response"))' in source
    assert 'NetworkClient.start_mainline(mainline_id, _user_name, false, [], Callable(self, "_on_mainline_start_response"), true)' in source
    assert 'NetworkClient.next_battle_mainline(_active_mainline_id, _user_name, [], Callable(self, "_on_mainline_next_battle_response"))' in source
    assert "NetworkClient.start_mainline(mainline_id, _user_name, false, [], Callable(self, \"_on_mainline_start_response\"))" not in source


def test_godot_prepare_ui_uses_hero_backend_actions():
    source = _read(MAIN_GD)
    required_snippets = [
        "func _render_mainline_prepare() -> void:",
        "func _build_prepare_heroes_text(payload: Dictionary) -> String:",
        "func _build_prepare_equipment_text(payload: Dictionary) -> String:",
        "func _build_prepare_mercenary_text() -> String:",
        "func _build_prepare_shop_text() -> String:",
        "NetworkClient.promote_mainline_hero(",
        "NetworkClient.equip_mainline_hero(",
        "NetworkClient.get_post_battle_shop(",
        "NetworkClient.purchase_post_battle_shop_item(",
        "NetworkClient.get_mercenary_config(",
        "NetworkClient.allocate_mercenary_points(",
    ]
    for snippet in required_snippets:
        assert snippet in source


def test_godot_empty_barracks_recruit_uses_tile_click_path():
    source = _read(MAIN_GD)
    assert "func _pick_empty_my_barracks_at_cell(cell: Vector2i) -> Dictionary:" in source
    assert "_try_open_recruit_at_tile(tile)" in source
    assert "_show_recruit_at(batt)" in source
    assert "NetworkClient.action_recruit(_game_id, _player_id, tile_x, tile_y, unit_type" in source


def test_godot_attack_targets_exclude_teammates():
    source = _read(MAIN_GD)
    assert "func _player_team_key(player_id: int) -> String:" in source
    assert "var my_team_key: String = _player_team_key(me_pid)" in source
    assert "_player_team_key(candidate_pid) == my_team_key" in source
    assert "continue" in source


def test_godot_claim_remains_available_after_moving_onto_enemy_hq():
    source = _read(MAIN_GD)
    assert "context != _ACTION_CONTEXT_POST_ACTION" not in source
    assert "var can_claim := has_unit and _can_claim_here(ud)" in source
    assert "NetworkClient.action_claim(_game_id, _player_id, _selected_unit_id)" in source


def test_godot_game_over_stops_refreshing_and_polling():
    source = _read(MAIN_GD)
    assert "if _game_over:" in source
    assert "_board_refresh_pending = false" in source
    assert "_state_poll_timer.stop()" in source


def test_godot_client_defaults_to_full_hd_viewport():
    source = _read(PROJECT_GODOT)
    assert "window/size/viewport_width=1920" in source
    assert "window/size/viewport_height=1080" in source


def test_godot_unit_art_uses_high_quality_resize_not_pixelated_resize():
    source = _read(TEXTURE_LOADER_GD)
    start = source.index("static func fit_image_to_square")
    body = source[start:]
    assert "img.resize(out_w, out_h, Image.INTERPOLATE_LANCZOS)" in body
    assert "Image.INTERPOLATE_NEAREST" not in body


def test_godot_texture_loader_avoids_stale_import_cache_errors():
    source = _read(TEXTURE_LOADER_GD)
    assert "static func _imported_texture_ready(res_path: String) -> bool:" in source
    assert "_imported_texture_ready(res_path) and ResourceLoader.exists(res_path)" in source
    assert 'var marker := "dest_files=[\\""' in source


def test_godot_state_refresh_does_not_auto_paint_enemy_threat_range():
    source = _read(MAIN_GD)
    start = source.index("func _on_state_updated(_snapshot: Dictionary) -> void:")
    end = source.index("# GET /state", start)
    body = source[start:end]
    assert "_show_threat_tiles()" not in body
    assert "func _show_threat_tiles()" in source
    threat_start = source.index("func _show_threat_tiles() -> void:")
    threat_end = source.index("func _on_state_updated(_snapshot: Dictionary) -> void:", threat_start)
    threat_body = source[threat_start:threat_end]
    assert "_last_threat_show_ms" not in source
    assert "Time.get_ticks_msec()" not in threat_body


def test_godot_unit_refresh_does_not_reset_position_or_leave_stale_tweens():
    board = _read(BOARD_GD)
    unit_node = _read(UNIT_NODE_GD)
    assert "existing.set_meta(\"move_tween\", t)" in board
    assert "old_tween.kill()" in board
    assert "position = Vector2.ZERO" not in unit_node


def test_godot_team_badge_color_comes_from_team_not_player_color():
    board = _read(BOARD_GD)
    assert "func _team_color_for_unit(unit_data: Dictionary) -> Color:" in board
    assert '"team_a": return Config.player_color("red")' in board
    assert '"team_b": return Config.player_color("blue")' in board
    assert "presenter.setup(unit_dict, _team_color_for_unit(unit_dict), _team_id_for_unit(unit_dict))" in board


def test_legacy_web_attack_targets_use_manhattan_range_only():
    source = _read(WEB_APP_JS)
    start = source.index("function canUnitAttack(")
    end = source.index("// Combat forecast", start)
    body = source[start:end]
    assert "manhattan(fromX, fromY, toX, toY)" in body
    assert "clientHasLineOfSight" not in body
