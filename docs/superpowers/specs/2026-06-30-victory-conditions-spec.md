# P2.3 地图任务多样化（4 种胜利模式 + 组队）

**状态**：Draft（等待 owner 进一步 review）
**日期**：2026-06-30
**Owner**：BattleBlitz user
**范围**：新增 4 种胜利条件 + 组队模式 + 必要的地图/UI 改造

---

## 1. 背景

当前游戏只有 **Rout（歼灭战）** 一种胜利模式——`apply_end_of_turn` 检查 `survivors ≤ 1`，最后存活的一方胜。P2.3 要扩成 4 种：

- **Rout（歼灭战）**—— 现有逻辑，所有人共用
- **Seize（占领）**—— 占对方 HQ，归属变更即胜
- **Reach（抵达）**—— 单位到目标格即胜
- **Defend（坚守）**—— 撑到指定回合

同时新增**组队模式**——同 team 玩家算一队。

---

## 2. 胜利模式

### 2.1 Rout（歼灭战）—— **全地图通用**

```
当一方的单位全灭时，则该方失败
哪怕只有一个单位存活也是属于存活状态
场上存活的最后一方就是胜利者
```

- **存活方判定** = 阵营 (`team_id`) 还有 `hp > 0` 的 Unit
- **Rout 即时触发**：某玩家所有单位 `hp <= 0` 时（`cleanup_dead_units` 调用点），该 `team` 立即从 alive 集合移除
- **胜者**：只剩 1 个 `team` 还有存活单位时，剩者为胜
- **平局**：所有 `team` 都没单位 → 平局
- **0 人 / 1 人加入** → 已经是边角情况，Rout 不需要"队"概念也能跑

### 2.2 Seize（占领）—— **全地图通用**（不限于任务地图）

- 玩家初始绑定 1 个 castle 作为 HQ（每个 player 1 个）
- Seize 胜 = 单位完成对方 HQ 的占领（归属变更的瞬间）
- 复用现有 P0.4 占领机制（ClaimSession 2 回合完成归属）
- **不需要为 Seize 加独立计时**——归属完成即胜（这是 owner 在 brainstorm 里定的）
- **组队模式**：A 阵营**所有** HQ 都被占领 = A 阵营输
- **Rout 模式 + 组队**：见 §3
- **占方谁**：占方阵营 + 当前已存活阵营的判定

### 2.3 Reach（抵达）—— **仅任务地图**

- 任务地图 JSON 必填 `reach_tile: {x: int, y: int}`
- 触发点：`move` 端点（行 178-289）完成后 + `apply_end_of_turn` 兜底
- 胜者 = 拥有该格上 Unit（`unit.hp > 0`）的阵营
- 多个阵营同回合到达 → **先到者胜**（按回合先后顺序）

### 2.4 Defend（坚守）—— **仅任务地图**

- 任务地图 JSON 必填 `defend_turns: int`
- 胜者 = 全局第 N 回合结束 (`game.turn_number >= defend_turns`) 时**仍存活**的阵营
- "全局回合" = 全部存活玩家都进行过 1 次回合（"一轮"）= 1 个完整 round
- 提前被全灭的阵营不算胜
- **多阵营同时存活到 N**：按"阵营 ID 字典序"取 1 个为胜（明确规则：先到者 + ID）

---

## 3. 组队模式（team_id）

### 3.1 Player 加 `team_id` 字段

```python
# models.py Player
team_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
```

- 默认 `team_id == color`（保持向后兼容）
- `JoinGameRequest` 加 `team: Optional[str] = None`，`create_game`/`join` 时落地
- `PlayerOut` schema 加 `team_id`
- **如果未指定 team**：自动用 color（红/蓝/黄/绿）作为 team

### 3.2 "方"的定义

| 概念 | 含义 |
|---|---|
| **玩家 (Player)** | 1 个 = 1 个真人/AI 控制方 |
| **阵营 (team)** | 1 个或多个玩家同属 |
| **存活判定粒度** | **team 维度**（不是 player 维度）|
| **HQ 归属** | `tile.owner_id` 仍存 `player.id`（不是 team），但胜者判定按 team 聚合 |

### 3.3 阵营旗 / 颜色

- 主人说"由不同颜色的小三角旗区分"
- 实现：棋盘上每个 Unit 的 **小队旗** = `team_id` 派生的小三角 SVG / emoji（3 种：🔴🔵🟢🟡）
- 加在 unit 元素右上角，不影响现有 player 颜色
- 占对方 HQ 时，HQ tile 上同时显示"占方阵营旗"（小图标）

### 3.4 1V1 默认行为

如果所有人都用 color 当 team（不显式指定 team），1V1 行为**完全不变**——向后兼容。

---

## 4. 数据模型

### 4.1 Game 加列

```python
# models.py Game
win_condition: Mapped[str] = mapped_column(String(16), default="rout")  # rout|seize|reach|defend
reach_tile_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tiles.id"), nullable=True)
defend_turns: Mapped[int] = mapped_column(Integer, default=10)
# (boss_unit_id 占位预留，不实装)
win_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # "rout" | "seize:..."
```

### 4.2 Player 加列

```python
# models.py Player
team_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # 默认 = color
```

### 4.3 迁移

`_run_legacy_migrations` 加：
- `ALTER TABLE games ADD COLUMN win_condition VARCHAR(16) NOT NULL DEFAULT 'rout'`
- `ALTER TABLE games ADD COLUMN reach_tile_id INTEGER`
- `ALTER TABLE games ADD COLUMN defend_turns INTEGER NOT NULL DEFAULT 10`
- `ALTER TABLE games ADD COLUMN win_reason VARCHAR(32)`
- `ALTER TABLE players ADD COLUMN team_id VARCHAR(16)`

### 4.4 兼容

- `tile.owner_id` 仍存 `player.id`（不变）
- 阵营旗 = 从 `team_id` 派生；老游戏 `team_id == color`，渲染用 `player.color`（兼容）

---

## 5. 判定函数

### 5.1 `check_win_condition(session, game) -> Optional[Dict]`

返回 `{winner_team_id: str | None, win_reason: str} | None`：
- `None` = 游戏继续
- `Dict` = 胜负已分，写入 `game.win_reason` + `game.status="finished"`

#### 5.1.1 内部步骤
1. 把存活 Unit 按 `team_id` 聚合（缺省用 `color`）
2. 存活阵营 = `team` 还有 `hp > 0` Unit 的集合
3. Switch on `game.win_condition`:
   - **rout**: 存活阵营 = 1 → 该阵营胜；= 0 → 平局
   - **seize**: 查 `check_pending_claims` 的归属变更——如果本回合有 HQ 的归属变更、变更方 ≠ 旧属方阵营 → 变更方胜
   - **reach**: 查 `tile.occupied_unit_id` 对应的 unit，其 `team_id` 阵营胜
   - **defend**: `game.turn_number >= game.defend_turns` 且存活阵营 = 1 → 胜

### 5.2 触发位置

- `apply_end_of_turn`（每次回合结算时）→ 调 `check_win_condition`
- `move` 端点成功后（Reach 即时触发）→ 调 `check_win_condition`
- `attack` 端点成功后（即时触发 Rout）→ 调 `check_win_condition`
- `check_pending_claims` 完成后（Seize 即时触发）→ 调 `check_win_condition`

### 5.3 团灭 vs Rout

每次 `cleanup_dead_units` 后立刻调 `check_win_condition`：
- 某 team 0 存活单位 → 立即从 alive 移除
- 1 个 team 仍存活 → 该 team 胜
- 0 个 team 存活 → 平局

### 5.4 失败 / 平局返回结构

```json
{
  "winner_team_id": "red" | "blue" | null,  // null = 平局
  "win_reason": "rout" | "seize" | "reach" | "defend" | "draw"
}
```

写进 `game.win_reason`。

---

## 6. preset JSON schema

### 6.1 内置地图（现有 12 张）

**全部默认 Rout**——不动它们。
- Rout 是默认
- Seize 在所有 12 张地图上**自动启用**（不需要 win_condition = "seize"）
- Reach / Defend 必须显式 `win_condition: "reach"` / `"defend"` 才启用

### 6.2 任务地图（新增 4-6 张专门地图）

| 地图 | win_condition | reach_tile / defend_turns |
|---|---|---|
| `reach_heaven_25` | reach | `(2, 2)` 角落 |
| `reach_corner_30` | reach | `(0, 0)` 角 |
| `defend_15_turns_20` | defend | 15 |
| `defend_stronghold_30` | defend | 25 |
| `seize_demo_25` | seize | (不填 reach/defend) |
| `reach_corner_40` | reach | `(0, 0)` 角 |

任务地图生成器：`tools/gen_task_presets.py`

### 6.3 任务地图 JSON schema

```json
{
  "id": "reach_heaven_25",
  "name": "抵达天堂·25×25",
  "description": "派一个单位到地图角",
  "win_condition": "reach",
  "reach_tile": {"x": 2, "y": 2},
  "size": 25,
  "biome": "grass",
  "chars": {...},
  "layout": [...]
}
```

### 6.4 Schema 字段

| 字段 | 类型 | 适用 | 必填 |
|---|---|---|---|
| `win_condition` | str | 所有 | 内置默认 rout；任务必填 reach/defend/seize |
| `reach_tile` | `{x, y}` | reach | reach 必填 |
| `defend_turns` | int | defend | defend 必填（默认 10） |
| `seize_turns_required` | int | seize | 可选（默认复用 CLAIM_TURNS_REQUIRED=2） |

---

## 7. 端点改动

### 7.1 `CreateGameRequest` 加字段

```python
class CreateGameRequest(BaseModel):
    name: str
    map_seed: Optional[int]
    max_players: int
    map_preset: Optional[str]
    map_biome: str
    unit_composition: Optional[str]
    # P2.3:
    win_condition: str = "rout"  # rout | seize | reach | defend
    reach_tile: Optional[Dict] = None  # {x, y}
    defend_turns: int = 10
```

### 7.2 `JoinGameRequest` 加字段

```python
class JoinGameRequest(BaseModel):
    user_name: str
    color: Optional[str]
    team: Optional[str] = None  # 默认 = color
```

### 7.3 `/presets` 端点

`PresetInfo` 加字段：
```python
win_condition: str = "rout"
reach_tile: Optional[Dict] = None
defend_turns: int = 10
```

### 7.4 `/games/{id}/state` 返回

`GameSummaryOut` 加 `win_condition` + `win_reason` 字段。

### 7.5 Editor 改动

`CustomMapSave` 加 win_condition / reach_tile / defend_turns，让玩家在地图编辑器里设计任务地图。

---

## 8. UI 改动

### 8.1 创建游戏表单

- **胜利模式下拉**：Rout（默认）/ Seize（占对方 HQ）/ Reach（仅任务地图）/ Defend（仅任务地图）
- **如果选 Reach**：显示 "目标格 (x, y)" 输入框
- **如果选 Defend**：显示 "目标回合 N" 输入框
- **如果选 Seize 或 Rout**：隐藏输入框

### 8.2 创房/加入 UI

- 新增"阵营"输入框（下拉）：自动列出已加入的阵营 + "新阵营（用我自己的颜色）"选项
- 默认选"新阵营"
- 房间列表显示每位玩家的 `team` 小色标

### 8.3 棋盘渲染

- 每个 Unit 元素右上角加阵营旗（emoji: 🔴🔵🟢🟡）
- 任务地图的 reach_tile 高亮（如黄色脉冲）
- 占对方 HQ 时 HQ tile 上加占方阵营旗

### 8.4 胜利弹窗

- `game-over-modal` 内容根据 `win_reason` 显示不同文案：
  - **Rout**: "🏆 {team} 歼灭获胜！"
  - **Seize**: "🚩 {team} 占领了对方 HQ！"
  - **Reach**: "🎯 {team} 单位抵达目标！"
  - **Defend**: "⏱ {team} 坚守成功！"
  - **Draw**: "⚖️ 全员阵亡 - 平局"

### 8.5 房间列表（小三角旗）

```
🔴 红色  Alice (HP 45)  Bob (HP 30)
🔵 蓝色  Charlie
🟢 绿色  Diana  Eve
```

---

## 9. 测试

### 9.1 服务端
- `test_rout_team_alive_check`: 3 阵营轮流死，剩 1 个胜
- `test_seize_one_hq_changes_winner`: A 站到 B 的 HQ 完成占领 → A 胜
- `test_seize_team_loses_when_all_hqs_lost`: 2V1，A1+A2 的 HQ 都被占 → A 阵营输
- `test_reach_immediate_win_on_move`: Reach 模式，单位 move 到目标格 → game.status="finished"
- `test_defend_turns_complete`: Defend 模式，turn 10 仍存活 → 胜
- `test_default_team_equals_color`: 不指定 team 时默认用 color

### 9.2 HTTP
- `POST /games` 带 `win_condition=reach, reach_tile={x:2,y:2}` → 落库 OK
- `POST /games/{id}/join` 带 `team="red"` → 玩家 team_id 落库
- `GET /games/presets` → 任务地图带 `win_condition` 字段

### 9.3 前端
- 棋盘渲染：阵营旗在 Unit 右上角正确显示
- 胜利弹窗：win_reason 决定文案

---

## 10. 实施分阶段

**Phase 1: 数据 + 迁移 + 简单 Rout 增强**
- 加 Game / Player 列 + 迁移
- `cleanup_dead_units` 后调 `check_win_condition`
- 现有 12 张地图默认 Rout 跑通

**Phase 2: Seize（复用 P0.4 占领）**
- `check_pending_claims` 后调 `check_win_condition` 判 Seize
- 验证：占对方 HQ 完成 → Seize 胜

**Phase 3: Reach 模式**
- 加 `move` 端点即时判定
- 加 2-3 张 reach 任务地图
- 任务地图 preset JSON 加载

**Phase 4: Defend 模式**
- `apply_end_of_turn` 兜底
- 加 2 张 defend 任务地图

**Phase 5: 组队模式**
- Player.team_id + JoinGameRequest.team
- 阵营旗 UI
- 多阵营 Seize 验证

**Phase 6: UI 完成 + 战报**
- 创建表单 win_condition 选择
- 胜利弹窗 win_reason 文案
- 房间列表阵营旗

---

## 11. 不在本次范围（YAGNI）

- Boss 模式（先不做）
- 武器耐久度 P1.1
- 迷雾战争 P2.1
- 指挥官 P2.2
- 多人 / 认证
- 多任务地图的混合胜利条件

---

## 12. Spec 自审

- **占位符**：无，所有字段有具体值
- **内部一致**：§5 check_win_condition 跟 §3 规则一致
- **范围**：单一 feature，6 个 phase 实施
- **歧义**：Defend 模式"全局回合"定义明确（§2.4）；Rout 平局 = "全阵营 0 单位" 明确
- **没动**: Boss 模式独立于本 spec，留作后续
