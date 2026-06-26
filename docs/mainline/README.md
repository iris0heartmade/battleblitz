# 主线模式（战役 / 章节）

> **目的**：让用户能选一条主线 → 沿剧本推进战斗 → 角色成长跨战斗保留
> **状态**：v1 已发布（4 步全 ✅，2026-06-27）

---

## 一句话目标

大厅加"主线模式"入口 → 选一条主线（如 chapter_01）→ 进入剧情对话 → 进入第 1 场战斗 → 战后保留角色成长/装备 → 进入下一段对话 → 第 2 场战斗 → ... → 主线通关。

整套配置靠 JSON 描述，**不改代码即可新增主线 / 新增对话剧本 / 调整战斗场数**。

---

## 三层数据模型

```
┌─────────────────────────────────────────────────────────────────┐
│ 用户存档 (PlayerProfile)         ← 跨主线、跨局                │
│   ├─ user_name                                                       │
│   ├─ unlocked_classes: ["swordsman", "archer", ...]                  │
│   ├─ units: List[UnitInstance]   ← 角色（持久化）                   │
│   └─ progress: {chapter: "01", battle_index: 1, scene_id: "..."}    │
├─────────────────────────────────────────────────────────────────┤
│ 主线定义 (Mainline JSON)         ← 一条战役的配置                 │
│   ├─ id / title / synopsis / cover_art                              │
│   ├─ required_classes                                               │
│   ├─ battles:  [BattleSpec, BattleSpec, ...]                        │
│   ├─ dialogues: { "intro": "stories/ch01/intro.json", ... }         │
│   └─ rewards_on_clear: {gold, unlock_class, exp_per_unit}           │
├─────────────────────────────────────────────────────────────────┤
│ 战斗单场配置 (BattleSpec)       ← 嵌在主线里                     │
│   ├─ map_preset / map_seed                                          │
│   ├─ win_condition: "rout" | "seize" | "defend" | "boss"            │
│   ├─ ally_composition / enemy_composition                           │
│   └─ pre_battle_dialogue / post_battle_dialogue                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4 步实施（已全部完成）

| Step | 主题 | 详情 |
|------|------|------|
| 1 | 数据格式 + 加载器 | [`steps.md#step-1`](steps.md#step-1--数据格式--加载器-) |
| 2 | 存档接入主线进度 | [`steps.md#step-2`](steps.md#step-2--存档接入主线进度-) + [`migrations.md`](migrations.md) |
| 3 | 引擎 + 入口 + 前端 | [`steps.md#step-3`](steps.md#step-3--引擎--入口--前端-) |
| 4 | 内容 + E2E | [`steps.md#step-4`](steps.md#step-4--内容--e2e-) |

实施偏差（D1-D5）见 [`deviations.md`](deviations.md)。

---

## 文件落点

```
game/
├── mainlines/                    ← 主线 JSON 配置
│   └── chapter_01_steel_rebellion.json
├── stories/chapter_01/           ← 对话剧本
│   ├── intro.json
│   ├── battle_01_after.json
│   ├── battle_02_after.json
│   └── victory.json
└── app/
    ├── mainline/                 ← schemas / loader / engine
    ├── routes/mainline.py        ← 5 端点 + dialogue 静态服务
    ├── routes/profile.py         ← 存档端点
    └── progression/              ← Profile / Service
```
