# 维护 — 索引

> 运维记录、代码质量文档、一次性问题排查归档。
> 建立索引时间：2026-10-06

> **判断当前事实请读** [`../路线/项目状态.md`](../路线/项目状态.md)。本目录记录的是**过程**（当时发生了什么、为什么这么改），不是现状。

---

## ⚠️ 唯一还开着的待办

| 文档 | 状态 |
|---|---|
| [`2026-07-22-missing-initial-units-todo.md`](2026-07-22-missing-initial-units-todo.md) | 🔴 **未完成** — 53 张地图中 39 张仍缺 `initial_units`，靠老格式回退兜底。**2026-10-06 已复核确认仍开放** |

---

## 代码质量

| 文档 | 说明 |
|---|---|
| [`死代码清单.md`](死代码清单.md) | vulture 扫描结果 + 清理优先级，最后更新 2026-07-04 |
| [`main_gd-拆分重构计划.md`](main_gd-拆分重构计划.md) | 拆分 4,869 行 `main.gd` 的计划，**状态：待执行** |

---

## Godot 客户端问题排查（一次性修复记录）

这些记录的 bug **均已修复**，保留用于「同一个坑别再踩第二次」。

| 文档 | 解决的问题 |
|---|---|
| [`2026-07-23-godot-unit-info-click-freeze.md`](2026-07-23-godot-unit-info-click-freeze.md) | 点击单位信息面板时界面卡死 |
| [`2026-07-26-godot-action-latency.md`](2026-07-26-godot-action-latency.md) | 指令响应延迟（附根因结构树）|
| [`2026-07-26-godot-path-step-movement.md`](2026-07-26-godot-path-step-movement.md) | 逐格路径移动实现 |
| [`2026-07-26-godot-view-position-reset.md`](2026-07-26-godot-view-position-reset.md) | 切换界面后位置漂移不重置 |
| [`2026-07-28-map-bounds-pan-zoom-fix.md`](2026-07-28-map-bounds-pan-zoom-fix.md) | 大地图边界越界、佣兵站不显示、缩放拖动异常 |
| [`2026-07-26-lobby-start-ai-seat-fix.md`](2026-07-26-lobby-start-ai-seat-fix.md) | 联机大厅开局与 AI 座位分配 |
| [`2026-07-27-fe8-slot-first-mainline-entry.md`](2026-07-27-fe8-slot-first-mainline-entry.md) | FE8 三槽优先的主线入口 |
| [`2026-07-28-free-mode-victory-suspend.md`](2026-07-28-free-mode-victory-suspend.md) | 自由模式胜利判定与中断存档 |
| [`2026-07-28-unit-portraits-transparent-panel.md`](2026-07-28-unit-portraits-transparent-panel.md) | 单位立绘接入 + 透明立绘区 |
| [`2026-07-28-unit-portrait-prompts.md`](2026-07-28-unit-portrait-prompts.md) | 15 张单位立绘的生成提示词（美术复用）|

---

## 玩法与数值调整

| 文档 | 说明 |
|---|---|
| [`2026-07-23-growth-lane-policy.md`](2026-07-23-growth-lane-policy.md) | 成长「强弱侧」公式调整 |
| [`2026-08-10-dual-track-growth-redesign.md`](2026-08-10-dual-track-growth-redesign.md) | 双轨成长重构维护记录（详细设计见 [`../规范/双轨制单位模型设计方案.md`](../规范/双轨制单位模型设计方案.md)）|
| [`2026-07-14-职业英雄地形行动修正规划.md`](2026-07-14-职业英雄地形行动修正规划.md) | 职业 / 英雄的地形行动成本修正 |
| [`2026-07-14-hero-mainline-debug-analysis.md`](2026-07-14-hero-mainline-debug-analysis.md) | 英雄主线问题的 debug 分析 |
| [`2026-07-18-hero-mercenary-implementation.md`](2026-07-18-hero-mercenary-implementation.md) | 英雄 / 佣兵双轨实施记录 |

---

## 内容与地图

| 文档 | 说明 |
|---|---|
| [`2026-07-23-free-mode-hq-commander-spawn.md`](2026-07-23-free-mode-hq-commander-spawn.md) | 自由模式 HQ 与指挥官开局生成 |
| [`2026-07-28-red-full-roster-map-and-recruit.md`](2026-07-28-red-full-roster-map-and-recruit.md) | 红方全兵种 4P 地图与佣兵站扩容 |
| [`2026-07-28-rules-ai-teammate-hq-targeting.md`](2026-07-28-rules-ai-teammate-hq-targeting.md) | 规则 AI 队友 HQ 目标修复 |
| [`2026-07-22-battle-map-reference-research.md`](2026-07-22-battle-map-reference-research.md) | 战斗地图参考调研归档日志（报告见 [`../路线/参考调研/`](../路线/参考调研/)）|
| [`2026-08-10-yilan-baiyu-heroes.md`](2026-08-10-yilan-baiyu-heroes.md) | 林依澜与白予英雄单位落地 |

---

## 子目录

| 目录 | 说明 |
|---|---|
| [`审计/`](审计/) | 全项目审计快照（`YYYY-MM-DD-<主题>.md`）|
| [`死资产/`](死资产/) | 未使用资源清单 |

---

## 维护规则

- 新增排查/修复记录用 `YYYY-MM-DD-<主题>.md` 命名，**直接放本目录**并在上表登记一行。
- 纯全项目审计报告放进 [`审计/`](审计/) 子目录。
- **待办类文档必须在标题或状态行标明是否仍未完成** —— 避免已修好的旧 TODO 误导后人。
- 详细规范见 [`../规范/文档存放规范.md`](../规范/文档存放规范.md)。
