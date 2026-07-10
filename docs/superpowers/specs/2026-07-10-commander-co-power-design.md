# Spec & Design: 指挥官 + CO Power 系统 (Commander & CO Power)

**Date:** 2026-07-10
**Status:** Design (待实施)
**Milestone:** P3.0
**Scope:** Hero 系统扩展 + Player/Game 数据扩展 + 主线 schema 扩展 + 新模块 `app/commanders/` + 新路由 + UI HUD 改造 + AI 行为 + 测试覆盖

---

## 1. 背景

P2.6 落地了 Hero 系统（Yun / Anna 等具名英雄，有 stat 覆盖 + 美术 + 技能）。
但**英雄在战斗里只是一个单位**——没有"指挥官"层的全局加成，没有"大招"式的爆发。

需求引入 Advance Wars 风格的 **CO (Commanding Officer) 机制**：

1. **指挥官 = 英雄本身**：已解锁的英雄中可以选一个作"指挥官"。
   指挥官在场上战斗（与上场英雄共存），同时给全队提供光环与 CO Power。
2. **不同指挥官效果不同**：每个英雄有自己独立的 `commander_passive`
   （持续生效的全队光环）和 `commander_power`（meter 充满后发动的大招）。
3. **通过主线解锁**：主线战斗胜利可选解锁某个英雄为可用指挥官。
4. **CO meter 充能**：杀敌得分 + 自家阵亡得分，二者累加到阈值即可发动 CO Power。
5. **大轮次时效**：CO Power 效果持续 1 个大轮次（自己回合 + 所有其他玩家回合），
   玩家下个回合开始时自动失效 + meter 归零。
6. **多玩家共存**：所有玩家都有自己的 commander + meter + 状态，彼此独立。

指挥官池 = 当前战斗 `starting_units` 里**带 hero_id 的单位** ∩ 玩家**已解锁指挥官**列表。

---

## 2. 用户拍板的关键决策

| 决策点 | 选定方案 | 备注 |
|---|---|---|
| 指挥官与英雄的关系 | **指挥官 = 英雄本身** | 复用 P2.6 hero 系统，给 BaseHero 加 4 个字段 |
| 指挥官数据形态 | **Python 类 + 自动发现** | 与现有 hero 一致；不动 JSON 风格 |
| 指挥官效果定义 | **代码层 dataclass + 调度函数** | `CommanderPassive` / `CommanderPower` 两个 frozen dataclass |
| 被动光环作用时机 | **创建战斗时烘焙到 Unit** | 与 `_apply_hero_overrides` 同级，一次性写入 unit.atk/def_/mov/range |
| CO Power 作用时机 | **发动时叠加到 Unit** | 在已含 passive 的 unit 上再叠，power 撤销时还原到 passive 基线 |
| Meter 计分 | **杀敌 + 阵亡 双权重总和** | 单一数值；越惨越能反扑 |
| Meter 持久性 | **跨回合保留，归零仅在下次自己开局** | 1 个大轮次 = 1 cycle |
| CO Power 时效 | **1 个大轮次**（自己回合 + 所有其他玩家回合） | 下次自己回合开始时失效 + meter 归零 |
| 多玩家 power 共存 | **各自独立追踪** | per-player `last_start_turn` 检测，不共享 cycle 计数 |
| 指挥官池 | **当前战斗 starting_units 里的英雄 ∩ 已解锁** | 未解锁或未上场都不能选 |
| 主线 AI 指挥官 | **BattleSpec.enemy_commander 字段** | 地图作者预填 |
| 自由模式 AI 指挥官 | **开房人替 AI 选** | create-game body 携带 `ai_commanders: {seat: hero_id}` |
| 主线玩家指挥官选择时机 | **进入 chapter 时选一次，整章锁定** | 在 lobby 可切换 |
| UI 展示 | **每个玩家一个 CO meter 条 + 头像** | HUD 顶部，多玩家同时可见 |

---

## 3. 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│ mainlines/chapter_01_steel_rebellion.json                       │
│   starting_units: [{hero_id:"yun",...}, {hero_id:"anna",...}]   │
│   battles[].unlocks_commander: "anna"     ← 新增 Optional        │
│   battles[].enemy_commander: "kor"        ← 新增 Optional        │
└────────────┬─────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ app/mainline/schemas.py::BattleSpec                              │
│   unlocks_commander / enemy_commander 字段 + 校验                │
└────────────┬─────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ MainlineEngine.apply_victory()                                   │
│   ├─ 原有: gold / unlocked_classes / xp                          │
│   └─ 🆕 if unlocks_commander: profile.unlocked_commanders.append │
└────────────┬─────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ app/classes/heroes/yun.py                                        │
│   is_commander = True                                            │
│   commander_passive = CommanderPassive(atk_pct=0.10, range_delta=1)│
│   commander_power = CommanderPower(atk_pct=0.30, heal_pct=0.50)  │
│   power_threshold = 22                                           │
└────────────┬─────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ app/commanders/  (新模块)                                        │
│   ├─ passive.py: CommanderPassive dataclass                      │
│   ├─ power.py:   CommanderPower dataclass                        │
│   ├─ state.py:   COState dataclass + 序列化                      │
│   ├─ meter.py:   on_kill/on_death 得分 + 阈值检测                │
│   ├─ effects.py: bake_passive_into_units / fire_co_power /       │
│   │             expire_power / on_player_turn_start              │
│   └─ registry.py: 从 heroes 注册器拉取可作指挥官的英雄            │
└────────────┬─────────────────────────────────────────────────────┘
             │
       ┌─────┼─────────────────────────────────────────┐
       ▼     ▼                                         ▼
┌──────────────┐  ┌────────────────────┐  ┌──────────────────────┐
│ Player 行    │  │ routes/turns.py    │  │ routes/actions.py    │
│ commander_id │  │ on_player_turn_    │  │ attack hook:         │
│ co_state JSON│  │ start() 检测 cycle │  │   meter.on_kill()    │
└──────────────┘  │ 过期 / 归零        │  │   meter.on_death()   │
                  └────────────────────┘  └──────────────────────┘
                                                  │
                                                  ▼
                                          ┌──────────────────────┐
                                          │ routes/commanders.py │
                                          │   POST /co-power     │
                                          │   POST /select-...   │
                                          └──────────────────────┘
```

辅助链路：

```
PlayerProfile.unlocked_commanders: List[str]   ← 跨战斗持久
        ↓
GET /players/me/commanders (debug)
        ↓
HUD 渲染（meter 条 + 头像）
```

---

## 4. 数据模型

### 4.1 `BaseHero` 扩展（4 个新字段）

```python
# game/app/classes/heroes/base.py
class BaseHero(ABC):
    hero_id: str
    # ... 现有字段不动 ...

    # 🆕 指挥官相关（None 默认，绝大多数英雄仍是 None）
    is_commander: bool = False
    commander_passive: Optional["CommanderPassive"] = None
    commander_power: Optional["CommanderPower"] = None
    power_threshold: int = 20          # meter 阈值，按英雄差异化
```

实际定义见 §11。

### 4.2 三个 dataclass（`app/commanders/`）

```python
# app/commanders/passive.py
@dataclass(frozen=True)
class CommanderPassive:
    atk_pct: float = 0.0          # -0.20 ~ +0.50 推荐
    def_pct: float = 0.0
    matk_pct: float = 0.0
    mdef_pct: float = 0.0
    hp_pct: float = 0.0           # 满血上场
    mov_delta: int = 0            # ±1~2
    range_delta: int = 0          # 远程 ±1


# app/commanders/power.py
@dataclass(frozen=True)
class CommanderPower:
    atk_pct: float = 0.0
    def_pct: float = 0.0
    matk_pct: float = 0.0
    mdef_pct: float = 0.0
    heal_pct: float = 0.0         # 全体友军回该比例 max_hp
    extra_mov: int = 0            # 额外移动力 +mp
    range_delta: int = 0


# app/commanders/state.py
@dataclass
class COState:
    commander_id: Optional[str]   # 当前指挥官 hero_id（None = 未选）
    meter: int = 0
    threshold: int = 20
    is_power_active: bool = False
    last_start_turn: int = -1     # 自己上次回合开始时的 game.turn_number
                                  # 用 game.turn_number > last_start_turn
                                  # 判断"是否到了下次自己开局"
```

> `last_start_turn` 是核心：每玩家独立追踪，4 人游戏自然算出
> "下次自己开局"是 3 个 turn_number 之后。具体见 §5.4。

### 4.3 数据库扩展

| 表 / 字段 | 类型 | 备注 |
|---|---|---|
| `Player.commander_id` | `String(64) NULL` | 当前战斗指挥官 |
| `Player.co_state` | `JSON` | `COState.dump()` |
| `PlayerProfile.unlocked_commanders` | `JSON` | `List[str]`（hero_id） |
| `BattleSpec.unlocks_commander` | `Optional[str]` | 胜利本场后解锁 |
| `BattleSpec.enemy_commander` | `Optional[str]` | 主线 AI 用 |
| `BattleConfig.commander` | `Optional[str]` | 自由建房玩家侧指挥官 |
| `BattleConfig.ai_commanders` | `Optional[Dict[seat, hero_id]]` | 自由建房 AI 指挥官 |

### 4.4 GameStateOut 扩展

```python
class PlayerCOStateOut(BaseModel):
    player_id: int
    seat: int
    color: str
    commander_id: Optional[str]
    meter: int
    threshold: int
    is_power_active: bool
    can_fire: bool                # meter >= threshold 且未 active

class GameStateOut(BaseModel):
    # ... 现有字段 ...
    co_states: List[PlayerCOStateOut]   # 🆕 每玩家一条
```

---

## 5. 关键实现细节

### 5.1 被动烘焙（battle 创建时一次性）

```python
# app/commanders/effects.py::bake_passive_into_units

def bake_passive_into_units(player):
    hero = registry.get_hero(player.commander_id)
    p = hero.commander_passive
    if p is None:
        return
    for unit in player.units:
        # 数值叠加（基于 base class 写过的当前值）
        if p.hp_pct:
            unit.max_hp = round(unit.max_hp * (1 + p.hp_pct))
            unit.hp = unit.max_hp
        if p.atk_pct:
            unit.atk = round(unit.atk * (1 + p.atk_pct))
        if p.def_pct:
            unit.def_ = round(unit.def_ * (1 + p.def_pct))
        if p.matk_pct:
            unit.matk = round(unit.matk * (1 + p.matk_pct))
        if p.mdef_pct:
            unit.mdef = round(unit.mdef * (1 + p.mdef_pct))
        if p.mov_delta:
            unit.mov = max(1, unit.mov + p.mov_delta)
        if p.range_delta:
            # attack_range 类级缓存到 unit._base_attack_range
            unit._base_attack_range = unit.attack_range + p.range_delta

        unit._commander_passive = p   # 标记，便于 expire 时识别
```

调用点：
- `routes/game.py::_start_battle_internal` —— 玩家选 commander 后
- `routes/mainline.py::_spawn_battle_for_index` —— 主线 AI 用 enemy_commander

### 5.2 CO Power 发动（叠加在 passive 之上）

```python
def fire_co_power(player, game):
    co = player.co_state
    hero = registry.get_hero(co.commander_id)
    pw = hero.commander_power
    if pw is None:
        raise ValueError("commander has no power")
    if co.is_power_active:
        raise ValueError("power already active")
    if co.meter < co.threshold:
        raise ValueError("meter not full")

    for unit in player.units:
        # 数值叠加（基于已含 passive 的当前值）
        if pw.atk_pct:
            unit.atk = round(unit.atk * (1 + pw.atk_pct))
        if pw.def_pct:
            unit.def_ = round(unit.def_ * (1 + pw.def_pct))
        if pw.matk_pct:
            unit.matk = round(unit.matk * (1 + pw.matk_pct))
        if pw.mdef_pct:
            unit.mdef = round(unit.mdef * (1 + pw.mdef_pct))
        if pw.range_delta:
            unit._base_attack_range = (unit._base_attack_range or unit.attack_range) + pw.range_delta

        unit._commander_power = pw   # 标记，便于 expire 时撤销

    # 全体回血（按当前 max_hp 的 heal_pct）
    if pw.heal_pct:
        for unit in player.units:
            heal = round(unit.max_hp * pw.heal_pct)
            unit.hp = min(unit.max_hp, unit.hp + heal)

    # 额外移动力（加到当前 mp）
    if pw.extra_mov:
        for unit in player.units:
            unit.mp = min(unit.mov, unit.mp + pw.extra_mov)

    co.is_power_active = True
    co.meter = 0
    # 失效交给下次 on_player_turn_start 处理（不需要记 expires_on_turn）

    action_log.append("co_power_fired", {
        "commander_id": co.commander_id,
        "player_id": player.id,
        "turn": game.turn_number,
    })
```

### 5.3 CO Power 失效（per-player 独立）

```python
def expire_power(player):
    """撤销 power 数值叠加，回到 passive 基线（passive 仍生效）"""
    for unit in player.units:
        if hasattr(unit, "_commander_power"):
            _revert_power_only(unit)
            del unit._commander_power

    player.co_state.is_power_active = False
```

`on_player_turn_start` 检测下次自己开局：

```python
def on_player_turn_start(player, game):
    """在每玩家回合正式开始时调用一次（人类 + AI 共用入口）"""
    co = player.co_state
    # last_start_turn != -1 表示这不是首回合
    # turn_number > last_start_turn 表示跨过了至少 1 个 turn（即其他玩家动过了）
    if co.last_start_turn != -1 and game.turn_number > co.last_start_turn:
        # 跨过完整 cycle → 失效 + 归零
        if co.is_power_active:
            expire_power(player)
        co.meter = 0
    co.last_start_turn = game.turn_number
```

> **关键**：4 玩家游戏中 red→blue→green→yellow→red 后 turn_number 增 3，
> `3 > 0` 触发 expire。2 玩家游戏中增 1，同样触发。

调用点：
- `routes/turns.py::end_turn` round-wrap 段（人类玩家的下个玩家开始时调该下个玩家的 hook）
- `routes/turns.py::_run_ai_turn_chain_locked`（AI 玩家回合开始时）

### 5.4 4 玩家场景验证

```
T=1  red T1 starts    red.last_start_turn: -1 → 1   (无 expire)
T=1  red T1 ends      game.turn_number → 2
T=2  blue T1 starts   blue.last_start_turn: -1 → 2  (无 expire)
T=2  blue T1 ends     game.turn_number → 3
T=3  green T1 starts  green.last_start_turn: -1 → 3 (无 expire)
T=3  green T1 ends    game.turn_number → 4
T=4  yellow T1 starts yellow.last_start_turn: -1 → 4 (无 expire)
T=4  yellow T1 ends   game.turn_number → 5
T=5  red T2 starts    red.last_start_turn: 1, turn=5, 5>1 → expire+reset
                                          red.last_start_turn: 1 → 5
T=5  red T2 ends      game.turn_number → 6
T=6  blue T2 starts   blue.last_start_turn: 2, turn=6, 6>2 → expire+reset
                                          blue.last_start_turn: 2 → 6
... 各自独立 ✓
```

### 5.5 Meter 计分（杀敌 + 阵亡）

```python
# app/commanders/meter.py
UNIT_DESTROY_SCORES = {
    "swordsman": 2, "archer": 3, "lancer": 2,
    "knight": 4, "warlock": 4, "healer": 3,
}
DEATH_PENALTY = 2  # 自家单位被打死的固定得分

def on_kill(attacker_player, killed_unit):
    score = UNIT_DESTROY_SCORES.get(killed_unit.unit_type, 2)
    attacker_player.co_state.meter += score
    return score

def on_death(dead_player, dead_unit):
    # 被打死的玩家自家充能（越惨越强）
    dead_player.co_state.meter += DEATH_PENALTY
```

调用点：
- `routes/actions.py::attack` 中 `is_kill = target.hp <= 0` 之后，
  `cleanup_dead_units` 之前（同步 hook）
- 走 `bus.publish(...)` 之后；同步路径必须独立于 bus

### 5.6 指挥官选择（选人时机）

| 模式 | 时机 | API |
|---|---|---|
| **主线** | 进入 chapter 时选，整章锁定 | `POST /mainlines/{id}/select-commander` |
| **主线 lobby 内** | 同一 chapter 可切换 | 同上 API |
| **自由建房** | 开房时随 create-game body | `BattleConfig.commander` / `ai_commanders` |
| **战斗中** | **禁止切换** | `POST /games/{id}/select-commander` 拒绝 |

```python
def select_commander(player, commander_id, unlocked_pool, current_heroes):
    """unlocked_pool ∩ current_heroes 才能选"""
    if commander_id is None:
        player.commander_id = None
        player.co_state = COState(commander_id=None)
        return
    if commander_id not in unlocked_pool:
        raise ValueError("not unlocked")
    if commander_id not in {h.hero_id for h in current_heroes}:
        raise ValueError("not in starting units")
    player.commander_id = commander_id
    threshold = registry.get_hero(commander_id).power_threshold
    player.co_state = COState(
        commander_id=commander_id,
        threshold=threshold,
    )
```

### 5.7 解锁流程（按需，不是每章必解锁）

```python
# app/mainline/engine.py::apply_victory
def apply_victory(self, profile, mainline_id, rewards, unlocks_commander=None):
    profile.gold += rewards.gold
    if rewards.unlock_class:
        if rewards.unlock_class not in profile.unlocked_classes:
            profile.unlocked_classes.append(rewards.unlock_class)
    if unlocks_commander:                                          # 🆕
        if unlocks_commander not in profile.unlocked_commanders:
            profile.unlocked_commanders.append(unlocks_commander)
    # ... 原有 XP / mainline_progress ...
```

Pydantic 校验：
- `BattleSpec.unlocks_commander` 必须在 `heroes` 注册器内 **且** `is_commander=True`
  （解锁没配置的 hero 没意义，玩家永远选不出来）
- `BattleSpec.enemy_commander` 必须在 `heroes` 注册器内 + `is_commander=True`

### 5.8 AI 行为

```python
# AI 玩家创建时：
def setup_ai_player_commander(ai_player, commander_id):
    if commander_id:
        ai_player.commander_id = commander_id
        bake_passive_into_units(ai_player)

# AI 决策回合：
def ai_should_fire_co_power(ai_player):
    co = ai_player.co_state
    if co.commander_id is None or co.is_power_active:
        return False
    return co.meter >= co.threshold   # 满了就发，简单粗暴
```

调用点：`routes/turns.py::_run_ai_turn_chain_locked` 在每次 action 前检查。

### 5.9 新单位中途入场（power 生效期间）

```python
def apply_power_if_active(unit, player):
    """新单位加入 board 时调用，确保 power 期间的加成同步"""
    co = player.co_state
    if co.is_power_active:
        pw = registry.get_hero(co.commander_id).commander_power
        # 同 fire_co_power 的数值叠加段
        ...
```

调用点：未来召唤 / 复活等场景使用。

---

## 6. API 端点清单

| 方法 | 路径 | 作用 | 状态码 |
|---|---|---|---|
| GET | `/players/me/commanders` | 列已解锁指挥官 | 200 |
| POST | `/mainlines/{id}/select-commander` | 主线选指挥官 | 200/422 |
| POST | `/games/{id}/select-commander` | 自由建房选指挥官 | 200/422 |
| POST | `/games/{id}/co-power` | 发动 CO Power | 200/422 |
| GET | `/games/{id}/state` | 扩展 `co_states[]` | 200 |

422 触发条件（POST /co-power）：
- `commander_id is None`
- `is_power_active is True`
- `meter < threshold`
- `commander_power is None`（该英雄没配大招）

---

## 7. UI 集成

### 7.1 HUD 顶部 CO meter 区

```
┌─ HUD 顶部 ─────────────────────────────────────────────────────────┐
│  RED: [Yun ▣] ████████░░ 18/22      ⚡ power 生效中               │
│  BLU: [Kor ▣] ██████░░░░ 12/20                                    │
│  GRN: [??? ▢] ░░░░░░░░░░  0/20      未选指挥官                     │
│  YEL: [Vex ▣] ██████████ 22/22      [发动 Vex CO Power] 🔥        │
└───────────────────────────────────────────────────────────────────┘
```

- 每人一条横条 + 指挥官头像（无选 = 默认灰色头像 + 「未选」字样）
- meter 满 → 该玩家「发动」按钮亮起（自己可点；AI 自动）
- power 生效中 → 头像外加发光描边 + 「⚡」标 + meter 显示 "ACTIVE"

### 7.2 指挥官池下拉框（选择面板）

- 主线 lobby：在 chapter header 显示当前指挥官，点击切换
- 自由建房 create-game：在表单加 player_commander 下拉 + ai_commanders 按 seat 设置
- 只列出 `is_commander=True` ∩ `已解锁` ∩ `当前 starting_units 含该 hero_id` 的英雄

### 7.3 文件改动

| 文件 | 改动 |
|---|---|
| `game/app/web/index.html` | HUD CO meter 区 + 选择面板 markup |
| `game/app/web/app.js` | `renderCOMeters(state)` + 选择器逻辑 + 按钮点击 → POST |
| `game/app/web/style.css` | meter 条样式 + ⚡ 描边动画 |

---

## 8. 文件变更清单

| 文件 | 改动类型 |
|---|---|
| `game/app/commanders/__init__.py` | 新建 — 模块入口 |
| `game/app/commanders/passive.py` | 新建 — `CommanderPassive` dataclass |
| `game/app/commanders/power.py` | 新建 — `CommanderPower` dataclass |
| `game/app/commanders/state.py` | 新建 — `COState` dataclass + 序列化 |
| `game/app/commanders/meter.py` | 新建 — 计分 + 阈值检测 |
| `game/app/commanders/effects.py` | 新建 — bake / fire / expire / on_turn_start |
| `game/app/commanders/registry.py` | 新建 — 从 heroes 拉指挥官视图 |
| `game/app/classes/heroes/base.py` | 加 `is_commander / commander_passive / commander_power / power_threshold` |
| `game/app/classes/heroes/yun.py` | 填真实 commander 数据 |
| `game/app/classes/heroes/anna.py` | 填真实 commander 数据 |
| `game/app/routes/commanders.py` | 新建 — 选人 / 发动 / 查询 API |
| `game/app/routes/game.py` | `_start_battle_internal` 加 bake_passive + 战斗禁止切换 commander |
| `game/app/routes/mainline.py` | `_spawn_battle_for_index` 烘焙 AI 被动 + 提供选人 UI 数据 |
| `game/app/routes/turns.py` | `end_turn` / `_run_ai_turn_chain_locked` 加 `on_player_turn_start` hook + AI fire 决策 |
| `game/app/routes/actions.py` | `attack` 中插入 `meter.on_kill / on_death` |
| `game/app/main.py` | `include_router(commanders_routes.router)` |
| `game/app/models.py` | `Player.commander_id / co_state` + `PlayerProfile.unlocked_commanders` |
| `game/app/database.py` | 自动迁移加列 |
| `game/app/schemas.py` | `BattleConfig.commander / ai_commanders` + `PlayerCOStateOut / GameStateOut.co_states` |
| `game/app/mainline/schemas.py` | `BattleSpec.unlocks_commander / enemy_commander` + 校验器 |
| `game/app/mainline/engine.py` | `apply_victory` 写 `unlocked_commanders` |
| `game/app/web/index.html` | HUD CO meter + 选择面板 |
| `game/app/web/app.js` | 渲染 + 选人 + 发动 |
| `game/app/web/style.css` | meter 样式 |
| `game/mainlines/chapter_01_steel_rebellion.json` | `unlocks_commander` 填 "anna"，`enemy_commander` 填占位 |
| `game/tests/test_commanders_passive.py` | 新建 — passive 烘焙测试 |
| `game/tests/test_commanders_power.py` | 新建 — fire / expire / 数值叠加测试 |
| `game/tests/test_commanders_meter.py` | 新建 — kill / death 计分测试 |
| `game/tests/test_commanders_lifecycle.py` | 新建 — 4 玩家独立 expire 测试 |
| `game/tests/test_commanders_unlock.py` | 新建 — 主线胜利解锁测试 |
| `game/tests/test_commanders_api.py` | 新建 — 选人 / 发动 API 测试 |
| `game/tests/test_commanders_snapshots.py` | 新建 — yun / anna 数值快照 |

---

## 9. 边界情况

| # | 场景 | 期望行为 |
|---|---|---|
| 1 | 指挥官单位自己被打死 | power 仍生效（aura 不依赖存活）；过期逻辑正常 |
| 2 | power 生效中指挥官单位被复活 | 单位带 power 加成复活 |
| 3 | power 生效中新单位加入战场 | 该新单位继承 power 加成（重跑 `apply_power_if_active`） |
| 4 | commander_id=None 时点发动 | 422 |
| 5 | meter 未满时点发动 | 422 |
| 6 | 已经在 power 中点发动 | 422 |
| 7 | 已解锁指挥官但本章没上场 | UI 不可选 |
| 8 | starting_units 含未解锁英雄作指挥官候选 | UI 标灰 |
| 9 | 一边没选指挥官 | 该玩家无被动无 power；meter 条「未选」 |
| 10 | 双方都没选指挥官 | meter 全程不动 |
| 11 | 战斗胜利时 power 仍 active | 战斗结束清理状态 |
| 12 | 战斗中切换 commander | 禁止（API 拒绝） |
| 13 | 主线 lobby 切指挥官后再开战 | 新 commander_id 在创建战斗时烘焙 |
| 14 | 4 人混战：3 人发动 1 人不发动 | 各自独立 expire |
| 15 | 同一 cycle 内 meter 满又回满 | 不会发生（发动后立刻清零） |
| 16 | AI 玩家发动 CO Power | 走 AI 决策路径自动 fire |
| 17 | 玩家投降 / 退出 | co_state 持久化不影响其他玩家 |
| 18 | chapter 重复胜利 | unlocked_commanders 去重 |
| 19 | `unlocks_commander` 字段缺失 | 不解锁（向后兼容） |
| 20 | 自由建房没指定 commander | commander_id=None |
| 21 | AI commander_id 指向未注册的 hero | 启动 WARNING + 当作 None |
| 22 | meter 在 on_kill 时已经 active | 已 active 时 meter 累计到下个 cycle 才生效 |

---

## 10. 测试矩阵

| 层 | 测试 | 关键断言 |
|---|---|---|
| **Unit · meter** | `test_on_kill_scores_by_class` | swordsman +2, archer +3 |
| | `test_on_death_scores_flat` | 任何单位被打死 +2 |
| | `test_meter_accumulates_mixed_events` | 混合事件累加正确 |
| **Unit · effects** | `test_bake_passive_doubles_yun_atk` | yun 烘焙后 atk 正确 |
| | `test_bake_passive_handles_negative_pct` | -10% atk 正确下调 |
| | `test_fire_co_power_stacks_on_passive` | passive 烘焙后 fire 再叠 |
| | `test_expire_power_reverts_only_power_layer` | expire 后回到 passive 基线 |
| **Unit · lifecycle** | `test_on_player_turn_start_expires_power` | last_start_turn 检测正确 |
| | `test_meter_resets_on_new_cycle_even_without_fire` | 不发也归零 |
| | `test_multi_player_independent_expiry` | 4 人各自独立 expire |
| **Integration** | `test_chapter_clear_unlocks_commander` | unlocks_commander 字段生效 |
| | `test_unlocks_commanders_dedup` | 重复解锁不报错 |
| | `test_select_commander_in_mainline_lobby` | API 校验 + 持久化 |
| | `test_create_game_with_player_commander` | 自由建房 API 接受 commander |
| | `test_ai_player_uses_enemy_commander_in_mainline` | 主线 AI 用 BattleSpec.enemy_commander |
| | `test_fire_co_power_returns_422_when_meter_low` | API 边界 |
| | `test_fire_co_power_returns_422_when_active` | API 边界 |
| | `test_commander_dies_power_still_active` | 边界 1 |
| | `test_new_unit_inherits_active_power` | 边界 3 |
| | `test_select_commander_in_battle_blocked` | 边界 12 |
| **Snapshot** | `test_yun_commander_values_snapshot` | 固定数值防漂移 |
| | `test_anna_commander_values_snapshot` | 同上 |

---

## 11. Yun / Anna 指挥官数值草案

> 这是占位值，实际数值由后续平衡 PR 调整。Snapshot 测试会用这些值。

```python
# game/app/classes/heroes/yun.py
class YunHero(BaseHero):
    hero_id = "yun"
    is_commander = True
    commander_passive = CommanderPassive(
        atk_pct=0.10,        # 全队 +10% atk
        range_delta=1,       # 远程 +1 格
    )
    commander_power = CommanderPower(
        atk_pct=0.30,        # 全队 +30% atk
        heal_pct=0.50,       # 全体回 50% max_hp
    )
    power_threshold = 22

# game/app/classes/heroes/anna.py
class AnnaHero(BaseHero):
    hero_id = "anna"
    is_commander = True
    commander_passive = CommanderPassive(
        def_pct=0.15,        # 全队 +15% def
        mdef_pct=0.10,       # 全队 +10% mdef
    )
    commander_power = CommanderPower(
        def_pct=0.30,
        mdef_pct=0.30,
        heal_pct=0.80,       # 全体回 80% max_hp（强治疗）
    )
    power_threshold = 18
```

数值调整原则：
- passive 偏平衡（-20% ~ +20%）
- power 偏爆发（同一字段可 ±50%）
- threshold 视 commander 强度调整：弱 commander 18，强 commander 22

---

## 12. 给后续维护者的清单

- 改 `BaseHero` 指挥官字段 → 同时改 `HeroProfile` + `compile()` + registry 拉取视图
- 加新 commander 字段（如 `crit_rate`）→ 4 处：`passive.py` dataclass、`power.py` dataclass、`effects.py` 烘焙段、`effects.py` expire 段（保存 baseline）
- 改 meter 计分权重 → `meter.py::UNIT_DESTROY_SCORES` + snapshot 测试同步
- 改 threshold 默认值 → `BaseHero.power_threshold` 默认值同步
- 加新 API（取消 CO Power 等）→ 模仿 `commanders.py::fire_co_power` 写法
- 调数值时 → 同步改 §11 草案 + snapshot 测试

---

## 13. 已知限制 / 待办（明确不做）

- ❌ **同 chapter 内战斗中切换 commander** — 锁定到 chapter 开始
- ❌ **AI 智慧点判断** — 满了就发，简单粗暴（先跑通）
- ❌ **多 cue / 多阶段 CO Power** — 一个指挥官一个 power
- ❌ **指挥官专属剧情对话** — 复用英雄现有 dialogue_name
- ❌ **CO Power 音效** — 用通用 activate 音效，后续单独 PR
- ❌ **CO meter 跨 chapter 累积** — 每次战斗重置
- ❌ **power 期间召唤 / 复活以外的复杂单位变换** — 仅 apply_power_if_active 兜底

---

## 14. 端到端验证（计划）

### 14.1 单元 + 集成

```bash
$ cd game
$ PYTHONPATH= python -m pytest \
    tests/test_commanders_*.py \
    tests/test_integration_smoke.py \
    -q --no-header
```
预期：所有 commander 相关测试通过；无回归。

### 14.2 HTTP 端到端

```bash
# 1. 启动服务器
cd game && uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. 启动主线 chapter_01（带 unlocks_commander="anna"）
POST /mainlines/chapter_01_steel_rebellion/start
→ game_id=1

# 3. 选 yun 作指挥官
POST /games/1/select-commander  body={"commander_id": "yun"}
→ 200, player.co_state.commander_id = "yun"
→ /games/1/state 中 yun 单位的 atk 比 hero override 后再 +10%

# 4. 杀敌累积 meter
... 战斗 ...

# 5. meter 满后发动 CO Power
POST /games/1/co-power
→ 200, is_power_active=true, meter=0
→ /games/1/state 中所有友方单位 atk 再 +30%, hp 已部分恢复

# 6. 跨过 1 cycle 后自动失效
... 玩家结束回合 + 对手回合 ...
→ 玩家下次回合开始：power 自动撤销，回到 passive 基线，meter=0
```

### 14.3 HUD 渲染

浏览器打开 `http://localhost:8000/ui/` → HUD 顶部看到 4 条 CO meter 条 +
指挥官头像。点击「发动」按钮 → 单位数值变化 + meter 清零。

---

## 15. Next steps

> 按优先级从高到低排，都是 **单文件 / 双文件**的小改动。

1. **创建 `app/commanders/` 骨架** — 三个 dataclass + 空函数占位
2. **扩展 `BaseHero`** — 4 字段 + 编译逻辑
3. **改 chapter_01 JSON** — 加 `unlocks_commander: "anna"` + `enemy_commander` 占位
4. **API 端点** — 选人 + 发动
5. **烘焙 + 发动 + 失效** — effects.py 三函数
6. **turns.py + actions.py 集成** — on_player_turn_start hook + meter.on_kill
7. **HUD 渲染** — 前端 CO meter 条
8. **snapshot 测试** — yun / anna 数值固定
9. **平衡调整** — 跑几次测试战斗，调数值（占位草案先跑通再调）

---

## 16. 用户确认要点（设计已锁定）

- ✅ 指挥官 = 英雄本身（互斥取消）
- ✅ 被动烘焙进 Unit，power 叠加在 passive 之上
- ✅ meter 双权重总和 + 跨回合 + 下次自己开局归零
- ✅ CO Power 持续 1 个大轮次
- ✅ 多玩家 power 各自独立追踪
- ✅ 主线 enemy_commander + 自由建房 host 选 AI
- ✅ UI 全玩家 meter 条 + 头像
- ✅ 解锁按需（BattleSpec.unlocks_commander 字段）
- ✅ 20 个边界情况已列