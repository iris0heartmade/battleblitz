# 主线模式 — 实施偏差汇总（plan vs 实际）

> **目的**：记录 `mainline_short_plan.md` / `step3_plan.md` / `step4_content_plan.md`
> 里决策点 **D1-D5** 的"计划方案"vs"实际落地"差异。
> **日期**：2026-06-26 审计

---

## D1 — `battle_02` 地图预设

| 项 | 内容 |
|---|------|
| **计划** | 两种方案：① 改 JSON 用 `four_lakes`（A，0 代码）；② 新增 `castle_siege` 预设（B，约 30 行 + 1 单测）|
| **推荐** | A（最小改动）|
| **实际** | 暂未落定。`chapter_01_steel_rebellion.json` 的 `battle_02.map_preset` 仍写 `"castle_siege"`，运行时会 fallback 到 `generate_map_preset` 随机生成 |
| **差距** | 当前未走 A 也未走 B；功能上"能跑"（fallback），但叙事上"围城战"标签不准确 |
| **建议** | 步骤 4 落地时**走 A**（改 JSON 一行），B 留到地图编辑器时一起做 |

## D2 — `battle_ref` 类型处理

| 项 | 内容 |
|---|------|
| **计划** | 两种方案：① Dialog 新增 `_renderBattleRef` 分支（+8 行 + DOM 钩子）；② 用 `wait` + 引擎侧约定代替（无 UI 改动）|
| **推荐** | ①（语义清晰）|
| **实际** | ⚠️ **未支持**。`app.js:1849-1858` 的 `_run()` 分支只有 `dialogue / narration / choice / wait`，其他 type 落入 else 分支被**静默吞掉** |
| **风险** | `step4_content_plan.md` 的 `intro.json` 含 `battle_ref` type（idx 6），当前会**被静默忽略** — 战斗不会从对话后自动触发 |
| **建议** | 步骤 4 验收前**必须**先实施 D2-①（约 10 行 JS）|

## D3 — `intro.choice` 是否影响战斗

| 项 | 内容 |
|---|------|
| **计划** | v1 仅展示（选 rush/scout 都不改 `enemy_composition` / `map_seed`）；V2 再做"分支战斗" |
| **实际** | 与计划一致。`choice.value` 在 v1 丢弃（或仅记日志）|
| **建议** | 维持现状。V2 决定要不要加 `route_forks` 字段 |

## D4 — `stories/` 相对路径基准

| 项 | 内容 |
|---|------|
| **计划** | `loader.py` 以 `mainlines/` 为基准解析 `dialogues["intro"] = "stories/chapter_01/intro.json"` |
| **实际** | ⚠️ **未实装**。`game/app/mainline/loader.py` 当前是占位（仅 schemas + 占位类；详见当时 step-3 计划 §2.4 复用点清单）|
| **风险** | 步骤 3 必须先在 `loader.py` 加 `relative_to(mainlines_dir())` 解析，否则前端 `GET /mainlines/dialogue?path=...` 拿不到文件 |
| **建议** | 在 step 3 的 `_start_battle_internal` 之后立即加 ~5 行路径解析 |

## D5 — `victory.choice.replay` 实现

| 项 | 内容 |
|---|------|
| **计划** | v1 仅 toast 提示"已记录回放入口"，V2 实装；两个选项（lobby / replay）都回大厅，toast 文本区分 |
| **实际** | 与计划一致。v1 不做真实回放 |
| **建议** | 维持现状。V2 触发条件：用户投诉"看不到上一把" 或 游戏 demo 视频需求 |

---

## 总览：状态 × 决策

| ID | 决策 | 计划推荐 | 实际状态 | 阻塞步骤 4 E2E？ |
|----|------|----------|----------|-----------------|
| D1 | battle_02 地图 | A（改 four_lakes） | ⚠️ 未做 | 否（fallback 跑通）|
| D2 | battle_ref Dialog 分支 | ①（新增分支） | ❌ 未做 | **是** |
| D3 | choice 影响战斗 | v1 仅展示 | ✅ 一致 | 否 |
| D4 | stories 路径解析 | loader 加 ~5 行 | ❌ 未做 | **是**（依赖 loader 落定）|
| D5 | victory.choice.replay | v1 仅 toast | ✅ 一致 | 否 |

**步骤 4 E2E 验收阻塞项**：**D2 + D4**（缺这两块，`intro.json → battle_01` 链路就断）

---

## 附：审计日期 + 数据来源

- 审计日期：2026-06-26
- 数据来源：
  - `step3_plan.md` §7 风险 + 决策点
  - `step4_content_plan.md` §5 R1-R6 + §7 D1-D5
  - `docs/architecture.md` §0 项目状态
  - `archive/2026-06-26-bugs.md`（已归档）bug 审计结论

---

*合并整理：2026-06-27（doc/ + todo/ 合并到 docs/）*
