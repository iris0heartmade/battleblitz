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


def test_godot_free_lobby_create_sends_free_mode_to_backend():
    network = _read(NETWORK_CLIENT)
    main = _read(MAIN_GD)
    assert '"mode": mode' in network
    assert 'mode: String = "free"' in network
    assert 'Callable(self, "_on_lobby_create_response"),\n\t\t_selected_lobby_seat_commanders(),\n\t\t"free"' in main
    ai_start = main.index("func _selected_lobby_ai_commanders() -> Dictionary:")
    ai_end = main.index("func _setup_lobby_win_condition_options", ai_start)
    ai_body = main[ai_start:ai_end]
    assert "return {2: commander_id}" not in ai_body
    assert "for seat_index in range(_selected_lobby_player_count()):" in ai_body
    assert "_lobby_ai_replacement_for_seat(seat_index)" in ai_body


def test_godot_save_views_use_save_api_not_game_delete_api():
    # #16: saves 域已抽到 saves_controller.gd(三槽卡片);
    # mainline 域到 mainline_controller.gd(章节 cleared 标注 join /saves);
    # in_progress 域到 in_progress_controller.gd。
    saves_src = _read(ROOT / "godot-client" / "scripts" / "ui" / "saves_controller.gd")
    mainline_src = _read(ROOT / "godot-client" / "scripts" / "mainline" / "mainline_controller.gd")
    in_progress_src = _read(ROOT / "godot-client" / "scripts" / "ui" / "in_progress_controller.gd")
    main_src = _read(MAIN_GD)
    combined = saves_src + mainline_src + in_progress_src + main_src
    assert 'NetworkClient.list_saves(_main._user_name, Callable(self, "_on_saves_response"))' in saves_src
    # FE8-style entry — mainline now starts from the three formal slots.
    assert 'NetworkClient.list_saves(_main._user_name, Callable(self, "_on_ml_slots_response"))' in mainline_src
    assert "func _render_mainline_slots() -> void:" in mainline_src
    assert "ml_slots_container" not in mainline_src
    # in_progress 视图
    assert 'NetworkClient.list_saves(_main._user_name, Callable(self, "_on_saves_response"))' in in_progress_src
    assert "NetworkClient.load_save(" in combined
    assert "NetworkClient.erase_save(" in combined
    assert 'NetworkClient.delete_game(_selected_save_id' not in combined
    assert 'NetworkClient.list_games(Callable(self, "_on_saves_response")' not in combined


def test_godot_hero_portrait_renders_in_bottom_left_not_info_panel():
    # T:#18 — 英雄立绘原本嵌在 InfoPanel 右侧 position=(282, 108) size=(86,118),
    # 遮挡 "Lv.1" / 攻击射程 等文字。改成挂在独立的 HeroPortraitPanel 槽位,
    # 该槽位锚定到 GameView/HUD 左下角(GoldPanel 上方),
    # 不再嵌进 InfoPanel;unit_info.offset_right 也不再为立绘腾空间。
    main_src = _read(MAIN_GD)
    main_tscn = _read(ROOT / "godot-client" / "scenes" / "main.tscn")
    # 1) .tscn 里有 HeroPortraitPanel,挂在 GameView/HUD 下(不在 BottomLeft HBox 里)
    assert '[node name="HeroPortraitPanel" type="Panel" parent="GameView/HUD"]' in main_tscn
    assert "HeroPortraitPanel" in main_tscn
    # 2) 锚定到左上(TurnBadge 下方、GoldPanel 上方),offset_left=28
    hp_idx = main_tscn.index('[node name="HeroPortraitPanel"')
    hp_end = main_tscn.index("\n\n", hp_idx)
    hp_block = main_tscn[hp_idx:hp_end]
    assert "anchor_top = 0.0" in hp_block
    assert "anchor_bottom = 0.0" in hp_block
    assert "offset_left = 28.0" in hp_block
    # 3) main.gd @onready var 指向新路径
    assert "@onready var hero_portrait_panel: Panel = $GameView/HUD/HeroPortraitPanel" in main_src
    # 4) _set_unit_info_portrait 把 TextureRect 挂到 hero_portrait_panel(不再挂 info_panel)
    func_idx = main_src.index("func _set_unit_info_portrait(")
    func_end = main_src.index("\n\n", func_idx)
    func_body = main_src[func_idx:func_end]
    assert "hero_portrait_panel.add_child(_unit_info_portrait_tex)" in func_body
    # 5) 不再调 unit_info.offset_right = -108 (那是给 InfoPanel 内嵌立绘腾空间的)
    assert "unit_info.offset_right = -108" not in func_body
    # 6) 旧硬编码位置 (282, 108) 已删
    assert "position = Vector2(282, 108)" not in func_body


def test_godot_winner_resolution_returns_no_winner_for_draw_or_ambiguous():
    # T:#18 — _winner_player_id_from_finished_snapshot 之前在 0 队伍或 ≥2 队伍时
    # fallback 到 _player_id,导致"全员阵亡"或"多队伍并存"的 draw / 异常情况下
    # 错误地显示"学长 获胜!"。改:0 队伍(全员死光)和 ≥2 队伍(未决出胜者)都返回 -1,
    # 让 show_battle_result 把 winner 留空("—")而不是冒认。
    main_src = _read(MAIN_GD)
    func_idx = main_src.index("func _winner_player_id_from_finished_snapshot(")
    func_end = main_src.index("\n\n", func_idx)
    func_body = main_src[func_idx:func_end]
    # 唯一队伍时仍正确返回那个 pid
    assert "alive_team_to_pid.size() == 1" in func_body
    assert "alive_team_to_pid.values()[0]" in func_body
    # 兜底必须是 -1,不能是 _player_id(否则 draw 会被认成"自己赢")
    fallback_lines = [ln.strip() for ln in func_body.splitlines() if ln.strip().startswith("return ")]
    last_return = fallback_lines[-1]
    assert "return -1" in last_return
    assert "return _player_id" not in func_body


def test_godot_battle_result_winner_uses_rich_text_label_for_bbcode():
    # T:#18 — show_battle_result (main.gd:2967) 把 bbcode_enabled = true 赋给
    # battle_result_winner,但 #18 之前 WinnerBanner 是 Label 节点 → SCRIPT ERROR:
    # "Invalid assignment of property or key 'bbcode_enabled' with value of type
    # 'bool' on a base object of type 'Label'"。
    # 这会让 _on_match_ended 直接崩,GameView 卡死,玩家以为对局没结束。
    # 修法:WinnerBanner 节点类型必须是 RichTextLabel,@onready 变量类型也要对齐。
    main_src = _read(MAIN_GD)
    main_tscn = _read(ROOT / "godot-client" / "scenes" / "main.tscn")
    # 1) main.gd 里 show_battle_result 真的在用 bbcode_enabled
    assert "battle_result_winner.bbcode_enabled = true" in main_src
    # 2) 节点必须是 RichTextLabel
    assert '[node name="WinnerBanner" type="RichTextLabel"' in main_tscn
    # 3) @onready 变量类型也必须对齐
    assert "battle_result_winner: RichTextLabel" in main_src
    # 4) 字体覆盖要走 normal_font_size(RichTextLabel 字段名),不是 Label 的 font_size
    winner_idx = main_src.index("func show_battle_result(")
    winner_end = main_src.index("\n\n", winner_idx)
    winner_body = main_src[winner_idx:winner_end]
    assert "add_theme_font_size_override(\"normal_font_size\"" in winner_body or "battle_result_stats" in winner_body
    # 5) .tscn 里 bbcode_enabled 已默认打开
    assert "WinnerBanner" in main_tscn
    winner_block = main_tscn[main_tscn.index("WinnerBanner"):main_tscn.index("StatsList")]
    assert 'type="RichTextLabel"' in winner_block


def test_godot_in_progress_view_only_reads_saves_not_active_games():
    # T:#17 — 进行中视图语义收窄到"存档域":
    #  - suspend(中断存档, 至多 1 个)
    #  - 已存的活动主线 manual 槽
    # 故意不渲染 /games 里的活动对局 — 那跟"中断存档"是两回事,
    # 活动对局应通过联机大厅的 room list 找回。
    in_progress_src = _read(ROOT / "godot-client" / "scripts" / "ui" / "in_progress_controller.gd")
    # 1) InProgressView 仍然只拉 /saves(不破坏已有 _on_saves_response 解析)
    assert 'NetworkClient.list_saves(_main._user_name, Callable(self, "_on_saves_response"))' in in_progress_src
    # 2) InProgressView 不应该再拉 /games
    assert "NetworkClient.list_games" not in in_progress_src
    # 3) 不应该再有 _active_games 字段 / 活动对局渲染块 / _render_game_row / _on_game_resume_pressed
    assert "_active_games" not in in_progress_src
    assert "_on_games_response" not in in_progress_src
    assert "_render_game_row" not in in_progress_src
    assert "_on_game_resume_pressed" not in in_progress_src
    # 4) 空态文案要跟新语义对齐
    assert "中断存档" in in_progress_src
    assert "活动主线" in in_progress_src
    # 5) 旧 UI 文案"进行中游戏"已删
    assert "进行中游戏" not in in_progress_src
    assert "🎮" not in in_progress_src


def test_godot_lobby_commander_fetch_forwards_to_mainline_controller():
    # T:#16 — commanders 拉取统一收口在 mainline_controller._on_commanders_response,
    # 它会同时刷新主线指挥官下拉和联机大厅下拉(末尾 _main._setup_lobby_commander_options)。
    # 联机大厅 _enter_lobby_view 调 get_unlocked_commanders 时,回调必须
    # 转发到 mainline_view,不能挂到 self(main.gd 根本没有 _on_commanders_response,
    # 否则 lobby_commander_option 永远只剩"不选择指挥官"一项,创房时所有座位都拿不到 host commander)。
    main_src = _read(MAIN_GD)
    mainline_src = _read(ROOT / "godot-client" / "scripts" / "mainline" / "mainline_controller.gd")
    # 1) mainline_controller 仍是 commander 拉取的唯一所有者
    assert "func _on_commanders_response(" in mainline_src
    # 2) main.gd 不应有这个方法(避免重入 / 误用)
    assert "func _on_commanders_response(" not in main_src
    # 3) _enter_lobby_view 里调用 get_unlocked_commanders 时,callback 必须是
    #    Callable(mainline_view, "_on_commanders_response"),不能是 self
    lobby_start = main_src.index("func _enter_lobby_view(")
    lobby_end = main_src.index("\n\n", lobby_start)
    lobby_body = main_src[lobby_start:lobby_end]
    assert "NetworkClient.get_unlocked_commanders" in lobby_body
    assert 'Callable(mainline_view, "_on_commanders_response")' in lobby_body
    assert 'Callable(self, "_on_commanders_response")' not in lobby_body


def test_godot_mainline_start_passes_prepare_compatible_arguments():
    # P2: mainline 域已抽到 mainline_controller.gd(main.gd 还保留 _on_ml_slot_resume_response
    # 等 thin wrapper,但 start/prepare/start_response 等已搬走)。
    src = _read(ROOT / "godot-client" / "scripts" / "mainline" / "mainline_controller.gd")
    assert "NetworkClient.get_mainline_prepare(" in src
    assert "func _on_prepare_start_pressed() -> void:" in src
    assert 'NetworkClient.start_mainline(_main._selected_mainline_id, _main._user_name, false, [], Callable(self, "_on_mainline_start_response"))' in src
    assert 'NetworkClient.start_mainline(mainline_id, _main._user_name, false, [], Callable(self, "_on_mainline_start_response"), true)' in src
    assert 'NetworkClient.next_battle_mainline(_main._active_mainline_id, _main._user_name, [], Callable(self, "_on_mainline_next_battle_response"))' in src


def test_godot_mainline_entry_is_slot_first_not_chapter_list():
    # FE8-style mainline entry: choose one of the three formal save slots first.
    # The full chapter list may still exist as an internal/debug helper, but it
    # must not be the default player-facing entry path.
    src = _read(ROOT / "godot-client" / "scripts" / "mainline" / "mainline_controller.gd")
    open_start = src.index("func open() -> void:")
    open_end = src.index("func _set_node_visible(", open_start)
    open_body = src[open_start:open_end]
    assert 'NetworkClient.list_saves(_main._user_name, Callable(self, "_on_ml_slots_response"))' in open_body
    assert "NetworkClient.list_mainlines" not in open_body
    assert "NetworkClient.list_mainlines" in src
    assert "func _on_ml_slots_response(" in src
    assert "func _on_slot_continue_pressed(" in src
    assert "func _on_slot_new_game_pressed(" in src


def test_godot_mainline_slots_continue_and_new_game_use_save_cursor():
    src = _read(ROOT / "godot-client" / "scripts" / "mainline" / "mainline_controller.gd")
    assert 'NetworkClient.load_save(_main._user_name, "manual", slot_index' in src
    assert 'NetworkClient.start_mainline(_DEFAULT_MAINLINE_ID, _main._user_name, false, [], Callable(self, "_on_slot_new_start_response").bind(slot_index), true)' in src
    assert "NetworkClient.save_manual(" in src
    assert '_main._selected_mainline_id = str(body.get("mainline_id"' in src
    assert 'NetworkClient.get_mainline_detail(_main._selected_mainline_id' in src


def test_godot_prepare_ui_uses_hero_backend_actions():
    # P2: prepare UI 已抽到 mainline_controller.gd(plan §Batch B)。
    src = _read(ROOT / "godot-client" / "scripts" / "mainline" / "mainline_controller.gd")
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
        assert snippet in src


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





def test_godot_lobby_ai_replacement_renders_ai_state_not_waiting_player():
    source = _read(MAIN_GD)
    start = source.index("func _build_lobby_seat_card(")
    end = source.index("func _lobby_team_index_for_seat(", start)
    body = source[start:end]
    helper_start = source.index("func _lobby_seat_status_text(")
    helper_end = source.index("func _lobby_seat_commander_id(", helper_start)
    helper = source[helper_start:helper_end]
    assert "_lobby_seat_status_text(index)" in body
    assert "等待玩家入座" in helper
    assert "入座中" in helper
    assert "_lobby_ai_replacement_for_seat" in helper
    assert '"%s 已入座" % occupant_name' not in body


def test_godot_lobby_ai_replacement_is_per_seat_not_global():
    source = _read(MAIN_GD)
    toggle_start = source.index("func _on_lobby_seat_ai_toggled(")
    toggle_end = source.index("func _request_add_ai_for_seat(", toggle_start)
    toggle_body = source[toggle_start:toggle_end]
    clear_start = source.index("func _clear_player_from_other_seats(")
    clear_end = source.index("func _on_lobby_seat_update_response(", clear_start)
    clear_body = source[clear_start:clear_end]

    assert "_clear_player_from_other_seats(_user_name, seat_index)" in toggle_body
    assert "for i in range(_lobby_seat_ai_replacements.size()):" not in toggle_body
    assert "_lobby_seat_ai_replacements[i] = false" not in clear_body


def test_godot_lobby_add_ai_passes_target_seat_and_auto_start_skips_room_page():
    main = _read(MAIN_GD)
    network = _read(NETWORK_CLIENT)

    request_start = main.index("func _request_add_ai_for_seat(")
    request_end = main.index("func _on_lobby_seat_ai_remove_response(", request_start)
    request_body = main[request_start:request_end]
    assert 'Callable(self, "_on_lobby_seat_ai_add_response").bind(seat_index),' in request_body
    assert "seat_index)" in request_body

    pipeline_start = main.index("func _continue_lobby_ai_creation(")
    pipeline_end = main.index("func _on_lobby_configured_ai_added(", pipeline_start)
    pipeline_body = main[pipeline_start:pipeline_end]
    assert 'Callable(self, "_on_lobby_configured_ai_added").bind(seat_index),' in pipeline_body
    assert "seat_index\n\t)" in pipeline_body

    configured_start = main.index("func _on_lobby_configured_ai_added(")
    configured_end = main.index("func _on_lobby_configured_ai_seated(", configured_start)
    configured_body = main[configured_start:configured_end]
    assert "NetworkClient.update_player_seat" not in configured_body

    join_start = main.index("func _on_lobby_join_response(")
    join_end = main.index("func _auto_add_ai_after_lobby_create(", join_start)
    join_body = main[join_start:join_end]
    pending_line = "if _entry_flow == \"lobby_create\" and _game_id > 0 and _pending_lobby_start_after_create:"
    assert pending_line in join_body
    assert join_body.index(pending_line) < join_body.index("_show_lobby_in_room()")

    assert "seat: int = -1" in network
    assert 'body["seat"] = seat' in network


def test_godot_lobby_start_requires_all_map_seats_configured():
    source = _read(MAIN_GD)

    assert "func _configured_lobby_create_participant_count() -> int:" in source
    assert "func _refresh_lobby_create_start_gate() -> void:" in source
    assert "configured < required" in source

    create_start = source.index("func _on_create_room_pressed() -> void:")
    create_end = source.index("func _on_join_selected_pressed() -> void:", create_start)
    create_body = source[create_start:create_end]
    assert "_configured_lobby_create_participant_count() < _selected_lobby_player_count()" in create_body
    assert "return" in create_body

    lobby_state_start = source.index("func _on_lobby_state(")
    lobby_state_end = source.index("func _render_lobby_ai_options(", lobby_state_start)
    lobby_state_body = source[lobby_state_start:lobby_state_end]
    assert "fighter_count < required_count" in lobby_state_body
    assert "lobby_start_btn.disabled = fighter_count < required_count" in lobby_state_body
    assert "start_game_inline_btn.disabled = fighter_count < required_count" in lobby_state_body


def test_godot_lobby_four_player_seat_cards_have_room_for_commander_text():
    source = _read(MAIN_GD)
    start = source.index("func _build_lobby_seat_card(")
    end = source.index("func _lobby_team_index_for_seat(", start)
    body = source[start:end]

    assert "card.custom_minimum_size = Vector2(0, 190)" in body
    assert "ability.custom_minimum_size = Vector2(0, 34)" in body
    assert "ability.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART" in body
    assert "ability.clip_text = true" in body


def test_godot_home_buttons_are_connected_or_intentionally_dynamic():
    source = _read(MAIN_GD)
    scene = _read(ROOT / "godot-client" / "scenes" / "main.tscn")

    for node_name, callback in [
        ("HelpButton", "_on_help_pressed"),
        ("SettingsButton", "_on_settings_open_pressed"),
        ("InProgressButton", "_on_in_progress_pressed"),
        ("SavesButton", "_on_saves_pressed"),
        ("EditorButton", "_on_editor_pressed"),
    ]:
        assert f'[node name="{node_name}" type="Button"' in scene
        assert callback in source
        assert f".pressed.connect({callback})" in source
    assert '[node name="ResumeButton" type="Button"' in scene
    assert "resume_button.visible = _resume_game_id > 0" in source


def test_godot_mainline_page_switch_hides_prepare_controls_except_ready():
    source = _read(ROOT / "godot-client" / "scripts" / "mainline" / "mainline_controller.gd")
    start = source.index("func _set_mainline_page(")
    end = source.index("func _on_ml_list_response(", start)
    body = source[start:end]
    # ✅ 准备好了 在 chapter_list 常驻可见(start/refresh/action/alt_action 只在 prepare 显示)
    for control in [
        "ml_prep_start_btn",
        "ml_prep_refresh_btn",
        "ml_prep_action_btn",
        "ml_prep_alt_action_btn",
    ]:
        assert control in body
    scene = _read(ROOT / "godot-client" / "scenes" / "main.tscn")
    complete_start = scene.index('[node name="MLPrepCompleteBtn"')
    complete_end = scene.index("\n\n", complete_start)
    refresh_start = scene.index('[node name="MLPrepRefreshBtn"')
    refresh_end = scene.index("\n\n", refresh_start)
    assert scene[complete_start:complete_end] != scene[refresh_start:refresh_end].replace(
        "MLPrepRefreshBtn", "MLPrepCompleteBtn"
    ).replace("刷新整备", "✅ 准备好了")
    ready_start = source.index("func _ready() -> void:")
    ready_end = source.index("func open() -> void:", ready_start)
    ready_body = source[ready_start:ready_end]
    for callback in [
        "_on_ml_back_pressed",
        "_on_ml_abandon_pressed",
        "_on_prepare_start_pressed",
        "_on_prepare_complete_pressed",
        "_on_prepare_refresh_pressed",
        "_on_prepare_primary_action_pressed",
        "_on_prepare_secondary_action_pressed",
    ]:
        assert callback in ready_body
    action_start = source.index("func _update_prepare_action_buttons() -> void:")
    action_end = source.index("func _on_prepare_primary_action_pressed()", action_start)
    action_body = source[action_start:action_end]
    assert '_main._mainline_page != "prepare"' in action_body


def test_godot_saves_view_sections_have_explicit_vertical_order():
    source = _read(ROOT / "godot-client" / "scenes" / "main.tscn")
    frame_start = source.index('[node name="SaveFrame"')
    frame_end = source.index("; ============================================================", frame_start + 1)
    frame = source[frame_start:frame_end]
    assert 'type="VBoxContainer"' in frame or 'type="ScrollContainer"' in frame
    assert "SaveSlotsContainer" in frame
    assert "SaveAutoRow" in frame
    assert "SaveSuspendRow" in frame
    for legacy_title in ['[node name="OpenTitle"', '[node name="MainlineTitle"']:
        title_start = frame.index(legacy_title)
        title_end = frame.index("\n\n", title_start)
        assert "visible = false" in frame[title_start:title_end]


def test_godot_lobby_seat_invariant_one_player_one_seat():
    # T:#19 — 同一玩家(_user_name)最多出现在 1 个座位的 occupants;
    # 同一 AI 占位最多出现在 1 个座位(避免 toggle AI 后多槽同 AI)。
    # _on_lobby_seat_action_pressed 入座前必须先清掉其它座位里的 _user_name;
    # _on_lobby_seat_ai_toggled ON 之前必须先清掉其它 AI 占位。
    src = _read(MAIN_GD)
    func_idx = src.index("func _on_lobby_seat_action_pressed(")
    func_end = src.index("\n\n", func_idx)
    body = src[func_idx:func_end]
    assert "_clear_player_from_other_seats" in body, "入座前必须清掉其它座位里的 _user_name"
    ai_idx = src.index("func _on_lobby_seat_ai_toggled(")
    ai_end = src.index("\n\n", ai_idx)
    ai_body = src[ai_idx:ai_end]
    assert "_clear_player_from_other_seats" in ai_body, "AI 切换前必须清掉其它座位里的 _user_name + 其它 AI 占位"
    helper_idx = src.index("func _clear_player_from_other_seats(")
    helper_end = src.index("\n\n", helper_idx)
    helper = src[helper_idx:helper_end]
    assert "exclude_seat" in helper, "helper 必须支持 exclude_seat 参数"


def test_godot_lobby_start_success_enters_game_without_connecting_view():
    source = _read(MAIN_GD)
    start = source.index("func _on_lobby_start_response(")
    end = source.index("func _on_lobby_back_pressed(", start)
    body = source[start:end]
    assert '_show_view("game")' in body
    assert '_show_view("connecting")' not in body
    assert "NetworkClient.connect_to_game" in body


def test_godot_portrait_uses_native_size_inside_target_panel():
    source = _read(MAIN_GD)
    scene = _read(ROOT / "godot-client" / "scenes" / "main.tscn")
    assert '[node name="HeroPortraitPanel" type="Panel" parent="GameView/HUD"]' in scene
    # T:V6 — 立绘改 STRETCH_KEEP_ASPECT_CENTERED 缩放到 panel 大小(用户要求
    # 高度一致、宽度按比例自适应、原图比例不变)
    assert "STRETCH_KEEP_ASPECT_CENTERED" in source
    assert "_unit_info_portrait_tex.size = hero_portrait_panel.size" in source
    assert "unit_info.offset_right = -108" not in source


def test_legacy_web_attack_targets_use_manhattan_range_only():
    source = _read(WEB_APP_JS)
    start = source.index("function canUnitAttack(")
    end = source.index("// Combat forecast", start)
    body = source[start:end]
    assert "manhattan(fromX, fromY, toX, toY)" in body
    assert "clientHasLineOfSight" not in body
