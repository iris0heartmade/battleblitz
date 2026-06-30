# P0.4 地形增强 + 城堡内布景 + 战斗内经济

**状态**：Draft（等待 owner review）
**日期**：2026-06-30
**Owner**：BattleBlitz user
**扩展**：在现有 5 种地形（平原/森林/山地/河流/城堡）+ 物理/魔法战斗基础上，加 4 种新地形、6 种城堡内布景、主动占领机制、回合内金币系统、单位招募

---

## 1. 背景与目标

### 1.1 现有系统回顾

- 5 种地形：`plain / forest / mountain / river / castle`
- 战斗：物攻/物防 + 魔攻/魔防，按 attack_kind 分流
- 城堡占领：移动到 castle 格即自动归属（`claim_castle_if_present`）
- 无经济系统

### 1.2 目标

1. **4 种新地形**：村落 (village) / 佣兵站 (barracks) / 道路 (road) / 关卡 (gate)
2. **6 种城堡内布景**：地板 (castle_floor) / 墙壁 (castle_wall) / 王座 (castle_throne) / 阶梯 (castle_stairs) / 金库 (castle_vault) / 门扉 (castle_door)
3. **主动占领机制**：单位主动使用"占领"指令 → 2 个连续完整回合后归属变更
4. **回合内经济系统**：每方回合开始结算归属建筑的金币产出，加到 `Player.gold`
5. **单位招募**：佣兵站产出金币 + 提供招募单位端点（花 N 金买一个新单位）

---

## 2. 新地形规则

| 地形 ID | 中文名 | 可走 | 可停 | 阻挡 LOS | MP 消耗 | DEF 加成 | 归属 | 每回合金币 |
|---|---|---|---|---|---|---|---|---|
| `village` | 村落 | ✅ | ✅ | ❌ | 1 | +0 | ✅ 可被占领 | +50（占位）|
| `barracks` | 佣兵站 | ✅ | ✅ | ❌ | 1 | +1 | ✅ 可被占领 | +100（占位）+ 可招募 |
| `road` | 道路 | ✅ | ✅ | ❌ | 0.5 | +0 | ❌ | 0 |
| `gate` | 关卡 | ❌ | ❌ | ✅ | ∞ | — | ❌ | 0 |
| `plain` | 平地 | ✅ | ✅ | ❌ | 1 | 0 | ❌ | 0 |
| `forest` | 森林 | ✅ | ✅ | ✅ | 2 | +2 | ❌ | 0 |
| `mountain` | 山地 | ✅ | ✅ | ✅ | 3 | +3 | ❌ | 0 |
| `river` | 河流 | ✅ | ✅ | ✅ | 3 | 0 | ❌ | 0 |

**MP 减半规则**：道路格按 `0.5` 计算，但 BFS 寻路要避免浮点——用 `cost = 2` 整数表示，"单位剩 MP × 2 可走"的路格视为 1（寻路时若目标是普通格，每移动一格扣 MP=2；如果格是道路，扣 MP=1）。

> 实现细节（见 §6.2）：把 `MOV 0.5` 用整数乘以 2 表达。`unit.mov` 整数不变，`TERRAIN_MOVE_COST_HALF` 取整存「2 倍值」：`road=1, plain=2, forest=4, mountain=6, river=6`。

### 2.1 关卡 (gate) 用途

- 阻挡单位（不可走）
- 不阻挡视线（不会误伤远程射击，类比 FE 的「破墙」逻辑）
- 概念上：「敌方设置的阻拦格」
- 创作者可在地图编辑器放置

---

## 3. 城堡内布景

城堡由 6 种 sub-feature 组成，组成一个完整城堡：

| Feature ID | 中文 | 可走 | 可停 | 作用 |
|---|---|---|---|---|
| `castle_floor` | 地板 | ✅ | ✅ | 城堡内部可走空地 |
| `castle_wall` | 墙壁 | ❌ | ❌ | 城堡边界 / 内部隔断 |
| `castle_throne` | 王座 | ✅ | ✅ | 占领全图所有 throne 即获胜（Sezie 模式）|
| `castle_stairs` | 阶梯 | ✅ | ✅ | 装饰 |
| `castle_vault` | 金库 | ✅ | ✅ | 归属方每回合 +150 金（占位）|
| `castle_door` | 门扉 | ✅ | ✅ | 城堡入口（外部通城堡内部）|

**金库归属**：1 玩家最多 1 个城堡金库——多金库不会叠加。
**王座归属**：与城堡整体归属一致（同一 castle），独立的 owner_id 字段。

### 3.1 城堡布局规则

- 一个城堡由 1 块 tile 标 `castle_door`（入口）+ 周围 8 格内部 + `castle_wall` 隔断 + 1 块 `castle_throne` + 1 块 `castle_vault` + 多块 `castle_floor` + 1 块 `castle_stairs`
- **自动生成**：默认 `_CASTLE_LAYOUTS` 现在生成完整 6-subfeature 城堡
- **手动编辑**：地图编辑器支持每种 sub-feature 单格放置

### 3.2 数据模型

**选择方案 B**：保留 `Tile.terrain = "castle_*"` 子类型，新加 `subtype: String(16) nullable` 列存 "floor / wall / throne / stairs / vault / door"。这样：
- 现有 `Tile.terrain == "castle"` 的代码改为分类匹配
- 老存档兼容：新加列默认 NULL 表示传统整块城堡
- subtype == NULL 视为 "floor"（默认）

### 3.3 Seize 胜利条件（占位）

- **新增胜利条件枚举** `Game.win_condition: String(16) default="rout"`
- `"rout"`（现有）：全灭对方获胜
- `"seize"`（新）：占领所有对方 throne 5 回合即获胜（占位，需要时再细化）

第一版只实现 Rout；Seize 是后续。

---

## 4. 主动占领机制

### 4.1 规则

- 单位**主动**选择"占领"指令（不是站着不动就自动占）
- 占领中单位：不能移动，可以被攻击、可以反击、可以施法（愈合）
- 2 个**完整**回合后完成归属变更
- 期间归属仍是原占有方

### 4.2 时序

| 回合 | 单位 A 操作 | 建筑归属 | 给金币给谁 |
|---|---|---|---|
| N | A 用占领指令，进入"占领中"状态 | 原占有方 (e.g. B) | B |
| N+1 | A 继续占领指令（强制）| 原占有方 (B) | B |
| **N+1 末** | 占领完成 → 触发 `claim_tile(session, tile, player)` | **变为新占有方 A** | — |
| N+2 | A 现在可以自由行动 | A | **A** 开始拿金币 |

**关键不变量**：占领方第 N+2 回合开始才能拿金币。这是延迟 1 回合。

### 4.3 实现

新加端点 `POST /games/{id}/claim`：
1. 校验单位存活、未移动过本回合 (`has_moved = False`？等等，让我看一下)
2. 当前 tile.terrain ∈ {"village", "barracks", "castle_vault"}
3. 当前 unit 在该 tile 上
4. 写 `ClaimSession` 新记录：`{game_id, tile_id, unit_id, started_at, completes_at}`
5. 每回合结束清理超时 `ClaimSession`（超过 1 回合还没完成 = 失败）
6. `apply_end_of_turn` 之前，检查 `ClaimSession.completes_at <= now` → 触发归属变更 + 删 session

### 4.4 中断与失败

- 占领单位**死亡** → session 失败，归属不变
- 占领单位**被驱逐**（被敌方推走、踩走）→ session 失败
- 占领单位**主动移动** → session 失败（取消占领后可以重新开始，但要从 0 数）
- 实现：`unit.has_moved` 标志在占领期间不允许设置；中途任何移动/被推会自动清理 ClaimSession

---

## 5. 战斗内经济系统

### 5.1 金币数据模型

新加列：
```python
# models.py
Player.gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
Game.income_log: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # 可选
```

### 5.2 收入触发点

**位置**：每方回合开始（不是回合结束）—— 在 `apply_end_of_turn` 之后 / 切换到下一玩家之前？

实际位置：`turns.py:end_turn` 当切换到下一玩家时（`current_player_index = next_seat`），调 `_collect_income_for_player(player)`：
1. 收集所有 `tile.owner_id == player.id AND tile.terrain in INCOME_TERRAINS` 的格子
2. 算 `gold += sum(income_table[terrain])`
3. 写 ActionLog：玩家 X 收入 +N 金币（来源：village ×2 + vault ×1 = +250）
4. 返回 `{gold_gain, sources: {village:2, vault:1}}`，前端 toast 显示

### 5.3 收入参数表（占位）

```python
# config.py
INCOME_PER_TURN = {
    "village": 50,
    "barracks": 100,
    "castle_vault": 150,
}
```

### 5.4 招募系统

新加端点 `POST /games/{id}/recruit`：
- 请求：`{player_id, unit_type, x, y}`
- 校验：
  - `player.gold >= RECRUIT_COST[unit_type]`
  - 目标格 = `barracks` 且 `tile.owner_id == player.id`（自己占的佣兵站）
  - 目标格空地（无单位）
- 扣金币，创建一个新单位放在 (x, y)
- 返回新 Unit

**招募费用占位**：
```python
RECRUIT_COST = {
    "swordsman": 200,
    "archer":    250,
    "knight":    400,
    "warlock":   300,
    "healer":    350,
}
```

### 5.5 前端 UI

- **玩家卡片**（大厅 + 游戏内）：在 `user_name` 旁显示 `💰 X` 金币数
- **金币变动 toast**：收入 / 支出时短暂弹出
- **占领进度条**：单位占领中显示在头顶（"占领中（还需 N 回合）"）
- **招募按钮**：在佣兵站格选中单位后弹出，气泡按钮 "招募 单位 (💰 200)"

---

## 6. 实现细节

### 6.1 后端改动文件

| 文件 | 改动 |
|---|---|
| `config.py` | 新增 4+6 = 10 个 TERRAIN 常量；`TERRAIN_MOVE_COST_HALF`、`INCOME_PER_TURN`、`RECRUIT_COST`、`CASTLE_FEATURE_DEF_BONUS`；扩展 `TERRAIN_DEF_BONUS`、`TERRAIN_SPAWN_WEIGHTS`；`MAX_VAULT_PER_PLAYER = 1` |
| `models.py` | Tile 加 `subtype: String(16) nullable`；Player 加 `gold: Integer default=0`；加 `ClaimSession` 新表 `{id, game_id, tile_id, unit_id, started_turn, completes_turn}` |
| `database.py` | `_run_legacy_migrations` 加 3 列：tiles.subtype / players.gold / 不可空表 `claim_sessions` 的 create_all |
| `game_logic.py` | `_layout_to_tiles` 扩展 + `_CASTLE_LAYOUTS` 改 6-feature 自动布局；新函数 `_collect_income_for_player(player, game_state)`；新函数 `check_pending_claims(session, game)`；`claim_castle_if_present` 改为只发事件 + 委托给 `claim_tile` |
| `utils.py` | `terrain_passable` 加 `gate/wall` false；BFS/A* 改用 half-cost 路径计算（道路格 cost=1 vs 其他 cost=2）|
| `routes/actions.py` | 新端点 `POST /claim`、`POST /recruit`；move 路径检查 gate/wall；castle 占用时记录完整 subtype |
| `routes/turns.py` | `end_turn` 后调 `_collect_income_for_player`；`check_pending_claims` 在轮切换时跑 |
| `routes/editor.py` | `_VALID_TERRAINS` 加 4 个新地形 + 6 个城堡 subtype；`_validate_layout` 加 castle_* 字符合法 |
| `schemas.py` | `ClaimRequest`、`RecruitRequest`、`PlayerOut.gold`、`TileOut.subtype` |
| `routes/game.py` | `/units` 含新地形 metadata（display name/move cost/def/gold income）|

### 6.2 整数 MP 减半实现

```python
# config.py
TERRAIN_MOVE_COST = {  # integer cost (real_cost * 2)
    "plain": 2, "forest": 4, "mountain": 6, "river": 6,
    "castle_floor": 2, "castle_throne": 2, "castle_stairs": 2,
    "castle_door": 2, "castle_vault": 2,
    "village": 2, "barracks": 2, "road": 1,
    "gate": 9999, "castle_wall": 9999,
}
```

实际移动时，数据库存 `unit.mp` 是整数（5）。寻路成本用整数表示的"半个 MP"。`unit.mp = 5` 实际可走 `5 * 2 = 10` 个 cost 单位。

### 6.3 claim 端点协议

`POST /games/{id}/claim` body: `{player_id, unit_id}`

返回 `ClaimResult {ok, started_turn, completes_turn, message}`

如果已在占领中（`ClaimSession` 存在），返回 `ok=false, reason="already_claiming"`。

### 6.4 招募端点协议

`POST /games/{id}/recruit` body: `{player_id, unit_type, x, y, color?}`

返回 `RecruitResult {ok, unit: UnitOut, gold_remaining, message}`。

---

## 7. 前端改动

| 文件 | 改动 |
|---|---|
| `style.css` | 2 套主题 × 4 个新 `--t-*` 变量；`.cell.t-village` / `.cell.t-barracks` / `.cell.t-road` / `.cell.t-gate`；`.cell.castle-wall/throne/...`；金币 UI 样式 `.gold-badge`、占领进度环 `.claim-progress` |
| `app.js` | `TILE_VARIANTS` 加 4 项；`TERRAIN_CHAR_TO_NAME` 加 4 项（含 `castle_floor / castle_wall / ...`）；`TERRAIN_REF` 追加 4 行 + 6 行子项；编辑器工具栏加 4 个按钮；玩家卡片加 `💰 ${gold}`；`claim` 动作气泡按钮；`recruit` 动作气泡按钮；`_drawClaims` 画占领进度环 |
| `index.html` | 编辑器加 4 个新地形工具按钮 + 6 个城堡 sub 工具按钮（折叠面板）；玩家卡加 gold slot |
| `assets/tiles/` | 生成 4×2 variants = 8 个新地形 PNG（village / barracks / road / gate）+ 6 sub-features：12 个 PNG。新 village/barracks/road/gate 不分 biome，6 个城堡 sub 占 18 个 PNG（6×3 biomes）。总共 +30 PNG |

---

## 8. 测试

| 测试 | 内容 |
|---|---|
| `test_terrain_passable_new` | gate / wall 不可走；road / village / barracks 可走 |
| `test_claim_2_turn_completion` | 单位 claim 后第 N+1 回合末完成，归属变更 |
| `test_claim_killed_unit_fail` | 占领单位死亡 → session 失败，归属不变 |
| `test_collect_income_village` | village 归属方每回合 +50 |
| `test_recruit_deducts_gold` | recruit swordsman 扣 200 金 |
| `test_recruit_insufficient_gold` | 金币不足返 400 |
| `test_road_mp_half` | unit.mp=5 + road 一路，可走 10 个 road cost 而非 5 |
| `test_separate_layout_compatibility` | 老存档 tile.subtype=NULL 视为 floor |
| `test_existing_46_tests_still_green` | 已有 46 测试不许破 |

---

## 9. 实施分阶段（建议）

**Phase 1：模型 + 迁移 + 新地形常量（无视觉无规则）**
- config.py / models.py / database.py / game_logic.py 增加地形常量但不动 Tile 行
- 验证：老游戏不破 / pytest 全绿

**Phase 2：编辑器 + 视觉**
- CSS 变量、贴图、TERRAIN_REF
- 编辑器白名单 _VALID_TERRAINS
- 验证：编辑器里能放新地形，棋盘能看到

**Phase 3：passability + 寻路**
- utils.py 改寻路
- 验证：gate 不能走、road MP 减半

**Phase 4：Player.gold + apply 收入钩子**
- Player.gold 字段
- turns.py 切换玩家前收金币
- 验证：每个玩家回合开始金币 +50 (1 个 village)

**Phase 5：claim 端点 + ClaimSession**
- POST /claim
- ClaimSession 表 + 每回合结算
- 验证：2 回合后归属变更、金币 1 回合延迟到账

**Phase 6：recruit 端点 + 前端按钮**
- POST /recruit
- 前端气泡按钮
- 验证：花 200 金获得 1 个剑士

---

## 10. 风险与决策点

### 10.1 已确认 ✅

- 城堡内布景**有规则**（门扉+地板+王座+金库）
- 关卡是普通地形（手工放置）
- 道路 MP 减半
- 占领 = 主动指令 + 2 个完整回合
- 延迟 1 回合给金币
- 招募系统实现
- 金币数据：`Player.gold`

### 10.2 待定（先占位，后续可调）

- 收入数值（village/barracks/vault = 50/100/150）
- 招募费用（swordsman=200 等）
- 王座 Seize 模式具体规则（先只 Rout）
- 金库是否 1 玩家最多 1 个
- 王座如何标归属（与 castle 整块 / 还是单独）

### 10.3 风险

- **MP 整数减半**：BFS 寻路可能引入路径成本计算复杂度（用整数 × 2 规避浮点）
- **占领期间被推走**：寻路时该单位不能再作为路径图节点占据（实现时小心）
- **招募位置**：佣兵站邻接格 vs 佣兵站本身格？本 spec 采用：放在佣兵站所在的格（如果空），否则报 400
- **金库归属最大数**：暂定 1 / 玩家，多了忽略（视为 King of the Hill）

---

## 11. 不在本次范围（YAGNI）

- Seize 胜利条件详细规则
- 道路连接路网加成（"连续 3 格道路无视地形"）
- 攻城器械（投石车、云梯）
- 多重税收政策（人头税、战时税）
- 货币单位（金币 / 银币 / 宝石）
- 跨局金币积累（每局重置）

---

## 12. Spec 自审

- **占位符**：§10.2 标了 4 个占位项但主人已说"还没想好"→ 可接受
- **内部一致**：Phase 1-6 的实施顺序与 §6.1 改动清单对应
- **范围**：单一 feature（地形 + 城堡 + 经济），可被一个 implementation plan 覆盖
- **歧义**：金库是否 1 玩家 1 个在 §10.2 留了口子，但 §3 写的是"1 玩家最多 1 个"，前后不一致 → 修正：§3 改为"暂定最多 1 个，§10.2 留口子"