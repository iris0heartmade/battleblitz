# Hero / Mercenary Dual-Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a clean dual-track architecture where campaign Heroes use FE-style persistent growth while Mercenaries use chapter-driven roster and allocation rules without inheriting Hero progression logic.

**Architecture:** Keep `app/progression/` as the persistence and campaign orchestration layer, introduce a new Hero battle-core package for FE-style templates and runtime state, and introduce a separate Mercenary package for chapter balance, recruitment, and allocation. Integrate mainline battle spawning through these new domain objects instead of continuing to overload `routes/game.py` hero override logic.

**Tech Stack:** Python, FastAPI, SQLAlchemy async ORM, Pydantic, existing `mainline/`, `progression/`, and `classes/heroes/` packages.

---

### Task 1: Create Hero Domain Package Skeleton

**Files:**
- Create: `game/app/hero_domain/__init__.py`
- Create: `game/app/hero_domain/templates.py`
- Create: `game/app/hero_domain/state.py`
- Test: `game/tests/test_hero_domain_models.py`

- [ ] **Step 1: Write the failing test**

```python
from app.hero_domain.templates import HeroCharacterTemplate, HeroClassTemplate
from app.hero_domain.state import HeroCampaignState


def test_hero_campaign_state_can_be_built_from_templates():
    char = HeroCharacterTemplate(
        hero_id="yun",
        default_class_id="warlock",
        base_stats={"hp": 45, "atk": 8, "def": 10, "matk": 22, "mdef": 12},
        growth_rates={"hp": 70, "atk": 35, "def": 25, "matk": 55, "mdef": 30},
        base_weapon_ranks={"anima": 1},
    )
    cls = HeroClassTemplate(
        class_id="warlock",
        tier=1,
        base_modifiers={"hp": 0, "atk": 0, "def": 0, "matk": 0, "mdef": 0},
        caps={"hp": 60, "atk": 30, "def": 24, "matk": 34, "mdef": 28},
        promotion_options=["sage"],
        promotion_bonuses={"hp": 3, "matk": 2},
    )
    state = HeroCampaignState.from_templates(char, cls)
    assert state.hero_id == "yun"
    assert state.class_id == "warlock"
    assert state.level == 1
    assert state.exp == 0
    assert state.base_stats["matk"] == 22
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd game && pytest tests/test_hero_domain_models.py::test_hero_campaign_state_can_be_built_from_templates -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.hero_domain'`

- [ ] **Step 3: Write minimal implementation**

```python
# game/app/hero_domain/templates.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class HeroCharacterTemplate:
    hero_id: str
    default_class_id: str
    base_stats: dict[str, int]
    growth_rates: dict[str, int]
    base_weapon_ranks: dict[str, int]


@dataclass(frozen=True)
class HeroClassTemplate:
    class_id: str
    tier: int
    base_modifiers: dict[str, int]
    caps: dict[str, int]
    promotion_options: list[str]
    promotion_bonuses: dict[str, int]
```

```python
# game/app/hero_domain/state.py
from __future__ import annotations
from dataclasses import dataclass, field

from app.hero_domain.templates import HeroCharacterTemplate, HeroClassTemplate


@dataclass
class HeroCampaignState:
    hero_id: str
    class_id: str
    level: int
    exp: int
    base_stats: dict[str, int]
    weapon_ranks: dict[str, int] = field(default_factory=dict)
    learned_skills: list[str] = field(default_factory=list)
    promoted: bool = False

    @classmethod
    def from_templates(
        cls,
        character: HeroCharacterTemplate,
        hero_class: HeroClassTemplate,
    ) -> "HeroCampaignState":
        return cls(
            hero_id=character.hero_id,
            class_id=hero_class.class_id,
            level=1,
            exp=0,
            base_stats=dict(character.base_stats),
            weapon_ranks=dict(character.base_weapon_ranks),
        )
```

```python
# game/app/hero_domain/__init__.py
from app.hero_domain.templates import HeroCharacterTemplate, HeroClassTemplate
from app.hero_domain.state import HeroCampaignState

__all__ = [
    "HeroCharacterTemplate",
    "HeroClassTemplate",
    "HeroCampaignState",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd game && pytest tests/test_hero_domain_models.py::test_hero_campaign_state_can_be_built_from_templates -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add game/app/hero_domain/__init__.py game/app/hero_domain/templates.py game/app/hero_domain/state.py game/tests/test_hero_domain_models.py
git commit -m "feat: add hero domain model skeleton"
```

### Task 2: Create Mercenary Domain Package Skeleton

**Files:**
- Create: `game/app/mercenary_domain/__init__.py`
- Create: `game/app/mercenary_domain/templates.py`
- Create: `game/app/mercenary_domain/state.py`
- Test: `game/tests/test_mercenary_domain_models.py`

- [ ] **Step 1: Write the failing test**

```python
from app.mercenary_domain.templates import MercenaryTemplate, ChapterBalanceConfig
from app.mercenary_domain.state import CommanderAllocation


def test_commander_allocation_tracks_spent_points():
    allocation = CommanderAllocation(total_points=100)
    allocation.add_upgrade("infantry", "atk", 1, 10)
    assert allocation.spent_points == 10
    assert allocation.unit_type_upgrades["infantry"]["atk"] == 1


def test_chapter_balance_config_defaults_enemy_modifiers():
    cfg = ChapterBalanceConfig()
    assert cfg.enemy_modifiers["attack"] == 0
    assert cfg.enemy_modifiers["defense"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd game && pytest tests/test_mercenary_domain_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.mercenary_domain'`

- [ ] **Step 3: Write minimal implementation**

```python
# game/app/mercenary_domain/templates.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MercenaryTemplate:
    unit_type: str
    base_stats: dict[str, int]
    recruit_cost: int
    default_skills: list[str] = field(default_factory=list)


@dataclass
class ChapterBalanceConfig:
    enemy_modifiers: dict[str, int] = field(
        default_factory=lambda: {
            "attack": 0,
            "defense": 0,
            "income": 0,
            "move": 0,
            "vision": 0,
        }
    )
```

```python
# game/app/mercenary_domain/state.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class CommanderAllocation:
    total_points: int = 100
    spent_points: int = 0
    unit_type_upgrades: dict[str, dict[str, int]] = field(default_factory=dict)

    def add_upgrade(self, unit_type: str, stat: str, value: int, cost: int) -> None:
        if self.spent_points + cost > self.total_points:
            raise ValueError("points exceeded")
        bucket = self.unit_type_upgrades.setdefault(unit_type, {})
        bucket[stat] = bucket.get(stat, 0) + value
        self.spent_points += cost
```

```python
# game/app/mercenary_domain/__init__.py
from app.mercenary_domain.templates import MercenaryTemplate, ChapterBalanceConfig
from app.mercenary_domain.state import CommanderAllocation

__all__ = [
    "MercenaryTemplate",
    "ChapterBalanceConfig",
    "CommanderAllocation",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd game && pytest tests/test_mercenary_domain_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add game/app/mercenary_domain/__init__.py game/app/mercenary_domain/templates.py game/app/mercenary_domain/state.py game/tests/test_mercenary_domain_models.py
git commit -m "feat: add mercenary domain model skeleton"
```

### Task 3: Introduce Campaign-Persistent Hero State Model

**Files:**
- Modify: `game/app/progression/models.py`
- Create: `game/tests/test_progression_hero_campaign_state.py`

- [ ] **Step 1: Write the failing test**

```python
from app.progression.models import PlayerProfile


def test_player_profile_has_hero_campaign_states_json():
    profile = PlayerProfile(user_name="tester")
    assert isinstance(profile.hero_campaign_states, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd game && pytest tests/test_progression_hero_campaign_state.py::test_player_profile_has_hero_campaign_states_json -v`
Expected: FAIL with `AttributeError: 'PlayerProfile' object has no attribute 'hero_campaign_states'`

- [ ] **Step 3: Write minimal implementation**

```python
# in game/app/progression/models.py inside PlayerProfile
hero_campaign_states: Mapped[dict] = mapped_column(
    JSON, nullable=False, default=dict
)
mercenary_roster_state: Mapped[dict] = mapped_column(
    JSON, nullable=False, default=dict
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd game && pytest tests/test_progression_hero_campaign_state.py::test_player_profile_has_hero_campaign_states_json -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add game/app/progression/models.py game/tests/test_progression_hero_campaign_state.py
git commit -m "feat: add dual-track persistence fields to player profile"
```

### Task 4: Add Hero Materialization Helper for Mainline Battles

**Files:**
- Create: `game/app/hero_domain/materialize.py`
- Create: `game/tests/test_hero_materialize.py`

- [ ] **Step 1: Write the failing test**

```python
from app.hero_domain.materialize import build_hero_battle_state
from app.hero_domain.state import HeroCampaignState


def test_build_hero_battle_state_resets_temporary_resources():
    state = HeroCampaignState(
        hero_id="yun",
        class_id="warlock",
        level=7,
        exp=40,
        base_stats={"hp": 52, "atk": 18, "def": 11, "matk": 28, "mdef": 13, "mov": 4, "mp": 8},
        weapon_ranks={"anima": 2},
    )
    battle = build_hero_battle_state(state, x=3, y=4, player_id=1)
    assert battle.current_hp == 52
    assert battle.current_mp == 8
    assert battle.x == 3
    assert battle.y == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd game && pytest tests/test_hero_materialize.py::test_build_hero_battle_state_resets_temporary_resources -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write minimal implementation**

```python
# game/app/hero_domain/materialize.py
from __future__ import annotations
from dataclasses import dataclass

from app.hero_domain.state import HeroCampaignState


@dataclass
class HeroBattleState:
    hero_id: str
    class_id: str
    level: int
    exp: int
    current_hp: int
    current_mp: int
    x: int
    y: int
    player_id: int


def build_hero_battle_state(
    state: HeroCampaignState,
    *,
    x: int,
    y: int,
    player_id: int,
) -> HeroBattleState:
    return HeroBattleState(
        hero_id=state.hero_id,
        class_id=state.class_id,
        level=state.level,
        exp=state.exp,
        current_hp=state.base_stats["hp"],
        current_mp=state.base_stats["mp"],
        x=x,
        y=y,
        player_id=player_id,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd game && pytest tests/test_hero_materialize.py::test_build_hero_battle_state_resets_temporary_resources -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add game/app/hero_domain/materialize.py game/tests/test_hero_materialize.py
git commit -m "feat: add hero battle materialization helper"
```

### Task 5: Add Free-Mode Hero Preset Policy

**Files:**
- Create: `game/app/hero_domain/free_mode.py`
- Create: `game/tests/test_free_mode_hero_policy.py`

- [ ] **Step 1: Write the failing test**

```python
from app.hero_domain.free_mode import build_standardized_hero_state


def test_standardized_free_mode_hero_does_not_depend_on_campaign_growth():
    state = build_standardized_hero_state(
        hero_id="yun",
        class_id="warlock",
        preset_level=5,
    )
    assert state.level == 5
    assert state.exp == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd game && pytest tests/test_free_mode_hero_policy.py::test_standardized_free_mode_hero_does_not_depend_on_campaign_growth -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

```python
# game/app/hero_domain/free_mode.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class HeroPresetState:
    hero_id: str
    class_id: str
    level: int
    exp: int


def build_standardized_hero_state(
    *,
    hero_id: str,
    class_id: str,
    preset_level: int,
) -> HeroPresetState:
    return HeroPresetState(
        hero_id=hero_id,
        class_id=class_id,
        level=preset_level,
        exp=0,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd game && pytest tests/test_free_mode_hero_policy.py::test_standardized_free_mode_hero_does_not_depend_on_campaign_growth -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add game/app/hero_domain/free_mode.py game/tests/test_free_mode_hero_policy.py
git commit -m "feat: add standardized free-mode hero policy"
```

### Task 6: Connect Progression Service to Hero Campaign State Later

**Files:**
- Modify: `game/app/progression/service.py`
- Test: `game/tests/test_progression_hero_campaign_state.py`

- [ ] **Step 1: Write the failing test**

```python
def test_progression_service_exposes_hero_campaign_state_accessors():
    from app.progression.service import ProgressionService
    assert hasattr(ProgressionService, "get_hero_campaign_state")
    assert hasattr(ProgressionService, "set_hero_campaign_state")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd game && pytest tests/test_progression_hero_campaign_state.py::test_progression_service_exposes_hero_campaign_state_accessors -v`
Expected: FAIL because the methods do not exist

- [ ] **Step 3: Write minimal implementation**

```python
# in game/app/progression/service.py inside ProgressionService
    async def get_hero_campaign_state(
        self,
        user_name: str,
        hero_id: str,
    ) -> dict | None:
        profile = await self.profiles.get_by_name(user_name)
        if profile is None:
            return None
        states = dict(getattr(profile, "hero_campaign_states", {}) or {})
        return states.get(hero_id)

    async def set_hero_campaign_state(
        self,
        user_name: str,
        hero_id: str,
        state: dict,
    ) -> dict | None:
        profile = await self.profiles.get_by_name(user_name)
        if profile is None:
            return None
        states = dict(getattr(profile, "hero_campaign_states", {}) or {})
        states[hero_id] = state
        profile.hero_campaign_states = states
        await self.session.flush()
        return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd game && pytest tests/test_progression_hero_campaign_state.py::test_progression_service_exposes_hero_campaign_state_accessors -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add game/app/progression/service.py game/tests/test_progression_hero_campaign_state.py
git commit -m "feat: expose hero campaign state accessors"
```

---

## Self-Review

### Spec coverage

- Hero FE-style split: covered by Tasks 1 and 4.
- Mercenary separate system: covered by Task 2.
- Campaign persistence for Hero growth: covered by Tasks 3 and 6.
- Free-mode standardized Hero policy: covered by Task 5.
- Safe first scaffold without rewriting battle spawn: covered by task ordering.

### Placeholder scan

- No `TODO` / `TBD` placeholders remain in task steps.
- Each task names exact files and commands.
- Each code step contains concrete starter code.

### Type consistency

- `HeroCampaignState` is defined in Task 1 and re-used in Task 4.
- `hero_campaign_states` naming is consistent between Tasks 3 and 6.
- Mercenary allocation names are consistent inside Task 2.

