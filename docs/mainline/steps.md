# 主线模式 — 4 步实施步骤

> 4 步走完 v1 主线可玩版本。
> 全部已实装（✅ 2026-06-27）。详细历史实施日志保留在 git log。

---

## 总览

| Step | 主题 | 实施文件 | 决策点 | 状态 |
|------|------|----------|--------|------|
| 1 | 数据格式 + 加载器 | `app/mainline/{loader,schemas}.py` | A：纯 JSON loader | ✅ |
| 2 | 存档接入主线进度 | `progression/{models,service}.py` + `routes/profile.py` | B：存档粒度由前端调 advance 决定 | ✅ |
| 3 | 引擎 + 入口 + 前端 | `mainline/engine.py` + `routes/mainline.py` + `MainlineView` (app.js) | C：abandon 端点 / D：enemy 内部注入 | ✅ |
| 4 | 内容 + E2E | `mainlines/chapter_01_*.json` + `stories/chapter_01/*.json` | E：v1 章节全开放 | ✅ |

---

## Step 1 — 数据格式 + 加载器 ✅

**实施**：
- `game/app/mainline/schemas.py` — Pydantic 模型（`Mainline`, `BattleSpec`, `UnitSpec`）
- `game/app/mainline/loader.py` — `load_mainline(id) → Mainline`，从 `game/mainlines/*.json` 读取 + 缓存
- `game/mainlines/chapter_01_steel_rebellion.json` — 第一章主线配置

**关键决策**：
- **A** — V1 纯 JSON loader（不准 Python `loader_hook`），V2 再加 `module.func` 字段

**测试**：loader 单测覆盖 schema 校验 + 缓存失效路径

---

## Step 2 — 存档接入主线进度 ✅

**实施**：
- `PlayerProfile` 加 2 字段：`active_mainline` + `mainline_progress` (JSON)
- `progression/service.py` 加 4 个方法：`set_active_mainline / advance_progress / clear_active_mainline / get_profile`
- 3 个新端点：
  - `GET /profile/{name}` — 读当前 Profile
  - `POST /profile/{name}/mainline/start` — 激活主线
  - `POST /profile/{name}/mainline/advance` — 推进 cursor
- 迁移脚本：`tools/migrate_add_mainline_progress.py`（幂等）

**关键决策**：
- **B** — 存档粒度：战斗胜利 + 关键剧情节点双触发（前端 `advance` 调一次推进一帧）
- **B.2** — 进度格式扁平：`{battle_index, scene_id, started_at}`（V2 再考虑嵌套）

**测试**：`tests/test_profile_progress.py` 23/23 通过

详见 [`migrations.md`](migrations.md)。

---

## Step 3 — 引擎 + 入口 + 前端 ✅

**实施**：
- `game/app/routes/mainline.py` — 5 个端点：`list / detail / start / advance / next-battle / abandon` + 1 个 dialogue 静态服务
- `game/app/mainline/engine.py` — `MainlineEngine` 状态机 + `MainlineState` 枚举
- `game/app/routes/game.py` — 抽出 `_start_battle_internal`（**纯重构**，行为不变）供主线路由复用
- 前端：大厅按钮 + `view-mainline-list` / `view-mainline-play` 两个 SPA 段 + `app.js` 新增 ~200 行

**关键决策**：
- **C** — 提供 `abandon` 端点允许放弃（不清 Game 行，让背景 scheduler 自然清理）
- **D** — enemy 内部注入：`build_ai_player` + `_spawn_enemy_player` helper 直接构造 ORM 行，不走 `add-ai` HTTP
- 战斗 → advance 触发：**前端轮询**检测 `game.status=="finished"`（不改战斗逻辑）
- Game 命名约定：`mainline:{mainline_id}:{battle_id}`（不需新加列）

**端点**：

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/mainlines` | 列出全部主线 |
| `GET` | `/mainlines/{id}` | 章节详情 + battles 预览 |
| `POST` | `/mainlines/{id}/start` | 创建 Game + 注入 AI + 启动首战 |
| `POST` | `/mainlines/{id}/advance` | 战斗胜利后推进 |
| `POST` | `/mainlines/{id}/next-battle` | 推进到下一场战斗 |
| `POST` | `/mainlines/{id}/abandon` | 放弃当前进度 |
| `GET` | `/mainlines/dialogue?path=...` | 对话 JSON 静态服务 |

**测试**：`test_mainline_api.py` 22 + `test_mainline_engine.py` 23 = 45 用例

---

## Step 4 — 内容 + E2E ✅

**实施**：
- `game/mainlines/chapter_01_steel_rebellion.json` — 第一章 2 场战斗配置（battle_02.map_preset 改用 `four_lakes`，见 D1）
- `game/stories/chapter_01/` — 4 段对话剧本：
  - `intro.json`（7 段：2 nar + 3 dlg + 1 choice + 1 battle_ref）
  - `battle_01_after.json`（3 段）
  - `battle_02_after.json`（3 段）
  - `victory.json`（4 段，含 choice "回大厅" / "回放"）
- `game/app/web/app.js` — Dialog `_run()` 新增 `battle_ref` 分支（约 10 行）
- `game/tests/test_mainline_flow.py` — 7 个端到端 + 单元测试

**关键决策**：
- **E** — v1 章节全开放（无解锁依赖），V2 再做章节解锁
- **D2** — `battle_ref` 通过 Dialog 新分支处理（语义清晰）
- **D1** — `battle_02.map_preset` 用 `four_lakes` 替代缺失的 `castle_siege`（0 代码改动）
- **D3** — choice 不影响战斗参数（v1 仅展示）
- **D4** — `stories/` 路径以 `mainlines/` 为基准解析
- **D5** — `victory.choice.replay` v1 仅 toast

**状态**：4 段对话脚本就绪；自动化 E2E 由 `test_mainline_api.py` + `test_mainline_engine.py` + `test_mainline_flow.py` 覆盖；手动验收脚本见 git log (`a40b1a9`)。

---

## 与现有系统的对接（不重写战斗）

| 现有模块 | 在主线中的角色 | 改动 |
|----------|---------------|------|
| `classes/units/*.py` | 职业数据源 | **0 改动** |
| `progression/models.py` | 用户角色持久化 | +2 字段 |
| `progression/service.py` | 角色成长/装备 | 复用 |
| `Dialog` (S0.1) | 剧情播放 | +1 个 battle_ref 分支 |
| `routes/game.py` start_game | 战斗初始化 | 抽出 `_start_battle_internal` 供复用 |
| `routes/actions.py` / `turns.py` | 战斗内部 | **0 改动** |
| `add-ai` | 主线敌人注入 | **不**走，engine 内部构造 |

**核心原则**：主线 = 现有战斗系统的"剧本编排层"，不重写任何战斗逻辑。

---

## 实施偏差汇总

详见 [`deviations.md`](deviations.md)（D1-D5 计划 vs 实际）。
