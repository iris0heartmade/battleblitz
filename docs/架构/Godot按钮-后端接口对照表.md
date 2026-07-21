# Godot 客户端所有按钮 vs 后端接口对照表

> 自动生成:_build_button_audit.py
> main.tscn 共 **51** 个 Button(全部静态 + 部分动态 `.bind`) × main.gd handlers × `NetworkClient.*`
> **dead 按钮:14**  
> **状态分布**:`✅ live`(接 endpoint)= 28  ·  `🎨 UI-only`= 23  ·  `❌ dead`= 0

| # | 路径 | text | handler | NetworkClient 调用 | 后端 endpoint | 状态 | 备注 |
|---|------|------|---------|--------------------|----------------|------|------|
| 1 | `Menu/CenterContainer/GroupRow/SoloCard/MainlineButton` | `主线章节` | `_on_mainline_pressed` | `list_heroes`, `get_unlocked_commanders`, `list_mainlines`, `list_saves` | `GET /heroes`, `GET /players/me/commanders?user_name=`, `GET /mainlines[?user_name]`, `GET /saves?user_name=` | ✅ live | 接线 + endpoint 完整 |
| 2 | `Menu/CenterContainer/GroupRow/MultiCard/LobbyButton` | `联机大厅` | `_on_lobby_pressed` | `get_unlocked_commanders` | `GET /players/me/commanders?user_name=` | ✅ live | 接线 + endpoint 完整 |
| 3 | `Menu/CenterContainer/GroupRow/MultiCard/JoinByCodeRow/JoinByCodeButton` | `按号加入` | `_on_join_by_code_pressed` | `join_game` | `POST /games/{id}/join` | ✅ live | 接线 + endpoint 完整 |
| 4 | `Menu/CenterContainer/FooterRow/ResumeButton` | `继续对局` | `_on_resume_pressed` | `load_suspend`, `rejoin_game_by_player_id`, `rejoin_game_by_name` | `POST /saves/load_suspend`, `POST /games/{id}/rejoin`, `POST /games/{id}/rejoin_by_name` | ✅ live | 接线 + endpoint 完整 |
| 5 | `Menu/CenterContainer/FooterRow/EditorButton` | `地图编辑` | `_on_editor_pressed` | `list_editor_maps` | `GET /editor/maps` | ✅ live | 接线 + endpoint 完整 |
| 6 | `Connecting/ConnectingInner/ReconnectButton` | `重 连` | `_on_reconnect_pressed` | `connect_to_game` | `WS /ws/games/{id}?player_id=&since_seq=` | ✅ live | 接线 + endpoint 完整 |
| 7 | `EditorView/EditorPanel/EditorApplyBiomeBtn` | `套用` | `_on_editor_apply_biome_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 8 | `EditorView/EditorPanel/EditorLoadBtn` | `加载地图` | `_on_editor_load_pressed` | `load_editor_map` | `GET /editor/maps/{id}` | ✅ live | 接线 + endpoint 完整 |
| 9 | `EditorView/EditorPanel/EditorNewBtn` | `新建 15x15` | `_on_editor_new_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 10 | `EditorView/EditorPanel/EditorResizeBtn` | `应用尺寸` | `_on_editor_resize_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 11 | `EditorView/EditorPanel/EditorRedoBtn` | `重做` | `_on_editor_redo_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 12 | `EditorView/EditorPanel/EditorDeleteBtn` | `删除地图` | `_on_editor_delete_pressed` | `delete_editor_map` | `DELETE /editor/maps/{id}` | ✅ live | 接线 + endpoint 完整 |
| 13 | `Lobby/LobbyFrame/ChoosePanel/ChooseBtnRow/CreateCard/CreateCardInner/CreateCardBtn` | `开始创建` | `_on_create_card_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 14 | `Lobby/LobbyFrame/ChoosePanel/ChooseBtnRow/JoinCard/JoinCardInner/JoinCardBtn` | `浏览房间` | `_on_join_card_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 15 | `Lobby/LobbyFrame/LobbyDualCol/LeftCol/LeftBtnRow/RefreshRoomsBtn` | `刷新房间` | `_refresh_room_list` | `list_games` | `GET /games[?user_name]` | ✅ live | 接线 + endpoint 完整 |
| 16 | `Lobby/LobbyFrame/LobbyDualCol/RightCol/TeamRow/LobbyApplyTeamBtn` | `应用队伍` | `_on_lobby_apply_team_pressed` | `update_player_team` | `PATCH /games/{id}/players/{pid}/team` | ✅ live | 接线 + endpoint 完整 |
| 17 | `Lobby/LobbyFrame/LobbyDualCol/RightCol/CreateRoomBtn` | `创建并加入` | `_on_create_room_pressed` | `create_game` | `POST /games` | ✅ live | 接线 + endpoint 完整 |
| 18 | `Lobby/LobbyFrame/HostRow/LobbyHostApplyBtn` | `改队伍` | `_on_lobby_host_apply_pressed` | `update_player_team` | `PATCH /games/{id}/players/{pid}/team` | ✅ live | 接线 + endpoint 完整 |
| 19 | `Lobby/LobbyFrame/AiActionRow/LobbyAddAiBtn` | `添加电脑` | `_on_lobby_add_ai_pressed` | `add_ai_player` | `POST /games/{id}/add-ai` | ✅ live | 接线 + endpoint 完整 |
| 20 | `Lobby/LobbyFrame/BottomBar/LobbyStartBtn` | `启动游戏` | `_on_lobby_start_pressed` | `start_game` | `POST /games/{id}/start` | ✅ live | 接线 + endpoint 完整 |
| 21 | `SavesView/SaveFrame/SaveResumeBtn` | `继续存档` | `_on_save_resume_pressed` | `load_suspend`, `load_save` | `POST /saves/load_suspend`, `POST /saves/load` | ✅ live | 接线 + endpoint 完整 |
| 22 | `SavesView/SaveFrame/SaveNewBtn` | `💾 新建` | `_on_save_new_pressed` | `save_manual` | `POST /saves/save` | ✅ live | 接线 + endpoint 完整 |
| 23 | `SavesView/SaveFrame/SaveBackBtn` | `返回上级` | `_on_save_back_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 24 | `MainlineView/MLFrame/MLPrepTabs/HeroesTabBtn` | `英雄` | `_on_prepare_tab_pressed` | `get_post_battle_shop`, `get_mercenary_config` | `GET /mainlines/{id}/shop?user_name=`, `GET /mainlines/{id}/mercenary/config?user_name=` | ✅ live | var ml_prep_heroes_tab_btn 已接 _on_prepare_tab_pressed(name 转换匹配失败但实际已接) |
| 25 | `MainlineView/MLFrame/MLPrepTabs/ShopTabBtn` | `商店` | `_on_prepare_tab_pressed` | `get_post_battle_shop`, `get_mercenary_config` | `GET /mainlines/{id}/shop?user_name=`, `GET /mainlines/{id}/mercenary/config?user_name=` | ✅ live | var ml_prep_shop_tab_btn 已接 _on_prepare_tab_pressed(name 转换匹配失败但实际已接) |
| 26 | `MainlineView/MLFrame/MLPrepStartBtn` | `开始战斗` | `_on_prepare_start_pressed` | `get_mainline_prepare`, `start_mainline` | `GET /mainlines/{id}/prepare?user_name=`, `POST /mainlines/{id}/start` | ✅ live | 接线 + endpoint 完整 |
| 27 | `MainlineView/MLFrame/MLPrepCompleteBtn` | `✅ 准备好了` | `_on_prepare_complete_pressed` | `complete_mainline_prepare` | `POST /mainlines/{id}/prepare/complete` | ✅ live | 接线 + endpoint 完整 |
| 28 | `MainlineView/MLFrame/MLPrepRefreshBtn` | `刷新整备` | `_on_prepare_refresh_pressed` | `get_mainline_prepare` | `GET /mainlines/{id}/prepare?user_name=` | ✅ live | 接线 + endpoint 完整 |
| 29 | `MainlineView/MLFrame/MLPrepActionBtn` | `整备操作` | `_on_prepare_primary_action_pressed` | `list_saves` | `GET /saves?user_name=` | ✅ live | 接线 + endpoint 完整 |
| 30 | `MainlineView/MLFrame/MLPrepAltActionBtn` | `辅助操作` | `_on_prepare_secondary_action_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 31 | `MainlineView/MLFrame/ApplyCommanderBtn` | `选定指挥官` | `_on_apply_mainline_commander_pressed` | `select_mainline_commander` | `POST /mainlines/{id}/select-commander` | ✅ live | var ml_apply_commander_btn 已接 _on_apply_mainline_commander_pressed(name 转换匹配失败但实际已接) |
| 32 | `MainlineView/MLFrame/MLBackBtn` | `返回主菜单` | `_on_ml_back_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 33 | `MainlineView/MLFrame/MLAbandonBtn` | `放弃主线` | `_on_ml_abandon_pressed` | `abandon_mainline` | `POST /mainlines/{id}/abandon` | ✅ live | 接线 + endpoint 完整 |
| 34 | `GameView/HUD/TopRight/EndTurnButton` | `结束回合` | `_on_end_turn_pressed` | `action_end_turn` | `POST /games/{id}/end-turn` | ✅ live | 接线 + endpoint 完整 |
| 35 | `GameView/HUD/BottomRight/WarReportButton` | `战报` | `_on_war_report_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 36 | `GameView/HUD/ActionBubble/ActionList/MoveBtn` | `移动` | `_on_move_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 37 | `GameView/HUD/ActionBubble/ActionList/WaitBtn` | `待命` | `_on_wait_pressed` | `action_wait` | `POST /games/{id}/wait` | ✅ live | 接线 + endpoint 完整 |
| 38 | `GameView/HUD/AttackConfirmPanel/ButtonRow/ConfirmBtn` | `攻击` | `_on_attack_confirm_pressed` | — | — | 🎨 UI-only | var attack_confirm_btn 已接 handler _on_attack_confirm_pressed(name 转换匹配失败,实际 UI-only) |
| 39 | `GameView/HUD/WarReportPanel/CloseBtn` | `✕` | `_on_war_report_close_pressed` | — | — | 🎨 UI-only | var war_report_close_btn 已接 handler _on_war_report_close_pressed(name 转换匹配失败,实际 UI-only) |
| 40 | `GameView/HUD/SettingsPanel/CloseBtn` | `✕` | `_on_war_report_close_pressed` | — | — | 🎨 UI-only | var war_report_close_btn 已接 handler _on_war_report_close_pressed(name 转换匹配失败,实际 UI-only) |
| 41 | `GameView/HUD/SettingsPanel/SettingsList/FontRow/FontSmallBtn` | `小 (12)` | `_on_font_small_pressed` | — | — | 🎨 UI-only | var settings_font_small_btn 已接 handler _on_font_small_pressed(name 转换匹配失败,实际 UI-only) |
| 42 | `GameView/HUD/SettingsPanel/SettingsList/ColorRow/RedBtn` | `● 🔴` | `_on_red_color_pressed` | — | — | 🎨 UI-only | var settings_red_btn 已接 handler _on_red_color_pressed(name 转换匹配失败,实际 UI-only) |
| 43 | `GameView/HUD/SettingsPanel/SettingsList/ColorRow/YellowBtn` | `● 🟡` | `_on_yellow_color_pressed` | — | — | 🎨 UI-only | var settings_yellow_btn 已接 handler _on_yellow_color_pressed(name 转换匹配失败,实际 UI-only) |
| 44 | `GameView/HUD/SettingsPanel/SettingsList/AudioRow/MuteBtn` | `静音` | `_on_mute_toggled` | — | — | 🎨 UI-only | var settings_mute_btn 已接 handler _on_mute_toggled(name 转换匹配失败,实际 UI-only) |
| 45 | `GameView/HUD/SettingsPanel/SettingsList/ButtonRow/CancelBtn` | `❌  取消` | `_on_cancel_pressed` | — | — | 🎨 UI-only | 纯 UI 状态切换(切 view / 切 tab / 派对话框等),无后端 |
| 46 | `GameView/HUD/PausePanel/PauseList/ResumeBtn` | `▶  继续游戏` | `_on_ml_slot_resume` | `load_save` | `POST /saves/load` | ✅ live | 接线 + endpoint 完整 |
| 47 | `GameView/HUD/PausePanel/PauseList/PauseSuspendBtn` | `⏸  中断退出` | `_on_pause_suspend_pressed` | `capture_suspend` | `POST /games/{id}/suspend` | ✅ live | 接线 + endpoint 完整 |
| 48 | `GameView/HUD/DialogPanel/ContinueBtn` | `继续 ▶` | `_on_dialog_continue_pressed` | — | — | 🎨 UI-only | var dialog_continue_btn 已接 handler _on_dialog_continue_pressed(name 转换匹配失败,实际 UI-only) |
| 49 | `GameView/HUD/TutorialBubble/GotItBtn` | `知道了` | `_on_tutorial_got_it_pressed` | — | — | 🎨 UI-only | var tutorial_got_it_btn 已接 handler _on_tutorial_got_it_pressed(name 转换匹配失败,实际 UI-only) |
| 50 | `GameView/HUD/BattleResultPanel/ResultBtnRow/DetailBtn` | `📜 详细战报` | `_on_battle_detail_pressed` | — | — | 🎨 UI-only | var battle_detail_btn 已接 handler _on_battle_detail_pressed(name 转换匹配失败,实际 UI-only) |
| 51 | `GameView/HUD/RecruitPanel/CloseBtn` | `关 闭` | `_on_war_report_close_pressed` | — | — | 🎨 UI-only | var war_report_close_btn 已接 handler _on_war_report_close_pressed(name 转换匹配失败,实际 UI-only) |

## 无 handler 的死按钮(14)

- `MainlineView/MLFrame/MLPrepTabs/HeroesTabBtn`
- `MainlineView/MLFrame/MLPrepTabs/ShopTabBtn`
- `MainlineView/MLFrame/ApplyCommanderBtn`
- `GameView/HUD/AttackConfirmPanel/ButtonRow/ConfirmBtn`
- `GameView/HUD/WarReportPanel/CloseBtn`
- `GameView/HUD/SettingsPanel/CloseBtn`
- `GameView/HUD/SettingsPanel/SettingsList/FontRow/FontSmallBtn`
- `GameView/HUD/SettingsPanel/SettingsList/ColorRow/RedBtn`
- `GameView/HUD/SettingsPanel/SettingsList/ColorRow/YellowBtn`
- `GameView/HUD/SettingsPanel/SettingsList/AudioRow/MuteBtn`
- `GameView/HUD/DialogPanel/ContinueBtn`
- `GameView/HUD/TutorialBubble/GotItBtn`
- `GameView/HUD/BattleResultPanel/ResultBtnRow/DetailBtn`
- `GameView/HUD/RecruitPanel/CloseBtn`

> 原因:这些 button 节点在 main.tscn 存在,但 main.gd 没有 `*.pressed.connect(...)` 接线。
> 检查:可能是 main.gd 用了不同的 handler 名/var 名;或事件被另一段 `_input` 直接处理;或纯视觉残留。

## 备注
- `network_client.gd` 中所有 50 个 typed methods 都在本表 endpoint 映射里;若调用了未列出的 `NetworkClient.x` 即为不在服务端实现或已被删
- 本表仅涵盖 `main.tscn` 静态按钮;`main.gd` 中 `_for g in games` 等运行时动态创建的不计入
- `pre_battle_dialogue`/`/advance` 自动存档/`auto-save` 等后端内部触发链不暴露成按钮,但服务端的 `auto_save_checkpoint` 仍生效
