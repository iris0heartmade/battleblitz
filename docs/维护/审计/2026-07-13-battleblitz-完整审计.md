# BattleBlitz 全栈实现审计

**审计日期**:2026-07-13
**审计分支**:`feat/p2.6-data-driven-initial-units` (`07d2081`)
**审计方法**:只读,4 个并行 Explore Agent(后端核心 / 后端 API / 前端 UI / 测试覆盖)+ 设计文档交叉验证
**审计范围**:`game/app/`(92 个 .py 文件,~21,313 行)+ `game/app/web/` + `game/tests/`(53 文件 / ~10,560 行)
**pytest 实际**:**644 passed, 2 skipped** in 41.49s

---

## 0. 执行摘要(Executive Summary)

| 维度 | 结论 |
|------|------|
| **总完成度** | **~80%**(核心 + 经济 + 胜利 + 指挥官 + WS 已 ship;P1/P3 高级系统 4 项空白) |
| **设计覆盖** | ✅ 核心战斗 / S0 / P0 / P2.3 / CO Power / 数据驱动地图 / 编辑器 / BGM |
| **明显 gap** | ❌ P1.1 武器耐久 / P2.1 迷雾 / P3.1 支援 / P3.2 地形动态 |
| **生产风险** | 🔴 WS `/ws/games/{id}` 整端无 e2e 测试(290 行) |
| **测试覆盖率** | 🟢 后端强(644) / 🔴 WS 0 / 🔴 前端 e2e 0 / 🟡 fixtures 不一致 |

**一句话评级**:核心战斗+经济+胜利+指挥官已经完成、可玩、主线可通关;但 P1/P2/P3 高级玩法文档规划里很多,代码里没;WS 网关是单点风险,任何改动都没自动化保护。

---

## 1. 设计 vs 实现·总账

下表按设计文档(`路线.md` / `阶段.md` / `PROJECT_STATUS.md` / `架构.md`)中明确规划的功能项,逐项给出实装判定。

| 设计项 | 来源 | 状态 | 完成度 | 关键证据 |
|--------|------|------|--------|---------|
| **S0.1 对话框系统**(4 scene) | 路线 §S0.1 | ✅ | 100% | `app/web/app.js:3739-4147` 5 种 scene(`+ battle_ref`)、打字机 40 字/s、Space/Enter/Esc |
| **S0.2 主线剧情系统** | 路线 §S0.2 | ✅ | 100% | `app/mainline/{loader,engine,schemas,spawn_overrides}.py` 4 文件;5 态机 (`MENU/DIALOGUE/BATTLE/VICTORY/ABANDONED`);50+ 测试覆盖 |
| **S0.3 存档系统**(主线部分) | 路线 §S0.3 | 🟡 | 70% | `PlayerProfile.mainline_progress` 按 user_name 持久化 OK;**自由模式 SaveSlot 未实装** |
| **P0.1 敌我分阶段** | 路线 §P0.1 | ✅ | 100% | `models.py:62 Game.phase` 字段;`routes/turns.py:141` 切换;AI 链 1.2s 延迟 |
| **P0.2 战斗预测面板** | 路线 §P0.2 | ✅ | 100% | `routes/actions.py` 完整实现;`forecastSingleHit/forecastAttack` 含反击/暴击 |
| **P0.3 反击系统** | 路线 §P0.3 | ✅ | 100% | `COUNTER_DAMAGE_MULT=0.5`;AI 与玩家共用 `attack_with_double_strike()` (commit `b0df415`) |
| **P0.4 地形体系+经济** | 路线 §P0.4 | ✅ | 100% | 16 地形全实装;village/barracks/vault 收入;claim+recruit 端点 |
| **P1.1 武器耐久度** | 路线 §P1.1 | ❌ | 0% | `models.py` Unit **无** `weapons` 字段;无 `WEAPON_TEMPLATES`;grep 0 命中 |
| **P1.2 兵种克制扩展(剑→斧→枪三角)** | 路线 §P1.2 | 🟡 | 20% | 只保留了原 `swordsman→knight→archer` 2 条克制线 |
| **P1.3 晋升/等级系统** | 路线 §P1.3 | 🟡 | 70% | 走 **线性 tier**(TIER_LEVEL_CAP / TIER_PROMO_LEVEL_REQ)非原设计 **PROMOTE_XP_TABLE + 转职证**;`service.py` 完整,`api.py` 9 端点 |
| **P2.1 迷雾战争** | 路线 §P2.1 | ❌ | 5% | DB 无 `Unit.vision` 字段;引擎无 `compute_vision`;LLM prompt 端用了简单 manhattan 视野(`agent/snapshot.py:52`),玩家路径仍上帝视角 |
| **P2.2 指挥官 + CO Power** | 路线 §P2.2 | 🟡 | 60% | **2 个**指挥官(yun + anna,hero & commander 合一),非设计 4 个;meter 是 kill-driven 非 per-turn 充能;AI 调用 stub |
| **P2.3 胜利条件多样化** | 路线 §P2.3 | ✅ | 80% | rout/seize/reach/defend 全实装,**boss schema 接受但引擎无分支**;seize 检查 universal化(2026-07-13) |
| **P3.1 支援系统** | 路线 §P3.1 | ❌ | 0% | DB 无 `support_pairs`;计算路径无引用 |
| **P3.2 地形动态(火/冰/沙尘暴)** | 路线 §P3.2 | ❌ | 0% | DB 无 `Tile.status`;无 StatusEffect 表/字典 |
| **P3.3 招募 + 经济** | 路线 §P3.3 | ✅ | 80% | claim + recruit 端点 OK;平衡未细调;无最大单位数限制 |
| **P3.4 战斗动画层** | 路线 §P3.4 | ✅ | 100% | 13 类浮动文字(damage/crit/kill/heal/gold/levelup/反击)+ FLIP + 阶段横幅 + 对话滑入 |
| **随机地图生成器** | 规格文档(592 行) | ✅ | 100% | `map_generation/` 5 段 pipeline(BSP/castle/symmetry/terrain_clusters/river_network/road_network);`game_logic.generate_map()` 默认走新路径 |
| **生产 WebSocket 网关** | P0.1 收尾 | ✅ | 100% | `app/routes/ws_gateway.py` 290 行;server.hello/state.snapshot/event.delta/server.pong/error 全帧;200 事件 replay buffer;X-Player-Id 双路鉴权 |
| **自定义地图编辑器** | P1.3 | ✅ | 100% | 前端 26 工具按钮齐;后端 4 端点(`GET/POST/DELETE /editor/maps`);选/移/删/改色/biome/撤销重做 50 步栈 |
| **BGM 系统** | P2.9 | ✅ | 100% | `routes/audio.py` + `populateBgmPicker` + `AudioManager` fade/过渡 + `mainline-bgm` 徽章 + 后端 down 兜底 |
| **测试覆盖** | 横切 RT.3 | 🟡 | 70% | 后端 644 测强;WS 0 e2e;前端 Playwright 0 |

### 1.1 设计原则验证

| 关键设计原则 | 文档 | 验证 |
|------------|------|------|
| MP 系统(替代简单 MOV) | 架构 §五 7.1 | ✅ `bfs_reachable` 按地形成本消耗 MP |
| 士气系统(替代纯 EXP/Level) | 架构 §五 7.2 | ✅ 新单位默认 0 星,击杀 +1,上限 3 |
| 首玩家公平性规则 | 架构 §五 7.3 | ✅ `first_player_done_first_turn` 一次性标记 |
| 兵种/技能模块化 | 架构 §三 3.x | ✅ `classes/units/` 自动注册表 + 钩子签名 |
| 事件总线 | 架构 §十一 11.1 | ✅ `GameEventBus` + 17 种 EventType |
| 主线 JSON 剧情格式 | 架构 §十二 12.1 | ✅ `loader.py:93-122` + 缓存 |
| 共享 combat resolver | 路线 §P2.2 后续 | ✅ AI 与玩家共用 `attack_with_double_strike()` |

---

## 2. 战斗核心(深度)

### 2.1 战斗公式实现

```
damage = ATK_eff × (ATK_eff / (ATK_eff + DEF_eff)) × 克制 × 暴击 × 士气缩放
ATK_eff  = ATK × (1 + morale × 0.10)
DEF_eff  = (DEF + terrain_bonus) × (1 + morale × 0.05)
```

- **物理/魔法派发**:`attack_kind` 字段,魔法分支用 MATK vs MDEF+terrain(`game_logic.py:414-416`)
- **暴击**:`BASE_CRIT_RATE=0.05 + CRIT_PER_LEVEL=0.01 × level`,1.5× 倍率(`config.py:345-347`)
- **类型克制**:双向表 `strong_against`,默认 1.0,优势 +20%(`classes/units/__init__.py:68-71`)
- **士气**:0-3 星,每杀 +1(上限),+10% ATK / +5% DEF 每星(`config.py:404-407`)
- **MP 系统**:每回合 `Unit.mp = mov`,地形成本从 `TERRAIN_MOVE_COST` 扣减;`bfs_reachable()` 预算 `mov × 2`(道路减半)
- **公平性**:`first_player_done_first_turn` 一次性布尔标记(`models.py:62` + `routes/turns.py:197-198`)
- **反击**:50% × 反击方自己 stats 重算;AI 与玩家共用同一函数(`game_logic.py:1881-1892`)

### 2.2 5 兵种·4 技能

| 单位 | 类型 | HP | ATK | DEF | MATK | MDEF | 射程 | MP | 技能 |
|------|------|-----|-----|-----|------|------|------|-----|------|
| 剑士 swordsman | 物理 | 45 | 18 | 12 | 4 | 4 | 1 | 5 | — |
| 弓手 archer | 物理 | 35 | 20 | 6 | 4 | 4 | 2(min 1) | 5 | [被动] sniper +1 射程 |
| 骑士 knight | 物理 | 55 | 22 | 8 | 4 | 4 | 1 | 8 | [被动] 连击 2× 50% |
| 术士 warlock | 魔法 | 45 | 8 | 10 | **22** | **12** | 1-2 | 8 | — |
| 治疗师 healer | 魔法 | 40 | 5 | 9 | 8 | 12 | 1-2 | 5 | [主动] heal 20HP 相邻 |

**技能**:`heal`(主动,healer 默认) / `snipe`(被动,archer 默认) / `double_strike`(被动,knight 默认) / `arcane_strike`(主动,yun 专属) / `rally` **已主动移除**(2026-06-30 重构,见 `game_logic.py:567-572` 注释;`healer.py:8-9` docstring 说明)

### 2.3 16 种地形

基础 5(plain / forest / mountain / river / castle)+ 7 城堡子物(castle_floor / wall / door / stairs / throne / vault)+ 4 资源地(village / barracks / road / gate)+ bridge

**`CLAIMABLE_TERRAINS` = {village, barracks, castle_vault, castle}** —— HQ 可被占领,2026-07-13 修复确认

---

## 3. REST + WebSocket 全景

### 3.1 WebSocket 生产网关

| 项 | 状态 | 证据 |
|---|---|---|
| 端点 `/ws/games/{game_id}` | ✅ | `routes/ws_gateway.py:131` `@router.websocket("/games/{game_id}")` |
| Debug 端点 `/debug/ws/games/{game_id}` | ✅ | `routes/debug_ws.py:32` |
| 鉴权机制 | ✅ | X-Player-Id header **或** `?player_id=` query(浏览器兼容) |
| `server.hello` | ✅ | `ws_gateway.py:196-209` |
| `state.snapshot` | ✅ | `ws_gateway.py:226-231` |
| `event.delta` | ✅ | `ws_gateway.py:268-286` |
| `server.pong` | ✅ | `ws_gateway.py:175-179` (heartbeat 30s) |
| Replay buffer | ✅ | 200 事件,按 `since_seq` 重放 |

**完整帧集合**:`server.hello` / `state.snapshot` / `event.delta` / `server.pong` / `error`,协议版本 v1(`protocol/v1.py:27`)

### 3.2 REST 端点清单

| 类别 | 端点数 | 有测试 | 零测试 |
|------|--------|--------|--------|
| `/games/*` 生命周期 | 14 | 11 | rejoin, rejoin_by_name |
| `/games/*` 操作 (move/attack/skill/wait/claim/recruit/end-turn) | 7 | 4 | **skill, wait** |
| `/games/presets` `/skills` `/units` | 3 | 1 | skills, units |
| `/mainlines/*` | 7 | 7 ✅ | — |
| `/profile/*` | 4 | 4 ✅ | — |
| `/editor/maps` | 4 | 1 | GET list/detail |
| `/progression/*` | 9 | 20 ✅ | — |
| `/commanders` + `/heroes` + `/audio` | 4 | 16+ | `/heroes` GET |
| `WS /ws/games/{id}` (生产网关) | 1 | **0** 🔴 | — |
| `WS /debug/ws/games/{id}` | 1 | 0 | — |

**端点覆盖率**:38 个 REST + 2 WS = 40 端点,其中 32 有测试 / 8 零测试 / 1 端到端空白(WS)

---

## 4. 前端实现全景

### 4.1 12 个视图

| View | 用途 | 默认 | 切换触发 |
|------|------|------|---------|
| `view-menu` | 主菜单 | visible | `showView("menu")` |
| `view-free-mode` | 自由模式入口 | hidden | `goto-free-mode` |
| `view-settings` | 设置 | hidden | `goto-settings` |
| `view-new-game` | 创建游戏表单 | hidden | `goto-new-game` + populatePresetSelects |
| `view-join-game` | 加入房间 | hidden | `goto-join-game` + renderJoinList |
| `view-help` | 帮助 | hidden | `goto-help` |
| `view-mainline-list` | 主线章节列表 | hidden | `goto-mainline-list` 并发拉 3 个 render fn |
| `view-saves` | 存档管理 | hidden | `goto-saves` |
| `view-editor` | 地图编辑器 | hidden | `goto-editor` + initEditor |
| `view-mainline-play` | 主线游玩 | hidden | `MainlineView._enterPlayView()` |
| `view-lobby` | 大厅 | hidden | `enterLobby(gid)` |
| `view-game` | 棋盘主界面 | hidden | `enterGame()` + 自动连 WS |

公共切换由 `showView(name)` (`app.js:294-308`) 统一管理,离开 `game` 视图自动 `disconnectWS()` + `AudioManager.stopCurrentBgm()`

### 4.2 棋盘 UI 组件(18 项)

棋盘 / 单位头像(经典像素)/ HP 条(三态)/ Morale 星标(避免 overflow 裁剪)/ MP 徽章 / 气泡菜单(7 种 action)/ 战报面板 / 选中单位信息 / 玩家列表(含 AI/spectator/team-pill)/ 金币 HUD / 指挥官充能条 / 阶段横幅(4 类)/ 回合切换横幅 / 占领进度条 / 地块 owner 标记 / 参考面板(3 tab)/ AI 点评面板 / 行动计数

### 4.3 WebSocket 客户端

`connectWS() / _wsHandleMessage() / _wsApplyEvent() / 1-30s 退避 / 200ms coalesce / lastSeq 同步 / showView 离开断开` —— WS 已 **完全接管** 3s 轮询(轮询仅作兜底)

### 4.4 对话框系统

5 种 scene:`dialogue / narration / choice / wait / battle_ref`;打字机 40 字/s(dialogue) vs 25 字/s(narration);队列 + Space/Enter/Esc + 选项点击 + 立绘面板独立

### 4.5 地图编辑器

26 个工具按钮全实装:BFS 填充 / Bresenham 画线 / 撤销重做 50 步栈 / 选取移动改色 / biome 切换 / 尺寸 15-45 / 单位放置(5 兵种)

### 4.6 动画(13 类)

FLIP 单位移动 / 浮动文字(damage/crit/kill/heal/gold/levelup/反击)/ 阶段横幅 pulse / 回合切换 banner-slide(3s 自动消失)/ 对话框 slideIn / 叙述 fadeIn / 打字机 caretBlink / 立绘淡入淡出

### 4.7 BGM

`GET /audio/tracks` 填充 picker + `new-bgm-meta` 元数据 + fade in/out 跨歌过渡 + mainline 进入战斗前 `mainline-bgm` 徽章

---

## 5. 测试覆盖深度

### 5.1 总数

- **53 个测试文件**、**644 passed / 2 skipped / 156 warnings / 41.49s**
- **测试 : 产品代码 ≈ 1 : 2**(`tests/` 10,560 行 vs `app/` 21,313 行)
- `tests/agent/` 内 4 个文件 **导入失败**(`from app.agent.agent import ...` 找不到 `app` 模块)
- `playwright-commander-ui/` **0 个测试文件**,只有 5 张截图

### 5.2 强覆盖(>10 测试)

战斗公式(34)/ AI 三种 personality(15)/ 5 种集成 smoke(15)/ logging(14)/ 战斗 polish(14)/ Snow 地形(13)/ 事件总线(12)/ battle_config(12)/ spectator(11)/ utils(26)/ progression leveling(25)/ mainline api(25)/ mainline engine(22)/ victory(22)/ profile mainline(23)/ progression api(20)/ mainline loader(19)/ mainline spawn(4)/ data-driven initial units(18)/ AI move once(2)/ unit skill(8)/ AI personality(15)

### 5.3 缺口清单(按风险)

#### 🔴 P0 级(必须补)

| 缺口 | 风险 | 工作量 |
|------|------|--------|
| WS `/ws/games/{id}` 整端 0 e2e | 290 行无自动化保护,改就靠手动 | 0.5 天 |
| 3 个已修 bug 缺回归(commit `ce9cb08` attack 500 / `16f9d80` AI income / `9388e24` WS snapshot) | 同类 bug 静默重现 | 每个 0.5h |
| `POST /games/{id}/skill` + `/wait` 零测试 | 路由存在,逻辑空跑可能 | 1 天 |

#### 🟡 P1 级

| 缺口 | 风险 |
|------|------|
| `POST /games/{id}/rejoin` / `/rejoin_by_name` | 断线重连无测试 |
| `/editor/maps` GET list/detail | 编辑器只能进,不能浏览 |
| `/heroes` GET | 英雄 meta 0 测 |
| boss 胜条件(引擎无分支) | schema 接受但无实现,先确认是 gap 还是设计意图 |

#### 🟢 P2 级

| 缺口 | 备注 |
|------|------|
| Playwright e2e = 0 | `playwright-commander-ui/` 有截图,无 spec |
| `tests/agent/` 4 文件 import 失败 | 需要 conftest 路径修复 |

### 5.4 测试基础设施隐患

1. **`game/tests/` 没有自己的 conftest**——依赖根 `game/conftest.py`,脆弱
2. **`TestClient`(同步 starlette)** 出现在 `test_commanders_api.py` / `test_team_mode.py`,绕过 ASGI lifespan,可能污染状态
3. **`fixtures` 复制粘贴**:`commander_client` / `ml_client` / `prog_client` 在多个文件重复定义,未集中到 conftest
4. **无 coverage 工具**:`pytest.ini` 未配 `--cov`;`requirements-dev.txt` 应有 `pytest-cov` 但运行结果不显示

---

## 6. Top 5 关键 Gap 与 ROI 建议

| # | Gap | 影响 | 工作量 | 优先级 |
|---|-----|------|--------|--------|
| 1 | WS `/ws/games/{id}` 0 e2e | 一改协议就盲飞 | 1 个 `test_ws_gateway.py` ≈ 0.5 天 | 🔴 P0 |
| 2 | 3 个 P0 bug 缺回归 | 重复 bug 静默回来 | 共 1.5h | 🔴 P0 |
| 3 | `/skill` + `/wait` + `/rejoin` 端到端测试 | 玩家断线/技能释放路径无保护 | 1-2 天 | 🟡 P1 |
| 4 | 编辑器/`/heroes`/Boss 胜条件 决策 + 测试 | 长尾 API 无覆盖 | 2 天 | 🟡 P1 |
| 5 | P2.1 迷雾 / P1.1 武器 / P3.1 支援 / P3.2 地形动态 开工决策 | 4 个高级系统空白 | 各 3-5 天,选 1 个 | 🟢 P2 |

---

## 7. 前端次要清理(不影响功能)

按发现顺序:

1. **观战模式"切换"按钮**半成品——`joinGame` 弹窗点"切换为观战"只 toast 提示,要么实装要么删按钮
2. **死代码 DOM**:`chat-float` div / `game-menu` 抽屉(注释自承 back-compat shell)/ `new-reach-tile-row` + `new-defend-turns-row` 表单行 / `WIN_CONDITION_LABEL` 字面量残留
3. **`map-preset` 硬编码 `<option>`**:被 `populatePresetSelects` 立即覆盖,冗余
4. **CSS 残留**:`.chat-box` 与 `#chat-float` 双规则都没 DOM 命中;`#game-menu [hidden]` 反向 hack `display: flex !important` 保留抽屉动画
5. **`assets/_unused/`** 目录有 20+ 归档图,前端 0 引用

---

## 8. 整体评分

| 维度 | 评分 | 备注 |
|------|------|------|
| **核心可玩性** | ⭐⭐⭐⭐⭐ | 1-4 人 / 5 兵种 / 4 胜条件 / 主线可通关 |
| **代码完整度** | ⭐⭐⭐⭐ | P0 全完,P1/P2 部分,P3 大量空白 |
| **生产就绪度** | ⭐⭐⭐ | WS 已上线,但 0 e2e + 死代码残留需清 |
| **数据驱动设计** | ⭐⭐⭐⭐⭐ | 41 张地图 initial_units 化,MAP_STYLES 丰富 |
| **架构清晰度** | ⭐⭐⭐⭐⭐ | 模块化 + 事件总线 + 协议分层 + 5 态机 |
| **英雄/指挥官** | ⭐⭐⭐⭐ | 绑定美术 + 充能 + CO power + AI 决策,但只 2 个 |
| **测试覆盖** | ⭐⭐⭐ | 后端强 / WS 0 / 前端 0 / fixtures 不一致 |

**综合评级**:⭐⭐⭐⭐ / 5(beta 完整可用,P0 收尾 + P1/P2 推进空间大)

---

## 9. 推荐下一步路线

### 9.1 立即可启动(0.5-1 天)

1. **WS e2e 测试**(1 个文件,覆盖 hello/snapshot/delta/pong/replay/reconnect 退避)
2. **3 个 P0 bug 回归**(各 0.5h,补 `test_regression_*.py`)
3. **前端死代码清理**(半天,删 5 处残留)

### 9.2 第 2 周(3-5 天)

4. **`/skill` / `/wait` / `/rejoin` 端到端测试**
5. **编辑器 `/GET` + `/heroes` 端到端测试**
6. **观战模式切换按钮** 决策(实装 or 删除)

### 9.3 第 3-4 周(1-2 周)

7. **P1.x 或 P2.x 之一开工**(迷雾战争最推荐,玩家上帝视角转阵营视角体验极大)
8. **fixtures 统一**到 `game/tests/conftest.py`,加 coverage 配置

---

## 10. 附录

### 10.1 审计依据的源文件

#### 设计文档
- `README.md`(当前状态描述)
- `HANDOFF_TO_NEXT_AGENT.md`(分支快照)
- `PROJECT_STATUS.md`(Beta 进度)
- `docs/路线.md`(S0/P0-P3 路线图)
- `docs/阶段.md`(分阶段开发方案)
- `docs/架构.md`(架构总览)
- `docs/死代码.md`(死代码清单)
- `docs/superpowers/specs/`(各项功能规格)
- `docs/superpowers/plans/`(实施计划)

#### 实现源码
- `game/app/`(92 .py 文件)
- `game/app/web/{index.html, app.js, style.css, assets/}`

#### 测试
- `game/tests/`(53 文件,644 测通过)
- `tests/agent/`(部分失败)
- `playwright-commander-ui/`(只有截图)

### 10.2 审计结论可信度

- ✅ 结论可信度高:基于实际 grep / 文件:行号 证据
- ⚠️ 注释中描述的实现 / 与实际代码可能有差异——审计时尽量实际读源码佐证
- ❌ 没读到的文件(`tools/`, `venv/`, `tools/node_modules/`)不计入结论

### 10.3 已知审计盲区

- 没动 `tools/`(git_ssh / ssh_askpass / gen_terrain_tiles 等)
- 没读 `venv/`(site-packages)
- 没拉 playwright 跑一遍真实 e2e
- 没实际联调线上后端验证 WS 协议级兼容性

---

*审计完成 2026-07-13*
*执行人:Claude(猫娘学妹)* (=^・ω・^=)♡
*下次审计建议时机:WS e2e 落地后 / 任何 P1.x 或 P2.x 完工后*
