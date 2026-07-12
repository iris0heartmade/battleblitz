# BattleBlitz 文档

> 当前文档状态(2026-07-13):全部文档已重组为 [架构 / 路线 / 规范 / 参考 / 维护 / superpowers] 六大子目录,中文字段命名,根目录仅保留项目 `README.md`。最新一次完整审计见 [维护/审计/2026-07-13-battleblitz-完整审计.md](维护/审计/2026-07-13-battleblitz-完整审计.md)。

> 项目文档导览。v0.2.0 — 回合制战棋 + LLM 对手 + 主线模式 + 物理/魔法双重战斗体系(均已实装)。

## 子目录导航

| 子目录 | 内容 | 入口 |
|--------|------|------|
| **架构** | 稳定的设计文档(系统架构 + 分阶段开发方案) | [`架构/README.md`](架构/README.md) |
| **路线** | 活的进度文档(路线图 + 项目状态快照 + 交接笔记) | [`路线/README.md`](路线/README.md) |
| **规范** | 功能级 spec 文档(地图生成 / 战斗音频 / 主线布阵) | [`规范/README.md`](规范/README.md) |
| **参考** | 稳定的 how-to 和 API 参考(地图 JSON + LLM agent) | [`参考/README.md`](参考/README.md) |
| **维护** | 运维与质量(死代码扫描 + 审计报告归档) | [`维护/README.md`](维护/README.md) |
| **superpowers** | 历史 superpowers 工作法的设计 spec + plan(已封档) | [`superpowers/specs/`](superpowers/specs/) · [`superpowers/plans/`](superpowers/plans/) |

## 主要文档快速跳

### 新人入口

1. [`../README.md`](../README.md) — 项目 README(启动 / 玩法 / API 速查)
2. [`架构/架构.md`](架构/架构.md) — 看完就能画出整个系统的图
3. [`规范/地图JSON规范.md`](规范/地图生成方案.md) —— 如果你想做一张新地图,看 [`参考/地图JSON规范.md`](参考/地图JSON规范.md)

### 找状态

- [`路线/路线.md`](路线/路线.md) — 当前进度 ✓
- [`路线/项目状态.md`](路线/项目状态.md) — Beta 阶段全景快照
- [`路线/交接笔记.md`](路线/交接笔记.md) — 当前在做的分支
- [`维护/审计/`](维护/审计/) — 历次完整项目审计

### 找设计

- 任何 [规格 / spec / 设计决策](路线/路线.md) 找 [`架构/架构.md`](架构/架构.md) 第五节
- 任何 [功能 spec](路线/路线.md) 找 [`规范/`](规范/) 子目录
- 任何 [历史 design / plan 文档](路线/路线.md) 找 [`superpowers/specs/`](superpowers/specs/)

### 找参考

- [地图 JSON 怎么写](参考/地图JSON规范.md)
- [LLM Agent 协议](参考/llm-agent/README.md)
- [LLM Agent API 规范](参考/llm-agent/api.md)

## 命名约定

- 文件名:**中文 kebab-case**(如 `战斗音频.md`、`2026-07-13-battleblitz-完整审计.md`)
- 子目录:中文短词(架构 / 路线 / 规范 / 参考 / 维护)
- 日期前缀:`YYYY-MM-DD-` 用在审计报告和 superpowers 类文档
- 文档间链接:**相对路径**,不要用绝对路径或 GitHub URL

## 与项目入口的关系

- 项目入口:[`../README.md`](../README.md)
- 文档入口:本文件

两个 README 之间互相引用,新人从任一入口进入都能找到对方。

---

*最后整理:2026-07-13(按 [架构重组方案](维护/审计/2026-07-13-battleblitz-完整审计.md)执行)*
