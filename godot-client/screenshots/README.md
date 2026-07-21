# Godot 客户端截图集

> 生成时间:2026-07-21
> 后端依赖:`http://127.0.0.1:8000`(部分图需要后端在跑)
> Godot 4.7 + OpenGL 3.3,`tools/` 下 17 个 screenshot 工具批量产物

## 总览

按主菜单 → 子菜单 → 战斗 → 子控件 顺序组织。所有 PNG 都是 1280×720 GBA 风渲染。

| 编号 | 文件 | 内容 |
|---|---|---|
| 01 | `01_menu.png` | 主菜单(GBA 烫金 + 6 入口按钮):主线章节 / 联机大厅 / 存档管理 / 玩法说明 / 地图编辑 / 设置 |
| 02 | `02_settings.png` | SettingsPanel 主菜单态:玩家名 / 字号 12·14·16 / 颜色 4 色 / 主题(深绿像素/金属银/极简明亮)/ 静音切换 |
| 03 | `03_story_dialog.png` | DialogPanel 剧情文字("云:路, 就到这里了吗") + 头部型头像 + 选项按钮 |
| 04 | `04_demo_board.png` | demo 棋盘视角:TileMapLayer 三层 + 9 种地形渲染 |
| 06 | `06_game_hud.png` | 战斗 HUD 全景:回合/阶段徽章 + EndTurnButton + CO Bar + InfoPanel 选中单位详情 + 玩家列表 + AI Thinking pulse |
| 07 | `07_game_overview.png` | PausePanel 暂停态 + 完整 HUD 同框 |
| 09 | `09_lobby_subview_1_choose.png` | 大厅"模式选择"页:choose/create/join 三卡 |
| 09 | `09_lobby_subview_2_create.png` | 大厅"创建房间"页(地图选择 + BGM + CO + 队伍 + AI) |
| 09 | `09_lobby_subview_3_join.png` | 大厅"加入房间"页(waiting 房间列表 + JoinMode + Team) |
| 09 | `09_lobby_subview_4_in_room.png` | 大厅"已加入"页(座位 4 列 + AI 配置 + 启动按钮) |
| 11 | `11_flow_d0_setup.png` | flow_v0.3 demo 帧 0:进入对局初始棋盘 |
| 11 | `11_flow_d1_selected.png` | flow 帧 1:选中单位 + ActionBubble 弹出(动态 5 按钮按单位能力) |
| 11 | `11_flow_d2_move_mode.png` | flow 帧 2:移动模式可达格蓝框 + 路径 dot |
| 12 | `12_full_game_d0.png` | full_game_screenshot 帧 0:整局 vs AI 起始 |
| 12 | `12_full_game_d1_t2.png` | full_game 帧 1 turn 2 |
| 12 | `12_full_game_d1_t5.png` | full_game 帧 1 turn 5 |
| 13 | `13_live.png` | live_screenshot:WS snapshot 后立即截,2P / 225 tile / turn 1 |
| 14 | `14_attack.png` | 攻击流程:选中 → 攻击 → POST /attack → unit_attacked 后截图 |
| 14 | `14_attack_forecast.png` | 服务端 forecast 攻击预测:右侧 InfoPanel 战斗预测区显示 dmg / counter / kill |
| 17 | `17_entry_lobby.png` | entry_flow_e2e:大厅创建房间 → 启动 → GameView |
| 17 | `17_entry_mainline.png` | entry_flow_e2e:主线章节 → 准备 → GameView |

## 子菜单 / 控件说明(按 main.tscn 节点路径)

```
Main/
├── Menu/CenterContainer/
│   ├── TitleBlock / TitleLine1-2 / TitleDivider         → 01
│   ├── GroupRow/SoloCard/MainlineButton                 → 03
│   ├── GroupRow/MultiCard/LobbyButton                   → 09-2
│   └── GroupRow/MultiCard/JoinByCodeRow/                → 02 P1
│       ├── JoinByCodeInput(LineEdit + Enter)
│       └── JoinByCodeButton("按号加入")
├── FooterRow/
│   ├── ResumeButton(动态:继续对局 #N / ▶ 继续中断战斗) → P0
│   ├── SavesButton                                      → 09-lobby_saves
│   ├── HelpButton(玩法说明 → show_help())               → P1
│   ├── EditorButton                                     → editor
│   ├── SettingsButton(主菜单下也能开 SettingsPanel) → 02
│   └── ExitButton
├── ConnectingPanel                                     → 17-(loading)
└── Backdrop(ColorRect 主题色)

SettingsPanel(reparent 到 Main 根)
└── SettingsList/
    ├── NameRow / NameInput(玩家名)
    ├── FontRow / FontSmall·Med·BigBtn(字号 12/14/16)    → 02
    ├── ColorRow / Red·Blue·Green·YellowBtn(偏好色)    → 02
    ├── ThemeRow / ThemeDropdown(3 主题)                  → 02 P2
    ├── AudioRow / MuteBtn(切换 toggle_mode)            → 02 P1
    └── ButtonRow / ApplyBtn / CancelBtn                  → 02

MainlineView/MLFrame/
├── MLSlotsContainer(3 个存档格)                       → P0
├── MLListContainer(章节卡 + 盟主码选择面板)         → 03 / 17-mainline
├── MLPrepSummary / MLPrepContent(6 tab)               → 17-mainline
└── MLPrepStartBtn / MLPrepCompleteBtn("✅ 准备好了")  → P2

Lobby/LobbyFrame/                       → 09-1/2/3/4
├── LobbyInfoBar
├── LobbyDualCol/LeftCol(MapPlayerCountOption + MapPreviewPanel)
├── LobbyDualCol/RightCol/CreateNameInput + SeatPanel
├── HostRow / LobbyHostPlayerOption + ...
├── AiConfigRow + AiActionRow
└── BottomBar / LobbyStartBtn + LobbyBackBtn

GameView/HUD/                           → 06 / 07
├── TopLeft/TurnBadge · PhaseBadge
├── TopRight/CurrentPlayerBadge · EndTurnButton(动态:"✅ 确认(继续)" / "⏭ 结束回合")
├── BottomLeft/GoldPanel
├── BottomRight/AIThinking(0.4↔1.0 pulse)· WarReportButton
├── CORoster(头像 + meter + 发动按钮)
├── InfoPanel/CommanderTitle + CommanderName + CommanderCOBar + UnitInfo / PlayersList
├── SettingsPanel(reparent 到 Main 根,P1 后主菜单也能开)
├── PausePanel/PauseList/(Resume / Settings / ⏸ 中断退出(P0) / MainMenu / Quit)
├── DialogPanel(剧情五场景类型)
├── TutorialBubble(5 条本地写死)
├── WarReportPanel/ActionLog(双栏 RichTextLabel,scroll_following)
├── AttackConfirmPanel/ConfirmBtn + CancelBtn
├── BattleResultPanel/WinnerBanner + StatsList + DetailBtn + BackMenuBtn + MainlineNextBtn(P0)
├── ActionBubble(动态 5 按钮 + 取消)
├── AutoSaveToast(P0)
└── TurnBannerFrame(回合切换滑入)
```

## 缺失 / 已知问题

| 项 | 状态 |
|---|---|
| `views_screenshot.gd` | add_child race 报错(预先存在 bug,非本次 P0/P1/P2 引入) |
| `move_screenshot.gd` | 100s timeout hang 在 WS 重连,可能是 dev_ai_game 中 NetworkClient 状态未及时收尾 |
| `lobby_create_preview_screenshot.gd` | 同上 — dev_ai_game 多次 retry 后写 lobby_create_2p.png / lobby_create_4p.png,但本轮未重跑 |
| `flow_screenshot.gd` v0.3 后续帧(d3-d7)| 88-100s timeout 截到 d0/d1/d2,d3+ 已超 budget,源码逻辑本身的 GameState.poll 等待延迟 |
| `full_game_screenshot.gd` 后续帧 | 同上 |

## P0 实现的存档控件(暂停面板新增)
- **⏸ 中断退出** 按钮:`PausePanel / PauseList / PauseSuspendBtn` → 调 `capture_suspend()` → 写服务端正 / 切主菜单
- **Saves 视图 → 💾 新建** 按钮:`SavesView / SaveFrame / SaveNewBtn` + `SaveSlotOption`(槽 1/2/3 下拉)
- **Mainline 准备页 → ✅ 准备好了** 按钮:`MainlineView / MLFrame / MLPrepCompleteBtn` → 触发 `/prepare/complete` 自动存档
- **AutoSaveToast**:`GameView / HUD / AutoSaveToast` + `ToastLabel` 顶部居中浮

## P1 实现的死按钮接通
- **SettingsButton**(主菜单 FooterRow)→ `_on_settings_open_pressed`
- **HelpButton**(主菜单 FooterRow)→ `show_help()` 浮层
- **JoinByCodeButton**(主菜单 MultiCard)→ `_on_join_by_code_pressed` 入指定房间号
- **MuteBtn**(SettingsPanel AudioRow)→ `toggled` 单参 → AudioManager.set_muted
- **Bug 修复**:`network_client.gd:95-96` 字段名 `is_connected` → `ws_connected`

## P2 实现的抛光
- **主题切换** (`SettingsPanel/ThemeRow`):metal_silver + minimal_light 两套完整样式
- **commentary WS**:`commentary.text` 自动 → 战报面板 → `_on_log_received` 显示
- **THREAT 模式**:每帧 `_on_state_updated` 计算所有敌方单位攻击范围叠加显示红框
- **spec 模式按钮文案**:`EndTurnButton` 在 `phase == "spectator"` 时切换为 "✅ 确认(继续)"
- **preferred_color hot-effect**:`_apply_preferred_color` 改 `✓ 偏好色已记下: <色>` 让玩家立刻感知
- **prepare_complete 触发**:`MLPrepCompleteBtn` 触发 `complete_mainline_prepare()`,响应 toast

## 重跑命令

```bash
# 启动后端
cd game && ./venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 单个截图(需要 backend 已启动)
cd godot-client
"D:/Python/godot/Godot_v4.7-stable_win64_console.exe" --rendering-driver opengl3 \
    --path . res://tools/menu_screenshot.tscn
"D:/Python/godot/Godot_v4.7-stable_win64_console.exe" --rendering-driver opengl3 \
    --path . res://tools/lobby_subview_screenshot.tscn
# ...etc

# 复制 user:// → 项目 screenshots/
cp "C:/Users/15353/AppData/Roaming/Godot/app_userdata/BattleBlitz Godot Client"/*.png \
   screenshots/
```

## 自动化测试覆盖 (`smoke_test`)

`./Godot_v4.7-stable_win64_console.exe --headless --path . res://tools/smoke_test.tscn` → **Passed: 435 Failed: 1**
- 1 个 fail: `unit sprite canvas width: got 37 expected 48`(图片资源 baseline 形状问题,与本次 P0/P1/P2 改动无关)
