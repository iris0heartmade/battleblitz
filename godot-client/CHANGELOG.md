# BattleBlitz Godot Client Changelog

## 2026-07-31

- 修复棋盘 ↔ 主菜单的「瞬切错位」bug(游戏胜利 / 失败 / 中断 退出再回主菜单时,主菜单会被 BoardCamera 的 zoom/position/smoothing 残值拉飞一帧):
  - `main.gd` 重写 `_reset_board_cameras`: 先强制把每个 `Camera2D` 的 `zoom = (1,1)`、`position = (0,0)`、关掉 `position_smoothing_enabled` 与 `zoom_smoothing_enabled`,再 `enabled = false`,最后 `viewport.canvas_transform = IDENTITY`。
  - 新增 `_disable_all_cameras_in_tree`: 用 `find_children("Camera2D")` 兜底扫整棵树,防未来新增 Editor/UI 相机漏网。
  - 新增 `_post_frame_viewport_reset`(`call_deferred`): 帧末再 reset 一次,接住同帧内残留 tween / state_updated 回调又把 camera 设回去的情况。仅当 `_current_view != "game" / "editor"` 时生效,正常游戏视图不受影响。
  - 新增 `_current_view` 跟踪当前 view 状态,作为 _show_view 内 `_reset_board_cameras` 的开关依据。
  - `HUD` / `BattleBackdrop` 的 `CanvasLayer.transform` 同步归零,兜底 CanvasLayer 上的 transform 残值。
  - 同步修复两条之前漏掉 `_reset_game_state_for_main_menu` 的返回路径:`_on_battle_back_menu_pressed`(战报 → 主菜单)与 `_on_battle_back_lobby_pressed`(战报 → 大厅),补全 action bubble / recruit / move-attack-skill mode / GameState / Board 高亮 / WS / tween 清理,与 pause → 主菜单行为一致。

## 2026-07-30

- Added hero `youko` / 洋子 as a T1 special Bard (`bard`) with the active skill `sing` / 吟诗, Godot skill targeting, and hero assets (`youko.png`, `portrait_youko.png`, `crest_youko.png`). Bard is intentionally excluded from ordinary barracks recruitment.

- 修复主线开战前对白被跳过/不可见: `DialogManager` 播放时重新显示对话面板,主线 start 响应改为先等待 `pre_battle_dialogue_url` 播放完成,再进入棋盘并连接战斗。
- 修正 `entry_flow_e2e.gd` 的合并后入口调用: 主线改走 `MainlineView` 存档槽控制器,大厅改走 `$Lobby` 控制器,并在失败后停止误报 PASS。
- 修复 `main.gd` 模块化重构合并 `origin/feat/godot-mainline-fe-ui` 后的战斗 UI 回退: 恢复战斗专用背景层显隐、棋盘外深色 HUD 边界、行动气泡侧翼/避让定位、CO 顶栏中文化与紧凑排版、单位检视卡正式文案和地形移动消耗信息; 保留本地通用单位立绘路径与 `PortraitLoader` 加载逻辑。
- 新增 `test_godot_battle_hud_keeps_mainline_fe_ui_layout_rules` 防止旧版透明背景、贴单位气泡、`RED:<null>`/`Hero ID` 调试字段再次回流; 同步 `smoke_test.gd` 与 `portrait_check_screenshot.gd` 的立绘调用参数。
- 合并 `origin/feat/godot-mainline-fe-ui` 到 `refactor/extract-mainline-modules`,保留 UI 分支完整历史,同时延续本地 `main.gd` 模块化抽离成果。
- 接入主线响应式 `CampaignPanel` / `PreparePanel` 场景、战斗 HUD 美术素材、`battle_theme.gd` / `mainline_theme.gd` / `mainline_*_panel.gd` 新 UI 组件。
- 调和冲突点: `scenes/main.tscn` 采用 UI 分支的新场景结构并补回 `$Lobby` 的 `lobby_controller.gd` 挂载;`mainline_controller.gd` 保留存档优先渲染,英雄对话缓存切回 `DialogManager`;`main.gd` 保持对话/大厅/主题抽离,只补新增 HUD 节点引用与单位检视卡接线。
- 单位检视卡合并两边能力: UI 分支的紧凑右侧卡片 + 本地通用兵种立绘路径共存;透明无边框立绘槽断言迁移到抽离后的 `hud_theme.gd`。
- 验证: `python -m pytest game/tests/test_godot_unit_portrait_paths.py game/tests/test_save_resume_fixes.py game/tests/test_save_slot_independence.py` 16 passed;本机 PATH 未发现 `godot`,Godot headless 场景测试需在装有 Godot CLI 的环境补跑。

## 2026-07-29

- 对话系统抽离为 `DialogManager` 全局 autoload:新增 `scripts/autoload/dialog_manager.gd`(498 行),挂在 root 层 CanvasLayer(layer=50)上,跨 menu / lobby / game view 都可见。从 `scripts/main.gd` 删除 6 个 `@onready` 引用、3 个常量、9 个状态变量、13 个函数(~220 行),同步从 `scenes/main.tscn` 删除 DialogPanel 子树 62 行(7 个节点)。新增 `scripts/core/portrait_loader.gd` 共享头像加载器。
- 对话 API 重构为 async/await 范式:`DialogManager.play(scenes, context) -> Dictionary` 可 `await` 并返回 `{"choice_value": String}`;同时暴露 `signal scene_advanced / dialogue_finished / choice_made / dialogue_aborted` 供 fire-and-forget。配套 `show_dialog(scene)` / `hide_dialog()` / `reset()` / `is_playing()` / `load_portrait(path)` / `register_hero_speaker()` 公共方法。
- 首批 4 套触发点接入:`_on_state_updated` 末尾检测本地玩家回合起(去重 `(game_id, turn, player_id)` 避免 state poll 反复触发)、`GameState.unit_killed` 旁白、CO power 前后(由 `UserSettings` `dialog.v1.co_power_confirm` 开关,默认关闭避免疲劳)、攻击前后(由 `dialog.v1.attack_confirm` 开关);招募/占领响应尾部追加旁白。
- `NetworkClient.action_attack / action_co_power / action_claim` 三个 wrapper 新增 `callback: Callable = Callable()` 透传参数(`action_recruit` 早已支持),为「动作后旁白」提供 REST 回调通道。
- `InputState` 新增嵌套可重入 `lock() / unlock() / set_locked() / is_input_locked()` 与 `lock_changed` 信号;`DialogManager._start()` 自动 `InputState.lock()`,`_advance()` 队列空时自动 `unlock()`,业务侧不需手动管理。
- 顺手修 3 个真 bug:
  - Typewriter 重写为 `RichTextLabel.visible_ratio` + `tween_method`(原 tween 创建后立即 kill,callback 只改 `_dialog_visible_text` 不写 `dialog_text.text`,实际整段直接闪现)。
  - `choices[].value` 通过 `pressed.connect(_on_choice_selected.bind(value))` 上报,`play()` 返回值携带;原代码 handler 零参,100% 丢弃 `.value`。
  - 主线对话 404 时(`code < 200 or code >= 300`)显示状态提示而非空旁白框;`DialogManager.play` 自身拒绝 `null` / 空 `scenes`。
- `mainline_responses.gd` 删除死代码 `on_dialogue_response`(全项目无调用方),同时删除 18 行的 doc 引用。
- `tools/smoke_test.gd` 新增 3 条 DialogManager 断言(autoload 注册 / `play` 方法 / `is_playing` 方法),共 548 通过 / 0 失败。
- 验证:smoke_test **548 通过 / 0 失败**,对比基线 +3(新断言全过);action_latency_test 20 / 0;map_logic_movement_test、tileset_atlas_test 通过;view_position_reset_test 4 通过 / 2 失败(BoardCamera 既有问题,与本 PR 无关)。
- 已知限制(留 follow-up,本 PR 不阻塞):
  - 嵌套 `play()` 行为未定义,同一时刻只支持一个 awaiter;首批触发点无人嵌套。
  - `GameState.unit_killed` 信号触发时 victim 已从缓存移除,`GameState.get_unit(unit_id)` 大概率返回 `{}`,fallback 到 `unit_type`;精确名字需在 `_on_event_delta` 先抓快照再发信号。
  - `mainline_controller.gd:527` 那个死分支现在 CanvasLayer 隔离已修,但仍依赖后端 `chapters.py:180` schema 加 `dialogue` 字段。
  - chapter_06 整章对话 404(`game/stories/chapter_06/` 整个目录不存在),404 容错后显示状态提示,但章节本身没内容是设计层面问题。
  - 6/8 演讲者缺肖像(`红`/`太子`/`卡尔德` 等),fallback 显示 👤 emoji;需补 hero 模块。
- main.gd 净变化:本 PR 起点 3835 行(此前 PR 重构 mainline + lobby + theme + cn_labels 后),本轮再降 124 行 → 3711 行(累计从 6300 → 3711,共 -41%)。

## 2026-07-28

- 重构 `scripts/main.gd`：6300 行 → 3835 行（-39%），纯搬运，零行为改动。
- 新增 `scripts/ui/lobby_controller.gd`（2140 行）：整套联机大厅从 main.gd 抽离，挂在场景 `$Lobby` 节点上，沿用 saves / mainline / editor 已有的「子节点挂脚本 + `_main` 注入」模式。大厅的 43 个子控件引用、30 个私有状态变量、20 处信号接线全部自管；main.gd 侧只保留 `_on_lobby_pressed` 与 `_setup_lobby_commander_options` 两个转发薄壳。
- 新增 `scripts/ui/hud_theme.gd`（332 行）：`_apply_gba_theme` / `_apply_hud_theme` / `_apply_theme` 三个纯样式函数抽为 static，采用 `mainline_responses.gd` 既有的 host 派发约定；main.gd 保留同名薄壳，四处既有调用点未改动。
- 新增 `scripts/ui/cn_labels.gd`（201 行）：单位 / 技能 / 地形 / 指挥官 / 颜色 / 队伍 / 席位共 12 个中文查表函数抽为 static，main.gd 与 lobby_controller 均可直接取用，不再经 `_main` 绕行。
- 大厅控制器新增对外接口 `open()` / `show_choose()` / `enter_room_after_join()` / `reset_state()` / `selected_join_role()` / `selected_join_team()`，收敛 main.gd 原先散落的六处跨域调用。
- 编辑器保存地图后写入大厅预设的信号（`editor_view.map_saved`）改接到控制器；回主菜单时的大厅状态清理改由 `lobby_controller.reset_state()` 承接。
- 三个新模块一律用 `const X = preload(...)` 而非 `class_name`，避免 headless 跑测试时全局类缓存未建立导致的 Parse Error。
- 同步更新 `tools/smoke_test.gd`（15 处）与 `tools/view_position_reset_test.gd`（2 处）：大厅相关断言改指 `$Lobby` 控制器，断言强度不变。
- 验证：smoke_test 545 通过 / 0 失败、action_latency_test 20 通过 / 0 失败、map_logic_movement_test 与 tileset_atlas_test 通过、view_position_reset_test 4 通过 / 2 失败——全部与重构前基线逐项一致（该 2 项 BoardCamera 失败为既有问题，与本次重构无关）。

- Added a transparent, borderless selected-unit portrait slot that resolves hero portraits first and generic unit portraits from `assets/unit_portraits/`.
- Added generated generic unit portraits for all 15 registered unit types, with T2 portraits rendered more richly than T1 while keeping NPC eyes hidden.
- Fixed large-map camera refresh: state polling no longer reloads the same board every tick, so manual zoom and pan stay in place.
- Added middle-mouse panning support on the Godot board while keeping wheel zoom.
- Fixed rules-AI HQ targeting in team games: AI now excludes teammate HQs from enemy castle pull targets, so allied AI advances toward enemy HQs instead of the player's HQ.
- Added `red_full_roster_4p_20`, a 20x20 four-player free-mode map where red starts with one of every registered unit type and nearby village, barracks, and vault economy tiles.
- Expanded barracks recruitment across backend, Web, and Godot clients so every registered unit type is available from recruit UI paths.
- Fixed free-mode victory cleanup: the final kill now flushes dead units before rout evaluation, and match finish clears the player's suspend save so returning to menu cannot resume into the victory screen.

## 2026-07-27

- Changed the mainline entry to an FE8-style slot-first flow: players now choose one of the three formal save slots before the current chapter is resolved.
- Added `assets/tilesets/` as the preferred atlas-sheet home for map art.
- Wired the three new 48px-grid map sheets into `Config.TILESET_ATLAS_COORDS`.
- Updated `TileSetBuilder` so configured atlas sheets become shared runtime `TileSetAtlasSource` resources before legacy per-tile PNG fallback.
- Updated `MapLoader` to paint configured atlas coordinates directly.
- Routed transparent forest/mountain-style tiles through overlay layers so they render above biome-appropriate base ground.
- Added a focused `tileset_atlas_test` scene and smoke-test assertions for the new atlas mapping.
- Fixed Godot client movement previews so allied units are pass-through but not valid destinations; enemy units still fully block movement.
- Upgraded atlas rendering to parse sibling `.txt` label maps, grouping same-terrain variants by biome and selecting stable per-cell variants across each map.
