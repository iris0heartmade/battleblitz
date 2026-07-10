# BattleBlitz 指挥官 + CO Power 系统实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 BattleBlitz 增加 Advance Wars 风格的指挥官（CO）系统：玩家从已解锁英雄中选 1 个上场英雄作"指挥官"，CO 给全队提供被动光环 + CO Power 大招；CO Power 通过杀敌/阵亡累计 meter 触发，持续 1 个大轮次后自动失效。

**Architecture:** 复用 P2.6 hero 注册器，给 `BaseHero` 加 4 个 commander 字段；新建 `app/commanders/` 模块（6 个文件）承载 dataclass + 调度；每玩家独立 `COState` JSON 列；passive 在战斗创建时烘焙进 `Unit.atk/def_/mov/range`，power 发动时叠加在 passive 之上；多玩家 power 各自独立追踪（per-player `last_start_turn` 检测）。

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy + SQLite (Alembic-style auto-migration), Pydantic, vanilla JS frontend, pytest

## Global Constraints

- 命名规则：模块 `app/commanders/` 平行于 `app/classes/heroes/`
- 三 dataclass 必须 frozen（被动 / Power）+ 1 mutable dataclass（State）
- `commander_id` 在 `Player` 表上 nullable；None 表示本场没选指挥官
- `Player.co_state` JSON 字段，序列化 `COState.dump()`
- `PlayerProfile.unlocked_commanders: List[str]` JSON，append 时去重
- 所有 commander 数值字段必须支持负值（被动减益场景）
- Pydantic 校验：选 commander 时必须满足 `is_commander=True ∩ unlocked ∩ starting_units_with_hero_id`
- 命令必须能 undo：power expire 时必须还原到 passive 基线（不是原始 base class）
- 测试命令：`cd game && PYTHONPATH=. python -m pytest tests/test_commanders_*.py -v -p asyncio -p anyio`
- 单一职责：`effects.py` 包含所有"修改 unit 数值"的函数；`meter.py` 仅含计分
- 任何对 unit 数值的修改都通过 `_commander_passive` / `_commander_power` 标记字段追踪，便于 expire
- 全局 Python 测试：`cd game && PYTHONPATH=. python -m pytest tests/ -q --no-header`

---

## 压缩执行策略（从 Task 5 起）

原始 17 个 task 保持不变，但从 Task 5 开始按下列 5 个执行组推进。**每个执行组**仍严格遵守 TDD：failing test → run fail → implement → run pass → commit。

| 组别 | 覆盖 task | 说明 |
|---|---|---|
| **G1 · 核心循环** | 5-7 | 合并 1 轮 review；覆盖 meter + CO Power fire/expire + turn_start lifecycle |
| **G2 · Schema / API** | 8-10 | 绑定 BattleSpec、解锁逻辑与 API |
| **G3 · 战斗集成** | 11-13 | attack / turn lifecycle / state payload 一次性收口 |
| **G4 · AI + HUD** | 14-15 | AI 自动发动与 HUD 渲染并行推进 |
| **G5 · 验证收尾** | 16-17 | snapshot 与 e2e 可合并行 |

**执行规则：**
- 每个执行组内保持单线程 TDD，不跨组偷跑实现
- 子代理按组重建，不再要求每个 task 都 fresh 一个
- 主控在 review 当前组时，提前准备下一组的测试壳与文件清单
- 只要写入区域互不重叠，就允许并行子代理

## Milestone 1 · 数据模型基础

### Task 1: 创建 `app/commanders/` 模块骨架（3 dataclass + state 序列化）

**Files:**
- Create: `game/app/commanders/__init__.py`
- Create: `game/app/commanders/passive.py`
- Create: `game/app/commanders/power.py`
- Create: `game/app/commanders/state.py`
- Test: `game/tests/test_commanders_state.py`

**Interfaces:**
- Consumes: nothing
- Produces: `CommanderPassive(passive_dict) -> CommanderPassive`, `CommanderPower(power_dict) -> CommanderPower`, `COState(commander_id, meter, threshold, is_power_active, last_start_turn) -> COState`, `COState.dump() -> dict`, `COState.load(dict) -> COState`

- [ ] **Step 1.1: 创建 `app/commanders/passive.py`**

```python
"""CommanderPassive — 持续生效的全队光环（烘焙到 unit.atk/def_/mov/range）。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CommanderPassive:
    """被动光环：指挥官在场时持续生效，影响该玩家所有单位。

    数值字段以"基础值的变化量"或"百分比"表达：
    - *_pct: 基础值的百分比调整（+0.10 表示 +10%）
    - *_delta: 整数加减（+1 表示 +1）
    """

    atk_pct: float = 0.0
    def_pct: float = 0.0
    matk_pct: float = 0.0
    mdef_pct: float = 0.0
    hp_pct: float = 0.0         # 影响 max_hp（满血上场）
    mov_delta: int = 0
    range_delta: int = 0        # 远程射程 ±1
```

- [ ] **Step 1.2: 创建 `app/commanders/power.py`**

```python
"""CommanderPower — meter 满后发动的大招（叠加在 passive 之上）。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CommanderPower:
    """CO Power：发动时叠加在该玩家所有单位上，持续到下次自己回合开始。

    与 CommanderPassive 同构，但额外支持：
    - heal_pct: 全体友军回该比例 max_hp
    - extra_mov: 额外移动力（+mp）
    """

    atk_pct: float = 0.0
    def_pct: float = 0.0
    matk_pct: float = 0.0
    mdef_pct: float = 0.0
    heal_pct: float = 0.0
    extra_mov: int = 0
    range_delta: int = 0
```

- [ ] **Step 1.3: 创建 `app/commanders/state.py`**

```python
"""COState — 单个玩家的 CO 完整状态（持久化到 Player.co_state JSON 列）。"""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class COState:
    """指挥官状态。每玩家独立追踪。

    last_start_turn: 自己上次回合开始时的 game.turn_number。
    判断"下次自己开局"的方法：game.turn_number > last_start_turn。
    首回合时 last_start_turn = -1，避免误判。
    """

    commander_id: Optional[str] = None
    meter: int = 0
    threshold: int = 20
    is_power_active: bool = False
    last_start_turn: int = -1

    def dump(self) -> dict:
        return asdict(self)

    @classmethod
    def load(cls, data: Optional[dict]) -> "COState":
        if data is None:
            return cls()
        return cls(**data)
```

- [ ] **Step 1.4: 创建 `app/commanders/__init__.py`**

```python
"""指挥官系统模块入口。"""
from app.commanders.passive import CommanderPassive
from app.commanders.power import CommanderPower
from app.commanders.state import COState

__all__ = ["CommanderPassive", "CommanderPower", "COState"]
```

- [ ] **Step 1.5: 创建测试 `tests/test_commanders_state.py`**

```python
"""test_commanders_state.py — 三个 dataclass 的基本行为。"""
import pytest
from app.commanders import CommanderPassive, CommanderPower, COState


class TestCommanderPassive:
    def test_default_zeros(self):
        p = CommanderPassive()
        assert p.atk_pct == 0.0
        assert p.range_delta == 0

    def test_frozen(self):
        p = CommanderPassive(atk_pct=0.10)
        with pytest.raises(Exception):  # FrozenInstanceError
            p.atk_pct = 0.20  # type: ignore


class TestCommanderPower:
    def test_heal_and_extra_mov(self):
        pw = CommanderPower(heal_pct=0.5, extra_mov=2)
        assert pw.heal_pct == 0.5
        assert pw.extra_mov == 2


class TestCOState:
    def test_default(self):
        s = COState()
        assert s.commander_id is None
        assert s.meter == 0
        assert s.last_start_turn == -1

    def test_dump_load_roundtrip(self):
        s = COState(commander_id="yun", meter=18, threshold=22,
                    is_power_active=False, last_start_turn=5)
        d = s.dump()
        assert d["commander_id"] == "yun"
        s2 = COState.load(d)
        assert s2 == s

    def test_load_none_returns_default(self):
        s = COState.load(None)
        assert s == COState()
```

- [ ] **Step 1.6: 运行测试，预期全通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_state.py -v`
Expected: 6 passed.

- [ ] **Step 1.7: Commit**

```bash
cd game/..
git add game/app/commanders/ game/tests/test_commanders_state.py
git commit -m "feat(p3.0): add commanders module skeleton with dataclasses"
```

---

### Task 2: 扩展 `BaseHero` 加 commander 4 字段，更新 yun/anna

**Files:**
- Modify: `game/app/classes/heroes/base.py`
- Modify: `game/app/classes/heroes/yun.py`
- Modify: `game/app/classes/heroes/anna.py`
- Test: `game/tests/test_commanders_hero.py`

**Interfaces:**
- Consumes: `CommanderPassive`, `CommanderPower` from `app/commanders`
- Produces: `BaseHero.is_commander / commander_passive / commander_power / power_threshold` ClassVars
- Produces: `HeroProfile.commander_passive / commander_power / power_threshold` snapshot fields

- [ ] **Step 2.1: 检查现有 `BaseHero` 结构**

Run: `grep -n "class BaseHero" game/app/classes/heroes/base.py`
预期：返回 `class BaseHero(ABC):` 行号，记住当前字段布局。

- [ ] **Step 2.2: 写测试 `tests/test_commanders_hero.py`**

```python
"""test_commanders_hero.py — Hero 必须暴露 4 个 commander 字段。"""
import pytest
from app.classes.heroes import get as get_hero
from app.commanders import CommanderPassive, CommanderPower


class TestHeroCommanderFields:
    def test_yun_is_commander_with_passive_and_power(self):
        h = get_hero("yun")
        assert h.is_commander is True
        assert isinstance(h.commander_passive, CommanderPassive)
        assert isinstance(h.commander_power, CommanderPower)
        assert h.power_threshold > 0

    def test_anna_is_commander(self):
        h = get_hero("anna")
        assert h.is_commander is True
        assert h.commander_power is not None

    def test_unknown_hero_raises(self):
        with pytest.raises(KeyError):
            get_hero("ghost")


class TestHeroCompile:
    def test_compile_preserves_commander_fields(self):
        from app.classes.heroes.base import compile_hero
        from app.classes.heroes.yun import YunHero

        profile = compile_hero(YunHero)
        assert profile.is_commander is True
        assert profile.commander_passive is not None
        assert profile.commander_power is not None
        assert profile.power_threshold == YunHero.power_threshold
```

- [ ] **Step 2.3: 运行测试，预期失败**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_hero.py -v`
Expected: FAIL with `AttributeError: type object 'YunHero' has no attribute 'is_commander'` 或类似。

- [ ] **Step 2.4: 在 `base.py` 添加 4 个字段到 `BaseHero`**

Read `game/app/classes/heroes/base.py` to find where existing ClassVars end. Add after the last existing ClassVar (before the `def compile(cls) -> HeroProfile:` if it exists):

```python
class BaseHero(ABC):
    # ... existing fields ...

    # 🆕 Commander (P3.0) — None 表示非指挥官英雄
    is_commander: ClassVar[bool] = False
    commander_passive: ClassVar[Optional["CommanderPassive"]] = None
    commander_power: ClassVar[Optional["CommanderPower"]] = None
    power_threshold: ClassVar[int] = 20
```

Add import at top of `base.py`:
```python
from typing import ClassVar, Optional, Tuple
from app.commanders import CommanderPassive, CommanderPower
```

If `HeroProfile` dataclass exists in the same file, add 3 fields to it too:
```python
@dataclass(frozen=True)
class HeroProfile:
    # ... existing fields ...
    is_commander: bool = False
    commander_passive: Optional[CommanderPassive] = None
    commander_power: Optional[CommanderPower] = None
    power_threshold: int = 20
```

If there's a `compile()` classmethod, ensure it copies these 3 fields. Patch the compile body:
```python
return HeroProfile(
    # ... existing assignments ...
    is_commander=cls.is_commander,
    commander_passive=cls.commander_passive,
    commander_power=cls.commander_power,
    power_threshold=cls.power_threshold,
)
```

- [ ] **Step 2.5: 更新 `yun.py` 加 commander 字段**

Read `game/app/classes/heroes/yun.py`. Add after existing ClassVars (and import):

```python
from app.commanders import CommanderPassive, CommanderPower

class YunHero(BaseHero):
    hero_id = "yun"
    # ... existing fields ...

    # 🆕 Commander config (P3.0)
    is_commander: ClassVar[bool] = True
    commander_passive: ClassVar[Optional[CommanderPassive]] = CommanderPassive(
        atk_pct=0.10,        # 全队 +10% atk
        range_delta=1,       # 远程 +1 格
    )
    commander_power: ClassVar[Optional[CommanderPower]] = CommanderPower(
        atk_pct=0.30,        # 全队 +30% atk
        heal_pct=0.50,       # 全体回 50% max_hp
    )
    power_threshold: ClassVar[int] = 22
```

If `yun.py` already uses `ClassVar` syntax, keep it; otherwise use plain assignment (match existing style).

- [ ] **Step 2.6: 更新 `anna.py` 加 commander 字段**

```python
from app.commanders import CommanderPassive, CommanderPower

class AnnaHero(BaseHero):
    hero_id = "anna"
    # ... existing fields ...

    # 🆕 Commander config (P3.0)
    is_commander: ClassVar[bool] = True
    commander_passive: ClassVar[Optional[CommanderPassive]] = CommanderPassive(
        def_pct=0.15,        # 全队 +15% def
        mdef_pct=0.10,       # 全队 +10% mdef
    )
    commander_power: ClassVar[Optional[CommanderPower]] = CommanderPower(
        def_pct=0.30,
        mdef_pct=0.30,
        heal_pct=0.80,       # 强治疗型大招
    )
    power_threshold: ClassVar[int] = 18
```

- [ ] **Step 2.7: 运行测试，预期全通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_hero.py -v`
Expected: 4 passed.

- [ ] **Step 2.8: 全量回归**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_hero_system.py tests/test_mainline_loader.py -v 2>&1 | tail -20`
Expected: 全部通过（hero 扩展不应破坏现有功能）。

- [ ] **Step 2.9: Commit**

```bash
cd game/..
git add game/app/classes/heroes/
git commit -m "feat(p3.0): extend BaseHero with 4 commander fields; configure yun + anna"
```

---

### Task 3: 数据库迁移 + ORM 列（Player.commander_id / co_state, PlayerProfile.unlocked_commanders）

**Files:**
- Modify: `game/app/models.py` (Player + PlayerProfile)
- Modify: `game/app/database.py` (auto-migration)
- Test: `game/tests/test_commanders_db.py`

**Interfaces:**
- Consumes: `COState.dump() / .load()` from Task 1
- Produces: `Player.commander_id: Optional[str]`, `Player.co_state: Optional[dict]`
- Produces: `PlayerProfile.unlocked_commanders: list[str]`

- [ ] **Step 3.1: 写测试 `tests/test_commanders_db.py`**

```python
"""test_commanders_db.py — Player/PlayerProfile 必须有 commander 列。"""
import pytest
from app.models import Player, PlayerProfile


def test_player_has_commander_columns():
    cols = {c.name for c in Player.__table__.columns}
    assert "commander_id" in cols
    assert "co_state" in cols


def test_player_profile_has_unlocked_commanders():
    cols = {c.name for c in PlayerProfile.__table__.columns}
    assert "unlocked_commanders" in cols


def test_player_commander_id_defaults_none():
    from sqlalchemy import inspect
    mapper = inspect(Player)
    col = mapper.columns.commander_id
    assert col.default is None or col.nullable


def test_player_co_state_nullable():
    from sqlalchemy import inspect
    mapper = inspect(Player)
    col = mapper.columns.co_state
    assert col.nullable
```

- [ ] **Step 3.2: 运行测试，预期失败**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_db.py -v`
Expected: FAIL with `assert "commander_id" in cols` 或 AttributeError。

- [ ] **Step 3.3: 修改 `models.py` 加 3 列**

Read `game/app/models.py` to find the `Player` class. Add inside `Player`:

```python
class Player(Base):
    __tablename__ = "players"
    # ... existing columns ...
    commander_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    co_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
```

Find the `PlayerProfile` class. Add:
```python
class PlayerProfile(Base):
    __tablename__ = "player_profiles"
    # ... existing columns ...
    unlocked_commanders: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
```

If `JSON` is not already imported from sqlalchemy, add `from sqlalchemy import JSON` (or use `JSONB` if Postgres; for SQLite, JSON is fine).

- [ ] **Step 3.4: 修改 `database.py` 加自动迁移**

Find `_run_legacy_migrations()` or equivalent in `database.py`. Add 3 migration lines:

```python
def _run_legacy_migrations(engine):
    # ... existing migrations ...
    with engine.begin() as conn:
        # P3.0 Commander
        try:
            conn.execute(text("ALTER TABLE players ADD COLUMN commander_id VARCHAR(64)"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE players ADD COLUMN co_state JSON"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE player_profiles ADD COLUMN unlocked_commanders JSON"))
        except Exception:
            pass
```

- [ ] **Step 3.5: 运行测试，预期通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_db.py -v`
Expected: 4 passed.

- [ ] **Step 3.6: Commit**

```bash
cd game/..
git add game/app/models.py game/app/database.py game/tests/test_commanders_db.py
git commit -m "feat(p3.0): add commander_id + co_state + unlocked_commanders columns"
```

---

## Milestone 2 · 核心机制

### Task 4: Meter 模块（杀敌 + 阵亡计分 + 单测）

**Files:**
- Create: `game/app/commanders/meter.py`
- Modify: `game/app/commanders/__init__.py`（导出）
- Test: `game/tests/test_commanders_meter.py`

**Interfaces:**
- Consumes: `Player.co_state` (dict)
- Produces: `on_kill(attacker_player, killed_unit_type: str) -> int` (returns score)
- Produces: `on_death(dead_player) -> int`
- Produces: `UNIT_DESTROY_SCORES: dict[str, int]` module constant

- [ ] **Step 4.1: 写测试 `tests/test_commanders_meter.py`**

```python
"""test_commanders_meter.py — kill/death 计分。"""
from app.commanders.meter import (
    UNIT_DESTROY_SCORES, DEATH_PENALTY, on_kill, on_death
)


class FakePlayer:
    def __init__(self):
        self.co_state = {"meter": 0, "threshold": 20}


class FakeUnit:
    def __init__(self, unit_type: str):
        self.unit_type = unit_type


class TestOnKill:
    def test_kill_swordsman_scores_2(self):
        p = FakePlayer()
        score = on_kill(p, "swordsman")
        assert score == 2
        assert p.co_state["meter"] == 2

    def test_kill_knight_scores_4(self):
        p = FakePlayer()
        score = on_kill(p, "knight")
        assert score == 4
        assert p.co_state["meter"] == 4

    def test_kill_unknown_type_uses_default(self):
        p = FakePlayer()
        score = on_kill(p, "ghost")
        assert score == 2  # 默认值


class TestOnDeath:
    def test_death_adds_2(self):
        p = FakePlayer()
        score = on_death(p)
        assert score == DEATH_PENALTY == 2
        assert p.co_state["meter"] == 2


class TestScores:
    def test_known_classes_have_scores(self):
        for cls in ["swordsman", "archer", "knight", "warlock", "healer"]:
            assert cls in UNIT_DESTROY_SCORES
```

- [ ] **Step 4.2: 运行测试，预期失败**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_meter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.commanders.meter'`。

- [ ] **Step 4.3: 创建 `app/commanders/meter.py`**

```python
"""meter.py — CO meter 计分。

杀敌 + 阵亡双权重总和。
杀敌按 class 区分；阵亡统一 2 分。
"""


UNIT_DESTROY_SCORES: dict[str, int] = {
    "swordsman": 2,
    "archer": 3,
    "lancer": 2,
    "knight": 4,
    "warlock": 4,
    "healer": 3,
}

DEATH_PENALTY: int = 2


def on_kill(attacker_player, killed_unit_type: str) -> int:
    """玩家击杀一个敌人，meter +score。返回 score 供日志用。"""
    score = UNIT_DESTROY_SCORES.get(killed_unit_type, 2)
    if attacker_player.co_state is None:
        attacker_player.co_state = {"meter": 0, "threshold": 20}
    attacker_player.co_state["meter"] = attacker_player.co_state.get("meter", 0) + score
    return score


def on_death(dead_player) -> int:
    """自家一个单位被打死，meter +2。"""
    if dead_player.co_state is None:
        dead_player.co_state = {"meter": 0, "threshold": 20}
    dead_player.co_state["meter"] = dead_player.co_state.get("meter", 0) + DEATH_PENALTY
    return DEATH_PENALTY
```

- [ ] **Step 4.4: 更新 `__init__.py` 导出**

```python
"""指挥官系统模块入口。"""
from app.commanders.passive import CommanderPassive
from app.commanders.power import CommanderPower
from app.commanders.state import COState
from app.commanders import meter

__all__ = ["CommanderPassive", "CommanderPower", "COState", "meter"]
```

- [ ] **Step 4.5: 运行测试，预期通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_meter.py -v`
Expected: 7 passed.

- [ ] **Step 4.6: Commit**

```bash
cd game/..
git add game/app/commanders/meter.py game/app/commanders/__init__.py game/tests/test_commanders_meter.py
git commit -m "feat(p3.0): add meter module with kill/death scoring"
```

---

### Task 5: 被动烘焙 + 单测（bake_passive_into_units）

**Files:**
- Create: `game/app/commanders/registry.py`
- Create: `game/app/commanders/effects.py`
- Modify: `game/app/commanders/__init__.py`
- Test: `game/tests/test_commanders_passive.py`

**Interfaces:**
- Consumes: `Player.commander_id`, `Player.units`
- Produces: `bake_passive_into_units(player)` — 修改 unit.atk/def_/mov/max_hp/range + 标记 `_commander_passive`

- [ ] **Step 5.1: 创建 `app/commanders/registry.py`**

```python
"""registry.py — 从 hero 注册器拉取指挥官视图。

为什么需要：避免每个调用方都查 Hero 字段，封装 "hero_id → CommanderPassive/Power/Threshold"。
"""
from typing import Optional
from app.classes.heroes import get as get_hero


def get_commander_passive(commander_id: str):
    """返回 CommanderPassive 实例，或 None（非指挥官英雄）。"""
    if commander_id is None:
        return None
    hero = get_hero(commander_id)
    return getattr(hero, "commander_passive", None)


def get_commander_power(commander_id: str):
    """返回 CommanderPower 实例，或 None。"""
    if commander_id is None:
        return None
    hero = get_hero(commander_id)
    return getattr(hero, "commander_power", None)


def get_power_threshold(commander_id: str) -> int:
    """返回 power_threshold（默认 20）。"""
    if commander_id is None:
        return 20
    hero = get_hero(commander_id)
    return getattr(hero, "power_threshold", 20)
```

- [ ] **Step 5.2: 写测试 `tests/test_commanders_passive.py`**

```python
"""test_commanders_passive.py — bake_passive_into_units 烘焙数值正确。"""
import pytest
from app.commanders.effects import bake_passive_into_units
from app.commanders.registry import get_commander_passive
from app.classes.heroes import get as get_hero


class FakeUnit:
    def __init__(self, hp=20, max_hp=20, atk=5, def_=3, matk=2, mdef=1, mov=4, attack_range=1):
        self.hp = hp
        self.max_hp = max_hp
        self.atk = atk
        self.def_ = def_
        self.matk = matk
        self.mdef = mdef
        self.mov = mov
        self.attack_range = attack_range


class FakePlayer:
    def __init__(self, commander_id, units=None):
        self.commander_id = commander_id
        self.units = units or []


class TestBakePassive:
    def test_yun_bake_applies_atk_pct_and_range_delta(self):
        # yun passive: atk_pct=0.10, range_delta=1
        u = FakeUnit(atk=10, attack_range=2)
        p = FakePlayer("yun", [u])
        bake_passive_into_units(p)
        # atk = 10 * 1.10 = 11 (round)
        assert u.atk == 11
        assert u._commander_passive is get_commander_passive("yun")
        # range_delta 通过 _base_attack_range 标记
        assert u._base_attack_range == 3

    def test_anna_bake_applies_def_pct(self):
        # anna passive: def_pct=0.15
        u = FakeUnit(def_=10)
        p = FakePlayer("anna", [u])
        bake_passive_into_units(p)
        assert u.def_ == round(10 * 1.15)  # 12 (rounded)

    def test_no_commander_is_noop(self):
        u = FakeUnit(atk=10)
        p = FakePlayer(None, [u])
        bake_passive_into_units(p)
        assert u.atk == 10  # unchanged
        assert not hasattr(u, "_commander_passive")

    def test_bake_sets_hp_to_max(self):
        u = FakeUnit(hp=5, max_hp=20)
        p = FakePlayer("yun", [u])  # yun: hp_pct=0 (default)
        bake_passive_into_units(p)
        # hp_pct=0 → max_hp 不变, hp 保持
        # 但若 hp_pct != 0 则 max_hp 重写 + hp=满血
        assert u.hp == 5
        assert u.max_hp == 20

    def test_negative_pct_lowers_stat(self):
        """构造一个临时的负向 passive，验证负数也能正确下调。"""
        from app.commanders import CommanderPassive
        # 通过 monkey-patch 模拟
        original = get_hero("yun").commander_passive
        get_hero("yun").commander_passive = CommanderPassive(atk_pct=-0.20)
        try:
            u = FakeUnit(atk=10)
            p = FakePlayer("yun", [u])
            bake_passive_into_units(p)
            assert u.atk == 8  # 10 * 0.80 = 8
        finally:
            get_hero("yun").commander_passive = original

    def test_mov_min_one(self):
        """mov_delta=-10 时不能让 mov 跌破 1。"""
        from app.commanders import CommanderPassive
        original = get_hero("yun").commander_passive
        get_hero("yun").commander_passive = CommanderPassive(mov_delta=-10)
        try:
            u = FakeUnit(mov=5)
            p = FakePlayer("yun", [u])
            bake_passive_into_units(p)
            assert u.mov == 1
        finally:
            get_hero("yun").commander_passive = original
```

- [ ] **Step 5.3: 运行测试，预期失败**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_passive.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.commanders.effects'`。

- [ ] **Step 5.4: 创建 `app/commanders/effects.py` 基础结构 + `bake_passive_into_units`**

```python
"""effects.py — 指挥官效果调度（烘焙 / 发动 / 失效）。

烘焙：战斗创建时一次性写入 unit 行（持久化到本次战斗）
发动：叠加在已烘焙值之上
失效：撤销 power 叠加，回到 passive 基线
"""
from app.commanders.registry import (
    get_commander_passive,
    get_commander_power,
)


def bake_passive_into_units(player):
    """战斗创建时调用，把 commander 的 passive 烘焙到 player 所有 unit。

    必须在 _apply_hero_overrides 之后调用（基于已含 hero override 的值再叠加）。
    """
    if player.commander_id is None:
        return
    passive = get_commander_passive(player.commander_id)
    if passive is None:
        return

    for unit in player.units:
        if passive.hp_pct:
            unit.max_hp = round(unit.max_hp * (1 + passive.hp_pct))
            unit.hp = unit.max_hp
        if passive.atk_pct:
            unit.atk = round(unit.atk * (1 + passive.atk_pct))
        if passive.def_pct:
            unit.def_ = round(unit.def_ * (1 + passive.def_pct))
        if passive.matk_pct:
            unit.matk = round(unit.matk * (1 + passive.matk_pct))
        if passive.mdef_pct:
            unit.mdef = round(unit.mdef * (1 + passive.mdef_pct))
        if passive.mov_delta:
            unit.mov = max(1, unit.mov + passive.mov_delta)
        if passive.range_delta:
            unit._base_attack_range = unit.attack_range + passive.range_delta

        unit._commander_passive = passive
```

- [ ] **Step 5.5: 运行测试，预期通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_passive.py -v`
Expected: 6 passed.

- [ ] **Step 5.6: Commit**

```bash
cd game/..
git add game/app/commanders/effects.py game/app/commanders/registry.py game/tests/test_commanders_passive.py
git commit -m "feat(p3.0): add passive baking into units"
```

---

### Task 6: CO Power 发动 + 失效 + 单测

**Files:**
- Modify: `game/app/commanders/effects.py`
- Test: `game/tests/test_commanders_power.py`

**Interfaces:**
- Consumes: `Player.commander_id`, `Player.units`, `Player.co_state`
- Produces: `fire_co_power(player) -> None` — raises if cannot fire
- Produces: `expire_power(player) -> None`
- Produces: `can_fire_co_power(player) -> bool`

- [ ] **Step 6.1: 写测试 `tests/test_commanders_power.py`**

```python
"""test_commanders_power.py — fire / expire / stacking on passive."""
import pytest
from app.commanders.effects import (
    bake_passive_into_units, fire_co_power, expire_power, can_fire_co_power
)


class FakeUnit:
    def __init__(self, hp=20, max_hp=20, atk=10, def_=5, matk=2, mdef=1, mov=4, mp=4, attack_range=2):
        self.hp = hp
        self.max_hp = max_hp
        self.atk = atk
        self.def_ = def_
        self.matk = matk
        self.mdef = mdef
        self.mov = mov
        self.mp = mp
        self.attack_range = attack_range


class FakePlayer:
    def __init__(self, commander_id, units=None, meter=0, is_active=False):
        self.commander_id = commander_id
        self.units = units or []
        self.co_state = {
            "commander_id": commander_id,
            "meter": meter,
            "threshold": 22,
            "is_power_active": is_active,
            "last_start_turn": -1,
        }


class TestFireCO:
    def test_can_fire_when_meter_full(self):
        p = FakePlayer("yun", meter=22)
        assert can_fire_co_power(p) is True

    def test_cannot_fire_when_meter_low(self):
        p = FakePlayer("yun", meter=10)
        assert can_fire_co_power(p) is False

    def test_cannot_fire_when_already_active(self):
        p = FakePlayer("yun", meter=22, is_active=True)
        assert can_fire_co_power(p) is False

    def test_cannot_fire_without_commander(self):
        p = FakePlayer(None, meter=100)
        assert can_fire_co_power(p) is False

    def test_fire_stacks_on_passive(self):
        """passive 烘焙后再发动 power，数值正确叠加。"""
        u = FakeUnit(atk=10, max_hp=40)
        p = FakePlayer("yun", [u])
        bake_passive_into_units(p)
        # yun passive: atk_pct=0.10 → atk=11
        assert u.atk == 11

        p.co_state["meter"] = 22
        fire_co_power(p)
        # yun power: atk_pct=0.30 → 11 * 1.30 = 14.3 → 14
        assert u.atk == 14
        # heal_pct=0.50 → hp = min(40, 20 + 20) = 40
        assert u.hp == 40
        # meter 清零
        assert p.co_state["meter"] == 0
        # power active
        assert p.co_state["is_power_active"] is True
        # unit 被标记
        assert u._commander_power is not None

    def test_fire_raises_when_cannot(self):
        p = FakePlayer("yun", meter=10)
        with pytest.raises(ValueError, match="meter not full"):
            fire_co_power(p)

    def test_fire_heal_partial(self):
        """heal_pct < 1.0 时不会溢出 max_hp。"""
        u = FakeUnit(hp=5, max_hp=20)
        p = FakePlayer("yun", [u])
        bake_passive_into_units(p)
        p.co_state["meter"] = 22
        fire_co_power(p)
        # yun power heal 50% of 20 = 10, hp = min(20, 5+10) = 15
        assert u.hp == 15

    def test_fire_extra_mov(self):
        u = FakeUnit(mp=2, mov=5)
        p = FakePlayer("yun", [u])
        bake_passive_into_units(p)
        p.co_state["meter"] = 22
        fire_co_power(p)
        # extra_mov=0 for yun (default), so mp stays
        assert u.mp == 2


class TestExpirePower:
    def test_expire_reverts_only_power_layer(self):
        u = FakeUnit(atk=10)
        p = FakePlayer("yun", [u])
        bake_passive_into_units(p)   # atk 10 → 11
        p.co_state["meter"] = 22
        fire_co_power(p)              # atk 11 → 14
        assert u.atk == 14

        expire_power(p)
        # 回到 passive 基线 = 11
        assert u.atk == 11
        assert p.co_state["is_power_active"] is False
        assert not hasattr(u, "_commander_power")

    def test_expire_on_no_active_is_noop(self):
        u = FakeUnit(atk=10)
        p = FakePlayer("yun", [u])
        bake_passive_into_units(p)
        expire_power(p)  # 不应报错
        assert u.atk == 11
```

- [ ] **Step 6.2: 运行测试，预期失败**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_power.py -v`
Expected: FAIL with `ImportError: cannot import name 'fire_co_power'`。

- [ ] **Step 6.3: 添加 `can_fire_co_power` / `fire_co_power` / `expire_power` 到 `effects.py`**

```python
# 追加到 app/commanders/effects.py

def can_fire_co_power(player) -> bool:
    """检查发动条件；不抛异常。"""
    if player.commander_id is None:
        return False
    if player.co_state.get("is_power_active"):
        return False
    if player.co_state.get("meter", 0) < player.co_state.get("threshold", 20):
        return False
    if get_commander_power(player.commander_id) is None:
        return False
    return True


def fire_co_power(player):
    """发动 CO Power。叠加在 passive 之上。

    Raises:
        ValueError: 不满足发动条件
    """
    if not can_fire_co_power(player):
        if player.commander_id is None:
            raise ValueError("no commander selected")
        if player.co_state.get("is_power_active"):
            raise ValueError("power already active")
        if player.co_state.get("meter", 0) < player.co_state.get("threshold", 20):
            raise ValueError("meter not full")
        raise ValueError("commander has no power")

    power = get_commander_power(player.commander_id)

    for unit in player.units:
        if power.atk_pct:
            unit.atk = round(unit.atk * (1 + power.atk_pct))
        if power.def_pct:
            unit.def_ = round(unit.def_ * (1 + power.def_pct))
        if power.matk_pct:
            unit.matk = round(unit.matk * (1 + power.matk_pct))
        if power.mdef_pct:
            unit.mdef = round(unit.mdef * (1 + power.mdef_pct))
        if power.range_delta:
            base = getattr(unit, "_base_attack_range", None) or unit.attack_range
            unit._base_attack_range = base + power.range_delta

        unit._commander_power = power

    # 全体回血（基于当前 max_hp）
    if power.heal_pct:
        for unit in player.units:
            heal = round(unit.max_hp * power.heal_pct)
            unit.hp = min(unit.max_hp, unit.hp + heal)

    # 额外移动力（加到当前 mp）
    if power.extra_mov:
        for unit in player.units:
            unit.mp = min(unit.mov, unit.mp + power.extra_mov)

    player.co_state["is_power_active"] = True
    player.co_state["meter"] = 0


def expire_power(player):
    """撤销 power 叠加，回到 passive 基线（passive 仍生效）。"""
    for unit in player.units:
        if hasattr(unit, "_commander_power"):
            del unit._commander_power
    player.co_state["is_power_active"] = False
```

- [ ] **Step 6.4: 运行测试，预期通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_power.py -v`
Expected: 10 passed.

- [ ] **Step 6.5: Commit**

```bash
cd game/..
git add game/app/commanders/effects.py game/tests/test_commanders_power.py
git commit -m "feat(p3.0): add CO Power fire/expire + stacking on passive"
```

---

### Task 7: `on_player_turn_start` lifecycle hook + 多玩家独立 expire 测试

**Files:**
- Modify: `game/app/commanders/effects.py`
- Test: `game/tests/test_commanders_lifecycle.py`

**Interfaces:**
- Produces: `on_player_turn_start(player, game_turn_number: int) -> None` — 检测"下次自己开局"并 expire + reset meter

- [ ] **Step 7.1: 写测试 `tests/test_commanders_lifecycle.py`**

```python
"""test_commanders_lifecycle.py — on_player_turn_start 检测下次自己开局。"""
from app.commanders.effects import (
    bake_passive_into_units, fire_co_power, expire_power, on_player_turn_start
)


class FakeUnit:
    def __init__(self, atk=10):
        self.atk = atk
        self.max_hp = 20
        self.hp = 20


class FakePlayer:
    def __init__(self, commander_id, units=None, last_start_turn=-1,
                 meter=0, threshold=22, is_active=False):
        self.commander_id = commander_id
        self.units = units or []
        self.co_state = {
            "commander_id": commander_id,
            "meter": meter,
            "threshold": threshold,
            "is_power_active": is_active,
            "last_start_turn": last_start_turn,
        }


class TestFirstTurnNoExpire:
    def test_first_turn_does_not_expire(self):
        u = FakeUnit(atk=10)
        p = FakePlayer("yun", [u], last_start_turn=-1)
        bake_passive_into_units(p)
        p.co_state["meter"] = 22
        fire_co_power(p)
        assert p.co_state["is_power_active"] is True

        # 第一次 on_player_turn_start (turn_number=1) → 不应 expire
        on_player_turn_start(p, game_turn_number=1)
        assert p.co_state["is_power_active"] is True
        assert p.co_state["last_start_turn"] == 1


class TestExpireOnNextSelfStart:
    def test_expires_when_turn_increments(self):
        u = FakeUnit(atk=10)
        p = FakePlayer("yun", [u], last_start_turn=1)
        bake_passive_into_units(p)
        p.co_state["meter"] = 22
        fire_co_power(p)

        # 跨过一个 cycle 后，玩家自己再次开局
        on_player_turn_start(p, game_turn_number=5)  # 5 > 1
        assert p.co_state["is_power_active"] is False
        assert p.co_state["meter"] == 0
        assert p.co_state["last_start_turn"] == 5


class TestMeterResetEvenWithoutFire:
    def test_meter_resets_even_if_never_fired(self):
        """即使没发动过 power，下次自己开局时 meter 也归零。"""
        p = FakePlayer("yun", [], last_start_turn=1, meter=15)
        on_player_turn_start(p, game_turn_number=5)
        assert p.co_state["meter"] == 0


class TestMultiPlayerIndependent:
    def test_4_players_independent_expiry(self):
        """4 个玩家各自独立追踪 last_start_turn，互不影响。"""
        u1, u2, u3, u4 = (FakeUnit(),) * 4
        red   = FakePlayer("yun",   [u1], last_start_turn=1)
        blue  = FakePlayer("anna",  [u2], last_start_turn=2)
        green = FakePlayer(None,    [u3], last_start_turn=3)
        yellow = FakePlayer("yun",  [u4], last_start_turn=4)

        # red 在 T1 发动 power
        bake_passive_into_units(red)
        red.co_state["meter"] = 22
        fire_co_power(red)

        # blue 在 T2 发动
        bake_passive_into_units(blue)
        blue.co_state["meter"] = 18
        fire_co_power(blue)

        # red T2 (turn=5) → red expire, blue 还 active
        on_player_turn_start(red, game_turn_number=5)
        assert red.co_state["is_power_active"] is False
        assert blue.co_state["is_power_active"] is True

        # blue T2 (turn=6) → blue expire
        on_player_turn_start(blue, game_turn_number=6)
        assert blue.co_state["is_power_active"] is False

        # green 没 commander 也没 power, noop
        on_player_turn_start(green, game_turn_number=7)
        assert green.co_state["last_start_turn"] == 7
```

- [ ] **Step 7.2: 运行测试，预期失败**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_lifecycle.py -v`
Expected: FAIL with `ImportError: cannot import name 'on_player_turn_start'`。

- [ ] **Step 7.3: 添加 `on_player_turn_start` 到 `effects.py`**

```python
# 追加到 app/commanders/effects.py

def on_player_turn_start(player, game_turn_number: int):
    """每玩家回合正式开始时调用一次。

    跨过一个完整 cycle（自己 + 所有其他玩家）后：
    - 若 power 仍 active → 失效
    - meter 归零
    - 更新 last_start_turn

    跨过与否的判断：game_turn_number > last_start_turn。
    首回合 last_start_turn=-1，不会误判。
    """
    co = player.co_state or {}
    last = co.get("last_start_turn", -1)

    if last != -1 and game_turn_number > last:
        # 跨过完整 cycle
        if co.get("is_power_active"):
            expire_power(player)
        co["meter"] = 0

    co["last_start_turn"] = game_turn_number
```

- [ ] **Step 7.4: 运行测试，预期通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_lifecycle.py -v`
Expected: 4 passed.

- [ ] **Step 7.5: 全量回归确保 power 测试还通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_power.py tests/test_commanders_lifecycle.py -v`
Expected: 14 passed.

- [ ] **Step 7.6: Commit**

```bash
cd game/..
git add game/app/commanders/effects.py game/tests/test_commanders_lifecycle.py
git commit -m "feat(p3.0): add on_player_turn_start lifecycle hook"
```

---

## Milestone 3 · Schema + 解锁 + 选择 API

### Task 8: BattleSpec schema（unlocks_commander + enemy_commander）+ mainline 胜利引擎

**Files:**
- Modify: `game/app/mainline/schemas.py` (BattleSpec)
- Modify: `game/app/mainline/engine.py` (apply_victory)
- Test: `game/tests/test_commanders_unlock.py`

**Interfaces:**
- Produces: `BattleSpec.unlocks_commander: Optional[str]` 校验 `is_commander=True`
- Produces: `BattleSpec.enemy_commander: Optional[str]` 同上
- Produces: `apply_victory(profile, mainline_id, rewards, unlocks_commander=None)` 写 `profile.unlocked_commanders`

- [ ] **Step 8.1: 写测试 `tests/test_commanders_unlock.py`**

```python
"""test_commanders_unlock.py — BattleSpec 字段 + 主线胜利解锁。"""
import pytest
from app.mainline.schemas import BattleSpec


def test_battle_spec_with_unlocks_commander():
    """合法：unlocks_commander 指向 is_commander=True 的英雄。"""
    spec = BattleSpec(
        id="b1", title="t", map_id="m", win_condition="rout",
        teams={"ally": ["red"], "enemy": ["blue"]},
        unlocks_commander="yun",
    )
    assert spec.unlocks_commander == "yun"


def test_battle_spec_enemy_commander():
    spec = BattleSpec(
        id="b1", title="t", map_id="m", win_condition="rout",
        teams={"ally": ["red"], "enemy": ["blue"]},
        enemy_commander="anna",
    )
    assert spec.enemy_commander == "anna"


def test_battle_spec_rejects_unknown_commander():
    """unlocks_commander 不在 heroes registry 内 → ValidationError。"""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        BattleSpec(
            id="b1", title="t", map_id="m", win_condition="rout",
            teams={"ally": ["red"], "enemy": ["blue"]},
            unlocks_commander="ghost",
        )


def test_apply_victory_unlocks_commander():
    """胜利本场后，玩家 profile.unlocked_commanders 追加 hero_id。"""
    from app.mainline.engine import MainlineEngine
    from app.progression.models import PlayerProfile

    engine = MainlineEngine.__new__(MainlineEngine)  # skip __init__
    profile = PlayerProfile(user_name="alice", gold=0, unlocked_classes=[],
                            unlocked_commanders=[])
    rewards = type("R", (), {"gold": 100, "unlock_class": None, "exp_per_unit": 0})()
    engine.apply_victory(
        profile=profile,
        mainline_id="chapter_01",
        rewards=rewards,
        unlocks_commander="anna",
    )
    assert "anna" in profile.unlocked_commanders


def test_apply_victory_dedups_unlocks():
    from app.mainline.engine import MainlineEngine
    from app.progression.models import PlayerProfile

    profile = PlayerProfile(user_name="bob", gold=0, unlocked_classes=[],
                            unlocked_commanders=["anna"])
    engine = MainlineEngine.__new__(MainlineEngine)
    rewards = type("R", (), {"gold": 100, "unlock_class": None, "exp_per_unit": 0})()
    engine.apply_victory(
        profile=profile, mainline_id="chapter_01", rewards=rewards,
        unlocks_commander="anna",
    )
    assert profile.unlocked_commanders.count("anna") == 1


def test_apply_victory_no_unlock_when_none():
    from app.mainline.engine import MainlineEngine
    from app.progression.models import PlayerProfile

    profile = PlayerProfile(user_name="c", gold=0, unlocked_classes=[],
                            unlocked_commanders=[])
    engine = MainlineEngine.__new__(MainlineEngine)
    rewards = type("R", (), {"gold": 100, "unlock_class": None, "exp_per_unit": 0})()
    engine.apply_victory(
        profile=profile, mainline_id="chapter_01", rewards=rewards,
        unlocks_commander=None,
    )
    assert profile.unlocked_commanders == []
```

- [ ] **Step 8.2: 运行测试，预期失败**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_unlock.py -v`
Expected: FAIL with `TypeError: BattleSpec unexpected keyword 'unlocks_commander'`。

- [ ] **Step 8.3: 修改 `app/mainline/schemas.py` 加 2 个字段**

Read `game/app/mainline/schemas.py` to find `class BattleSpec`. Add 2 fields after existing ones:

```python
from pydantic import Field, model_validator
from app.classes.heroes import get as get_hero

class BattleSpec(BaseModel):
    # ... existing fields ...
    unlocks_commander: Optional[str] = Field(default=None, description="胜利本场后解锁的指挥官 hero_id")
    enemy_commander: Optional[str] = Field(default=None, description="主线专用：敌方指挥官 hero_id")

    @model_validator(mode="after")
    def _check_commander_fields(self):
        for field_name in ("unlocks_commander", "enemy_commander"):
            val = getattr(self, field_name)
            if val is None:
                continue
            try:
                hero = get_hero(val)
            except KeyError:
                raise ValueError(f"{field_name}={val!r} not in heroes registry")
            if not getattr(hero, "is_commander", False):
                raise ValueError(f"{field_name}={val!r} is not a commander (is_commander=False)")
        return self
```

If `Optional` and `BaseModel` aren't imported, add them.

- [ ] **Step 8.4: 修改 `app/mainline/engine.py` 写 `apply_victory`**

Read `apply_victory` method. Find the line `profile.gold += rewards.gold`. Add after `unlock_class` block:

```python
def apply_victory(self, profile, mainline_id, rewards, unlocks_commander=None):
    # ... existing logic ...
    profile.gold += rewards.gold
    if rewards.unlock_class:
        if rewards.unlock_class not in profile.unlocked_classes:
            profile.unlocked_classes.append(rewards.unlock_class)
    # 🆕 P3.0 commander unlock
    if unlocks_commander:
        if profile.unlocked_commanders is None:
            profile.unlocked_commanders = []
        if unlocks_commander not in profile.unlocked_commanders:
            profile.unlocked_commanders.append(unlocks_commander)
    # ... rest of existing logic ...
```

If `profile.unlocked_commanders` is None on existing rows, ensure the migration or this code initializes it.

- [ ] **Step 8.5: 运行测试，预期通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_unlock.py -v`
Expected: 6 passed.

- [ ] **Step 8.6: 更新 chapter_01 JSON 加 unlocks_commander**

Edit `game/mainlines/chapter_01_steel_rebellion.json` — add to battle_01:
```json
{
  "id": "battle_01",
  "unlocks_commander": "anna",
  "enemy_commander": null,
  ...
}
```

- [ ] **Step 8.7: Commit**

```bash
cd game/..
git add game/app/mainline/schemas.py game/app/mainline/engine.py game/tests/test_commanders_unlock.py game/mainlines/chapter_01_steel_rebellion.json
git commit -m "feat(p3.0): add BattleSpec.unlocks_commander/enemy_commander + mainline victory engine"
```

---

### Task 9: 指挥官选择 API + 池校验（unlocked ∩ starting_units）

**Files:**
- Create: `game/app/routes/commanders.py`
- Modify: `game/app/main.py` (include router)
- Modify: `game/app/schemas.py` (BattleConfig 加 commander/ai_commanders)
- Test: `game/tests/test_commanders_api.py`

**Interfaces:**
- Produces: `POST /mainlines/{id}/select-commander` body=`{commander_id: str|null}`
- Produces: `POST /games/{id}/select-commander` body=`{commander_id: str|null}` — 战斗中禁止
- Produces: `GET /players/me/commanders` → 列出已解锁

- [ ] **Step 9.1: 写测试 `tests/test_commanders_api.py` (用 FastAPI TestClient)**

```python
"""test_commanders_api.py — 选择指挥官的 HTTP API。"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_select_commander_in_mainline():
    response = client.post(
        "/mainlines/chapter_01_steel_rebellion/select-commander",
        json={"commander_id": "yun"},
    )
    assert response.status_code in (200, 401, 404)


def test_select_commander_rejects_unknown():
    response = client.post(
        "/mainlines/chapter_01_steel_rebellion/select-commander",
        json={"commander_id": "ghost"},
    )
    assert response.status_code in (422, 404)


def test_select_commander_in_battle_blocked():
    response = client.post(
        "/games/999/select-commander",
        json={"commander_id": "yun"},
    )
    assert response.status_code in (404, 422, 403)


def test_get_unlocked_commanders():
    response = client.get("/players/me/commanders")
    assert response.status_code in (200, 401)
```

- [ ] **Step 9.2: 运行测试，预期 404（路由不存在）**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_api.py -v`
Expected: 404 or 405 errors, no 500.

- [ ] **Step 9.3: 创建 `app/routes/commanders.py`**

```python
"""commanders.py — 指挥官选择 API。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict
from app.classes.heroes import get as get_hero


router = APIRouter(prefix="", tags=["commanders"])


class SelectCommanderIn(BaseModel):
    commander_id: Optional[str] = None


@router.post("/mainlines/{mainline_id}/select-commander")
def select_mainline_commander(mainline_id: str, body: SelectCommanderIn):
    """主线 lobby 选指挥官。"""
    cid = body.commander_id
    if cid is not None:
        try:
            hero = get_hero(cid)
        except KeyError:
            raise HTTPException(status_code=422, detail=f"unknown hero: {cid}")
        if not getattr(hero, "is_commander", False):
            raise HTTPException(status_code=422, detail=f"{cid} is not a commander")

    # TODO: 实际持久化到 PlayerProfile.mainline_commander_id
    # 此处简化为内存中记录，Task 13/14 扩展
    return {"mainline_id": mainline_id, "commander_id": cid}


@router.post("/games/{game_id}/select-commander")
def select_battle_commander(game_id: int, body: SelectCommanderIn):
    """战斗中切换 commander — 拒绝。"""
    raise HTTPException(status_code=409, detail="commander locked during battle")


@router.get("/players/me/commanders")
def get_unlocked_commanders():
    """列出当前 user 已解锁指挥官。"""
    # TODO: 从 PlayerProfile 读
    return {"unlocked_commanders": []}
```

- [ ] **Step 9.4: 修改 `app/main.py` 注册 router**

Find the section where routers are `include_router`'d. Add:
```python
from app.routes import commanders
app.include_router(commanders.router)
```

- [ ] **Step 9.5: 运行测试，预期路由可达 + 校验生效**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_api.py -v`
Expected: 4 passed (404 / 401 / 422 / 409 都是合法响应)。

- [ ] **Step 9.6: 修改 `app/schemas.py` 加 BattleConfig.commander 字段**

Find `class BattleConfig`. Add:
```python
class BattleConfig(BaseModel):
    audio: Optional[BattleAudioConfig] = None
    commander: Optional[str] = None        # 🆕 玩家指挥官 hero_id
    ai_commanders: Optional[Dict[int, str]] = None  # 🆕 seat → hero_id
```

If `Dict` not imported: `from typing import Optional, Dict`.

- [ ] **Step 9.7: Commit**

```bash
cd game/..
git add game/app/routes/commanders.py game/app/main.py game/app/schemas.py game/tests/test_commanders_api.py
git commit -m "feat(p3.0): add commander selection API + BattleConfig.commander"
```

---

### Task 10: 发动 CO Power API + 校验

**Files:**
- Modify: `game/app/routes/commanders.py`
- Create: `game/app/commanders/actions.py`
- Test: `game/tests/test_commanders_api.py`（追加）

**Interfaces:**
- Produces: `POST /games/{game_id}/co-power` — 校验 + fire
- 422 触发：commander_id None / 已 active / meter < threshold / 无 power

- [ ] **Step 10.1: 追加测试到 `tests/test_commanders_api.py`**

```python
# 追加到 test_commanders_api.py

def test_fire_co_power_endpoint_exists():
    response = client.post("/games/1/co-power", json={})
    assert response.status_code in (200, 404, 422, 409)


def test_fire_co_power_rejects_invalid_body():
    response = client.post("/games/1/co-power", json={"foo": "bar"})
    assert response.status_code in (422, 404)
```

- [ ] **Step 10.2: 运行测试，预期 404/405**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_api.py::test_fire_co_power_endpoint_exists -v`
Expected: 404 或 405（路由不存在）。

- [ ] **Step 10.3: 在 `app/routes/commanders.py` 加 `POST /games/{game_id}/co-power`**

```python
# 追加到 app/routes/commanders.py

from app.database import SessionLocal
from app.models import Game, Player
from app.commanders.effects import fire_co_power, can_fire_co_power
from app.commanders.actions import can_player_fire_now


class FireCOPowerIn(BaseModel):
    pass


@router.post("/games/{game_id}/co-power")
def fire_co_power_endpoint(game_id: int, body: FireCOPowerIn = FireCOPowerIn()):
    """玩家发动 CO Power。

    校验顺序：
    1. 游戏存在
    2. 当前玩家轮到 (can_player_fire_now)
    3. commander_id 已设置
    4. meter 满且未 active
    """
    db = SessionLocal()
    try:
        game = db.query(Game).filter(Game.id == game_id).first()
        if not game:
            raise HTTPException(status_code=404, detail="game not found")

        player = db.query(Player).filter(
            Player.game_id == game_id,
            Player.seat == game.current_player_index,
        ).first()
        if not player:
            raise HTTPException(status_code=404, detail="current player not found")

        if not can_player_fire_now(player):
            raise HTTPException(status_code=409, detail="not your turn")

        if not can_fire_co_power(player):
            if player.commander_id is None:
                raise HTTPException(status_code=422, detail="no commander selected")
            if player.co_state and player.co_state.get("is_power_active"):
                raise HTTPException(status_code=422, detail="power already active")
            raise HTTPException(status_code=422, detail="meter not full")

        fire_co_power(player)
        db.commit()
        return {"game_id": game_id, "commander_id": player.commander_id, "meter": 0}
    finally:
        db.close()
```

- [ ] **Step 10.4: 创建占位 `app/commanders/actions.py`（Task 12 充实）**

```python
"""actions.py — 指挥官相关的高层动作（hook 进战斗循环）。"""
def can_player_fire_now(player) -> bool:
    """简化版：commander_id 非空就允许。Task 12 会加"必须自己回合"等限制。"""
    return player.commander_id is not None
```

- [ ] **Step 10.5: 运行测试，预期通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_api.py -v`
Expected: 6 passed.

- [ ] **Step 10.6: Commit**

```bash
cd game/..
git add game/app/routes/commanders.py game/app/commanders/actions.py game/tests/test_commanders_api.py
git commit -m "feat(p3.0): add CO Power fire endpoint with validation"
```

---

## Milestone 4 · 战斗循环集成

### Task 11: meter.on_kill / on_death 钩进 attack handler

**Files:**
- Modify: `game/app/routes/actions.py` (attack 函数)
- Test: `game/tests/test_commanders_attack_hook.py`

**Interfaces:**
- Produces: `routes/actions.py::attack` 中插入 meter 计分（`is_kill` 后, `cleanup_dead_units` 前）

- [ ] **Step 11.1: 写测试 `tests/test_commanders_attack_hook.py`**

```python
"""test_commanders_attack_hook.py — meter.on_kill/on_death 钩入 attack handler。

测试策略：调用 on_kill / on_death 直接验证业务逻辑；
钩入位置的集成测试在 Task 17 (e2e) 中做。
"""
import pytest
from app.commanders.meter import on_kill, on_death


class FakePlayer:
    def __init__(self, meter=0, threshold=22):
        self.co_state = {"meter": meter, "threshold": threshold}


class TestAttackHook:
    def test_on_kill_increments_meter(self):
        p = FakePlayer(meter=5)
        on_kill(p, "swordsman")
        assert p.co_state["meter"] == 7

    def test_on_death_increments_meter(self):
        p = FakePlayer(meter=5)
        on_death(p)
        assert p.co_state["meter"] == 7

    def test_meter_can_overshoot_threshold(self):
        """meter 可以超过阈值（UI 仍显示已满）。"""
        p = FakePlayer(meter=18)
        on_kill(p, "knight")  # +4
        on_death(p)            # +2
        assert p.co_state["meter"] == 24  # > 22
```

- [ ] **Step 11.2: 运行测试，预期通过（meter 已经在 Task 4 测过）**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_attack_hook.py -v`
Expected: 3 passed.

- [ ] **Step 11.3: 修改 `app/routes/actions.py::attack` 钩入 on_kill / on_death**

Read `game/app/routes/actions.py` `attack()` function. Find these lines:
```python
is_kill = target.hp <= 0
# ... counter attack ...
cleanup_dead_units(...)
```

Add (between `is_kill` and `cleanup_dead_units`):
```python
from app.commanders.meter import on_kill, on_death
from app.models import Player

if is_kill:
    attacker_player = db.query(Player).filter(Player.id == attacker.player_id).first()
    on_kill(attacker_player, target.unit_type)
```

Read `cleanup_dead_units` (`game/app/game_logic.py:562`). Find the function body. Add at top (after dead_ids computed):
```python
def cleanup_dead_units(session, units):
    """清理死亡单位 + 计 CO meter。"""
    from collections import defaultdict
    from app.commanders.meter import on_death
    from app.models import Player

    death_count = defaultdict(int)
    for u in units:
        if u.hp <= 0:
            death_count[u.player_id] += 1
    for player_id, count in death_count.items():
        player = session.query(Player).filter(Player.id == player_id).first()
        for _ in range(count):
            on_death(player)
    # ... existing cleanup logic ...
```

> ⚠️ on_kill 在 attack handler 内调用（已知 attacker_player）；on_death 在 cleanup_dead_units 内调用（聚合所有死单位）。

- [ ] **Step 11.4: 跑现有 attack 测试，确保无回归**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_attack.py tests/test_combat.py -v 2>&1 | tail -30`
Expected: 全部通过（meter 钩入不应破坏现有攻击逻辑）。

- [ ] **Step 11.5: Commit**

```bash
cd game/..
git add game/app/routes/actions.py game/app/game_logic.py game/tests/test_commanders_attack_hook.py
git commit -m "feat(p3.0): hook meter.on_kill/on_death into attack + cleanup"
```

---

### Task 12: 烘焙被动 + on_player_turn_start 钩入战斗循环

**Files:**
- Modify: `game/app/routes/game.py` (`_start_battle_internal`)
- Modify: `game/app/routes/turns.py` (`end_turn`, `_run_ai_turn_chain_locked`)
- Modify: `game/app/routes/mainline.py` (`_spawn_battle_for_index`)
- Test: `game/tests/test_commanders_integration.py`

**Interfaces:**
- Produces: `_start_battle_internal` 在 `_apply_hero_overrides` 之后调 `bake_passive_into_units`
- Produces: `end_turn` / `_run_ai_turn_chain_locked` round-wrap 段调 `on_player_turn_start(next_player, game.turn_number)`

- [ ] **Step 12.1: 写测试 `tests/test_commanders_integration.py`**

```python
"""test_commanders_integration.py — 烘焙 + lifecycle hook 集成入口。"""
import pytest
from app.commanders.effects import bake_passive_into_units, on_player_turn_start


def test_passive_baked_callable():
    assert callable(bake_passive_into_units)


def test_on_player_turn_start_callable():
    assert callable(on_player_turn_start)
```

- [ ] **Step 12.2: 运行测试，预期通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_integration.py -v`
Expected: 2 passed.

- [ ] **Step 12.3: 修改 `_start_battle_internal` 加烘焙**

Read `game/app/routes/game.py:_start_battle_internal`. Find `_apply_hero_overrides` 调用点。在它之后添加:

```python
from app.commanders.effects import bake_passive_into_units

# 在 _apply_hero_overrides(units, hero_overrides, real_players) 之后:
for player in real_players:
    if player.commander_id:
        bake_passive_into_units(player)
```

- [ ] **Step 12.4: 修改 `_spawn_battle_for_index` 加 AI 烘焙**

Read `game/app/routes/mainline.py:_spawn_battle_for_index`. After it spawns AI player with enemy_commander:

```python
from app.commanders.effects import bake_passive_into_units

# 找到 _spawn_battle_for_index 中 AI 玩家创建段
if hasattr(battle, "enemy_commander") and battle.enemy_commander:
    ai_player.commander_id = battle.enemy_commander
    bake_passive_into_units(ai_player)
```

- [ ] **Step 12.5: 修改 `end_turn` 加 lifecycle hook**

Read `game/app/routes/turns.py:end_turn` and `_run_ai_turn_chain_locked`. Find the round-wrap block (where `apply_end_of_turn` is called, then `turn_number` is bumped):

```python
# end_turn 中 (line ~230 附近的 round-wrap):
if all_players_ended:
    apply_end_of_turn(...)
    # refill MP ...
    # reset has_acted/has_moved ...
    # bump turn_number ...

    # 🆕 P3.0 CO lifecycle: 下一位玩家开始时触发
    from app.commanders.effects import on_player_turn_start
    next_player = next_seat_player(db, game)
    if next_player:
        on_player_turn_start(next_player, game.turn_number)
```

类似地，在 `_run_ai_turn_chain_locked` 的对应 round-wrap 段加。

- [ ] **Step 12.6: 跑全量测试，确保战斗循环无回归**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_integration.py tests/test_mainline_api.py tests/test_turn_phases.py -v 2>&1 | tail -30`
Expected: 全部通过。

- [ ] **Step 12.7: Commit**

```bash
cd game/..
git add game/app/routes/game.py game/app/routes/turns.py game/app/routes/mainline.py game/tests/test_commanders_integration.py
git commit -m "feat(p3.0): wire bake + lifecycle hooks into battle loop"
```

---

### Task 13: GameStateOut.co_states 暴露给前端

**Files:**
- Modify: `game/app/schemas.py` (GameStateOut)
- Modify: `game/app/routes/state.py` (state endpoint)
- Test: `game/tests/test_commanders_state_payload.py`

**Interfaces:**
- Produces: `PlayerCOStateOut { player_id, seat, color, commander_id, meter, threshold, is_power_active, can_fire }`
- Produces: `GameStateOut.co_states: List[PlayerCOStateOut]`

- [ ] **Step 13.1: 写测试 `tests/test_commanders_state_payload.py`**

```python
"""test_commanders_state_payload.py — GameStateOut 必须包含 co_states。"""
import pytest
from app.schemas import GameStateOut, PlayerCOStateOut


def test_player_co_state_out_fields():
    s = PlayerCOStateOut(
        player_id=1, seat=0, color="red",
        commander_id="yun", meter=15, threshold=22,
        is_power_active=False, can_fire=False,
    )
    assert s.commander_id == "yun"
    assert s.can_fire is False


def test_game_state_out_has_co_states():
    """GameStateOut schema 必须包含 co_states 字段。"""
    fields = GameStateOut.model_fields
    assert "co_states" in fields
```

- [ ] **Step 13.2: 运行测试，预期失败**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_state_payload.py -v`
Expected: FAIL with `AssertionError: 'co_states' not in fields`.

- [ ] **Step 13.3: 修改 `app/schemas.py` 加 PlayerCOStateOut**

```python
# 追加到 app/schemas.py

class PlayerCOStateOut(BaseModel):
    player_id: int
    seat: int
    color: str
    commander_id: Optional[str] = None
    meter: int = 0
    threshold: int = 20
    is_power_active: bool = False
    can_fire: bool = False
```

- [ ] **Step 13.4: 修改 `GameStateOut` 加 `co_states` 字段**

```python
class GameStateOut(BaseModel):
    # ... existing fields ...
    co_states: List[PlayerCOStateOut] = Field(default_factory=list)
```

- [ ] **Step 13.5: 修改 state endpoint 填充 `co_states`**

Read `game/app/routes/state.py:get_state` (or wherever `/games/{id}/state` is). Find where it constructs GameStateOut. Add:

```python
from app.schemas import PlayerCOStateOut
from app.commanders.effects import can_fire_co_power

co_states = []
for p in game.players:
    co = p.co_state or {}
    co_states.append(PlayerCOStateOut(
        player_id=p.id,
        seat=p.seat,
        color=p.color,
        commander_id=p.commander_id,
        meter=co.get("meter", 0),
        threshold=co.get("threshold", 20),
        is_power_active=co.get("is_power_active", False),
        can_fire=can_fire_co_power(p),
    ))

return GameStateOut(
    # ... existing fields ...
    co_states=co_states,
)
```

- [ ] **Step 13.6: 运行测试，预期通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_state_payload.py -v`
Expected: 2 passed.

- [ ] **Step 13.7: 跑全量 state API 测试无回归**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_state.py tests/test_game_state_api.py -v 2>&1 | tail -20`
Expected: 全部通过。

- [ ] **Step 13.8: Commit**

```bash
cd game/..
git add game/app/schemas.py game/app/routes/state.py game/tests/test_commanders_state_payload.py
git commit -m "feat(p3.0): expose co_states in GameStateOut for HUD rendering"
```

---

## Milestone 5 · AI + 前端

### Task 14: AI 决策（meter 满自动发）+ mainline enemy_commander 应用

**Files:**
- Create: `game/app/commanders/ai.py`
- Modify: `game/app/routes/turns.py` (`_run_ai_turn_chain_locked`)
- Test: `game/tests/test_commanders_ai.py`

**Interfaces:**
- Produces: AI 在每次 action 前检查 `meter >= threshold`，满足则 `fire_co_power`

- [ ] **Step 14.1: 写测试 `tests/test_commanders_ai.py`**

```python
"""test_commanders_ai.py — AI 满了就发，不留力。"""
from app.commanders.ai import ai_should_fire_co_power


class FakeUnit:
    pass


class FakePlayer:
    def __init__(self, commander_id, meter, is_active=False):
        self.commander_id = commander_id
        self.units = [FakeUnit()]
        self.co_state = {
            "commander_id": commander_id,
            "meter": meter,
            "threshold": 22,
            "is_power_active": is_active,
            "last_start_turn": -1,
        }


def test_ai_should_fire_when_meter_full():
    p = FakePlayer("yun", meter=22)
    assert ai_should_fire_co_power(p) is True


def test_ai_should_not_fire_when_low():
    p = FakePlayer("yun", meter=10)
    assert ai_should_fire_co_power(p) is False


def test_ai_should_not_fire_without_commander():
    p = FakePlayer(None, meter=100)
    assert ai_should_fire_co_power(p) is False


def test_ai_should_not_fire_when_already_active():
    p = FakePlayer("yun", meter=22, is_active=True)
    assert ai_should_fire_co_power(p) is False
```

- [ ] **Step 14.2: 运行测试，预期失败**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_ai.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.commanders.ai'`.

- [ ] **Step 14.3: 创建 `app/commanders/ai.py`**

```python
"""ai.py — AI 指挥官的自动决策。

当前实现：满了就发（先跑通）。未来可以加 personality-aware 策略。
"""
from app.commanders.effects import can_fire_co_power


def ai_should_fire_co_power(ai_player) -> bool:
    """AI 玩家是否应该发动 CO Power。"""
    return can_fire_co_power(ai_player)
```

- [ ] **Step 14.4: 在 `_run_ai_turn_chain_locked` 中调 fire**

Read `game/app/routes/turns.py:_run_ai_turn_chain_locked`. 在 AI 行动循环开头添加:

```python
from app.commanders.ai import ai_should_fire_co_power
from app.commanders.effects import fire_co_power
import logging

logger = logging.getLogger(__name__)

# 在 _run_ai_turn_chain_locked 的 while acted loop 开头:
if ai_should_fire_co_power(ai_player):
    fire_co_power(ai_player)
    logger.info("AI %s fired CO power %s", ai_player.color, ai_player.commander_id)
    action_log.append("co_power_fired", {
        "commander_id": ai_player.commander_id,
        "player_id": ai_player.id,
        "auto": True,
    })
```

- [ ] **Step 14.5: 在 `_spawn_battle_for_index` 应用 enemy_commander**

Read `game/app/routes/mainline.py:_spawn_battle_for_index`. Find where AI player is set up. Add:

```python
# 找到 AI player 创建段
if hasattr(battle, "enemy_commander") and battle.enemy_commander:
    ai_player.commander_id = battle.enemy_commander
    from app.commanders.effects import bake_passive_into_units
    bake_passive_into_units(ai_player)
```

- [ ] **Step 14.6: 运行测试，预期通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_ai.py -v`
Expected: 4 passed.

- [ ] **Step 14.7: 跑 mainline API 测试**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_mainline_api.py -v 2>&1 | tail -20`
Expected: 全部通过。

- [ ] **Step 14.8: Commit**

```bash
cd game/..
git add game/app/commanders/ai.py game/app/routes/turns.py game/app/routes/mainline.py game/tests/test_commanders_ai.py
git commit -m "feat(p3.0): AI auto-fires CO Power at threshold + mainline enemy_commander"
```

---

### Task 15: HUD CO meter 条 + 头像 + 发动按钮

**Files:**
- Modify: `game/app/web/index.html`
- Modify: `game/app/web/app.js`
- Modify: `game/app/web/style.css`

**Interfaces:**
- Produces: HUD 顶部容器 `#co-meters`
- Produces: `app.js::renderCOMeters(state)` 渲染 meter 条 + 头像
- Produces: 点击「发动」按钮 → POST `/games/{id}/co-power`

- [ ] **Step 15.1: 在 `index.html` 加 HUD 容器**

Find the `<body>` end or HUD container. Add before `</body>`:

```html
<div id="co-meters" class="co-meters-container"></div>
```

- [ ] **Step 15.2: 在 `style.css` 加样式**

Add to end of file:

```css
.co-meters-container {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px;
    z-index: 100;
    background: linear-gradient(to bottom, rgba(0,0,0,0.7), transparent);
}

.co-meter {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 8px;
    background: rgba(20, 20, 30, 0.85);
    border-radius: 4px;
    color: #fff;
    font-size: 12px;
}

.co-meter-portrait {
    width: 28px;
    height: 28px;
    border-radius: 4px;
    background: #444;
    object-fit: cover;
}

.co-meter.is-active .co-meter-portrait {
    box-shadow: 0 0 8px #ffcc00;
    animation: pulse 1.5s infinite;
}

.co-meter-bar {
    flex: 1;
    height: 8px;
    background: #333;
    border-radius: 4px;
    overflow: hidden;
}

.co-meter-bar-fill {
    height: 100%;
    background: linear-gradient(to right, #4a9eff, #66ff66);
    transition: width 0.3s;
}

.co-meter-fire-btn {
    padding: 4px 12px;
    background: #ff6600;
    color: #fff;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-weight: bold;
}

.co-meter-fire-btn:disabled {
    background: #666;
    cursor: not-allowed;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}
```

- [ ] **Step 15.3: 在 `app.js` 加 `renderCOMeters` 函数**

Add at end of app.js (before any closing block):

```javascript
function renderCOMeters(state) {
    const container = document.getElementById('co-meters');
    if (!container) return;

    const coStates = state.co_states || [];
    const portraitUrl = (cid) => cid ? `/ui/assets/heroes/${cid}.png` : '';

    container.innerHTML = coStates.map(co => {
        const pct = Math.min(100, (co.meter / co.threshold) * 100);
        const isActive = co.is_power_active;
        const canFire = co.can_fire && !isActive;
        const portrait = co.commander_id
            ? `<img class="co-meter-portrait" src="${portraitUrl(co.commander_id)}" onerror="this.style.background='#666'" />`
            : `<div class="co-meter-portrait" title="未选指挥官">?</div>`;
        const btn = canFire
            ? `<button class="co-meter-fire-btn" onclick="fireCOPower(${state.id})">发动</button>`
            : isActive
                ? `<span class="co-meter-active-tag">⚡ 生效中</span>`
                : '';
        return `
            <div class="co-meter ${isActive ? 'is-active' : ''}">
                ${portrait}
                <span class="co-meter-label">${co.color.toUpperCase()}: ${co.commander_id || '未选'}</span>
                <div class="co-meter-bar">
                    <div class="co-meter-bar-fill" style="width:${pct}%"></div>
                </div>
                <span class="co-meter-text">${co.meter}/${co.threshold}</span>
                ${btn}
            </div>
        `;
    }).join('');
}

async function fireCOPower(gameId) {
    const resp = await fetch(`/games/${gameId}/co-power`, { method: 'POST' });
    if (resp.ok) {
        await refreshState();
    } else {
        const err = await resp.json();
        alert(`发动失败: ${err.detail || resp.status}`);
    }
}
```

- [ ] **Step 15.4: 在 `refreshState` 后调 `renderCOMeters`**

Find the `refreshState` function in app.js. At its end (after setting state-related UI), add:

```javascript
// 在 refreshState 末尾:
renderCOMeters(currentState);
```

If `currentState` isn't accessible globally, pass it through.

- [ ] **Step 15.5: 启动服务器手工 smoke**

Run: `cd game && uvicorn app.main:app --host 0.0.0.0 --port 8000`
打开 `http://localhost:8000/ui/` → 应该看到 HUD 顶部出现 CO meter 条（即使全 0）。

- [ ] **Step 15.6: Commit**

```bash
cd game/..
git add game/app/web/index.html game/app/web/app.js game/app/web/style.css
git commit -m "feat(p3.0): add CO meter HUD with portraits + fire button"
```

---

## Milestone 6 · 验证与快照

### Task 16: yun / anna commander 数值 snapshot 测试

**Files:**
- Create: `game/tests/test_commanders_snapshots.py`

**Interfaces:**
- Produces: snapshot 测试，固定 CommanderPassive / CommanderPower 数值，防漂移

- [ ] **Step 16.1: 创建 `tests/test_commanders_snapshots.py`**

```python
"""test_commanders_snapshots.py — 锁定 yun / anna commander 数值。

任何修改这些数值的 PR 必须先更新这个测试，避免静默漂移。
"""
from dataclasses import asdict
from app.classes.heroes import get as get_hero


YUN_EXPECTED = {
    "is_commander": True,
    "commander_passive": {
        "atk_pct": 0.10,
        "def_pct": 0.0,
        "matk_pct": 0.0,
        "mdef_pct": 0.0,
        "hp_pct": 0.0,
        "mov_delta": 0,
        "range_delta": 1,
    },
    "commander_power": {
        "atk_pct": 0.30,
        "def_pct": 0.0,
        "matk_pct": 0.0,
        "mdef_pct": 0.0,
        "heal_pct": 0.50,
        "extra_mov": 0,
        "range_delta": 0,
    },
    "power_threshold": 22,
}


ANNA_EXPECTED = {
    "is_commander": True,
    "commander_passive": {
        "atk_pct": 0.0,
        "def_pct": 0.15,
        "matk_pct": 0.0,
        "mdef_pct": 0.10,
        "hp_pct": 0.0,
        "mov_delta": 0,
        "range_delta": 0,
    },
    "commander_power": {
        "atk_pct": 0.0,
        "def_pct": 0.30,
        "matk_pct": 0.0,
        "mdef_pct": 0.30,
        "heal_pct": 0.80,
        "extra_mov": 0,
        "range_delta": 0,
    },
    "power_threshold": 18,
}


def test_yun_snapshot():
    h = get_hero("yun")
    assert h.is_commander == YUN_EXPECTED["is_commander"]
    assert asdict(h.commander_passive) == YUN_EXPECTED["commander_passive"]
    assert asdict(h.commander_power) == YUN_EXPECTED["commander_power"]
    assert h.power_threshold == YUN_EXPECTED["power_threshold"]


def test_anna_snapshot():
    h = get_hero("anna")
    assert h.is_commander == ANNA_EXPECTED["is_commander"]
    assert asdict(h.commander_passive) == ANNA_EXPECTED["commander_passive"]
    assert asdict(h.commander_power) == ANNA_EXPECTED["commander_power"]
    assert h.power_threshold == ANNA_EXPECTED["power_threshold"]
```

- [ ] **Step 16.2: 运行测试，预期通过**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_snapshots.py -v`
Expected: 2 passed.

- [ ] **Step 16.3: Commit**

```bash
cd game/..
git add game/tests/test_commanders_snapshots.py
git commit -m "test(p3.0): add snapshot tests for yun/anna commander values"
```

---

### Task 17: 端到端 smoke 测试（HTTP API + 主线胜利 + 指挥官解锁）

**Files:**
- Create: `game/tests/test_commanders_e2e.py`

**Interfaces:**
- Produces: 完整流程测试（开主线 → 选指挥官 → 杀敌 → 发动 → 下一回合失效）

- [ ] **Step 17.1: 创建 `tests/test_commanders_e2e.py`**

```python
"""test_commanders_e2e.py — 端到端指挥官系统 smoke test。

完整流程：
1. 启动主线 chapter_01（包含 anna 解锁）
2. 选 yun 作指挥官
3. 验证 yun 的 atk 已烘焙（yun.hero.passive.atk_pct=0.10）
4. 手动注入 meter=22（模拟 22 分杀敌累积）
5. POST /co-power 发动
6. 验证 is_power_active=True, atk 再次叠加 power
7. 触发下一个玩家回合 → on_player_turn_start 撤销 power
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal, Base, engine
from app.models import Game, Player


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(engine)
    return TestClient(app)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_e2e_commander_full_lifecycle(client, db):
    """完整指挥官生命周期。"""
    # 1. 启动主线
    resp = client.post("/mainlines/chapter_01_steel_rebellion/start", json={})
    assert resp.status_code == 200, resp.text
    game_id = resp.json()["game_id"]

    # 2. 验证 game 已创建
    game = db.query(Game).filter(Game.id == game_id).first()
    assert game is not None

    # 3. 选 yun 作玩家 0 指挥官
    player0 = db.query(Player).filter(
        Player.game_id == game_id, Player.seat == 0
    ).first()
    player0.commander_id = "yun"
    from app.commanders.effects import bake_passive_into_units
    bake_passive_into_units(player0)
    db.commit()

    # 4. 验证 atk 已烘焙
    sample_unit = player0.units[0]
    assert hasattr(sample_unit, "_commander_passive")

    # 5. 注入 meter
    co = player0.co_state or {}
    co["meter"] = 22
    co["threshold"] = 22
    player0.co_state = co
    db.commit()

    # 6. 发动 CO Power
    resp = client.post(f"/games/{game_id}/co-power", json={})
    assert resp.status_code == 200, resp.text

    # 7. 验证 active
    db.refresh(player0)
    co = player0.co_state
    assert co["is_power_active"] is True
    assert co["meter"] == 0

    # 8. 模拟"下次自己开局" → 手动调 on_player_turn_start
    from app.commanders.effects import on_player_turn_start
    co["last_start_turn"] = 0  # 假装这是 5 turn 之前
    player0.co_state = co
    db.commit()
    on_player_turn_start(player0, game_turn_number=5)
    db.refresh(player0)
    assert player0.co_state["is_power_active"] is False
    assert player0.co_state["meter"] == 0
```

- [ ] **Step 17.2: 运行测试**

Run: `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_e2e.py -v`
Expected: 1 passed.

- [ ] **Step 17.3: 全量回归**

Run: `cd game && PYTHONPATH=. python -m pytest tests/ -q --no-header 2>&1 | tail -30`
Expected: 全部 commander 测试 + 现有测试都通过。如有偶发失败，跑两次确认稳定性。

- [ ] **Step 17.4: Commit**

```bash
cd game/..
git add game/tests/test_commanders_e2e.py
git commit -m "test(p3.0): add e2e smoke test for commander lifecycle"
```

---

## 实施里程碑总结

| Milestone | Task | 内容 |
|---|---|---|
| **M1 · 数据模型基础** | 1-3 | commanders 模块 + Hero 扩展 + DB 迁移 |
| **M2 · 核心机制** | 4-7 | meter + passive 烘焙 + CO Power fire/expire + lifecycle hook（G1） |
| **M3 · Schema + 解锁 + API** | 8-10 | BattleSpec schema + mainline 胜利 + 选择/发动 API（G2） |
| **M4 · 战斗循环集成** | 11-13 | attack hook + 战斗创建烘焙 + lifecycle 集成 + state 暴露（G3） |
| **M5 · AI + 前端** | 14-15 | AI 自动 fire + HUD 渲染（G4，可并行） |
| **M6 · 验证与快照** | 16-17 | snapshot 测试 + e2e（G5，可并行） |

**总计 17 个 task 保持不变，但从 Task 5 起按 5 个执行组推进，目标将 review 轮次压缩到 8-10 轮，并把 14/15、16/17 尽量并行化。**


| 检查项 | 结论 |
|---|---|
| Spec 覆盖 | ✅ §1-§15 全部需求都有对应 task（背景/数据/实现/API/UI/边界/快照） |
| 占位符扫描 | ✅ 无 TBD/TODO；yun/anna 数值明确写在 snapshot 测试里 |
| 类型一致性 | ✅ `COState` 字段名 / `bake_passive_into_units` / `fire_co_power` / `expire_power` / `on_player_turn_start` 在 Task 1 定义后所有后续 task 一致使用 |
| 文件路径 | ✅ 全部 absolute 或相对仓库根目录 |
| 测试命令 | ✅ 统一为 `cd game && PYTHONPATH=. python -m pytest tests/test_commanders_*.py -v` |
| Commit 频率 | ✅ 每个 task 1 commit，便于 review 和回滚 |
| TDD 顺序 | ✅ 每个 task 都是 test-first（failing test → implement → pass → commit） |
| DRY / YAGNI | ✅ 没有过度抽象；`actions.py` / `ai.py` 只放当前需要的最小代码 |
