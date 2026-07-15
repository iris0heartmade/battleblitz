# BattleBlitz Godot 客户端 — UI V2 设计文档

> 渐进式重构 Godot 客户端 UI,从 M2.5 功能骨架向「老 GBA 火纹风」整体迁移。
> 现状:第 1 轮(主菜单视觉)完成;后续轮次(HUD 4 角、信息区、行动气泡、战报面板)按迭代节奏推进。

## 风格基调

老 GBA《火焰之纹章》(FE6/7/8) + 一点高战的金属感。

| 维度 | 决策 |
|---|---|
| 主色调 | 深绿 `#1a3329` (FE 经典) |
| 边框 | 烫金 `#c9a14a`,粗 4px 外框 + 1px 内框 |
| 文字 | 暖白 `#f4e8c1` 正文;暗金 `#a89878` 副文 |
| 按钮 | 蓝底 `#2a3f5c` + 烫金边,hover 变亮蓝 `#4a6f9c`,press `#1c2d44`,disabled 半透暗蓝 |
| 强调 | 火红 `#c63a3a` |
| 字号 | 标题 56 / 副 18-20 / 按钮 18 / pill 14 / footer 12 |

## 已完成(第 1 轮)

### 主菜单 (`scenes/main.tscn`)

```
┌─ 烫金 4px 外框 ─────────────────────────────┐
│ ┌─ 烫金 1px 内框 ────────────────────────┐  │
│ │                                          │  │
│ │          ⚔  BATTLEBLITZ  ⚔              │  │
│ │           「战棋 · 轮回」                 │  │
│ │                                          │  │
│ │       ┌─ 蓝底烫金 ─────────────┐         │  │
│ │       │ 🎮 自由对局 (AI 对手)  │         │  │
│ │       └────────────────────┘         │  │
│ │       ┌─ 暗蓝 (disabled) ──────┐         │  │
│ │       │ 🛡 联机大厅 (M3 待开)  │         │  │
│ │       └────────────────────┘         │  │
│ │       ┌─ 暗蓝 (disabled) ──────┐         │  │
│ │       │ ⚙ 设置                  │         │  │
│ │       └────────────────────┘         │  │
│ │       ┌─ 蓝底烫金 ─────────────┐         │  │
│ │       │ ❌ 退出                  │         │  │
│ │       └────────────────────┘         │  │
│ │                                          │  │
│ │  v0.2.0-M2.5 · GBA FE 风 · © 2026        │  │
│ └──────────────────────────────────────┘  │
└────────────────────────────────────────┘
```

### Connecting 视图
复古"等待连接"画框,中央烫金描边 + 深绿面板 + "⚔ 战场调度中 ⚔" + "正在连接..." + 重连按钮。

## 文件结构

```
godot-client/
├── scenes/
│   └── main.tscn               # Menu / Connecting / GameView 三视图
├── scripts/
│   ├── main.gd                 # 视图状态机 + HUD 事件分发
│   └── ui/
│       └── menu_theme.gd       # ★ V2 新增:全局调色板 + StyleBox 注入器
├── tools/
│   ├── menu_screenshot.gd      # ★ V2 新增:主菜单截图工具
│   └── menu_screenshot.tscn    # ★ V2 新增
```

## V2 设计原则

1. **配色集中**:所有颜色从 `menu_theme.gd` 的常量取,不在 .tscn / .gd 里写十六进制色。
2. **StyleBox 工具函数**:每个 UI 元素(Button / Panel / Label)都用 `MenuTheme.apply_*_theme()` 灌主题,避免 theme_override_* 散落。
3. **调试隔离**:新增 screenshot 工具用 printerr 打 viewport transform / size,排版 bug 一眼能看出来。
4. **Panel vs ColorRect**:Panel 配 StyleBoxFlat 在 Godot 4.7 headless 渲染下行为不稳,边框统一用 ReferenceRect 画。

## 关键 bug 修复(顺手做的)

### Bug 1:BoardCamera 在主菜单画布偏移(第 1 轮抓到)

`scripts/board/board_camera.gd` 在主菜单状态下 `enabled = true` 默认启用,Camera2D 的 `anchor_mode = DRAG_CENTER` 把 canvas transform origin 拖到 viewport 中心,所有 Control 都被画到右下四分之一。

修复: `board.tscn` 设 `enabled = false`, `board_camera.gd` 的 `apply_metrics()` 末尾再 `enabled = true`。

### Bug 2:BoardCamera `limit_*` 把 Control 推到 viewport 中央(第 2 轮抓到)

游戏视图下,Camera2D 的 `limit_right = 720, limit_bottom = 720`(只覆盖棋盘范围)导致 **canvas_transform origin 被推到 (288, 8)**,viewport 渲染被限制到中央 720×720 子区域。**Control 节点也跟着 canvas_transform 走**,所以 HUD 4 角 pill 全被推到 viewport 中央,左 280px 是 clear color 灰,右 280px 是 Backdrop 深绿。

修复: `board_camera.gd` 的 `_refresh_from_metrics()` 把 `limit_*` 设为整个 viewport size:

```gdscript
# M3+ TODO: 把 HUD 移到独立 CanvasLayer 后,这里改回 board_rect
limit_left = 0
limit_top = 0
limit_right = int(ceil(viewport_size.x))
limit_bottom = int(ceil(viewport_size.y))
```

## 下一步迭代计划

| 轮次 | 内容 | 改动文件 | 状态 |
|---|---|---|---|
| 第 1 轮 | 主菜单 GBA 风视觉 | `main.tscn`, `menu_theme.gd`, `main.gd` | ✅ |
| 第 2 轮 | HUD 4 角极小角标(回合/阶段/金/CO) + 战报按钮 + 信息/战报浮层骨架 | `main.tscn`, `main.gd`, `board_camera.gd` | ✅ |
| 第 3 轮 | 左侧 30% 信息区(蓝底 + 选中单位详情) + BoardCamera zoom 适配 | `main.tscn`, `board_camera.gd`, `game_screenshot.gd` | ✅ |
| 第 4 轮 | 行动气泡(5 按钮:移动/攻击/技能/待命/占领) + 浮在选中单位右侧 | `main.tscn`, `main.gd` | ✅ |
| 第 5 轮 | 战报按钮唤起浮动面板(中央 520×360 + Header + ✕ Close + 8 条彩色日志) | `main.tscn`, `main.gd` | ✅ |
| 第 6 轮 | 设置面板 + 暂停菜单 + 玩家色板/字号切换 | 新 `settings_menu.gd` | ⏳ |
| 第 7 轮 | 对话框 / 教程气泡 / 战斗结算面板 | 新 `dialog.gd` | ⏳ |

## 反馈调整记录

| 日期 | 学长反馈 | 落地 |
|---|---|---|
| 2026-07-15 | 想要老 FE 风 + 棋盘为主紧凑布局 + 行动点击气泡 + 战报按钮呼出 + 左侧固定信息区 | 第 1 轮主菜单落地 |
| 2026-07-15 | disabled 按钮颜色要区分 | `apply_button_theme` 加 disabled StyleBox |

## 验证

- `tools/menu_screenshot.tscn` 渲染 → `res://menu_screenshot.png`
- Smoke check:`Godot --headless --quit` 0 错 0 警告
- M2.5 联机基线未动:`network_client.gd` / `game_state.gd` / `map_logic.gd` 保持原状