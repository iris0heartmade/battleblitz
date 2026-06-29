# 设计：敌我分阶段 + 曼哈顿移动 + 中文回合日志

**日期**：2026-06-29
**作者**：架构 review
**状态**：待主人审

## 1. 背景

当前游戏循环是「每人一轮 → end_turn → 下一人」单线程串行。后端在 `end_turn` 末尾检查下一玩家是不是 AI，如果是就 `asyncio.create_task(_run_ai_turn_chain)` 让 AI 在后台跑直到轮到人类。

**三个待改进点**：

1. **阶段感缺失**：人类端不知道「现在是敌方阶段」，AI 在后台跑的时候人类照样能点格子（虽然后端会拒，但前端没视觉提示）。`阶段.md` 列出 P1.1 是 M1 里程碑的前置条件。
2. **移动动画走直线**：`renderBoard` 用 FLIP（First-Last-Invert-Play）做动画，diff 是单个 `translate(dx, dy)`，所以**多格移动是斜着飞过去的**，跟鼠标提示的曼哈顿路径（点阵）不一致。
3. **日志中英混杂**：后端部分用英文（`f"{unit.name} moved {len(path) - 1} tiles"`、`f"{attacker.name} hit {target.name}"`），部分用中文（heal/rally 技能）。前端按 `T1 · {description}` 平铺显示，玩家阅读体验差。

## 2. 设计目标

| 目标 | 验收 |
|------|------|
| 人类玩家清晰感知「我的阶段」/「敌方阶段」 | 阶段 banner 显示当前阶段；敌方阶段时所有格子灰化、点击无效（前端 + 后端双重校验）|
| 单位移动沿曼哈顿路径走格 | 鼠标 hover 时显示点阵（已有），AI 行动时按 1 格/0.3s 步进，单位真的**走**到目标 |
| 回合内日志全中文 + 关键事件分类着色 | 移动/攻击/技能/回合切换 都是中文，颜色按事件类型（move/attack/heal/skill/end_turn）区分 |

## 3. 架构：分阶段

### 3.1 阶段枚举

```python
# models.py 新增
class GamePhase(str, Enum):
    PLAYER = "player"   # 人类玩家操作阶段
    AI = "ai"           # 敌方 AI 操作阶段
    ANIMATING = "animating"  # 留作未来用：本回合所有行动播放中（动画未完）
```

加 `Game.phase: Mapped[str] = mapped_column(String(16), default="player")`。

### 3.2 阶段切换

后端在 `_run_ai_turn_chain` 入口设置 `game.phase = "ai"`，出口（回到人类 / 整轮结束）设置回 `"player"`。每次 `end_turn` 后决定下一个 active player：
- 如果下一个是 **AI** → 切到 `phase="ai"`，启动 `_run_ai_turn_chain`
- 如果下一个是 **人类** → 保持 `phase="player"`，等人类自己 end_turn

### 3.3 后端校验

`/games/{id}/actions` 全部 POST 端点（move/attack/skill/wait）加守卫：
```python
if game.phase != "player":
    raise HTTPException(403, f"当前是敌方阶段，不能操作（phase={game.phase}）")
```

人类在 AI 阶段发起任何 action 都会被拒（前端也要 gray-out 防止用户乱点）。

### 3.4 前端视觉

- 棋盘顶部加一个 phase banner：
  - "你的阶段"（绿）
  - "敌方阶段（AI 行动中…）"（红）
  - "等待其他玩家"（灰，多人时）
- AI 阶段时所有 `.cell` 加 `.phase-disabled` class：
  - 降低 opacity
  - `pointer-events: none`
  - 但单位仍可见（让玩家看到 AI 怎么动）
- AI 每次动作时 banner 实时更新 "敌方阶段 · 步进 1/2"

### 3.5 AI 步进播放

`_run_ai_turn_chain` 已经存在，但目前是连续跑完所有动作。改造为：
```python
async def _run_ai_turn_chain(game_id):
    while True:
        game = await load(game_id)
        if current_player 不是 AI: break
        await asyncio.sleep(AI_STEP_DELAY)  # 0.8-1.2s
        result = await ai_take_one_action(session, game, ai_player)  # 改：单步
        await broadcast_state_update(game_id)
```

**改动点**：`ai_take_turn`（整轮）拆成 `ai_take_one_action`（一步），每步完就 `asyncio.sleep(0.8-1.2s)` 然后让前端刷新。

`ai_take_turn` 留作单测 / 内部调用 wrapper，UI 走 `ai_take_one_action`。

`AI_STEP_DELAY` 加到 `config.py`（默认 0.8s，可调）。

## 4. 架构：曼哈顿移动动画

### 4.1 当前 FLIP 实现

`renderBoard` 拿 oldPositions + newPositions，diff 出 `dx/dy` 一次性 `translate` 动画。**问题**：对单步移动，曼哈顿 = 直线，没差；多步移动就斜着飞。

### 4.2 新动画：path-stepper

把 FLIP 替换为：
```js
function animateUnitAlongPath(unitId, pathCells /* [{x,y}, ...] */) {
  // pathCells[0] 是新位置, pathCells[length-1] 是最终位置
  // 从 pathCells[length-2] 倒着走到 [0]
  const board = document.getElementById("board");
  const cellSize = parseInt(getComputedStyle(board).getPropertyValue("--cell-size"));
  const stepMs = 220;
  const el = document.querySelector(`.unit[data-unit-id="${unitId}"]`);
  if (!el) return;
  for (let i = pathCells.length - 1; i > 0; i--) {
    const from = pathCells[i];     // 旧位置
    const to = pathCells[i - 1];   // 新位置
    const dx = (from.x - to.x) * cellSize;
    const dy = (from.y - to.y) * cellSize;
    // 先跳到 from（无 transition），再过渡到自然位置
    el.style.transition = "none";
    el.style.transform = `translate(${dx}px, ${dy}px)`;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        el.style.transition = `transform ${stepMs}ms linear`;
        el.style.transform = "";
      });
    });
    // 等待 stepMs 后走下一步
    await new Promise(r => setTimeout(r, stepMs));
  }
}
```

**问题**：DOM 实际位置已经是 `to`（renderBoard 把 unit 放到了新格），所以 `el.style.transform` 是相对**新位置**的偏移。我用「先跳到 from（无 transition）→ 过渡到自然位置 = to」实现『从 from 走到 to』的视觉。

### 4.3 数据来源

`pathCells` 从哪来？三种情况：
- **人类 move**：后端返回 `MoveResult` 只有 `to_x/to_y`，没有路径
- **AI move**：后端调 `_ai_move` 时有 path，但没暴露给前端
- **鼠标 hover**：前端 `computeClientPath` 算出来了，AI 阶段重算用得上

**方案**：后端 `MoveResult` 增加 `path: List[List[int]]`（不含起点），人类和 AI 都暴露。前端拿到后走 path-stepper。

对 AI：每次 `ai_take_one_action` 后调 `broadcast_state_update` 时附带 `last_action_path`。前端收到后用 path-stepper 走，再 fetch 最新 state。

### 4.4 单步移动

对 1 格移动，path 只有 1 段，跟现在 FLIP 一样视觉。无需特殊处理。

## 5. 架构：中文回合日志

### 5.1 当前 log 格式

后端在 `actions.py`、`turns.py` 写 description，部分英文部分中文。前端 `renderActionLog` 拼成 `T1 · {description}`。

### 5.2 新设计：服务端中文 + 事件类型

后端所有 log 描述统一改为中文，格式：

| action_type | 中文模板 | 示例 |
|-------------|----------|------|
| `move` | `{unit} 从 ({x0},{y0}) 移动到 ({x1},{y1})，消耗 {cost} MP` | `剑士 从 (3,5) 移动到 (5,7)，消耗 3 MP` |
| `attack` | `{attacker} 对 {target} 发动攻击，造成 {dmg} 点伤害{tail}` | `剑士 对 弓兵 发动攻击，造成 18 点伤害 [击杀]` |
| `heal` | `{healer} 治疗 {target}，恢复 {hp} 点 HP` | `治疗师 治疗 剑士，恢复 15 点 HP` |
| `skill` | `{unit} 发动「{skill_cn}」` | `骑士 发动「连击」` |
| `wait` | `{unit} 原地待命` | `弓手 原地待命` |
| `end_turn` | `{player} 结束回合（使用了 {n} 次行动）` | `玩家A 结束回合（使用了 2 次行动）` |
| `level_up` | `{unit} 升到了 Lv.{lvl}！` | `剑士 升到了 Lv.3！` |
| `eliminated` | `{player} 已被淘汰！` | `玩家B 已被淘汰！` |

**修改点**：
- `actions.py` 的 move/attack/wait/skill 函数
- `turns.py` 的 end_turn 函数
- `game_logic.py` 的 `apply_end_of_turn` (level_up / eliminated)

后端加 helper：
```python
def fmt_move(unit, path, cost): ...
def fmt_attack(attacker, target, dmg, is_kill, counter_dmg): ...
def fmt_skill(unit, skill_cn): ...
```

### 5.3 前端渲染

前端 `renderActionLog` 给每条 log 按 action_type 加 CSS class：
```css
.entry.move     { color: #8fc7ff; }   /* 蓝：移动 */
.entry.attack   { color: #ff8b8b; }   /* 红：攻击 */
.entry.heal     { color: #7ee07e; }   /* 绿：治疗 */
.entry.skill    { color: #ffce5c; }   /* 黄：技能 */
.entry.wait     { color: #aaa; }      /* 灰：待命 */
.entry.end_turn { color: #ddd; font-weight: bold; }
.entry.level_up { color: #ffce5c; font-weight: bold; }
.entry.eliminated { color: #ff8b8b; font-weight: bold; }
```

### 5.4 AI 阶段日志显示

AI 阶段的所有 action log 仍然在 `st.logs` 里，前端照常渲染。AI 完成自己回合后的人类端会自动收到包含所有 AI log 的 state。

## 6. 兼容性 / 迁移

### 6.1 DB migration

`games.phase` 字段是 `NOT NULL`，但现有 DB 没这列。需要：
- 在 `app/main.py` 启动时跑 `ALTER TABLE games ADD COLUMN phase VARCHAR(16) NOT NULL DEFAULT 'player'`（一次性）
- 或用 Alembic（之前文档提过没引入）

**选择**：一次性 ALTER（跟 `map_biome` 那次一样）。在 `database.py` 加 helper。

### 6.2 API 向后兼容

`phase` 是新字段，老客户端不会传。`GameStateOut` schema 加 `phase: str` 字段，老客户端忽略即可（FastAPI 默认忽略多余字段）。

`MoveResult` 加 `path: List[List[int]]`，老前端能容忍。

### 6.3 不破坏的东西

- 现有的 `current_player_index` 不动
- `_run_ai_turn_chain` 还在，只是循环粒度变了
- `ai_take_turn` 函数还在，被 `ai_take_one_action` 内部调用
- 现有的 FLIP 不立即删，path-stepper 走通后切换
- 路径 hover 提示完全不动（已经是对的了）

## 7. 测试

| 测试 | 类型 | 验证 |
|------|------|------|
| `test_phase_transitions` | pytest | end_turn → phase="ai" → AI 跑完 → phase="player" |
| `test_human_action_blocked_in_ai_phase` | pytest | AI 阶段人类 POST move 返回 403 |
| `test_move_path_in_result` | pytest | MoveResult.path 跟实际走的 path 一致 |
| `test_chinese_log_descriptions` | pytest | 所有 log.description 包含中文（`re.search(r"[一-鿿]", desc)`）|
| `test_ai_step_delay` | pytest | mock asyncio.sleep，验证每步都 sleep |
| 前端 E2E | 手动 | 玩一局 4 人，看 phase banner + 移动路径 + 中文日志 |

## 8. 实施顺序

按风险从低到高：
1. **中文日志**（后端 + 前端样式）— 风险低，验证容易
2. **path-stepper 动画**（前端）— 纯前端，无后端耦合
3. **MoveResult 加 path**（后端）— 字段扩展，向后兼容
4. **Game.phase 字段**（DB + models）— 一次性 ALTER
5. **end_turn 切 phase**（后端）— 改动小
6. **ai_take_one_action 拆分**（后端）— 需要 broadcast
7. **/actions 守卫 + 前端 phase banner**（双端）— 最后一起做

每步 commit + 跑 pytest，验完再下一步。
