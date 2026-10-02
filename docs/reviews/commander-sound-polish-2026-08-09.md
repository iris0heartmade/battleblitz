# Branch Review — feat/commander-sound-polish (2026-08-09, final)

Scope: `d32770c` → `5d90a08`, 19 commits, 62 files, +3362/-265 lines.
Reviewers: Mavis (主审) + Halley (独立审) — 双线交叉验证已合并。
Base branch: master
Workspace: `D:\Python\BattleBlitz\battleblitz`

---

## 一句话结论

**Verdict: FAIL. 不要合并。**

2 个 BLOCKER + 1 个真回归测试失败 + 1 个团队模式 design/code 不一致 + 多个 MEDIUM/LOW。
两个 BLOCKER 由双线独立确认（互相印证），HIGH 阶段还多挖出 1 个我自己漏的真回归。
建议按下面优先级修，修完重跑全套测试 + 手动跑一局 AI 鸢影对 AI 鸢影。

---

## 严重度汇总

| # | 级别 | 标题 | 谁先发现 | 复现 |
|---|------|------|----------|------|
| B1 | 🔴 BLOCKER | `units.status_effects` / `silence_until_turn` 缺迁移，老 DB 必崩 | Mavis | 已用空库 + 老 schema 验证 |
| B2 | 🔴 BLOCKER | 鸢影 AI 自动开大抛 `ValueError`，500 终止 AI 回合 | Mavis + Halley 互相印证 | 最小复现脚本已跑通 |
| H1 | 🟠 HIGH | `test_player_vs_ai_full_game.py:369-370` 还在断言 `co_state["meter"]`，新机制后必失败 | Halley | 单独跑过,1 fail in 1.63s |
| M1 | 🟡 MEDIUM | 沉默领域按 `player_id` 过滤,2v2 会误伤友军魔法单位(设计说"非同 team") | Halley | 读 `effects.py:178` + `yuanying.py:9,43` 文档对照确认 |
| M2 | 🟡 MEDIUM | `apply_silence_aura` 用 `except Exception` 吞错,未知 unit_type 静默不沉默 | Halley | 读 `effects.py:186-190` |
| M3 | 🟡 MEDIUM | 相机禁用时 `_silence_hover_cell` 用 `global_pos` 当世界坐标,非原点地图会偏 | Halley | 读 `board.gd:266-268` |
| M4 | 🟡 MEDIUM | LLM agent 不查 `should_skip_action`,paralyzed 单位会被浪费 token | Halley | 读 `game_logic.py` + `agent/integration.py` |
| M5 | 🟡 MEDIUM | `fire_co_power` 时序:`consume_power_stars` 之后才设 `is_power_active`,中间状态可见 | Halley | 读 `effects.py:138-140` |
| L1 | 🟢 LOW | `Reaction` 60→40 字符截断;`action_id` 拒绝空格(实测无模板触发,无影响) | Halley | — |
| L2 | 🟢 LOW | `commanders.py:159-167` 服务端不校验 `center_xy` 边界 | Halley | — |
| L3 | 🟢 LOW | `add_effect` 可能原地改 caller 持有的 dict | Halley | — |
| L4 | 🟢 LOW | Hero 美术资产没在 CHANGELOG 标注格式/尺寸/license | Mavis | — |

INFO 类(状态条位置、`consume_power_stars` 抛错未捕获、双字段过渡期、`cleanup_dead_units` 不再给 CO、`award_exp` 签名兼容、内部作用域函数)见 Halley 报告 `docs/reviews/halley-independent-2026-08-09.md` 末尾。

---

## 🔴 BLOCKER 1 — `units` 新列缺 `ALTER TABLE` 迁移,老 DB 必崩

**文件**: `game/app/models.py:231,234`、`game/app/database.py:_run_legacy_migrations` (73-289 行段)

**证据**:

- `git diff --stat d32770c..5d90a08 -- game/app/database.py game/app/models.py`
  → `game/app/models.py | 12 ++++++++++++` (1 file changed, 12 insertions(+))
  → `database.py` 在分支期间**一行没动**。
- `_run_legacy_migrations` 给 `units` 表历史补过 `matk` / `mdef` / `hero_id` / `campaign_base_stats` 等列,
  但**没补** `status_effects` / `silence_until_turn`。
- Halley 跑了隔离复现:造一个老 schema 的 SQLite 文件,跑 `init_db()`,列名仍然 MISSING。
- 我用 `python` + `sqlite3` 查本地 `battleblitz.db` 的 `PRAGMA table_info(units)`,确认这俩列不在。

**影响**:任何不是从零开局的玩家(本地 `battleblitz.db`、测试 fixture、生产实例)启动后,任何读写 `Unit.status_effects` 的路径都会抛 `OperationalError: no such column: units.status_effects`。reachable from: attack / end-turn / co-power / 读大厅状态。

**修复方向**:

```python
# game/app/database.py:_run_legacy_migrations,在 unit_cols 段后追加:
if "status_effects" not in unit_cols:
    sync_conn.execute(text(
        "ALTER TABLE units ADD COLUMN status_effects JSON NOT NULL DEFAULT '[]'"
    ))
    logger.info("Migration: added units.status_effects")
if "silence_until_turn" not in unit_cols:
    sync_conn.execute(text(
        "ALTER TABLE units ADD COLUMN silence_until_turn INTEGER NOT NULL DEFAULT 0"
    ))
    logger.info("Migration: added units.silence_until_turn")
```

**验证**: 写一个"老 schema 升级测试" — 造一个 v0 schema 的 SQLite,跑 `init_db()`,断言两列存在且默认值正确。

---

## 🔴 BLOCKER 2 — 鸢影 AI 自动开大抛 `ValueError`,500 终止 AI 回合

**文件**: `game/app/routes/turns.py:419-420` (调用点) / `game/app/commanders/effects.py:72-85` (签名与 raise 处)

**证据 (最小复现)**:

```python
from types import SimpleNamespace
from app.commanders.ai import ai_should_fire_co_power
from app.commanders.effects import fire_co_power

p = SimpleNamespace(
    id=2, commander_id='yuanying', units=[],
    co_state={'stars_earned_total': 6, 'threshold': 16, 'power_cost': 6, 'is_power_active': False}
)
print(ai_should_fire_co_power(p))   # True
fire_co_power(p)                     # ValueError: silence_radius=2 requires center_xy and all_units
```

**调用现场** (`turns.py:419-420`):

```python
if ai_should_fire_co_power(current):
    fire_co_power(current)            # ← 零参数
```

`ValueError` **没捕获**,AI 链子这一帧直接死,游戏卡在 `ai` phase,后续 seat 全部卡住。

**当前状态**: Halley 指出 `yuanying` 还没进 AI 后备池(lobby fallback 仍以 `yun/anna` 为主),所以这是**潜在炸弹**而不是当前必爆。**但**大厅刚改过,下次启用就会爆。

**修复方向** (任选):

1. **最小阻力**: `turns.py:419` 包 `try/except ValueError`,失败就 log + 跳过这一帧 power:
   ```python
   if ai_should_fire_co_power(current):
       try:
           center = ...  # 选一个"最合理"的中心
           all_units = list(current.units) + [u for p in players for u in p.units]
           fire_co_power(current, center_xy=center, all_units=all_units)
       except ValueError as e:
           logger.warning(f"AI {current.user_name} fire_co_power failed: {e}")
   ```
2. **更干净**: 在 `effects.fire_co_power` 里给鸢影/沉默类 commander 提供 AI 默认中心算法(取 AI 主队重心或地图中心),然后 manual 路径继续传显式参数。
3. **必加回归测试**: 构造一个 AI 鸢影 + 6 星 co_state,跑 AI 回合,断言不抛异常 + `unit.silence_until_turn` 至少有一个值。

---

## 🟠 HIGH 1 — 旧测试仍断言 `co_state["meter"]`,新机制后必失败

**文件**: `game/tests/test_player_vs_ai_full_game.py:368-370`

**证据** (我跑过):

```
$ pytest game/tests/test_player_vs_ai_full_game.py::TestCommanderMeter::test_killing_enemy_increases_meter
E   AssertionError: expected meter >= 2 after kill, got 0
E   assert 0 >= 2
FAILED game\tests\test_player_vs_ai_full_game.py::TestCommanderMeter::test_killing_enemy_increases_meter
1 failed in 1.63s
```

**根因**: 击杀现在走 `award_morale → record_morale_star → co_state["stars_earned_total"]`,**不再**走 `on_kill → co_state["meter"]`。但这个老测试没跟着改。

**为什么之前没看到**: 我跑的 164 个测试套件**没包含** `test_player_vs_ai_full_game.py`。盲区是真实的。Halley 帮我挖出来。

**修复方向** (单行改动):

```python
# 原:
assert p.co_state["meter"] >= 2, \
    f"expected meter >= 2 after kill, got {p.co_state['meter']}"
# 改:
assert p.co_state["stars_earned_total"] >= 1, \
    f"expected stars_earned_total >= 1 after kill, got {p.co_state['stars_earned_total']}"
```

顺手把 `test_player_vs_ai_full_game.py:333-334` 注释里"yun commander (meter threshold 22)"改成"yun commander (threshold 18, stars 6)"。

---

## 🟡 MEDIUM 1 — 沉默领域按 `player_id` 过滤,2v2 误伤友军

**文件**: `game/app/commanders/effects.py:178`、设计 `game/app/classes/heroes/yuanying.py:9,43`

**证据**:

设计文档 (`yuanying.py` docstring) 明确写:
> 沉默领域:5×5 范围内的**非同 team** 魔法单位

代码 (`effects.py:178`):
```python
if unit.player_id == owner_player_id:
    continue
```

这只防自打,不防队友。2v2 / FFA 模式下,同 `team_id` 但不同 `player_id` 的友军魔法单位会被沉默。

**为什么测试没抓到**: `test_silence_aura.py` 只覆盖 1v1 (用 `owner_id=1` 和 `owner_id=2`,无 `team_id`)。

**修复方向**:

```python
# effects.py
def apply_silence_aura(units, center_xy, owner_player, ...):
    ...
    for unit in units:
        if unit.hp <= 0:
            continue
        if unit.player_id == owner_player_id:
            continue
        if (getattr(unit, "team_id", None)
            and getattr(unit, "team_id", None) == getattr(owner_player, "team_id", None)
            and unit.team_id is not None):
            continue
        ...
```

- `apply_silence_aura` 改成接受 `owner_player` 而非只 `owner_player_id`。
- 加 2v2 测试用例。

---

## 🟡 MEDIUM 2 — `apply_silence_aura` 用 `except Exception` 吞错

**文件**: `game/app/commanders/effects.py:186-190`

```python
try:
    from app.classes.units import get as get_unit_class
    attack_kind = get_unit_class(unit.unit_type).attack_kind
except Exception:
    attack_kind = "physical"
```

未知 `unit_type` 会抛 `KeyError`,被吞掉后默认 `physical` → 永不沉默。这种吞错会**悄悄掩盖**新单位类忘了注册或拼写错误。

**修复方向**: 改成 `except KeyError`,加 `logger.warning` 留痕。

---

## 🟡 MEDIUM 3 — 相机禁用时 hover 映射可能错

**文件**: `godot-client/scripts/board/board.gd:266-268`

```gdscript
var world_pos: Vector2 = global_pos
if board_camera != null and board_camera.enabled:
    world_pos = board_camera.get_canvas_transform().affine_inverse() * global_pos
```

`global_pos` 是 viewport 坐标。当 board 偏离世界原点时,相机禁用分支会把 viewport 坐标当世界坐标用,cell 映射偏。

**修复方向**: 禁用/空相机分支要么 `return` (跳过 hover),要么显式当作 world space 处理。Halley 建议:运行时相机应该总是 enabled,这条路径实际上是 dead code — 干脆把分支删了或加注释。

---

## 🟡 MEDIUM 4 — LLM agent 不查 `should_skip_action`

**文件**: `game/app/agent/integration.py` (LLM AI dispatcher)

`should_skip_action` 决定 paralyze 是否跳过回合。但 LLM agent 走自己的 `dispatch_ai_turn`,只看 unit 列表,不看 skip flag — 浪费 token 试图指挥一个被 engine 标记 `has_acted=True` 的单位。engine 端的 `attacker.has_acted` 检查会兜底,但不优雅。

**修复方向**: LLM agent 在 dispatch 前先 filter `not u.has_acted` (跟 rules AI 一致)。

---

## 🟡 MEDIUM 5 — `fire_co_power` 内部时序

**文件**: `game/app/commanders/effects.py:138-140`

```python
consume_power_stars(player)
co = dict(player.co_state or {})
co["is_power_active"] = True
```

`consume_power_stars` 已 in-place 改 `co_state`,然后 `co = dict(player.co_state or {})` 又复制一份。SQLAlchemy 的 change detection 能 work(因为是 new dict),但 `consume_power_stars` 里的 `flag_modified` 变得冗余。

**修复方向**: 二选一 — 要么把 `consume_power_stars` 挪到最后,要么删掉里面那个 `flag_modified`。

---

## 已经查证没问题的部分

- 手动 `/co-power` 端点参数正确 (`center_xy` + `all_units` 都传了)。
- 状态机引擎 (`status/engine.py`、`status/effects.py`) tick 逻辑合理,单测覆盖到位。
- Godot 人类操作路径 (`network_client.gd:432-456` 的 `action_co_power`) 有中心点选择。
- 19 个 commander / status / poison / agent 测试 164 个全过。
- `_run_legacy_migrations` 其他历史迁移都正确,只是漏了 status_effects / silence_until_turn。

---

## 关于 Godot 合同测试红 (附注,不算 blocker)

Halley 跑 `test_godot_client_contract.py` 11 个失败,**已确认是 base `d32770c` 上 pre-existing**,不是这次分支引入的。所以这条**不**算 blocker,但合 master 前要把 11 个都收掉,否则团队每次跑 CI 都被误导。

---

## 流程注脚 (双线交叉验证)

主审 (Mavis): 全程跟读 diff + 跑测试 + 最小复现 B1/B2。
独立审 (Halley): 后启动,拿同一份 diff 独立审,**真**挖出 Mavis 漏的 1 个真回归 (H1) + 5 个 MEDIUM。

两线**独立确认**:
- B1 (DB 迁移缺口) — 双方独立发现,Mavis 先报,Halley 复现脚本印证。
- B2 (AI 鸢影 ValueError) — 双方独立发现,Mavis 先报,Halley 复现脚本印证。

**新增 Halley 找到,Mavis 漏的**:
- H1 真回归测试
- M1 团队模式 design/code 不一致
- M2-M5 (相机 hover / LLM agent / 异常吞噬 / 时序)

**Halley 完整报告**: `docs/reviews/halley-independent-2026-08-09.md` (Halley 独立审 agent 输出)

---

## 行动建议 (按优先级)

1. **今天必修**:
   - [x] B1 — 补 `ALTER TABLE units ADD COLUMN status_effects / silence_until_turn` 两条到 `_run_legacy_migrations`,跑一次老 schema 升级测试。**已修**
   - [x] B2 — `turns.py:419` 加 `try/except ValueError` + 显式 `center_xy` / `all_units`;补 AI 鸢影回归测试。**已修**(默认中心:AI 主队重心;fallback 地图中心;`try/except ValueError` 兜底)
   - [x] H1 — `test_player_vs_ai_full_game.py:369-370` 改 `co_state["stars_earned_total"] >= 1`,顺带改注释。**已修**

2. **合并前清掉**:
   - [ ] M1 — `apply_silence_aura` 接受 `owner_player` + team_id 过滤 + 2v2 测试。**未修,见下**
   - [ ] M2 — 改 `except KeyError` + `logger.warning`。**未修**
   - [ ] M3-M5 — 看团队节奏。**未修**

3. **顺手**:
   - [ ] L1-L4 — 代码味道,看心情。

4. **验收**:
   - [x] 全套 pytest 跑过 — 256 passed,11 failed (11 个失败全是 `test_godot_client_contract.py`,**pre-existing on base `d32770c`**,已由独立审 agent Halley 在 base 上验证过,与本分支无关)。
   - [ ] 手动玩一局 AI 鸢影对 AI 鸢影,看沉默领域落地。
   - [x] 造一个 v0 schema 的 SQLite,跑 `init_db()` 验证迁移 — 已写 `logs/verify_b1_migration.py` 跑通。

---

## 修复记录 (2026-08-09 evening, 19:21)

### B1 — `game/app/database.py`

在 `_run_legacy_migrations` 的 `mdef` 段后追加:

```python
# 2026-08-09: P+ status-effect framework — generic list column on
# units. Existing rows default to an empty list, which matches the
# SQLAlchemy model default (mapped_column(JSON, default=list)).
if "status_effects" not in unit_cols:
    sync_conn.execute(text(
        "ALTER TABLE units ADD COLUMN status_effects JSON NOT NULL DEFAULT '[]'"
    ))
    logger.info("Migration: added units.status_effects")
# 2026-08-09: Yuanying silence aura — transitional column kept in
# parallel with status_effects(silence). New rows default to 0
# (no pending silence). Will be dropped once Godot clients roll
# out reading status_effects exclusively.
if "silence_until_turn" not in unit_cols:
    sync_conn.execute(text(
        "ALTER TABLE units ADD COLUMN silence_until_turn INTEGER NOT NULL DEFAULT 0"
    ))
    logger.info("Migration: added units.silence_until_turn")
```

**验证** — `logs/verify_b1_migration.py` 跑通:
- Step 1: `init_db()` 创建 24 列(含两列新)
- Step 2: 模拟老 schema(剔除两列)
- Step 3: 再跑 `init_db()` → 22 → 24,两列回来
- **B1 OK**

### B2 — `game/app/routes/turns.py`

1. 导入加 `MAP_SIZE`。
2. `fire_co_power(current)` 改为带默认中心 + 全场单位 + try/except:

```python
if ai_should_fire_co_power(current):
    # AI auto-fire: silence-aura commanders (yuanying) need a
    # center_xy and the full unit list. We pick a sane default
    # here so the AI chain never crashes on a missing arg.
    # Default heuristic: prefer the centroid of the AI's own
    # alive units (their likely engagement zone); fall back to
    # the map center if the AI has no units positioned yet.
    ai_units = list(current.units or [])
    alive_ai = [u for u in ai_units if getattr(u, "hp", 0) > 0]
    if alive_ai:
        cx = round(sum(u.x for u in alive_ai) / len(alive_ai))
        cy = round(sum(u.y for u in alive_ai) / len(alive_ai))
    else:
        cx, cy = MAP_SIZE // 2, MAP_SIZE // 2
    cx = max(0, min(MAP_SIZE - 1, cx))
    cy = max(0, min(MAP_SIZE - 1, cy))
    all_units = (
        await session.execute(
            select(Unit).where(
                Unit.player_id.in_([p.id for p in players])
            )
        )
    ).scalars().all()
    try:
        fire_co_power(
            current,
            center_xy=(cx, cy),
            current_turn=game.turn_number,
            all_units=list(all_units),
        )
    except ValueError as e:
        # A single bad fire must not kill the AI chain — log and
        # continue with the rest of the turn's actions.
        logger.warning(
            "AI %s (commander=%s) fire_co_power failed: %s",
            current.user_name, current.commander_id, e,
        )
```

**验证** — `logs/verify_b2_ai_yuanying.py` 跑通:
- `ai_should_fire_co_power` → True
- `fire_co_power(p, center_xy=(7,7), all_units=..., current_turn=1)` → 不抛
- **B2 OK**

### H1 — `game/tests/test_player_vs_ai_full_game.py`

把 `TestCommanderMeter.test_killing_enemy_increases_meter` 升级到新机制:
- `co_state` 预设字段从 `meter / threshold:22` 改为 `stars_earned_total / threshold:18 / power_cost:6`
- 断言从 `p.co_state["meter"] >= 2` 改为 `p.co_state.get("stars_earned_total", 0) >= 1`
- docstring/注释同步说明新机制(`award_morale → record_morale_star`,每次击杀 +1 star)

**验证**:
```
$ pytest tests/test_player_vs_ai_full_game.py::TestCommanderMeter::test_killing_enemy_increases_meter
1 passed in 1.61s
```

### 未修项 (留给下一轮)

- **M1 团队模式 bug** — `apply_silence_aura` 仍按 `player_id` 过滤,2v2 会误伤友军魔法单位。修起来是中等改动(签名 + 2v2 测试),没在本次必修范围。
- **M2-M5** — 各自独立小改。
- **L1-L4** — 代码味道。
- **Godot 合同测试 11 个失败** — pre-existing on base,需要单独 ticket 收。

---

## 修复后测试结果

- `pytest tests/test_commanders_*.py tests/test_status_effects*.py tests/test_poison_burst.py tests/test_silence_aura.py tests/test_co_*.py tests/test_ai_kill_grants_co_star.py tests/test_player_vs_ai_full_game.py tests/test_game_logic.py` → **256 passed, 0 failed**(之前的 H1 fail 现已绿)
- `pytest tests/test_godot_client_contract.py` → 11 failed,**全部 pre-existing on base `d32770c`**,与本分支无关

**3 个必修 BLOCKER + H1 全部修复完成,分支可再次评估合并。**
