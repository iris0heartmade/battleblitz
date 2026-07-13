# BattleBlitz → Godot 移植方案（代码文件级分析）

> 文档版本：v1.0 · 2026-07-13
> 目标引擎：**Godot 4.7-stable**
> 移植路线：**保留 Python 后端 + Godot 只做客户端**（下称"路线 A"）
> 目标平台：**Windows 桌面 · 手机（Android/iOS）· Web（HTML5）**

---

## 0. 结论速览（TL;DR）

| 维度 | 结论 |
|------|------|
| **整体难度** | 🟢🟡 **中等偏低**。核心 3.7 万行 Python 游戏逻辑**全部原样复用**，只重写渲染 + 交互 + 网络传输。 |
| **要扔掉的** | 仅 `game/app/web/`（`app.js` 5837 行 + HTML/CSS）—— 这层用 DOM+CSS 画格子，是"地图丑"的根因。 |
| **要保留的** | 后端全部（战斗/AI/寻路/地图生成/占领/士气/指挥官/养成/战役/WebSocket）。 |
| **最大收益** | 地图从 `<div>+CSS` → **Godot TileMap**，是降维打击级别的画质提升。 |
| **最大约束** | 一旦上 Web/手机，Python 后端**必须部署成公网在线服务**（WASM/APK 内嵌不了 Python）。 |
| **预计工期** | 约 **3–4 周**（含地图重做、单机联机跑通、三平台导出适配）。 |

---

## 1. 项目现状盘点

### 1.1 技术栈与真实代码规模

| 层 | 技术栈 | 规模 | 移植角色 |
|----|--------|------|----------|
| **后端逻辑** | Python + FastAPI + SQLAlchemy(异步) + SQLite | `game_logic.py` 2378 行 + 子系统 | **游戏权威引擎**（原样复用）|
| **前端** | 原生 JS 单文件 `app.js` **5837 行** + HTML/CSS | ~10k 行 JS | ⚠️ **DOM+CSS 渲染，全部弃用重写** |
| **地图数据** | 服务端程序化生成 + JSON 预设 | 14 张预设 + 生成器 | 数据契约复用，渲染重做 |
| **联机** | WebSocket 实时事件流（协议 v1）| — | 客户端换 `WebSocketPeer` 对接 |
| `ref/` | Lua/Java/TMX **13 万行** | Advance Wars 等克隆 | 纯参考素材，**不移植** |

> ⚠️ 注意：`ref/` 目录下的 611 个 Lua/Java/TMX 文件全是外部开源参考项目，与本项目移植**无关**，切勿误当作待移植代码。

### 1.2 为什么"地图丑"—— 根因确认

前端棋盘用 **`<div class="cell t-forest">` + CSS Grid + `background-image`** 渲染（`innerHTML` 68 处、`className` 37 处、`createElement` 26 处，**完全没有 canvas/WebGL**）。DOM 画战棋图先天无法做：地形自动拼接、边缘过渡、光照、平滑动画。

👉 **Godot 的 `TileMap`/`TileSet` 正是为网格地图而生**，支持 autotiling、地形位掩码、着色器、图集变体，换引擎即彻底解决画质问题。

---

## 2. 移植架构总览

```
┌─────────────────────── 保留不动（Python 后端）───────────────────────┐
│  FastAPI (main.py)                                                    │
│   ├─ REST 路由 (game/actions/turns/editor/mainline/progression/...)   │
│   ├─ WebSocket 网关 (ws_gateway.py) —— 协议 v1                        │
│   ├─ 游戏逻辑 (game_logic.py + utils.py) —— 战斗/寻路/AI/占领/胜负     │
│   ├─ 地图生成 (map_generation/*)                                       │
│   ├─ 指挥官/养成/战役 (commanders/ progression/ mainline/)             │
│   └─ SQLite 持久化 (database.py + models.py)                          │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ HTTP (REST) + WSS (WebSocket)
                                 │ 传的都是 *Out JSON（Pydantic 契约）
┌───────────────────────────────┴───────────────────────────────────┐
│  Godot 4.7 客户端（新写）                                             │
│   ├─ NetworkClient.gd (autoload) —— HTTPRequest + WebSocketPeer      │
│   ├─ GameState.gd (autoload) —— 缓存 state.snapshot，作渲染权威源     │
│   ├─ TileMapLayer + TileSet —— 地形渲染（替代 DOM cell）              │
│   ├─ Node2D 单位层 + Sprite2D —— 单位/HP/MP/士气                      │
│   ├─ Highlights 层 —— 移动/攻击/路径高亮                              │
│   ├─ MapLogic.gd —— 镜像 BFS/A*/LoS/伤害预测（仅用于 UI 高亮预览）    │
│   ├─ Control UI —— 大厅/HUD/战斗预测/日志/对话                        │
│   └─ DialogSystem.gd + AudioManager.gd                               │
└───────────────────────────────────────────────────────────────────┘
```

**核心原则**：客户端**不重新实现任何游戏规则**。所有动作发给服务端裁决，服务端回 `state.snapshot` + `event.delta`，客户端只负责"漂亮地渲染 + 收集输入"。客户端镜像的 BFS/伤害公式**仅用于即时 UI 预览**（高亮可达格、显示预估伤害），最终以服务端为准。

---

## 3. 后端文件级分析（保留侧）

> 处置标记：【原样复用】后端不动 · 【需暴露 API/协议】契约要固化 · 【客户端需镜像】Godot 端要有等价数据结构/算法

### 3.1 核心逻辑层（`game/app/`）

| 文件 | 行数 | 职责 | 移植处置 | Godot 是否需要代码 |
|------|-----:|------|----------|--------------------|
| `game_logic.py` | 2378 | 战斗/伤害/AI/升级/占领/胜负/地图预设加载 | 【原样复用】 | 镜像少量公式（伤害/范围/BFS）用于 UI 高亮 |
| `models.py` | 354 | SQLAlchemy ORM：`Game/Player/Unit/Tile/ClaimSession/ActionLog` | 【客户端需镜像】 | 镜像所有 `*Out` 字段用于解析 JSON |
| `schemas.py` | 453 | Pydantic 请求/响应契约（前后端唯一协议层）| 【需暴露 API/协议】 | 1:1 生成 GDScript 类型（建议走 OpenAPI）|
| `main.py` | 134 | FastAPI 入口 + 路由挂载 + `/ui/` 静态托管 | 【原样复用】 | 移除 `/ui/`，其余不动 |
| `config.py` | 423 | **所有魔法数字唯一来源**（地形/移动/收入/暴击/士气/AI）| 【客户端需镜像】 | 关键常量表须复刻（见 §7）|
| `battle_config.py` | 143 | 战斗 BGM 配置合并 | 【原样复用 + API 暴露】 | 解析 `battle_config` + 调 `/audio/tracks` |
| `database.py` | 288 | aiosqlite 异步引擎 + 幂等迁移 | 【原样复用】 | 不需要 |
| `game_locks.py` | 40 | 单局写锁（进程内并发原语）| 【原样复用】 | 不需要 |
| `utils.py` | 245 | 纯算法：`bfs_reachable/pathfind/has_line_of_sight/manhattan` | 【客户端需镜像】 | 必须有等价实现（UI 高亮）|

**核心数据契约（`*Out`，客户端必须字段级镜像）**：
- `UnitOut`：`id/player_id/unit_type/name/level/exp/hp/max_hp/atk/def_/matk/mdef/mov/mp/morale/x/y/has_acted/has_moved/skills[]/attack_range/min_attack_range/hero_id`
- `TileOut`：`x/y/terrain/subtype/owner_id/occupied_unit_id`
- `PlayerOut`：`id/user_name/color/is_alive/has_ended_turn/seat/is_ai/agent_kind/agent_personality/gold/team/is_spectator/units[]`
- `GameSummaryOut`：`status/turn_number/current_player_index/map_preset/map_biome/phase/win_condition/win_reason/capacity/battle_config`
- `PendingClaimOut`：`tile_id/tile_x/tile_y/started_turn/completes_turn/turns_remaining/total_turns/target_player_id`（占领进度条）
- `PlayerCOStateOut`：`player_id/seat/color/commander_id/meter/threshold/is_power_active/can_fire`（CO 能量条 HUD）
- `ActionLogOut`：`turn_number/player_id/action_type/description/created_at`（战报）

> ⚠️ **陷阱**：`Unit.def_` 字段带下划线（因为 `def` 是 Python 关键字），JSON 里就是 `"def_"`，Godot 端**不要**改名成 `def`。

### 3.2 路由层（`game/app/routes/`）

| 文件 | 行数 | 职责 | 移植处置 |
|------|-----:|------|----------|
| `ws_gateway.py` | 289 | **生产 WebSocket 网关**（协议 v1，鉴权/快照/重连）| 【需对接·核心】 |
| `debug_ws.py` | 90 | 调试 WS（无鉴权，仅 dev）| 仅协议参考 |
| `actions.py` | 890 | REST 玩家动作 `/move /attack /skill /wait /claim /recruit` | 【需对接】 |
| `turns.py` | 754 | `/end-turn` + 后台调度（超时跳过/AI 链/收入结算）| 【原样复用·服务端】 |
| `game.py` | 1460 | 游戏生命周期：创建/加入/开始/状态/预设 | 【需对接】 |
| `editor.py` | 275 | 自定义地图 CRUD（`game/maps/custom/*.json`）| 【原样复用·服务端】 |
| `commanders.py` | 154 | 指挥官解锁 / CO Power 触发 | 【需对接】 |
| `heroes.py` | 97 | 英雄元数据 + 立绘 URL | 【需对接·启动拉一次】 |
| `mainline.py` | 956 | 剧情战役编排 | 【需对接】 |
| `profile.py` | 287 | 玩家档案（user_name 主键）| 【需对接】 |
| `audio.py` | 79 | BGM 目录 | 【需对接】 |

### 3.3 其余子系统

| 目录 | 关键文件 | 职责 | 移植处置 |
|------|----------|------|----------|
| `map_generation/` | `generator.py`(398) `castle_layout.py`(307) `river_network.py`(286) `road_network.py`(336) `symmetry.py`(280) `terrain_clusters.py`(409) | 程序化地图生成 | 【原样复用·服务端】。Godot 只读输出的 `tiles`。`castle_layout` 的 `subtype` 客户端渲染需理解 |
| `agent/` | `agent.py`(692) `legal_actions.py`(250) `llm_client.py`(312) `openai_client.py`(256) `snapshot.py`(219) `reactions.py`(457) 等 | AI 对手（rules + LLM）| 【原样复用·服务端】。`legal_actions` 规则可参考用于客户端 hint |
| `commanders/` | `effects.py`(147) `meter.py`(40) `state.py`(34) `registry.py`(26) 等 | 指挥官被动/CO Power/能量 | 【原样复用·服务端】。客户端只读 `co_states` |
| `progression/` | `service.py`(470) `models.py`(253) `leveling.py`(194) `api.py`(214) 等 | 养成/赛季/解锁 | 【原样复用·服务端】+ Godot 走 `/progression/*` |
| `mainline/` | `engine.py`(511) `schemas.py`(501) `loader.py`(167) `spawn_overrides.py`(107) | 剧情战役状态机 | 【原样复用·服务端】+ Godot 走 `/mainlines/*` |
| `events/` | `types.py`(123) `bus.py`(103) | 进程内事件总线 | 【原样复用·服务端】。`EventType` 17 种客户端要认 |
| `protocol/` | `v1.py`(168) | **WebSocket 协议契约** | 【需对接·核心】详见 §5 |
| `migrations/` | `versions/*.py` | DB 迁移（实际走手写 runner）| 【原样复用·服务端】|

---

## 4. 前端文件级分析（弃用重写侧）

### 4.1 `app.js`（5837 行）模块拆解与 Godot 替代

| 段落 | 行号 | 职责 | Godot 替代方案 |
|------|------|------|----------------|
| 常量 / 单位数据 | 1–122 | 常量、`COMMANDER_OPTIONS` | `Config.gd` 单例（建议从 API 拉）|
| `AudioManager` | 126–250 | BGM 淡入淡出 | `AudioStreamPlayer` + `Tween`（`linear_to_db`）|
| `api()` | 253–291 | fetch 封装 | `HTTPRequest`（封进 `NetworkClient.gd`）|
| `showView/toast/showModal` | 293–383 | 视图切换/通知/模态 | `Control` 显隐 + `AcceptDialog`/自定义 `Window` |
| 大厅/存档/设置视图 | 386–1134 | 玩家卡/队伍 chip/AI 行 | `Control` + `VBoxContainer` 场景 |
| WebSocket 客户端 | 1241–1405 | 重连/增量事件/状态合并 | `WebSocketPeer` + `SignalBus`（自定义信号）|
| `refreshGame/renderGame` | 1429–1504 | 状态刷新 + CO 能量条 | `GameState.gd` 收 snapshot 后发信号 |
| **`renderBoard`** | 1506–2085 | grid + cell + unit DOM + FLIP 动画 | **`TileMapLayer`**（地形）+ `Node2D`（单位）+ `Tween`（移动）|
| 战斗预测/寻路/视线 | 2087–2380 | 客户端 BFS/A*/LoS/伤害预测 | `MapLogic.gd`（可用 `AStarGrid2D`）|
| 操作气泡菜单 | 2381–2668 | 移动/攻击/治疗/占领/招募浮层 | `PopupPanel.popup_at()` |
| 寻路预览 hover | 2811–2911 | 悬浮画路径点 | `Highlights` 层 + `Sprite2D` 路径点 |
| `onCellClick` | 2913–3008 | 模式分发 | `InputState.gd` 状态机 + tile 点击信号 |
| 战斗动作 | 3059–3343 | 调 API + 浮动伤害字 | `NetworkClient` 调用 + `AnimationPlayer` |
| 日志/玩家列表/金币条 | 3345–3545 | 战报 + HUD | `RichTextLabel` + `Control` |
| 参考面板 | 3547–3674 | 地形/单位/技能文案 | `Control` 面板 |
| `Dialog` 对话系统 | 3676–4151 | 打字机剧情/选择/立绘 | `DialogSystem.gd` + `RichTextLabel`(BBCode) |
| `MainlineView` | 4153–4886 | 主线章节编排 | `MainlineView.gd`（只编排不重写逻辑）|
| 地图编辑器 | 5228–5835 | 绘制/撤销重做/保存 | `TileMap` 编辑模式 + 存 JSON（同 schema）|
| 拖拽分隔 + 全局绑定 | 4888–5224 | 布局 + 事件 | `SplitContainer` + 信号连接 |

**估算**：`renderBoard` + `Dialog` + `MainlineView` 三大块（约 2000 行 JS）转 GDScript 约 600–800 行（含状态机与 UI）。

### 4.2 视图与样式（`index.html` 630 行 / `style.css`）

- **三栏布局**：`.left-column`(日志+聊天) / `.game-main`(phase-banner + board) / `.right-column`(单位信息+玩家列表) → Godot 用 `HSplitContainer` + `VBoxContainer` 复刻。
- **CSS className 即枚举来源**：`.cell.t-<terrain>`（地形）、`.unit.u-<color>`（阵营）、`.floating-text.{damage,crit,heal,kill,levelup,gold,miss}`（飘字）、`.phase-banner.phase-{player,ai,waiting,animating,spectator}`（阶段）→ 全部映射为 Godot 枚举/Theme。
- **颜色变量**（`style.css:18-46`）：`--t-plain #cfe5b6 / --t-forest #4f8a47 / --t-mountain #8c8c8c / --t-river #5fb0e8 / --t-castle #f0c75e / --p-red #e85a6a / --p-blue #5fa8e8 / --p-green #7ec97e / --p-yellow #f0c75e` → Godot `Theme` 资源 + `Color` 常量（纯色 fallback）。

### 4.3 客户端状态（localStorage → Godot）

| JS 状态 | Godot 替代 |
|---------|-----------|
| `localStorage["battleblitz.settings.v1"]`（玩家名/颜色/主题/音量）| `ConfigFile`（`UserSettings.gd`）|
| `localStorage["battleblitz.session.v1"]`（会话/重连）| `UserCache.gd`，启动尝试重连 |
| `localStorage["battleblitz_split_left"]`（分隔位置）| `ConfigFile` |
| `state.game`（GameStateOut）| `GameState.gd`（autoload，渲染权威源）|
| `state.selectedUnit/actionMode/path/...`（交互瞬态）| `InputState.gd`（autoload）|

---

## 5. WebSocket 协议契约（Godot 对接命门）

> 来源：`app/protocol/v1.py` + `ws_gateway.py`。**协议版本 `PROTOCOL_VERSION = 1`。**

### 5.1 连接与信封

```
连接：ws(s)://<host>/ws/games/{game_id}?since_seq={N}&player_id={pid}
鉴权：X-Player-Id 头，或 ?player_id= 查询参数（浏览器 WS 无法设 header，用查询参数）

消息信封（通用）：
{
  "v": 1,                 // 协议版本
  "type": "<消息类型>",
  "seq": <int|null>,      // 服务器填充，per-game 单调递增
  "sent_at_ms": <int>,    // 服务器填充
  "payload": { ... }
}
```

### 5.2 Server → Client 消息

| type | 说明 | payload 关键字段 |
|------|------|------------------|
| `server.hello` | 连接首条 | `server_version, protocol_version, current_seq, heartbeat_sec(30), supports_replay, authed_player_id` |
| `state.snapshot` | **完整状态（渲染权威源）** | `game: GameStateOut`（见 §5.4）|
| `event.delta` | 单条实时事件 | `GameEvent`（见 §5.3）|
| `turn.advance` | 换玩家/换回合 | `turn, next_player_id, next_player_name, is_new_round` |
| `server.pong` | 心跳（每 30s）| `echo_at_ms` |
| `commentary.text/audio` | AI 解说（暂未推送）| `text[, audio_b64]` |
| `error` | 错误（关闭前发）| `code, message, field?, trace_id?` |

### 5.3 `event.delta` 的 `GameEvent`（17 种事件）

```
type ∈ { move, attack, kill, skill, wait,
         turn_end, round_end, match_start, match_end,
         castle_captured, level_up, low_hp_warning,
         comeback, victory_imminent, ai_step, auto_skip, error }

字段：game_id, turn, timestamp_ms,
     actor_player_id?, actor_unit_id?, actor_name?,
     target_player_id?, target_unit_id?, target_name?,
     context: {自由字段, 如 dmg/is_crit/from_x/to_y/...},
     importance ∈ { critical, important, normal }

CRITICAL = {kill, castle_captured, comeback, victory_imminent, match_end}
IMPORTANT = {level_up, round_end, match_start, low_hp_warning, auto_skip}
```

Godot 按 `type` 分发动画，按 `importance` 决定特效强度（critical → 屏幕震动/大飘字）。

### 5.4 `state.snapshot.payload.game`（GameStateOut）

```
game:            GameSummaryOut（见 §3.1）
tiles:           [TileOut]           x,y,terrain,subtype,owner_id,occupied_unit_id
players:         [PlayerOut]         含 units:[UnitOut]
current_player_id: int|null          == self.id 时才能操作
logs:            [ActionLogOut]      最近 50 条
pending_claims:  [PendingClaimOut]   占领进度 HUD
co_states:       [PlayerCOStateOut]  指挥官能量 HUD
```

### 5.5 重连与错误码

```
重连：GET .../ws/games/{id}?since_seq={最后收到的 seq}&player_id={pid}
     → server.hello(current_seq) → state.snapshot(全量) → event.delta×K(seq>N，环形缓冲最多200条) → 实时流

ErrorCode: OUT_OF_MP, OUT_OF_RANGE, NOT_YOUR_TURN, INVALID_TARGET,
           GAME_FINISHED, GAME_NOT_FOUND, INTERNAL, AUTH_REQUIRED,
           RATE_LIMITED, PROTOCOL_MISMATCH
```

> ⚠️ **重要**：网关**当前不消费** `client.action.*` 消息（`protocol/v1.py` 已定义类型但未接线）。**玩家动作目前仍走 REST**。若想纯 WS 走动作，需在 `ws_gateway.py` 加 dispatcher 把 `client.action.*` 转发到对应 REST handler。**移植初期建议：动作走 REST，状态/事件走 WS**（改动最小）。

### 5.6 REST 端点清单（Godot 需实现的调用）

| 分类 | 端点 |
|------|------|
| 生命周期 | `POST /games` · `POST /games/{id}/join` · `POST /games/{id}/rejoin[_by_name]` · `POST /games/{id}/start` · `GET /games/{id}/state` · `DELETE /games/{id}` |
| 大厅 | `GET /games/{id}/lobby` · `PATCH /games/{id}/players/{pid}/team` · `POST /games/{id}/add-ai` · `DELETE /games/{id}/players/{pid}` |
| 玩家动作 | `POST /games/{id}/{move,attack,skill,wait,claim,recruit,end-turn,co-power}` |
| 元数据 | `GET /games/presets` · `GET /games/units` · `GET /games/skills` · `GET /heroes` · `GET /audio/tracks` |
| 战役 | `GET /mainlines[/{id}]` · `GET /mainlines/dialogue?path=` · `POST /mainlines/{id}/{start,advance,next-battle,abandon,select-commander}` |
| 养成 | `POST /progression/profiles` · `GET /profile/{user_name}` · `GET/POST /progression/profiles/{id}/units` · `POST /units/{id}/{xp,promote}` |
| 编辑器 | `GET/POST /editor/maps` · `GET/DELETE /editor/maps/{id}` |

---

## 6. 地图系统重做（核心目标）

### 6.1 地图 JSON schema（复用）

```jsonc
{
  "id": "snake_case_id",
  "name": "中文显示名",
  "description": "短描述",
  "biome": "grass" | "desert" | "snow" | "castle",  // 影响 tile 配色
  "size": 15 | { "width": 20, "height": 15 },        // 15–45
  "layout": ["PPPFF...", "..."],   // 每行一字符串，长=width，行数=height
  "initial_units": [
    { "x": 3, "y": 4, "type": "swordsman", "color": "red", "level": 1 }
  ],
  "recommended_players": 2 | 3 | 4,
  "team_mode": "2v2" | "ffa",
  "notes": "设计备注"
}
```
合法地形字符：`P F M R C v b r g`（+ 城堡内联子字符 `f w t d s` 与 `$`）。

### 6.2 完整地形清单（Godot TileSet 要建 17 类）

| 字符 | terrain | 移动代价(×2) | 防御 | 阻视线 | 通行 | 备注 |
|:---:|---------|:---:|:---:|:---:|:---:|------|
| `P` | plain | 2 | 0 | 否 | ✓ | 基础 |
| `F` | forest | 4 | +2 | 是 | ✓ | biome 敏感贴图 |
| `M` | mountain | 6 | +3 | 是 | ✓ | snow biome 禁用 |
| `S` | snow_peak | 6 | +3 | 是 | ✓ | snow 专属 |
| `R` | river | 6 | 0 | 是 | ✓ | 4 种变体 |
| `C` | castle | 2 | +5 | 否 | ✓ | 带 subtype |
| `v` | village | 2 | 0 | 否 | ✓ | +50g/回合 |
| `b` | barracks | 2 | +1 | 否 | ✓ | +100g/回合 + 招募 |
| `r` | road | 1 | 0 | 否 | ✓ | MP 减半 |
| `g` | gate | 9999 | 0 | — | ✗ | 敌方阻拦 |
| `j` | bridge | 1 | 0 | 否 | ✓ | 道路过河（P2.8+）|

**城堡子地形（`Tile.subtype`）**：

| subtype | 移动 | 防御 | 通行 | 备注 |
|---------|:---:|:---:|:---:|------|
| castle_floor | 2 | +3 | ✓ | |
| castle_wall | 9999 | +99 | ✗ | 墙 |
| castle_throne | 2 | +6 | ✓ | 王座 |
| castle_stairs | 2 | +3 | ✓ | |
| castle_vault | 2 | +5 | ✓ | +150g/回合 |
| castle_door | 2 | +4 | ✓ | 门 |

**生物群系（biome）**：`grass`(默认) / `snow`(雪顶) / `desert`(沙漠绿洲) —— 影响 `forest_*/castle_*` 贴图变体。

### 6.3 Godot 渲染架构

```
Board (Node2D)
 ├─ TerrainLayer (TileMapLayer)     ← 11 地形，按 (terrain,biome) 选 atlas source
 ├─ CastleLayer  (TileMapLayer)     ← 城堡 subtype 叠加（避免与地形代价语义混淆）
 ├─ Highlights   (Node2D)           ← 移动/攻击/路径/威胁高亮（Sprite2D overlay）
 ├─ Units        (Node2D)           ← 每单位一个 Node2D：Sprite2D+HPBar+MPBadge+MoraleStars
 └─ Effects      (Node2D)           ← 飘字/特效（AnimationPlayer）
```

- **地形贴图**：现有 70 个 48×48 pixel-art PNG（`assets/tiles/`）导入为 `TileSetAtlasSource`；`mountain/gate/castle_wall` 加碰撞形状。
- **biome 变体**：每地形在 TileSet 建 3 个 source（grass/desert/snow），`set_cell` 时按 `map_biome` 选。
- **tile 变体随机**：复刻 `pickTileVariant`——用 `rand_from_seed(hash(x,y,terrain))` 保证视觉稳定但有变化。
- **画质升级空间**：autotiling 位掩码做地形边缘过渡、`CanvasModulate` 做昼夜/生物群系氛围、shader 做河流流动。

---

## 7. 客户端需硬编码/镜像的关键常量（`config.py` 复刻）

```gdscript
# —— 移动代价（×2 整数编码！实际 MP = cost / 2；road/bridge=1 即半 MP）——
const TERRAIN_MOVE_COST := {
    "plain":2, "forest":4, "mountain":6, "snow_peak":6, "river":6,
    "castle":2, "village":2, "barracks":2, "road":1, "gate":9999, "bridge":1,
}
const TERRAIN_DEF_BONUS := {
    "plain":0, "forest":2, "mountain":3, "snow_peak":3, "river":0,
    "castle":5, "village":0, "barracks":1, "road":0, "gate":0, "bridge":0,
    "castle_floor":3, "castle_wall":99, "castle_throne":6,
    "castle_stairs":3, "castle_vault":5, "castle_door":4,
}
# —— 经济 ——
const RECRUIT_COST := {"swordsman":200,"archer":250,"knight":400,"warlock":300,"healer":350}
const BUILDING_INCOME := {"village":50, "barracks":100, "castle_vault":150}
# —— 士气 ——
const MORALE_MAX := 3
const MORALE_ATK_PER_STAR := 0.10
const MORALE_DEF_PER_STAR := 0.05
# —— 战斗（仅前端预览）——
const BASE_CRIT_RATE := 0.05
const CRIT_PER_LEVEL := 0.01
const CRIT_MULTIPLIER := 1.5
const COUNTER_DAMAGE_MULT := 0.5
# —— 占领/规模 ——
const CLAIM_TURNS_REQUIRED := 2
const MAP_SIZE_DEFAULT := 15
const MAX_PLAYERS := 4
const MIN_PLAYERS := 2
const DEFAULT_PLAYER_COLORS := ["red","blue","green","yellow"]
const WIN_CONDITIONS := ["rout","seize","reach","defend"]
```

> 💡 **推荐做法**：新增一个 `GET /games/config` 端点，把这些常量从服务端 `config.py` 直接推给 Godot，避免"双改脱钩"。硬编码是次选方案。

### 7.1 数据一致性陷阱（务必遵守）

1. **移动代价用 ×2 整数编码**：`road=1` 表示半 MP，预算是 `mov*2`。客户端 BFS 若改浮点会与后端判定脱钩，导致高亮抖动。
2. **`terrain="castle"` + `subtype` 二维**：渲染城堡必须同时看 subtype，不能只看 terrain。
3. **`Unit.def_` 带下划线**：JSON 字段名是 `"def_"`，别改。
4. **`unit.mp` 是剩余 MP**：回合开始 `mp = mov`；显示 MP 时按需除 2。
5. **观战者座位**：位于 `[MAX_PLAYERS .. MAX_PLAYERS+max_spectators-1]`，不参与胜负判定。
6. **`since_seq` 是 per-game 序号**（非 per-connection），重连从最后收到的 seq rewind，环形缓冲 200 条。

---

## 8. 三平台导出与后端部署

### 8.1 后端部署（路线 A 的硬约束）

| 平台 | 后端连法 | 关键动作 |
|------|----------|----------|
| **Windows 桌面** | 可打包本地 Python 一起启动，或连远程 | 🟢 localhost 即可，最简单 |
| **Web (HTML5)** | ⚠️ WASM 跑不了 Python，**必须连远程 + WSS** | 🟡 租服务器 + 域名 + HTTPS/WSS 证书 |
| **手机 (Android/iOS)** | 同样连远程服务器 | 🟡 同上；iOS 上架需苹果开发者账号 |

**部署清单**：
1. 后端上公网（VPS/云主机/容器），用 `uvicorn` + 反向代理（Nginx/Caddy）终止 TLS。
2. 提供 `https://` + `wss://`（Web/手机强制加密）。
3. SQLite 单写者模型足够单实例用；若并发高需评估换 PostgreSQL（`database.py` 已用异步 ORM，切换成本低）。
4. `main.py` 的 `/ui/` 静态托管可删（Godot 不再需要）；保留 `/healthz`。

### 8.2 Godot 导出适配

| 平台 | 导出模板 | 注意事项 |
|------|----------|----------|
| Windows | Windows Desktop | 直接 .exe |
| Web | Web (WebAssembly) | 需 WSS（HTTPS 页面不能连 ws://）；注意 `WebSocketPeer` 在 Web 用查询参数传 `player_id` |
| Android | Android (需 SDK/JDK) | 触屏重映射：点击=选择，长按=气泡菜单，捏合=缩放 |
| iOS | iOS (需 macOS + Xcode) | 苹果开发者账号；触屏同上 |

**触屏适配要点**（桌面鼠标 → 触屏）：
- hover 路径预览 → 改为"首次点击选中即显示可达范围 + 路径"，第二次点击确认。
- 右键/悬浮气泡 → 长按或选中后浮层。
- 棋盘缩放/平移 → `Camera2D` + 手势（捏合缩放、拖拽平移）。

---

## 9. 里程碑与工期

| 阶段 | 内容 | 产出 | 预计 |
|:---:|------|------|:---:|
| **M0 骨架** | Godot 项目搭建、autoload 单例（NetworkClient/GameState/Config）、导入 tile/hero 资产 | 可运行空壳 | 2–3 天 |
| **M1 地图原型** ⭐ | TileMapLayer 加载一张现有 JSON 地图，biome 变体，highlights 层 | **立刻验证"变好看了"** | 3–4 天 |
| **M2 联机跑通** | WS 客户端 + REST 动作，跑通完整一局（桌面）：移动/攻击/占领/回合 | 桌面可玩 | 1 周 |
| **M3 完整功能** | 大厅/HUD/战斗预测/日志/CO 能量/招募/对话/主线 | 功能对齐旧前端 | 1 周 |
| **M4 触屏 + 手机导出** | 输入重映射 + Camera 手势 + Android/iOS 导出 | 手机可玩 | 3–4 天 |
| **M5 后端部署 + Web 导出** | 后端上公网 + WSS + Web 导出联调 | Web 可玩 | 3–4 天 |

⭐ **建议从 M1 地图原型开刀**：最小成本验证画质提升，风险最低、反馈最快。

---

## 10. 风险登记

| 风险 | 等级 | 缓解 |
|------|:---:|------|
| 客户端 BFS/伤害预测与后端脱钩 | 🟡 中 | 严格复刻 ×2 整数编码；预测仅作 UI，最终以服务端裁决为准 |
| Web 端 WSS/CORS/混合内容 | 🟡 中 | 后端统一 HTTPS+WSS；Godot Web 导出走查询参数鉴权 |
| 后端部署运维（域名/证书/存活）| 🟡 中 | 用 Caddy 自动证书；加 `/healthz` 监控 |
| 触屏交互重设计 | 🟢 低 | M4 集中处理，选中式两段确认 |
| iOS 上架门槛 | 🟢 低 | 需开发者账号，非技术阻塞 |
| 协议演进（`client.action.*` 未接线）| 🟢 低 | 初期动作走 REST，后续可选迁 WS |
| 美术资产不足（仅 2 英雄、1 首 BGM）| 🟢 低 | 不阻塞移植；后续补充 |

---

## 11. 附录：Godot 节点对照速查

| 旧（JS/DOM/CSS） | Godot 4.7 |
|------------------|-----------|
| `<div class="cell t-forest">` | `TileMapLayer` + `TileSetAtlasSource` |
| `<div class="unit u-red">` | `Node2D` + `Sprite2D`（HP/MP/士气子节点）|
| `--cell-size` + `fitBoard()` | `Camera2D.zoom` + viewport `size_changed` |
| `.cell.move-hint` 高亮 | `Sprite2D` overlay / `modulate` |
| `.cell.path-dot` | `Highlights` 层路径点精灵 |
| `#action-bubble` | `PopupPanel.popup_at()` |
| `@keyframes banner-slide/float-up` | `AnimationPlayer` / `Tween` |
| `<audio>` + AudioManager | `AudioStreamPlayer` + `Tween`（`linear_to_db`）|
| `fetch()` / WebSocket | `HTTPRequest` / `WebSocketPeer`（autoload）|
| `localStorage` | `ConfigFile`（autoload）|
| `state.game` | `GameState.gd`（autoload）|
| `renderBoard()` 全量重写 | 增量 `set_cell` / `Tween` 单位插值 |
| `computeReachable` BFS | `AStarGrid2D` / `MapLogic.gd` |
| `Dialog.show(scene)` 打字机 | `DialogSystem.gd` + `RichTextLabel`(BBCode) |
| 地图编辑器 | `TileMap` 编辑 + 存 JSON（同 schema）|

---

*本文档由代码文件级分析生成，覆盖后端 30+ 文件、前端 3 大文件、地图数据与美术资产。移植时以本文件为契约索引。*
