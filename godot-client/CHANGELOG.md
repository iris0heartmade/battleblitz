# BattleBlitz Godot Client Changelog

## 2026-08-09 键盘 + 手柄两个盲区修复(本轮)

上手柄接入后发现两处"有声无影"的断点,本次补上。

### 修复 1:棋盘光标永不激活 → 方向键/摇杆无法控制单位
- 根因:`_show_view("game")` 里 `call_deferred("_enter_board_focus")` 执行时棋盘还没
  加载地图(WS 快照未到,`board.map_size == 0`),`_enter_board_focus` 提前 return 且
  无人重试 → `InputState.board_focused` 永远 false → 光标不画、`board._handle_cursor_input`
  首行 return,方向键/摇杆全无效。
- 修复:`main.gd` 连接 `board.map_loaded` 信号 → `_on_board_map_loaded()`:当前是 game
  view 且尚未 board_focused 时补调 `_enter_board_focus()`。覆盖新建/重连/续档所有 load_map
  路径;已在焦点中则不动(不打断进行中的移动/攻击模式)。

### 修复 2:大厅(建房/加入/房内)控件无法用手柄操作
- 根因:`main._focus_default_for_view("lobby")` 是空 `pass`,lobby 各子视图切换
  (`_show_lobby_choose/_create_view/_join_view/_in_room`)从不 grab focus。Godot 手柄导航
  依赖某个 Control 先有焦点,否则十字键/确认键全无响应(主菜单能用正是因为抢了焦点)。
- 修复:`lobby_controller.gd` 新增 `_grab_focus_for_mode()`,按 `_lobby_mode` 抢默认焦点
  (choose→建房卡 / create→开启游戏 / join→加入 / in_room→开局),无可用按钮时兜底
  `UIPanelFocus.grab_first_focusable`。

### 后端连带:成长图表曲线下降波动(工具修复)
- `tools/growth_charts/dataset.py` 对 RolledGrowthPolicy 改为增量滚动 + 每主题固定种子
  (镜像 `app.modes.spawn_generic_stats`),曲线单调不减且两次运行 PNG 完全一致。旧实现每级
  独立重掷未播种随机数,L6 可能比 L5 低 → 图表锯齿下降。已更新 `test_growth_chart_policies.py`
  (含单调性回归)并给 full-roster 地图补上 `bard`。

### 后端连带:上一轮重构遗留的 ~23 条失败测试清理
成长/MOV-MP/组件化重构让一批旧测试失配,本次按新契约全部对齐:
- `test_modes.py` — spawn 断言从旧 autolevel 公式改为 rolled 播种契约(fix mov 静态断言)。
- `test_godot_client_contract.py` — 大厅函数已搬到 lobby_controller.gd,契约测试跟着改读
  LOBBY_GD;hero portrait 断言对齐"检视卡内嵌立绘"现行设计。
- `test_godot_ui_design_tokens.py` — battle/mainline 主题加入 Color 白名单。
- `test_commanders_integration.py` — passive 倍率断言改为反推预烘焙值(修 hero 单位 flaky)。
- `test_hero_promotion.py` / `test_mainline_hero_persistence.py` — yun 纯法师重做后 mp=4。
- `test_mainline_event_triggers.py` + `test_mainline_full_e2e.py` — **真 bug 修复**:
  `event_trigger._INSERT` 原始 SQL 漏了 NOT NULL 的 `growth_seed` / `status_effects`,
  wave 触发器 IntegrityError 崩掉 → 补齐两列。
- `test_ws_gateway.py` — Windows 上 sync TestClient + aiosqlite worker-thread leak 挂起
  (文件头已点名该限制),skip-on-win32,非 Windows CI 照常跑。

## 2026-08-09 键盘 + 手柄"返回上一级"补全(本轮 commit)

排查后发现 5 个 modal 缺键盘/手柄的"返回"快捷键,Connecting 面板缺"放弃"按钮。本次只补缺口,**不重构 view 栈**。

### 改动文件
- `scripts/main.gd`
  - `_unhandled_input` 顶部新增 modal-LIFO 分流:`ui_cancel` 触发时按优先级关最上层 modal。
  - `_try_close_topmost_modal()` 新方法:LIFO 顺序 Confirm → BattleResult → AttackConfirm → Recruit → WarReport → Tutorial → Settings → Pause → Connecting(放弃重连),命中即返回 true。
  - `_on_connecting_abort_pressed()` 新方法:ws_close + 切回 menu + 重置 _game_id/_player_id/_resume_*。
  - `@onready var connecting_abort_btn: Button` + `_ready` 里 connect 按钮事件。
  - `_focus_default_for_view("connecting")` 优先 focus 落 AbortButton(玩家进入该面板大概率想退出),fallback 到 ReconnectButton。
- `scenes/main.tscn` — `Connecting/ConnectingInner` 下新增 `AbortButton`(文字"放弃,返回主菜单")。

### 语义说明(务必读一下)

- **Esc / 手柄 A** = 全局"返回上一级 / 取消"键。
- 优先级:**最上层可见 modal 优先**(Confirm > BattleResult > AttackConfirm > Recruit > WarReport > Tutorial > Settings > Pause > Connecting)。
- 命中 modal → 关该 modal,后续逻辑(board.cancel / pause toggle)不再处理。
- 没 modal 可见时:
  - 棋盘光标模式 → `board.cancel_cursor`(取消行动模式 / 清高亮),这跟上次 commit 行为一致。
  - 非棋盘模式 → 走 `pause` action(暂停 toggle),老行为不变。

### ActionBubble 不走 ui_cancel

按 Esc 时,如果 ActionBubble 可见,ActionBubble 的 CancelBtn 不直接接 ui_cancel(避免和棋盘模式取消重复),仍由 `board._handle_cursor_input` 接管 — 它已经调 `_cursor_cancel_action` → `_cancel_action_mode + _hide_action_bubble`,等同于点 CancelBtn。

### Connecting 面板新行为

- 之前:重连失败时只能 Ctrl+W 强退。
- 现在:
  - 鼠标点 `放弃,返回主菜单` 按钮 → disconnect WS,回主菜单,清 _game_id/_player_id/_resume_*,避免下次进游戏误从中断存档续上。
  - 键盘按 Esc / 手柄 A → 走 `_try_close_topmost_modal` 命中 Abort 路径,等价于点按钮。
  - 面板打开时默认 focus 落 AbortButton(而不是 ReconnectButton),键盘玩家 Tab 一次就到了 ReconnectButton(更安全的"重试"留二选)。

### 测试

- `Godot --headless --quit-after 90 --path .` — 编译过、跑 1.5s 无 ERROR。
- `tools/button_smoke_test.tscn` — 116 pass / 0 fail(比上次 +2,新增 `connecting_abort_btn` 自动发现并 emit_signal 通过)。
- 后端 `game/tests/` 这次没动 backend,不受影响。

### 已知没动

- 顶层 view 之间没引入返回栈(menu → lobby → editor 等是单跳 back 按钮,按 Esc 在 GameView 不返回主菜单 — 得先开暂停 → 点退出战斗)。
- DialogManager(NPC 对话)的"继续"语义不是返回,没动。

## 2026-08-09 键盘 + 手柄操作模式接入

新增 Phase 1(UI 导航) + Phase 2(棋盘光标)。鼠标方案完全保留,新功能只是补充。

### 改动文件
- `project.godot` — `input` 段补全 5 个 ui_* 家族(`ui_accept` / `ui_cancel` / `ui_up/down/left/right`)和 10 个 board_* action;新增 `InputHints` autoload。
- `scripts/autoload/input_hints.gd`(新)— 平台感知的按键提示文字(KB / Xbox / PS / Switch),通过 `UserSettings` 的 `settings.v1.controller_style` 覆盖(`auto` / `keyboard` / `xbox` / `playstation` / `switch`)。
- `scripts/autoload/input_state.gd` — 加 `cursor_cell: Vector2i` + `board_focused: bool` + 两个对应 signal。
- `scripts/board/highlights.gd` — 新增 `Mode.CURSOR`(4 角带小三角 + 4px 厚白边的"虚拟光标"视觉,跟普通 hover 区分);`show_cursor_at(tile, color)` API 允许外部控制脉动 alpha。
- `scripts/board/board.gd`
  - `_process` 增加光标脉动 + 持续按方向键/摇杆 repeat timer。
  - `_handle_cursor_input` 路由 `board_cursor_*` / `board_zoom_*` / `board_confirm` / `board_cancel`。
  - `_handle_camera_input` 顶部:鼠标 hover 同步 `InputState.cursor_cell`(鼠标/手柄玩家看到一致的"当前格")。
  - `_zoom_at_viewport_center` — 手柄缩放改用屏幕中心为锚点(手柄玩家没鼠标)。
  - `_confirm_cursor` / `_cancel_cursor` — 复用现有 `emit_unit_clicked` / `emit_tile_clicked` / `_cursor_cancel_action` 路径,不绕过 main.gd 的状态机。
- `scripts/main.gd`
  - 7 个 panel(`pause_panel` / `settings_panel` / `recruit_panel` / `war_report_panel` / `attack_confirm_panel` / `confirm_dialog` / `battle_result_panel`)打开时调 `UIPanelFocus.grab_on_show` 抢焦点。
  - `_show_view` 切换时同步 `InputState.board_focused`:`game` 进 board_focus + 初始化光标(我方第一单位 > 地图中心);其它 view 退 board_focus + grab 该 view 主按钮。
  - `pause` action 在 board_focused 时让给 `board_cancel`(棋盘光标模式 Esc = 取消,不是暂停)。
  - `_update_path_dots_at_cell` + `_cursor_cancel_action` 两个薄包装给 board 调。
- `scripts/ui/_components/ui_panel_focus.gd`(新)— 纯静态工具,帮"打开 panel → grab focus 到默认按钮"。

### 玩家操作模式

**键盘(KB)**
| 场景 | 键位 |
| --- | --- |
| 菜单/面板 焦点跳转 | Tab / Shift+Tab |
| 菜单/面板 确认 | Enter / Space |
| 菜单/面板 取消 | Esc |
| 棋盘光标移动 | ↑ ↓ ← → / WASD |
| 棋盘光标确认 | Enter |
| 棋盘光标取消 | Esc / Backspace |
| 棋盘缩放 | `+` / `-`(或 `=` / `_`) |
| 暂停 | Esc(在 game view 顶层) |

**手柄(Switch 风格反转,默认)**

| 动作 | Switch | Xbox 等价 | PS 等价 |
| --- | --- | --- | --- |
| 确认 | B | A | × |
| 取消 | A | B | ○ |
| 光标移动 | 左摇杆 / D-pad | 同上 | 同上 |
| 缩放 | L / R | LB / RB | L1 / R1 |
| 暂停 | + | Start | Options |
| 结束回合 | X | Y | △ |

手柄按键文字会按 `UserSettings.controller_style` 自动调整。`auto` 模式下,只要 `Input.get_connected_joypads()` 看到手柄就显示 Switch 反转;否则显示键盘。

### 鼠标兼容性

- 完全保留。鼠标点击 / 滚轮缩放 / 左键拖拽 pan 行为不变。
- 鼠标 hover 时 `InputState.cursor_cell` 跟着鼠标走,所以鼠标/手柄玩家在棋盘上看到的"当前格"始终一致。
- 光标视觉(白色 outline + 4 角三角)只在 `InputState.board_focused = true` 时显示,纯鼠标玩家在主菜单看不到任何多余元素。

### 测试

- `Godot --headless --quit-after 120 --path .` — 编译过、跑 2 秒无 ERROR。
- `tools/button_smoke_test.tscn` — 114 pass / 0 fail,所有 button 引用 + `pressed` 信号没被新加的 autoload / panel focus 改动打乱。
- 后端 `game/tests/test_*.py` 这次没动 backend,不受影响(计划原则:这次只动 godot 前端)。

### 已知限制 / 后续增量

- 光标在棋盘边缘不自动滚屏(没用 scroll-at-edge 联动 camera)。需要玩家用 `+` / `-` 缩放,或手柄 L/R 调视野。
- 没接 CO Power / 技能快捷键(键位待定)。
- 主菜单 → 切到 game view 时,光标会从第一个我方单位起步;没找到我方单位则放地图中心。
- 多次"取消"会把光标重置回我方第一单位,避免取消后光标停在空地看起来像死锁。

## 2026-08-09 英雄美术资源登记(L4 review 补登记)

所有英雄美术资源均为 8-bit PNG,统一存放在 `godot-client/assets/heroes/`。

| Hero    | 单位立绘           | 大头贴 portrait          | 队徽 crest    | 备注 |
|---------|--------------------|--------------------------|----------------|------|
| anna    | `anna.png` 1254×1254 RGBA | `portrait_anna.png` 800×1400 RGBA | `crest_anna.png` 120×120 RGBA | 初始版 |
| anna_boss | (复用 anna)        | `portrait_anna_boss.png` 774×1355 **RGB** | (复用 anna)    | RGB 无 alpha,变体 BOSS 头像 |
| yun     | `yun.png` 717×781 RGBA    | `portrait_yun.png` 800×1400 RGBA  | `crest_yun.png` 120×120 RGBA  | |
| youko   | `youko.png` 1254×1254 RGBA | `portrait_youko.png` 800×1400 RGBA | `crest_youko.png` 120×120 RGBA | |
| yuanying | `yuanying.png` 768×768 RGBA | `portrait_yuanying.png` 948×1659 RGBA | `crest_yuanying.png` 256×256 RGBA | 鸢影;队徽比其它大一档(2× 边长) |

License / 来源:
- 当前批次均为项目内原创 / 委托绘制的占位与正式稿,版权属项目所有。
- 后续若引入外部素材(Free-license 库 / 委托 / 自制),需在每张资源同目录放
  `LICENSE.txt` / `CREDITS.md`,在 CHANGELOG 本节登记出处,license 类别
  (CC0 / CC-BY / MIT / 商业 等)。

格式约定(后续新增资源请遵守):
- 单位立绘 (`<hero>.png`):正方形 1024+ 边长,RGBA,带透明背景。
- 大头贴 (`portrait_<hero>.png`):近似 4:5(800×1400 或相近),RGBA。
- 队徽 (`crest_<hero>.png`):120×120,RGBA,适配小队栏 1× 显示。
- 不使用 JPG(WebP 在 Godot 4 已稳定,RGBA 不适用);PSD / AI 源文件不入库。

## 2026-08-02 资源收尾

- 鸢影美术资源二次收尾:
  - 同步更新 Web 与 Godot 两端的 `yuanying.png` / `portrait_yuanying.png` / `crest_yuanying.png`。
  - 已用 `game/tests/test_godot_unit_portrait_paths.py` 锁定资源路径与 Godot sprite registry，避免英雄图像资源缺失回流。

## 2026-08-02

- 鸢影正式可用化:
  - 补齐 `yuanying.png` / `crest_yuanying.png` / `portrait_yuanying.png` 在 Godot 与 Web 两端的英雄资源(Godot `.import` 旁文件由编辑器自动生成,被 `.gitignore` 排除,不入库)。
  - `unit_node.gd` hero sprite registry 加入 `yuanying`,鸢影英雄单位现在会在棋盘上使用专属立绘资源。
  - 大厅默认指挥官池 fallback 加入 `yuanying`,座位卡能力文案显示"5x5 沉默领域，术士压制"。
  - 新增集成测试锁定自由模式选择鸢影后:玩家 `commander_id=yuanying`,CO 阈值 16,HQ 生成 `hero_id=yuanying` 的 warlock,并继承 `poison_burst`。

- Agent 回归修复:
  - `_ask_llm_with_retry` 批量决策返回 list 的测试契约同步;单决策场景取首个 `ActionPlan`。
  - `Reaction` 文案重新按测试契约截断到 40 字。
  - `AgentAction.action_id` 禁止空格,防止 LLM 把合法动作 ID 改写成不可执行文本。
  - 未知 personality fallback 在 system prompt 中显式标注"均衡型人格"。

- 通用 status effect 框架(P+):
  - 后端 `game/app/status/` 新包:`effects.py` 注册表 + `engine.py` 钩子函数;`Unit.status_effects: list[dict]` JSON 字段,`UnitOut.status_effects` 公开字段;5 个 effect 注册(poison 毒 / paralyze 麻痹 / blind 致盲 / slow 减速 / silence 沉默,后者从 `silence_until_turn` 字段迁移)。
  - 钩子函数:`tick_effects_at_turn_start`(poison 扣 HP + 倒计时) / `should_skip_action`(paralyze 概率 skip) / `modify_hit_chance`(blind) / `modify_mov`(slow) / `should_block_attack`(silence) / `is_silenced` / `get_status_summary`。
  - `apply_silence_aura`(鸢影沉默领域)改用 `add_effect(unit, "silence", ...)` 写新字段,旧 `silence_until_turn` 字段保留作 fallback。
  - godot 端 `unit_node.gd` 把原单一 `silence_overlay`/`silence_label` 替换为通用 status overlay + glyph 行(`☠⚡👁❄🔇`);`core/types.gd:UNIT_KEYS` 加 `status_effects`。
  - 详细设计文档:`game/app/status/README.md`。27 个 pytest 全过(`game/tests/test_status_effects.py`),完整套件 140/140 全过。

- Status effect 实时接入(P+ 闭环):
  - `commanders.effects.on_player_turn_start` 集中钩子:每回合对玩家所有 unit 顺序执行 `should_skip_action`(paralyze → has_acted=True + paralyzed_until_turn) → `_refresh_mov_debuff`(slow 用 _base_mov 快照 + modify_mov 改 mov,过期自动恢复) → `tick_effects_at_turn_start`(poison 扣 HP / 倒计时 / 过期清理)。
  - `game_logic.attack_with_double_strike` 加 `_maybe_miss` wrap:每 hit 独立判定 `modify_hit_chance`,miss 时 `damage=0`;Double-Strike 两次 hit 各自掷骰。
  - 详细钩子调用顺序在 `commanders/effects.py:on_player_turn_start` 注释里(paralyze 在 tick 前判断,slow mov 在 tick 前生效)。
  - 13 个端到端测试覆盖:`test_status_effects_live.py`(poison/paralyze/blind/slow 各类型 + 同挂组合 + Double-Strike + blind 独立判定)。完整套件 153/153 全过。

- 沉默领域 godot 端 UI(鸢影 CO power 闭环):
  - `NetworkClient.action_co_power` 接可选 `center: Vector2i = (-1, -1)`,center 有效时附带 `body.center` 给后端。
  - `main.gd` 检测 `commander_id == "yuanying"` 时进入"选中心"模式(`_silence_pick_center_for_pid` 状态机),`_on_board_tile_clicked` 入口优先处理沉默选 center;右键 / ESC 取消。
  - `board.gd:highlight_silence_pick_mode(on)` 切换中央紫色提示气泡 + hover 时 `_refresh_silence_pick_outline` 实时绘制 5×5 紫色 outline(中心 ±2,地图边界裁剪);`main.gd:_unhandled_input` mouse_motion 转发 hover 给 board。
  - `highlights.gd` `Mode` 枚举加 `SILENCE_PICK`,紫色 `Color(0.75, 0.55, 1.0, 0.50)`。

- 鸢影 yuanying 基础注册:详见 commit `a672511` + `feat(heroes): 注册鸢影 yuanying - 沉默领域 CO, warlock 基础`。资产 `portrait_yuanying.png` 已就位,`sprite_path` / `crest_path` 仍待美术补。

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
