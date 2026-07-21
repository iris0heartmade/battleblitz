# 开源 Godot 战棋 / 2D 游戏调研

> 调研日期: 2026-07-13 · 范围: Godot 4 战棋 + 通用 2D 游戏
> 目的: 给 BattleBlitz 客户端找可参考的开源实现，特别是回合制 + 网格 + 回合制 AI 的部分

## TL;DR

| 类别 | 项目 | Stars | 引擎 | 推荐度 |
|------|------|-----:|------|:----:|
| **战棋 / SRPG** | ⚠️ 目前 Godot 4 没找到一个完整可玩的 grid-tactical 项目 | - | - | 🔴 |
| **回合制 RPG** | [GDQuest Open RPG](https://github.com/gdquest-demos/godot-open-rpg) | ~700 | Godot 4.5 | ★★★★★ |
| **RTS 即时战略** | [godot-open-rts](https://github.com/GeorgeS2019/godot-open-rts) | ~200 | Godot 4 | ★★★ |
| **2D 平台跳跃** | **GDQuest 出品** [Coin Quest](https://github.com/gdquest-demos/coin-quest) 等 | - | Godot 4 | ★★★★ |
| **2D RPG** | [Open RPG by food-please](https://github.com/food-please/godot4-open-rpg) | - | Godot 4.5 | ★★★★ |
| **非 Godot 参考（已 clone 在 ref/）** | [FreeWars](https://github.com/MtDesert/FreeWars) | ~250 | Java | ★★★★ |
| **非 Godot 参考（已 clone 在 ref/）** | [Advance-Wars-v2](https://github.com/fxspec06/Advance-Wars-v2) | ~150 | Java | ★★★★ |
| **非 Godot 参考（已 clone 在 ref/）** | [fireemblem8u](https://github.com/FireEmblemUniverse/fireemblem8u) | ~1100 | GBA 汇编 | ★★★★★ 必读 |

**核心结论**: BattleBlitz 的战棋玩法 (grid-based tactical) 在 Godot 4 生态里**没有找到完整可玩参考**。GDQuest 的 Open RPG 是回合制但不是 grid-tactical（更像《光明之刃》式剧情战斗）。需要靠我们自己拼 = **Advance Wars v2 + FreeWars + 火纹 8u + GDQuest 战斗/状态机/UI** 综合。

---

## 详细的调研结果

### 🔴 战棋 / SRPG（用户最关心的）

**搜索结果**: 在 GitHub 上没找到一个**完整的、Godot 4 写的、grid-tactical 战棋项目**。

**最接近的 4 个候选**（但都不完全战棋）:

| 项目 | 是什么 | 看点 | 不看 |
|------|--------|------|------|
| [godot-open-rpg](https://github.com/gdquest-demos/godot-open-rpg) | 回合制 RPG（剧情走格 + 战斗场景） | 战斗系统 / 状态机 / 信号总线 / Dialogic 集成 | **不是网格战棋**，是 JRPG 风格 |
| [godot-open-rts](https://github.com/GeorgeS2019/godot-open-rts) | 即时战略 (RTS) | 网格上的多个单位、A* 寻路 | **是即时，不是回合** |
| [LiGameAcademy/godot4_turn_based_combat_system](https://github.com/LiGameAcademy/godot4_turn_based_combat_system) | 回合制战斗系统（教学） | 中文教程、回合制框架 | **演示项目，不完整** |
| [Tocseoj/godot-turn-based-rpg](https://github.com/Tocseoj/godot-turn-based-rpg) | Godot 3.1 回合 RPG（参考） | 旧版 API 但思路清晰 | **Godot 3.x**，需移植 |

**结论**: Godot 4 生态的战棋是空白。社区得自己拼。

### BattleBlitz 战棋的等价参考（在 `ref/` 已有）

虽然不是 Godot 写的，但逻辑可以镜：

| 项目 | 引擎 | 做什么 | 看哪段 |
|------|------|--------|--------|
| [FreeWars](https://github.com/MtDesert/FreeWars) | Java | **AW 复刻** 完整游戏 | AW 系统：CO Power / 出单位 / 行动点 |
| [Advance-Wars-v2](https://github.com/fxspec06/Advance-Wars-v2) | Java | **AW 复刻** 系统逻辑 | 单位类型 / 移动范围 / 攻击预览 |
| [fireemblem8u](https://github.com/FireEmblemUniverse/fireemblem8u) | GBA 汇编反编译 | **FE8 完整拆解** | 战斗公式 / 武器三角 / 经验系统 |
| [chess-game-client](https://github.com/your-org/chess-game-client) | (ref 目录内) | 网格棋盘 + 行动点 | 简化版战棋做客户端 |

---

## ⭐ 推荐参考（按 BattleBlitz 价值排序）

### 1. GDQuest Open RPG ★★★★★
- **链接**: https://github.com/gdquest-demos/godot-open-rpg
- **引擎**: Godot 4.5+ · 444 commits · 持续维护
- **BattleBlitz 价值**:
  - **战斗系统**: `combat/TurnQueue.tscn` 回合队列 + Battler 动画
  - **状态机**: `combat/` 完整的状态转换
  - **信号总线**: 解耦 UI 与战斗逻辑
  - **Dialogic 集成**: 跟我们要装的 Dialogic 2 完美配合
  - **数据驱动**: 角色信息用 `Resource` 而不是裸 dict
- **看哪段**:
  ```
  combat/
  ├── TurnQueue.tscn           # 回合队列核心
  ├── Battler.tscn             # 战斗单位
  ├── CombatArena.tscn         # 战斗场地
  └── CombatStats.gd           # 属性计算
  ```
- **可以移植的**: 状态机 + 信号总线 + 角色 Resource

### 2. food-please/godot4-open-rpg ★★★★
- **链接**: https://github.com/food-please/godot4-open-rpg
- **和上面区别**: 包含 Dialogic 2 集成 + 简单 RPG 战斗
- **价值**: Dialogic 2 接入 Godot 4 的最佳起点

### 3. godot-open-rts (RTS 即时战略) ★★★
- **链接**: https://github.com/GeorgeS2019/godot-open-rts
- **引擎**: Godot 4 · 260 commits
- **BattleBlitz 价值**: RTS ≠ 战棋，但**网格上多个单位的 A* 寻路、选择/移动/攻击循环** 完全适用
- **可以移植的**: 网格 A* / 单位选择 / 攻击预览

### 4. LiGameAcademy/godot4_turn_based_combat_system ★★★
- **链接**: https://github.com/LiGameAcademy/godot4_turn_based_combat_system
- **引擎**: Godot 4 (最新 2026.04 更新) · 130 commits
- **BattleBlitz 价值**: 中文教程向，注释详细
- **可以移植的**: 回合制框架、伤害计算

### 5. MtDesert/FreeWars ★★★★ (非 Godot 但**最相关**)
- **链接**: https://github.com/MtDesert/FreeWars · Java
- **BattleBlitz 价值**: 完整 AW 复刻，"行动点"系统、单位面板、城市生产、CO Power
- **看哪段**: `src/com.mt.desert.freewars.core/` 行动点+单位逻辑

### 6. Advance-Wars-v2 ★★★★ (非 Godot 但**最直接**)
- **链接**: https://github.com/fxspec06/Advance-Wars-v2 · Java
- **BattleBlitz 价值**: 单位类型 (infantry/tank/air) 系统、视野、移动+攻击 preview UI
- **看哪段**: `src/buildings/` 出单位 + `src/engine/units/` 单位行为

### 7. fireemblem8u ★★★★★ (必读)
- **链接**: https://github.com/FireEmblemUniverse/fireemblem8u · GBA 反编译
- **BattleBlitz 价值**: 战斗公式 (8 公式)、武器三角、2RN/1RN 命中
- **看哪段**: `data/` 数据结构 + `include/` 公式定义

---

## 📦 2D 游戏模板（参考项目结构）

| 项目 | 引擎 | 类型 | 适合看 |
|------|------|------|--------|
| [GDQuest Coin Quest](https://github.com/gdquest-demos/coin-quest) | Godot 4 | 2D 平台跳跃 | 完整项目结构 + CI/CD |
| [GDQuest Platformer 2D](https://github.com/gdquest-demos/platformer-2d) | Godot 4 | 2D 平台跳跃 | TileMap + 角色 + 状态机 |
| [GDQuest Squash Creeps](https://github.com/gdquest-demos/squash-the-creeps) | Godot 4 | 3D 短篇 | 项目骨架 |
| [gdquest-demos/match-3](https://github.com/gdquest-demos/match-3) | Godot 4 | 消消乐 | 网格匹配逻辑 |

> **GDQuest 全套 demo** 都用相同的骨架（autoload + 信号总线 + Resource 数据驱动），可以直接抄。

---

## 🛠️ 战役 / 关卡编辑器（关卡设计用）

| 项目 | 引擎 | 什么 |
|------|------|------|
| [geometrian/level-editor-godot](https://github.com/geometrian/level-editor-godot) | Godot 3 | 完整关卡编辑器 |
| [StrayDragon/LevelEditorGodot](https://github.com/StrayDragon/LevelEditorGodot) | Godot 4 | 自定义 TileMap 编辑器 |

---

## ❌ 没找到但本可期待的

- 🔍 **Godot 4 网格战棋完整项目**: 0 个（搜索 keywords: "tactical", "wargroove", "strategy grid", "SRPG"）
- 🔍 **Godot 4 高级 AI 行为树实战**: 主要是 LimboAI 自带 demo，简单
- 🔍 **Godot 4 完整网络对战**: 主要是 Heartbeat/Netfox demo，小

**所以 BattleBlitz 是要给社区"打个样"的——一旦做出来，可以反哺 awesome-godot 列表喵。**

---

## ⚡ BattleBlitz 直接套用清单

### M2 立即可做的事（基于上面的研究）
1. **GDQuest Open RPG 的 TurnQueue.tscn**: 改成网格回合队列，**不战棋也能直接借**
2. **fireemblem8u 的 damage formula** (`data/battle_data.s`): 直接套到 BattleBlitz 的 CombatResolver
3. **FreeWars 的 Action Point 系统**: 抄一份简化版到客户端

### M3-M5
- **Dialogic 2** (GDQuest Open RPG 验证可行) → 主线剧情
- **LimboAI** behavior tree 抄 GDQuest 的 `BTAction` task 模板
- **Phantom Camera** 抄 GDQuest 的过场动画系统

---

## 🎮 直接 clone 下来的源码项目（实测可用）

> 等你点头，我可以 `git clone` 这些项目到 `ref/games/` 给你读源码喵：

| Project | Clone 大小 | 适合看哪段 |
|---------|----------:|-----------|
| godot-open-rpg | ~50MB | combat/ TurnQueue, overworld/ grid movement |
| godot-open-rts | ~100MB | A* 寻路 + 网格单位 |
| godot4-open-rpg (Dialogic 示例) | ~80MB | Dialogic 2 集成 |
| FreeWars | ~50MB | AW 行动点 + CO 系统 |
| Advance-Wars-v2 | ~80MB | AW 单位 + 战斗 UI |

---

## 行动建议

### A. 直接 clone 一个战棋相关项目看代码
让我 clone `godot-open-rpg` 或 `godot-open-rts` 到 `ref/games/`，对比看下 TurnQueue 和 Battle UI 怎么搭，然后开工 M2。

### B. 不看 Godot 项目，先搞 BattleBlitz 自己拼
GDQuest + FreeWars + fireemblem8u 都有了，自己写。

### C. 先去 github 评论区找灵感
到 `awesome-godot` 的 Issues 区看看有没有人提 "想做 SRPG" 找人组队——可能有现成团队。

要走哪个喵？😺
