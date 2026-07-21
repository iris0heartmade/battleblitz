# BattleBlitz Godot 4.7 客户端 · 功能调查报告

> **报告日期**:2026-07-21
> **范围**:`D:/Python/BattleBlitz/battleblitz/godot-client/`(纯客户端,后端不动)
> **数据源**:5 组 agent 在 2026-07-21 对 scripts/ + scenes/ + tools/ + assets/ 的实测;以 `main.gd`(7372 行)+ `network_client.gd` + `game_state.gd` + `smoke_test.gd`(73 KB)为锚点。
> **配套表格**:`架构/Godot客户端功能调查报告.xlsx`(同目录,10 sheet)

---

## 0. TL;DR

BattleBlitz Godot 客户端已实现**主路径闭环 + 主线 + 战斗 + 编辑器 + 存档**的全部前端功能,**服务端权威**架构贯穿全栈(`MEMORY.md` 的 `server-authority-no-duplicate-logic` 规则);**唯 4 个 P0/P1 缺口**集中在 save_manual 按钮未接、Help 面板无触发、静音无连接、JoinByCodeButton 死按钮;**tools/ 26 个脚本**提供约 72-78% 的可玩流程自动化覆盖。

---

## 1. 项目总览

### 1.1 工程数据

| 维度 | 数值 | 锚点 |
|---|---|---|
| 主场景 | `scenes/main.tscn` | 2048 行,所有 view 都是其子 Control |
| 主控脚本 | `scripts/main.gd` | 7372 行,**几乎所有视图逻辑都内联在这一个类里** |
| Autoload 单例 | 6 个 | Config / UserSettings / GameState / InputState / NetworkClient / AudioManager |
| 自有 .tscn | 2 个 | `main.tscn`(2048) + `board.tscn`(899 B,被 GameView/EditorView 各实例化 1 次) |
| Tools 脚本 | 26 个 | 1 smoke + 5 e2e + 17 截图 + 2 辅助 + 2 启动 |
| 资产 (PNG) | 70 tiles + 6 classic units + 5 hero portraits/crests + 2 BGM | 由 `sync_assets.py` 与 web 同步 |
| 网络通讯 | REST(单连接串行队列)+ WS(25s 心跳 + 0.5-30s 指数退避重连 + since_seq 回放) | `network_client.gd:106-180` |
| Bug 标记 | 1 处 `gs.set("is_connected")` 字段名错(应 `ws_connected`);`InputState` 信号未连线(M2 占位) | `network_client.gd:95-96` |
| 自动化覆盖率 | 约 **72-78%** 可玩流程(加权综合) | smoke_test 269 断言 + e2e_one_game + chapter_06_* 等 |

### 1.2 架构图(autoload 间 wiring + 数据流)

```
_config_version=5
Autoload 顺序(project.godot:19-26):
  1 Config          — 纯常量镜像(无 _ready)
  2 UserSettings    — user://battleblitz.cfg
  3 GameState       — wait_for_NetworkClient_to_wire
  4 InputState      — M2 占位(零订阅)
  5 NetworkClient   — _ready: HTTPRequest 单连接 + 双 Timer + _wire_to_game_state()
                          ↓
                          把 WS typed signals 接到 GameState
  6 AudioManager    — 确保 Music bus
```

### 1.3 关键架构哲学

1. **服务端权威** — 所有玩家动作 POST REST,客户端不重算 damage / 战斗规则;`MapLogic`(客户端镜像)只用于 UI 预览,**不基于此拒绝动作**
2. **API 唯一封装** — 所有 HTTP / WS 调用必经 `NetworkClient`,callback 强制 `(body, code)` 双参(`MEMORY.md` 的 `callback-signature-match.md` 锁死)
3. **WS + REST 混合** — 主要更新靠 WS(`server.hello` + `state.snapshot` + `event.delta`),REST `GET /state` 是 200ms debounce 兜底;服务端 WS 网关不消费 `client.action.*`,所有动作走 REST(MEMORY 的 `server-ws-events-gap.md`)
4. **autoload 顺序陷阱** — GameState._ready 留空、把 wiring 让 NetworkClient._ready 做(`MEMORY.md` 的 `autoload-order-ws-wiring.md`)
5. **参数化弱类型** — `MapLogic` / `MapTheme` / `TileSetBuilder` 都是 class_name 但不强制 scene 装配,EditorBoard 与 GameBoard 共用同一脚本

---

## 2. Autoload 六件套

### 2.1 Config(纯常量镜像) — `autoload/config.gd`

镜像 `game/app/config.py` 的所有常量和枚举,`config.gd:4-10` 注释:"Every magic number here MUST match its Python counterpart"。**未来计划**:动态 `GET /games/config`,但 M1 内联。

| 类型 | 示例 | 说明 |
|---|---|---|
| 棋盘尺寸 | `MAP_SIZE_DEFAULT=15`、`TILE_PIXEL_SIZE=48` | UI 与后端对齐 |
| 兵种常量 | `MORALE_MAX=3`、`BASE_CRIT_RATE=0.05`、`CRIT_MULTIPLIER=1.5`、`COUNTER_DAMAGE_MULT=0.5` | 与 `config.py` 1:1 |
| 地形 / 单位 / 兵营 | `TERRAIN_MOVE_COST`、`TERRAIN_DEF_BONUS`、`RECRUIT_COST` 表 | 5 兵种 × recruit_cost{swordsman:200, archer:250, knight:400, warlock:300, healer:350} |
| 网络 | `DEFAULT_API_BASE="http://127.0.0.1:8000"` / `DEFAULT_WS_BASE="ws://127.0.0.1:8000"` / `PROTOCOL_VERSION=1` | 客户端 only |
| Atlas | `FE8_TILE_COORDS / FE8_ATLAS_PATH / USE_FE8_ATLAS=false` | FE8 主图预留,走 legacy |
| Helpers | `is_passable / pick_tile_variant / tile_asset_basename / player_color / has_castle_subtype` | 全局可用 |

### 2.2 UserSettings — `autoload/user_settings.gd`

| 字段 | 默认 | 用途 |
|---|---|---|
| `settings.v1.player_name` | `""` | 玩家显示名 |
| `settings.v1.player_color` | `"red"` | 默认主色 |
| `settings.v1.theme` | `"dark"` | UI 主题 |
| `settings.v1.font_size` | 14 | 字号 |
| `settings.v1.color` | (运行时写入) | 偏好色(新房间生效) |
| `settings.v1.muted` | false | 静音 toggle |
| `settings.v1.tutorial_seen` | false | 教学完成 |
| `settings.v1.volume` | 0.7 | 音量 |
| `server.api_base` / `server.ws_base` | 见 Config | 可被 Settings 改写 |
| `session.v1.last_game_id` / `last_player_id` | 0 / 0 | Resume 用 |
| `session.v1.mainline_id / mainline_game_id / mainline_player_id` | 各类型默认 | 主线续局用 |
| `ui.split_left` | 0.32 | 左栏宽度 |

写入时机:`NOTIFICATION_WM_CLOSE_REQUEST` 或 `NOTIFICATION_PREDELETE` 写盘。Getter API:`get_value / set_value / get_api_base / get_ws_base`。

### 2.3 GameState — `autoload/game_state.gd`

**27 个 typed signals**(7 snapshot-level + 18 event-delta + 2 connection):

```
snapshot-level:
  snapshot_received(snapshot) / state_updated(snapshot) / tile_state_changed(x,y,new)
  units_changed(units[]) / unit_acted(id, has_acted, has_moved)
  current_player_changed(pid) / phase_changed(phase)
connection:
  connection_state_changed(connected)
event-delta(18 个):
  log_received(action) / unit_moved / unit_attacked / unit_killed / unit_leveled_up
  unit_waited / unit_used_skill / unit_claimed / unit_recruited / turn_ended
  round_started / match_started / match_ended / castle_captured / ai_thinking
  low_hp_warning / comeback / victory_imminent
```

字段: `latest_snapshot` + 9 个核心字段(tiles / players / current_player_id / co_states / logs / phase / local_player_id / is_local_turn setter / ws_connected setter)。**所有 setter 写时自动 emit 对应 signal**。

### 2.4 InputState — `autoload/input_state.gd`(M2 占位)

| 模式枚举 | 语义 |
|---|---|
| `IDLE` | 无选择;hover 仅显示信息 |
| `UNIT_SELECTED` | 友军单位已选;hover 显示 reach + path |
| `MOVE_MODE` | 用户选目的地 |
| `ATTACK_MODE` | 用户选攻击目标 |
| `CLAIM_MODE` | 用户指向可占领 tile |
| `RECRUIT_MODE` | 用户指向空 barracks |
| `SKILL_MODE` | 用户选技能目标 |

3 个 signals(`mode_changed / selected_unit_changed / hover_tile_changed`)。**⚠️ 当前 main.gd / board.gd 零 `InputState.X.connect` 调用**,定义完成但未连。

### 2.5 NetworkClient — `autoload/network_client.gd` ⭐ 核心

#### 2.5.1 HTTP 串行队列
- 1 颗 `HTTPRequest` 节点 + 内部队列 `_req_queue` 串联
- 失败 `RESULT_SUCCESS` 之外 → emit `api_error` + callback fallback
- 4xx/5xx 也走 `api_error` 但**仍 callback**(传 `parsed` + `code`)
- 无 409 retry — 业务侧自行判定

#### 2.5.2 所有 typed methods 行号速查

完整列表见 xlsx Sheet 3。共 7 类约 50 个方法:

| 类别 | 方法 | HTTP 路径 |
|---|---|---|
| **战斗动作** | action_move / action_attack / action_skill / action_wait / action_claim / action_recruit / action_end_turn / action_co_power | 8 个 POST |
| **预测** | forecast_attack(只读) | GET /games/{id}/forecast-attack |
| **大厅** | list_presets / list_editor_maps / load_editor_map / save_editor_map / delete_editor_map / list_games / delete_game / create_game / get_game_state / join_game / start_game / add_ai_player / remove_player / update_player_team / update_player_seat / get_lobby / rejoin_game_by_player_id / rejoin_game_by_name | 17 个 |
| **主线** | list_mainlines / list_heroes / get_mainline_detail / fetch_mainline_dialogue / get_unlocked_commanders / select_mainline_commander / get_mainline_prepare / promote_mainline_hero / equip_mainline_hero / get_post_battle_shop / purchase_post_battle_shop_item / complete_mainline_prepare / get_mercenary_config / allocate_mercenary_points / start_mainline / advance_mainline / next_battle_mainline / abandon_mainline | 17 个 |
| **存档** | list_saves / save_manual / load_save / load_suspend / erase_save / capture_suspend | 6 个 |
| **音频** | list_audio_tracks | GET /audio/tracks |
| **WS** | ws_send / ws_connect / connect_to_game / ws_close + heartbeat + reconnect | 4 个 |

**callback 签名铁律**:`(body, code)` 2-参

#### 2.5.3 WebSocket

- 鉴权:`?player_id=` query 或 `X-Player-Id` 头
- 心跳 `_ws_send_ping()`:每 25s 发 `{"type":"client.ping","sent_at_ms":...}`
- 重连 `_schedule_reconnect()`:指数退避 `0.5 → 30s` 封顶,带 since_seq 回放
- `_last_received_seq` 状态:`_dispatch_ws_message` 收到 `seq > 0` 更新,重连拼回 query
- 消息分发:
  - `server.hello` → `server_hello_received(seq, payload)`
  - `state.snapshot` → `state_snapshot_received(payload.game)` ← GameState 全替换缓存
  - `event.delta` → `event_delta_received(payload)` ← 派发 18 个子信号
  - `server.pong` → `server_pong_received(echo_at_ms)`
  - `commentary.text/audio` → **no-op**(预留,UI 未接)
  - `protocol_error` → emit + log

#### 2.5.4 已知 bug

`network_client.gd:95-96` lambda `gs.set("is_connected", true)` 字段名错(GameState 上是 `ws_connected`)。信号仍发,只是写入不生效。

### 2.6 AudioManager — `autoload/audio_manager.gd`

- BGM 数据来自 `GET /audio/tracks`(route audio.py)
- 缓存 `_track_cache: track_id → AudioStream`,路径扫描 `res://audio/<id>.{ogg,mp3,wav}`
- `apply_battle_bgm(bgm)` 委托 `crossfade_to(stream, fade_in_ms=600, target_volume)` — 取消旧 tween + 新流-80 dB 起 + 同时跑 2 tween
- 静音 / 音量 — `Music` bus,`db = 20*log(max(v,0.0001))/log(10)`,0 → -80 dB
- 触发点:只有 main.gd 调 3 次(行 511 / 1253 / 1799);**进大厅 / 进主线 / 进结算 三个触发场景尚未显式调**

---

## 3. 棋盘与渲染管线

### 3.1 `scenes/board.tscn` 8 层节点树

| 节点 | 类型 | z | 职责 |
|---|---|---|---|
| Board | Node2D | root | 协调 layers / camera |
| GroundLayer | TileMapLayer | 0 | 地形基础(plains/forest/river/mountain/...) |
| StructureLayer | TileMapLayer | 1 | castle/village/barracks/gate + 5 castle_subtype |
| DecorLayer | TileMapLayer | 2 | 装饰层(预留) |
| HighlightLayer | Node2D | 3 | 7 mode × sprite pool |
| UnitLayer | Node2D | 4 | UnitNode 实例(增量 diff) |
| EffectsLayer | Node2D | 5 | 浮动伤害/治疗文字(Tween 上浮 60px / 0.8s fade) |
| BoardCamera | Camera2D | viewport | fit / 拖 / 缩 |

3 层 TileMapLayer 共享同 TileSet(`TileSetBuilder.build()`,`board.gd:36`)。

### 3.2 MapMetrics(像素公式 / 任意尺寸)

- `TILE_SIZE = Vector2i(48, 48)`、`HALF_TILE = (24, 24)`
- `board_size_for(size) = size * TILE_SIZE` → 任意 15-45 + 非方形(w/h 独立)
- `cell_origin(tile) = tile * TILE_SIZE`、`cell_to_local(tile) = cell_origin + HALF_TILE`
- BoardCamera `_FIT_MARGIN=16`、`_UI_LEFT_FRACTION=0.00`、`_UI_RIGHT_FRACTION=0.45`
- `fit_zoom = min(zoom_x, zoom_y)`,viewport 中央 55% 区放棋盘
- 一旦 user 拖动 → `_user_positioned = true`,viewport resize 时不再 fit(冻结手动调节)

### 3.3 MapTheme + TileSetBuilder

- `LayerKind { GROUND, STRUCTURE, DECOR }`,4 种 overlay 地形(castle/village/barracks/gate)
- `TileSetBuilder.build()`:
  - **当前** `USE_FE8_ATLAS=false` → legacy per-terrain(每 terrain 一张 48×48n strip)
  - **预留** FE8:master atlas 512×512,放大 3× 到 1536×1536,32×32 = 1024 tile cell + 4 corner × 4 dir 的 `terrain_peering_bits` autotile 预留
- fallback 表:`bridge → road/river`、`snow_peak → mountain`、`castle → castle_floor`、`gate → castle_door/road`
- biome-aware:forest/castle/castle_subtype 8 种,3 biome(grass/snow/desert)→ 24 atlas 源

### 3.4 MapLoader(`core/map_loader.gd`)

字符 → 后端名字 → tile 资源:
- 单字符 → `Config.TERRAIN_CHAR_TO_NAME[char_a]`
- 双字符(castle_)→ next char 走 `_CASTLE_SUBTYPE_CHARS` 字典(f/F/w/W/t/T/d/D/s/S/V/v → 6 subtype)
- `MapTheme.layer_for_cell()` 决定进 Ground / Structure / Decor
- `tile_owners` **不写**(纯地图 JSON 不含;server snapshot 单独叠加)

### 3.5 MapLogic(纯客户端 UI 镜像,不拒动作)

`map_logic.gd:1-15` 注释:server 仍权威,client 不基于此拒绝动作。
- `in_bounds` / `manhattan` / `neighbors`(4 邻,无对角)
- `terrain_passable(terrain, owner_id, viewer)` — castle_wall/gate 永远 false;castle 仅 owner==-1 或 ==viewer
- `compute_reachable(start, ..., mov)` — BFS,budget = mov×2(L111),自维护 `dist` 防覆盖
- `pathfind(start, goal, ..., budget)` — 线性 scan 自实现 priority queue(L182-185,grid ≤ 45²=2025);**P2.5 fix 收尾**:`node == goal` 才接受,防穿墙
- `has_line_of_sight(a, b, blocked, size)` — 不允许对角 step;**castle 不挡 LoS**
- `attack_range_tiles(...)` — Manhattan 距离过滤 min≤d≤max

### 3.6 Board 增量 diff + FLIP 动画

`board.gd:_on_units_changed(units_data)` (L54-L90):
- `seen_ids` 集合,做增/改/删三态
- 已有 ID → 重 setup + 起点 prev_pos,FLIP Tween 0.32s `TRANS_CUBIC EASE_OUT`
- 新 ID → `_add_unit_node` 瞬时出现
- 消失 → `queue_free`

### 3.7 UnitNode 多组件渲染(`board/unit_node.gd`)

| 组件 | 行号 | 视觉 | 来源 |
|---|---|---|---|
| `_marker`(阵营底块) | L135 | 40×40,28% α | `team_color` |
| `_sprite` | L142 | 48×48 | `res://assets/classic/{unit_type}.png` + `TextureLoader.load_resized` 兜底 |
| `_type_label` | L157 | 22px 兜底字母 | `_FALLBACK_GLYPH` |
| `_hp_bar_bg` | L174 | 42×5 灰底 | unit.hp/max_hp |
| `_hp_bar` | L180 | 40×3,>0.5 绿 / >0.25 黄 / ≤0.25 红 | 三档颜色 |
| `_mp_badge` | L188 | 12×12 圆点 | `max_mp > 0` |
| `_mp_badge_label` | L195 | 百分比,100% 显 ★ | unit.mp/max_mp |
| `_hero_crest` | L210 | 18×18 | `hero_id != ""` |
| `_hero_badge` | L218 | 14×14 金方+H,crest 缺失时 fallback | — |
| `_star_label` | L236 | 12px 多个 ⭐(0 空) | `morale` 1-5 |
| `_acted_overlay` | L246 | 40×40 半透黑 | `has_acted=true` |

### 3.8 Highlights(7 mode × sprite pool)

| Mode | 颜色 | 用法 |
|---|---|---|
| MOVE | `#60c7fa66` 半透蓝 | 移动可达 |
| ATTACK | `#f2666b66` 红 | 攻击 / 治疗候选 |
| PATH | `#60c7fad9` | 路径 dot 8×8 |
| THREAT | `#fba64c80` 橙 | 预留(未用) |
| SELECTED | `#fad855d9` 金 | 选中格(预留) |
| HOVER | `#ffffff99` | hover(预留) |

**实际 main.gd 只用 MOVE / ATTACK / PATH**;THREAT / SELECTED / HOVER 预留未触发。

---

## 4. 战斗交互(玩家 → 后端完整链路)

### 4.1 7 动作 × 三阶段触发

| 动作 | 玩家动作 | main.gd 入口 | 状态字段 | 网络 |
|---|---|---|---|---|
| 移动 | 点己方 → 移动按钮 → 点可达格 | `_move_unit_to` (line ~2242) | `_move_mode_unit_id`, `_move_reachable_set` | `POST /games/{id}/move` |
| 攻击 | 点己方 → 攻击 → 点敌 | `_attack_unit_to` (7069-7083) | `_attack_mode_unit_id`, `_attack_targets` | 先 `GET /forecast-attack` 预览,确认后 `POST /attack` |
| 技能(heal / arcane) | 点有主动技单位 → 技能按钮 → 点目标 | `_use_skill_on_target` | `_skill_mode_unit_id`, `_skill_targets` | `POST /games/{id}/skill` |
| 占领 | 点有可占领 tile 单位 → 占领 | `_on_claim_pressed` 6759+ | `pending_claim` 状态 | `POST /games/{id}/claim` |
| 招募(barracks) | 点空 barracks → RecruitPanel | `_recruit_unit_to` (7194+) | `_recruit_pending_tile` | `POST /games/{id}/recruit` |
| 待命 | 点 wait | `_on_wait_pressed` | `has_acted=true` | `POST /games/{id}/wait` |
| 结束回合 | HUD end_turn | `_on_end_turn_pressed` (2017-2019) | 推进 current_player_index | `POST /games/{id}/end-turn` |
| CO Power | CO meter "发动" 按钮 | `_on_co_power_pressed` (~1747) | CO meter → 全友军 atk/def 加成 N 回合 | `POST /games/{id}/co-power` |

### 4.2 行动气泡(动态按钮)

3 个 mode context:

```
_ACTION_CONTEXT_INITIAL  = "initial"     — 第一次点选,未动
_ACTION_CONTEXT_POST_MOVE = "post_move"  — 移动后,还能再移
_ACTION_CONTEXT_POST_ACTION = "post_action" — 攻击 / 技能后,只能 wait + (可选) 继续移动
```

| 按钮 | 显示规则 |
|---|---|
| 移动 | initial:not has_moved + mp>0 + reachable>1 / post_move:mp>0 / post_action:mp>0 + `_unit_can_move_after_action`(archer/knight) |
| 攻击 | targets.size()>0 + not has_acted,post_action 不亮 |
| 技能 | `_available_active_skill(ud) != ""`(heal→有伤友军;arcane_strike→1-2 格内敌),post_action 不亮 |
| 占领 | 脚下 tile 是 village/barracks/castle_vault/castle 且 owner≠me 且 not has_acted,post_action 不亮 |
| 待命 | 始终显示 |
| 取消 | 始终显示 |

**(重要)**:气泡只做 UI 筛选,**后端仍按真实状态校验**(`MEMORY.md` 的 `server-authority-no-duplicate-logic`)。

### 4.3 战斗 HUD 节点

| 节点 | 数据 | 写入函数 |
|---|---|---|
| TurnBadge | "回合 N" | `_on_turn_ended` |
| PhaseBadge | "玩家阶段" / "电脑阶段" | `_show_turn_banner` |
| CurrentPlayerBadge | "→ 红方" 等(`_color_emoji`) | `_rewrite_players_list` |
| EndTurnButton | "结束回合" | `_on_end_pressed` |
| GoldPanel | "💰 N" | `_rewrite_players_list` |
| CORoster | 头像 + 名字 + ProgressBar + 发动按钮 | `_refresh_co_roster` |
| AIThinking | "电脑思考中..." pulse 0.4↔1.0 | `_on_ai_thinking` |
| WarReportButton | 切 war_report_panel | `_on_war_report_pressed` |
| InfoPanel | CommanderTitle / UnitInfo / PlayersList | `_refresh_commander_section / _refresh_unit_info` |
| WarReportPanel | ActionLog 单栏 scroll_following | `_on_log_received` |

**服务端预测注入位置**:`_build_attack_forecast_info_text` 写 `unit_info.text`,title 临时改为 "战斗预测",直到下次选中单位。

### 4.4 TurnBanner + AI Thinking pulse

- TurnBanner:kill 旧 tween + 起始 -60 offset y + α0,`set_parallel(true)` 跑 position y0 (0.45s) + α1 (0.45s) → `set_parallel(false).tween_interval(3.0)` → fade out 0.6s
- AIThinking:thinking=true → `_ai_pulse_tween.set_loops()` + 0.8s `TRANS_SINE` 0.4↔1.0 永久循环

### 4.5 EditorBoard 复用

`scenes/main.tscn:276`:
```
[node name="EditorView" type="Control" parent="."]
[node name="EditorBoard" parent="EditorView" instance=ExtResource("2_board")]
```

`board.tscn` 实例化 **2 次**:GameView/Board + EditorView/EditorBoard,共用 `Board` class_name。**EditorBoard 没有"编辑模式"标志**,只是 connect 不同的信号:
- `tile_clicked` → `_on_editor_tile_clicked` 分发到 paint surface / paint tile / place unit / erase unit

`map_size` 不同也不重置 — 每次 `load_map(map_json)` 触发 `apply_metrics` 重新 fit。

---

## 5. 大厅 + 创房 + 加入 + 观战

### 5.1 视图状态机(4 模式)

```
choose (default)
  ├─ create_card → _show_lobby_create_view
  ├─ join_card   → _show_lobby_join_view
  └─ back        → menu
in_room (进入后)
  ├─ 房主控件:加 AI / 移 AI / 改队伍 / 改座位 / 启动
  ├─ 玩家控件:切队伍 / 转观战
  └─ back        → choose (非 menu)
```

### 5.2 创房流水线(7 步)

```
on_create_room_pressed
  1. collect name/preset/biome/win_cond/commander/bgm
  2. POST /games{battle_config{commander, ai_commanders, seat_commanders, audio.bgm}}
  3. POST /games/{id}/join(host 自动占 host_seat)
  4. _start_lobby_polling(2s)
  5. _continue_lobby_create_pipeline:
       每条 add_ai → update_player_seat(分配座位) → update_player_team
  6. POST /games/{id}/start
  7. _show_view("game") + connect_to_game + get_game_state
```

### 5.3 加入流程

```
list_games → 过滤 status==waiting
join_game(role / team / seat)
进入 in_room,启 2s 轮询
```

### 5.4 观战转换

```
_on_lobby_to_spec_pressed:
  remove_player(self) → join_game(role="spectator") → refresh_lobby_view
```

### 5.5 大厅自动轮询(`_refresh_lobby_view` 5142-5145)

`get_game_state(game_id, _on_lobby_state)` — 2s 一次,`_on_lobby_state` 推断房主 + 同步 `_lobby_seat_occupants / ai_personalities / seat_index / is_host / is_spectator` + 渲染 seat columns + player rows。

### 5.6 房主控件

`_render_lobby_host_controls(players)`(5316-5357)只在房主模式显示 host 控件,`_lobby_host_player_sig` 比较避免 dropdown 重建时打断用户操作。

`_next_team_name()` 自动生成 `team1/team2/...` 不冲突。

### 5.7 4 大座位列(`_build_lobby_seat_card` 4728-4845)

每张 seat 卡片包含 9 项子控件:VBox portrait + FactionPortrait + SeatStatusBox + SeatOccupant + SeatControlRow + SeatActionBtn + TeamSideOption + AiReplaceToggle + AiStyleRow + CommanderRow + CommanderAbilityLabel。

---

## 6. 主线章节流

### 6.1 章节列表(主菜单页)

`_on_mainline_pressed` (行 5573-5604):
- 切 mainline view + `chapter_list` 页
- 清缓存(`_mainline_prepare_payload / shop_payload / mercenary_payload`)
- 拉 unlocked_commanders + list_mainlines + list_saves

3 个存档格 + 章节卡片列表:`BattlePreview / battle_count / synopsis`。

### 6.2 战前整备(6 tab 切换)

| tab | 行 | 数据流 |
|---|---|---|
| Heroes | 6154 | `_build_prepare_heroes_text` |
| Roster | 6208 | `_build_prepare_roster_text` |
| Equipment | 6228 | `_build_prepare_equipment_text` |
| Mercenary | 6294 | `_get_mercenary_config` + `_allocate_first_mercenary_point` |
| Shop | 6272 | `_get_post_battle_shop` + `_purchase_first_shop_item` |
| Saves | 6261 | 列出已有存档(只读) |

### 6.3 主线对话(DialogPanel)

5 场景类型:
- `dialogue` / `narration` / `choice` / `battle_ref` / `wait`
- typewriter tween 0.03s/char + 双重 tween
- `_hero_speaker_map` → `res://assets/heroes/<file>` portrait
- 时机:`pre_battle`(开始时) / `post_battle`(advance) / `victory`

### 6.4 主线推进链

```
match_ended → advance_mainline (winner == self)
  → advance response:
      state == "victory" → 清 active + 显示奖励 + MainlineNextBtn.visible=false
      next 场 → MainlineNextBtn.visible=true → player click → next_battle_mainline
```

### 6.5 409 重试鲁棒性

`_on_mainline_start_response` 检测 409 `mainline_already_active`:
- `_mainline_auto_retry_pending=true`
- `abandon_mainline` → `_on_mainline_auto_abandon_response`
- 重试 `start_mainline(retry=true)`

---

## 7. 存档

### 7.1 5 个槽位列表

`_on_saves_response`(1015-1052)渲染 2 组:
- `save_open_list` 开房存档
- `save_mainline_list` 主线 + suspend
- `save_select_option` 下拉

### 7.2 加载流程

- `kind=="suspend"` 走 `load_suspend(user_name)`
- 否则 `load_save(kind, slot_index)`,`_on_save_load_response` 写 `_active_mainline_id`,切 mainline view
- 重连 `rejoin_game_by_name` → `_on_ml_slot_resume_response`

### 7.3 ❌ P0 缺口 — 手动存档

> **`save_manual` 写盘 UI 完全缺失**
> - `NetworkClient.save_manual` 包好(行 672-682)
> - 但 main.tscn 没有任何 save_new_btn / 保存当前对局按钮
> - prepare 页 Saves tab **只读**(列出已有,无法新建)
> - **没有任何触发点**调 `NetworkClient.save_manual(...)`

### 7.4 删除

- `erase_save(kind, slot_index)` 支持 manual/auto/suspend
- suspend 不可手动删(UI 提示)

---

## 8. 暂停 / 教学 / 设置 / 帮助 / 静音

### 8.1 暂停(Esc → PauseOverlay)

`_toggle_pause` (行 2373-2387):`PROCESS_MODE_WHEN_PAUSED` + `get_tree().paused=true` + 关 action_bubble / war_report_panel。

### 8.2 教学气泡(本地硬编码)

`_trigger_first_tutorial` (行 904-909) — `_tutorial_shown=true` 后不再触发。5 条 BBCode:单位点击 / 蓝框可移动 / 红框攻击 / 行动完点结束 / 占领。`tutorial_seen=true` 持久化。

### 8.3 SettingsPanel(字号 3 档 / 颜色 4 色 / 主题 3 选 / 静音 / 玩家名)

| 项 | 真实生效? | 行 |
|---|---|---|
| 字号 12/14/16 | ✅ 改 `theme.default_font_size` + re-apply HUD | 2430-2475 |
| 颜色 4 色 | ⚠️ **只写 pref,新房间才生效** | 2442-2481 |
| 主题 3 选(deep_gba / metal_silver / minimal_light) | ⚠️ **只换 backdrop 色**,其他 StyleBox 仍 GBA 烫金 | 1814-1824 |
| 静音 toggle | ❌ **死按钮**,`_on_toggle_mute_pressed` 无 connect | 1797-1801 |
| 玩家名 Apply | ✅ | 2419-2426 |

### 8.4 Help 面板(死)

- `_help_panel: Panel = null` 动态 create
- `show_help()`(1831-1888) — 首次动态生成 Panel + Label title + RichTextLabel body + close
- `hide_help()`(1890-1892)
- ❌ **main.tscn 无任何触发按钮**

### 8.5 P1 死按钮清单

| 节点 | main.tscn 行 | 现状 |
|---|---|---|
| `JoinByCodeButton` | 143-146 | `disabled=true`,无 handler |
| 主菜单 `SettingsButton` | 173-175 | `disabled=true`,handler 只 `set status label`,无真面板入口 |
| 静音 toggle | (无节点) | 函数实现完整,无 connect |

---

## 9. 地图编辑器

### 9.1 容器布局(`scenes/main.tscn:271-449`)

20 个 EditorPanel 控件:EditorMapNameInput / EditorTerrainOption / EditorSurfaceOption / EditorSurfaceOwnerOption / EditorApplyBiomeBtn / EditorModeOption / EditorUnitOption / EditorUnitToolOption / EditorUnitColorOption / EditorUnitLevelOption / EditorWidthOption / EditorHeightOption / EditorUndoBtn / EditorRedoBtn / EditorNewBtn / EditorSaveBtn / EditorLoadBtn / EditorDeleteBtn / EditorBiomeOption / EditorBackBtn。

### 9.2 三部署模式

| 模式 | 字符 | UI 中文 | 后端 TERRAIN_CHAR_TO_NAME |
|---|---|---|---|
| Terrain | P/F/M/R/r/S | 平原/森林/山地/河流/道路/雪峰 | plain / forest / mountain / river / road / snow_peak |
| Surface | C/v/b/g | 城堡/村庄/兵营/城门 | castle / village / barracks / gate (+ 5 castle_subtype) |
| Unit | swordsman/archer/knight/healer/warlock + 4 色 + 等级 1-10 | 剑士/弓手/骑士/治疗师/术士 | — |

**后端契约对齐**:`_VALID_TERRAINS = "PFMSRCvbrg"`(9 个),client split 为 terrain(6) + surface(4),**完整覆盖无遗漏**。

### 9.3 撤销 / 重做(50 步栈)

数据结构:`_editor_undo_stack[]` / `_editor_redo_stack[]`,每次 `_snapshot_editor_map()` 深拷贝。

进入历史栈的 7 个动作(均调 `_push_editor_history`):
1. 地形绘制 `_paint_editor_tile` (3536)
2. 地表绘制 `_paint_editor_surface` (3581)
3. 单位放置 `_place_editor_unit` (3649)
4. 单位擦除 `_erase_editor_unit` (3619)
5. 新建地图 `_on_editor_new_pressed` (3660)
6. 调整尺寸 `_on_editor_resize_pressed` (3713)
7. 套用生态 `_on_editor_apply_biome_pressed` (3675)

清栈:加载/保存 / push 操作末尾自动 `_editor_redo_stack.clear()`。

快捷键:`Ctrl+Z` undo / `Ctrl+Y` redo(仅 editor_view visible 时生效)。

### 9.4 CustomMapIn schema

| 字段 | 类型 | 校验 |
|---|---|---|
| `id` | Optional[str] | None=新建 |
| `name` | str | 1-64 |
| `size` | MapSize{width, height} | 15-45 |
| `biome` | str | ∈ {grass, snow, desert} |
| `layout` | List[str] | 每行 width 字符 |
| `initial_units[]` | {x, y, type, color, level} | type/color/level 范围 |
| `tile_owners[]` | {x, y, color} | color ∈ 4 色 |

---

## 10. GBA 主题 / UI 系统

### 10.1 `ui/menu_theme.gd` 调色板 / 字号 / 间距常量

**16 个色**(`C_BG_DEEP #1a3329` / `C_BG_PANEL #0f1f18` / `C_GOLD #c9a14a` / `C_GOLD_BRIGHT #e8c878` / `C_TEXT_WARM #f4e8c1` / `C_TEXT_DIM #a89878` / `C_BTN_BLUE #2a3f5c` / `C_BTN_BLUE_HOVER #4a6f9c` / `C_BTN_BLUE_PRESS #1c2d44` / `C_FIRE_RED #c63a3a` / `C_HEAL_GREEN #7ec97e` / `C_BORDER_THIN #5a4426` / `C_DIVIDER #5a4426` / `C_DISABLED #5a5640`)等。

**9 个字号**:`FS_HERO=56` / `FS_TITLE=32` / `FS_SECTION=22` / `FS_BODY=16` / `FS_SUB=18` / `FS_BTN=17` / `FS_HINT=13` / `FS_FOOT=12` / `FS_PILL=14`。

**12 个间距**:`PAD_X=24` / `PAD_Y=18` / `PAD=16` / `GAP_SM=6` / `GAP=12` / `GAP_LG=18` / `ROW_H=36` / `BTN_W=280` / `BTN_H=40` / `FRAME_W=4` / `TITLE_BAR_H=44` / `FOOTER_BAR_H=48`。

### 10.2 4 套 StyleBox 函数

| 函数 | 用途 |
|---|---|
| `apply_button_theme` | 蓝底烫金 2px 边(默认) |
| `apply_primary_button_theme` | 烫金底(关键操作) |
| `apply_secondary_button_theme` | 灰底细边(返回/取消) |
| `apply_panel_theme` | 深绿 + 烫金外框 |

`_apply_gba_theme()`(main.gd:2863)统一灌色到 22+ 按钮 + 5 pill + InfoPanel + 战报 + 设置面板等。

### 10.3 主题切换(简化版)

`_apply_theme(theme_name)` 只换 `backdrop.color`,不切换 StyleBox / 字号 / 字体 → "金属银" / "极简明亮" 名不副实(M5.5 TODO 写完整 `.tres` 主题)。

Dropdown label "深绿像素" vs tscn 占位符 "像素战棋风" 两处不一致。

---

## 11. 资产同步 & 汉化扫描

### 11.1 `tools/sync_assets.py`(77 行,无依赖)

- 扫描 `game/app/web/assets/tiles/*.png` (70 张) → 同步到 `godot-client/assets/tiles/`
- 不做 BIOME 检测,只按文件名复制
- `--check` 模式 CI 用,byte-diff + exit 1
- 当前 70 PNG 完整对齐,无 drift

`.import` 运行时生成,`.gitignore` 已排除。

### 11.2 `tools/check_chinese_ui.py`(117 行)

- 扫 `scenes/ + scripts/` 下 `.gd` + `.tscn`
- 命中行:UI 文案 `text=/placeholder_text=/tooltip_text=` / `add_item(/set_item_text(/append_text(/` / `_update_status(` / `_show_error(`
- 白名单空(`ALLOW_WORDS: set[str] = set()`)
- 跳过 URL / 颜色 hex / 路径 / 字典 key
- exit 0/1 进 CI

### 11.3 资产目录结构

```
godot-client/assets/
├── classic/           # 6 张单位立绘(5 类 + heavy_armor)
├── heroes/            # 5 张 hero portrait/crest(anna / anna_boss / yun)
├── tiles/             # 70 张地形 PNG + 70 .import
├── tiles_fe8/         # 1 张 FE8 master atlas 预留
└── audio/
    ├── 1.mp3          # 占位 / fallback
    └── sample_battle_01.mp3
```

---

## 12. 工具链(`tools/` 26 个脚本)

完整命令清单见 xlsx **Sheet 9**,按职能分 5 类:

### 12.1 冒烟测试

`smoke_test` 73KB / 269 处 `_assert_*` 调用,跑法:
```bash
"<godot_exe>" --headless --path godot-client res://tools/smoke_test.tscn
```
覆盖 7-19 加的 Editor 撤销/重做/三部署模式 / ActionBubble(初始 + post-move 重命名 + attack-ready)/ Battle Result / Mainline / Saves view 节点 / Seat panel 4P A/B/C/D / AI personality 3 / tile_events / forced_heroes 等。

### 12.2 真打后端 E2E

| 工具 | 大小 | 用途 |
|---|---|---|
| `e2e_one_game` | 13KB | 完整一局 vs AI:5 步 entry flow + match_ended |
| `entry_flow_e2e` | 3.6KB | GUI 入口:mainline chapter start + lobby create-room start |
| `chapter_06_ai_takeover` | 18KB | **不调真 NetworkClient**,模拟 AI 走完 3 场战斗 |
| `chapter_06_verify_events` | 29KB | 验证 chapter_06 JSON 25 个可魔改字段 |
| `chapter_06_trigger_test` | 13KB | 5 张 snapshot 截图(battle_01/wave1/wave2/boss/章节卡) |
| `ws_e2e.py` | 11KB | **Python** websocket-client,5 阶段测试(server.hello + state.snapshot) |

### 12.3 截图工具(17 个)

- 静态:`menu / settings / story / game / game_overview / lobby_subview / lobby_create_preview / large_board / views / screenshot`
- 动态:`move / attack / attack_forecast / flow(8 帧)/ full_game / live` — 走 `_start_dev_ai_game()`

每个工具保存到 `user://*.png` + 副本 `res://*.png`(部分 commit 永久保留)。

### 12.4 辅助工具

- `sync_assets.py`(前述)
- `check_chinese_ui.py`(前述)

### 12.5 启动脚本

- `play.bat` Windows 双击
- `run_debug.sh` 自动 kill + 启动 + log

### 12.6 关键环境变量

| 变量 | 用途 |
|---|---|
| `BB_AUTO_PLAY=1` | 强制 main 进入 `_start_dev_ai_game()` |
| `BB_ATTACK_FORCE_RANGE=10` | 测试时强制攻击范围,总能找到目标 |
| `BB_AUTO_QUIT=N` | 跑 N 秒后退出 |

### 12.7 自动化覆盖率评估

按模块加权综合:**约 72-78%** 可玩流程自动化。

| 模块 | 覆盖 |
|---|---|
| 启动 / Menu / Settings | ~70% |
| Lobby (4 subview) | ~75% |
| Mainline 列表 + 准备页 | ~90%(chapter_06_* 三个工具很全) |
| Game 视图 / Board 渲染 / 48px TileSet | ~90% |
| 战斗 7 动作 | ~80% |
| 攻击预测 / 结算 | ~85% |
| 编辑器 | ~85% |
| Save 管理 | ~60% |
| 音频 / BGM / SFX | ~30% |
| Help / 静音 / 全局设置 | ~10% |

**缺失覆盖**:Help / 静音 / JoinByCode / SettingsButton / ResumeButton 反例 / 视图切换动画 / PausePanel 键位 / 战报多行滚动 / 1v1/2v2 切胜负条件 / TutorialBubble 触发条件链 / DialogPanel 翻页 / HP=0 击杀动画 / 多 bubble 并存 / 断网重连 / 房间列表空态。

---

## 13. 已知缺口与死代码(汇总)

### 13.1 P0 缺口

| 缺口 | 位置 | 修复方案 |
|---|---|---|
| **Manual save 按钮缺失** | main.tscn + main.gd | 新增 save_new_btn,在战斗中按"💾 保存"调 `NetworkClient.save_manual(user_name, slot_index, mainline_id, chapter_index, label)` |

### 13.2 P1 缺口

| 缺口 | 位置 | 修复方案 |
|---|---|---|
| **JoinByCodeButton 死按钮** | main.tscn:143-146 | 接 `_on_join_by_code_pressed` → 输入 code → `list_games` 过滤匹配 → `join_game` |
| **主菜单 SettingsButton** | main.tscn:173-175 | 接 `_on_settings_open_pressed`(main.gd 行 2410) 替代 status hack |
| **Help 面板无触发** | main.tscn + main.gd:1831 | 加 ❓ / "玩法说明" 按钮 → `show_help()` |
| **静音 toggle 死** | main.gd:1797 | 加静音按钮节点 → connect `_on_toggle_mute_pressed` |
| **`MainlineNextBtn` 默认 visible=false**(已 wired 但待 gameplay 验证) | main.tscn:1990-1993 | smoke 验过;真实 advance 流再确认 |
| **Editor 高级工具缺口** fill / line / select / move / recolor | main.gd | 与 docs/WebUI-vs-GodotClient-差异 P1 一致 |
| **Bug**:`gs.set("is_connected")` 字段名错 | network_client.gd:95-96 | 改为 `gs.set("ws_connected", true)` |

### 13.3 P2 polish

| 缺口 | 现状 | 建议 |
|---|---|---|
| 主题切换 stub(只换 backdrop 色) | main.gd:1814 | M5.5 写完整 .tres |
| **`_on_lobby_seat_commander_step` 只本地 UI** | main.gd:4951 | 若要持久化需补 API |
| **AI commentary WS 类型 no-op** | network_client.gd:327-329 | 接战报 / 聊天面板 |
| **场景中"结束回合"按钮 spec 模式下变 ✅ 确认(继续)** | main.gd | 未实现 |
| **3 主题 label/tcsn 不一致**(dropdown "深绿像素" vs tscn "像素战棋风") | main.tscn:1752 | 统一文本 |
| **`.apply_preferred_color` 只写 pref 不当前生效** | main.gd:2479-2481 | 加 hot-effect(改下一房间即时生效) |
| **board SPEC / THREAT / HOVER mode 预留未触发** | highlights.gd | 引入攻击威胁范围 |
| **`/games/{id}/suspend` capture_suspend 未触发** | network_client.gd:702 | 接主动挂起 UI |
| **complete_mainline_prepare 未触发** | network_client.gd:624 | 接主线"准备好了"按钮 |
| **get_lobby / delete_game / delete_editor_map 包好未触发** | network_client.gd | 接对应 UI |

### 13.4 死代码 / 死节点

| 类型 | 位置 | 状态 |
|---|---|---|
| 主菜单 `JoinByCodeButton` | main.tscn:143 | disabled=true |
| 主菜单 `SettingsButton` | main.tscn:173 | disabled=true |
| `_on_toggle_mute_pressed` 函数 | main.gd:1797 | 无 connect |
| `show_help / hide_help` 函数 | main.gd:1831/1890 | 无触发按钮 |
| `EditorSurfaceOption` 重复声明 | main.tscn 行 323 + 374 | 只有后者有 @onready,场景 bug |
| `_start_quick_ai_game` | main.gd:826 / network_client.gd:826 | 唯一绕过 typed wrapper 直接调 |

---

## 14. 关键调用栈 / 行号索引

### 14.1 玩家动作 → 后端 REST 完整链路

```
# 1. 移动
[click tile in MOVE_MODE]
    → _on_board_tile_clicked
    → _move_unit_to(unit_id, tile_x, tile_y)
    → NetworkClient.action_move(game_id, player_id, unit_id, tx, ty) [network_client.gd:391]
    → POST /games/{id}/move
[WS event.delta → GameState.unit_moved → Board FLIP Tween 0.32s]
    → _on_unit_moved → spawn_floating_text("🚶") + _show_post_action_bubble("post_move")

# 2. 攻击(含 forecast)
[click enemy in ATTACK_MODE]
    → _on_board_unit_clicked → _show_attack_confirm
    → NetworkClient.forecast_attack(game, player, attacker, target, _on_attack_forecast_response)
    → GET /games/{id}/forecast-attack
    → _build_attack_forecast_info_text(BBCode) → 写 unit_info.text
[ConfirmBtn]
    → _attack_unit_to(attacker, target)
    → NetworkClient.action_attack(...) [network_client.gd:396]
    → POST /games/{id}/attack
[WS event.delta → GameState.unit_attacked → spawn_floating_text("💥") + post_action_bubble]

# 3. 技能
[skill button in ActionBubble]
    → _on_skill_pressed → _active_skill_of
    → if heal: _heal_targets(self.healer) → 8-邻接 HP<max 的友军
    → if arcane: _arcane_targets(self.warlock) → Manhattan 1-2 内敌人
    → NetworkClient.action_skill(...) [network_client.gd:401]
    → POST /games/{id}/skill

# 4. 占领
[claim button]
    → _on_claim_pressed → NetworkClient.action_claim(...) [network_client.gd:413]
    → POST /games/{id}/claim

# 5. 招募
[click empty barracks]
    → _show_recruit_at → RecruitPanel
    → _recruit_unit_to(tile_x, tile_y, unit_type)
    → NetworkClient.action_recruit(...) [network_client.gd:418]
    → POST /games/{id}/recruit

# 6. 待命
[wait button]
    → _on_wait_pressed → NetworkClient.action_wait(...) [network_client.gd:408]
    → POST /games/{id}/wait

# 7. 结束回合
[end_turn button]
    → _on_end_turn_pressed → NetworkClient.action_end_turn(...) [network_client.gd:423]
    → POST /games/{id}/end-turn
```

### 14.2 WS → 客户端 UI 全链路

```
ws://…/ws/games/{id}?player_id=…&since_seq=…
    ↓
NetworkClient._ws_poll(0.05s tick)
    ↓ (per packet)
NetworkClient._dispatch_ws_message
    ├ server.hello → server_hello_received(seq, payload) → GameState._on_server_hello
    ├ state.snapshot → state_snapshot_received(payload.game) → GameState._on_state_snapshot
    │   ├ snapshot_received / state_updated
    │   ├ units_changed / current_player_changed / phase_changed
    └ event.delta → event_delta_received(payload) → GameState._on_event_delta
        ├ log_received (each event)
        └ event_type → typed signal (18 个)
            ├ move → unit_moved(...) → Board._on_units_changed FLIP
            ├ attack → unit_attacked(...) → Board.spawn_floating_text
            ├ kill → unit_killed(...)
            ├ recruit → unit_recruited(...)
            ├ turn_ended → turn_ended → main.gd._on_turn_ended → TurnBanner
            ├ match_ended → match_ended → main.gd._on_match_ended → BattleResultPanel
            └ ai_thinking → ai_thinking(true/false) → AIThinking pulse
[200ms debounce]
    → _schedule_board_refresh
    → NetworkClient.get_game_state
    → GameState.ingest (全替换)
    → units_changed (本地可能与 WS 重复但幂等)
```

### 14.3 主线流程(开始 → 战斗 → 推进 → 弃章)

```
[mainline_button]
    → _on_mainline_pressed (5573-5604)
    → set_mainline_page("chapter_list") + list_mainlines + list_saves

[chapter card clicked]
    → _on_ml_card_pressed (5774)
    → get_mainline_detail → dialogue pre_battle
    → _play_dialogue_scenes (2621-2633) → DialogPanel
    → get_mainline_prepare → _set_mainline_page("prepare")
    → 6 tabs (heroes / roster / equipment / mercenary / shop / saves)

[PrepareStartBtn]
    → _on_prepare_start_pressed → NetworkClient.start_mainline
    → _on_mainline_start_response (6503-6545)
        ├ 409 mainline_already_active:
        │   _mainline_auto_retry_pending = true
        │   → abandon_mainline → re-call start_mainline(retry=true)
        └ success:
            ├ fetch_mainline_dialogue(pre_battle_dialogue_url) → _play_dialogue_scenes
            ├ _show_view("game") + connect_to_game
            └ MainlineNextBtn.visible=false

[战斗结束 + winner==self + active_mainline]
    → NetworkClient.advance_mainline → _on_mainline_advance_response (6574-6604)
        ├ state=="victory" → 清 active + 显示奖励 + MainlineNextBtn.visible=false
        └ next 场 → MainlineNextBtn.visible=true

[MainlineNextBtn]
    → _on_mainline_next_battle_pressed → NetworkClient.next_battle_mainline
    → _on_mainline_next_battle_response → _on_mainline_start_response (alias)

[MLAbandonBtn]
    → NetworkClient.abandon_mainline → _on_mainline_abandon_response
    → 清 active + MainlineNextBtn.visible=false + 切回 mainline view
```

---

## 15. 测试覆盖总表

按模块加权综合:**72-78%**。

| 模块 | 覆盖 | 备注 |
|---|---|---|
| 启动 / Menu / Settings | 70% | settings_screenshot + smoke 节点存在 |
| Lobby 4 subview | 75% | lobby_subview + lobby_create_preview 截图齐 |
| Mainline 列表 + 准备页 | 90% | chapter_06_* 三个工具验证 |
| Game 视图 / Board 渲染 | 90% | 7 张地图 × TileSet 断言 + 大地图截图 |
| 战斗 7 动作 | 80% | smoke + move/attack/attack_forecast 截图 |
| 攻击预测 / 结算 | 85% | smoke 中文断言 + 截图 |
| 编辑器 | 85% | smoke 三部署模式很全,缺 .tscn 编辑流程截图 |
| Save 管理 | 60% | smoke 5 断言 + manual save P0 缺 |
| 音频 / BGM / SFX | 30% | 只验 list,无播放验证 |
| Help / 静音 / 全局设置 | 10% | 几乎全死 |

---

## 16. 结论与下一步建议

### 16.1 主结论

1. **Godot 客户端已可独立主路径** — 主线 + 战斗 + 大厅 + 编辑器 + 存档 主路径全部就绪,**服务端权威规则**贯穿全栈
2. **网络层实现稳健** — HTTPRequest 串行队列 + WS 心跳 25s + 0.5-30s 指数退避重连 + since_seq 回放 一套完整
3. **autoload 顺序陷阱** + **callback 签名铁律** + **服务端 WS 不发回合事件** 三条规则已在 MEMORY 里锁定
4. **测试覆盖 72-78%**,269 断言的 smoke_test + chapter_06_* + e2e_one_game 构成核心 CI
5. **P0/P1 缺口共 5 个**:manual save 写盘 + 4 个死按钮(JoinByCode / SettingsButton / Help / Mute)

### 16.2 短期(1-2 周)可清理

- [ ] **P0** 接入 save_manual 写盘按钮(战斗中 + 主线准备页 Saves tab)
- [ ] **P1** 修 `gs.set("is_connected")` 字段名 bug
- [ ] **P1** 给 JoinByCode / SettingsButton / Help / Mute 4 个死按钮接通(handler 已存在)
- [ ] **P1** 验证 MainlineNextBtn 真实 advance 流程可见性
- [ ] **P2** 接通 commentary.text / commentary.audio 到战报面板
- [ ] **P2** 主题切换完整版(.tres)
- [ ] **P2** capture_suspend / complete_mainline_prepare / get_lobby / delete_game 等包好方法的 UI 触发

### 16.3 中期

- [ ] WebUI 冻结维护,Godot 客户端作主客户端
- [ ] 端到端集成 E2E 覆盖从主菜单 → 主线 → 弃章 → 重进 → 续局 全链路
- [ ] 移动端 export(M4)+ HTML5 export(M5)

---

## 附录 A:文件锚点速查

| 主题 | 绝对路径 |
|---|---|
| 主场景 | `D:/Python/BattleBlitz/battleblitz/godot-client/scenes/main.tscn` |
| 棋盘场景 | `D:/Python/BattleBlitz/battleblitz/godot-client/scenes/board.tscn` |
| 主控脚本 | `D:/Python/BattleBlitz/battleblitz/godot-client/scripts/main.gd`(7372 行) |
| Autoloads | `D:/Python/BattleBlitz/battleblitz/godot-client/scripts/autoload/{config,user_settings,game_state,input_state,network_client,audio_manager}.gd` |
| Board / Camera / Highlight / Unit | `D:/Python/BattleBlitz/battleblitz/godot-client/scripts/board/{board,board_camera,highlights,unit_node}.gd` |
| Map | `D:/Python/BattleBlitz/battleblitz/godot-client/scripts/core/{map_metrics,map_theme,map_loader,map_logic,tile_set_builder,texture_loader,types}.gd` |
| UI | `D:/Python/BattleBlitz/battleblitz/godot-client/scripts/ui/{menu_theme,map_preview_summary}.gd` |
| 工程配置 | `D:/Python/BattleBlitz/battleblitz/godot-client/project.godot` |
| 资产 | `D:/Python/BattleBlitz/battleblitz/godot-client/assets/{tiles,classic,heroes,audio}/` |
| Tools | `D:/Python/BattleBlitz/battleblitz/godot-client/tools/(26 个脚本)` |
| Python 后端常量对照 | `D:/Python/BattleBlitz/battleblitz/game/app/config.py` |
| 配套 xlsx | `D:/Python/BattleBlitz/battleblitz/docs/架构/Godot客户端功能调查报告.xlsx` |

---

> 报告完。
