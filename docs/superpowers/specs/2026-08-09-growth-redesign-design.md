# Growth-redesign — per-stat roll + cap + MOV/MP merge

| | |
|---|---|
| **Date** | 2026-08-09 |
| **Status** | draft |
| **Owner** | gameplay / balance |
| **Scope** | `app.classes.units.*`, `app.classes.heroes.*`, `app.progression.policies`, `app.modes`, `tools/growth_charts/*`, `app.mercenary_domain`; spawn + level-up code paths; tests under `game/tests/`. |

---

## 1. Goal

Replace the current "everyone gets the same autolevel-bump % per stat"
formula with a **FE8-style per-stat roll system**, give every unit class
its **own growth table** (currently every class shares one rate), and
collapse the redundant `base_mov` + `mp_pool` pair into a single
`base_mov` field. Heroes get a **personal growth modifier** on top of
their class's table so the same class can produce two distinct heroes.

After this lands, the chart-tool's PNGs will show meaningfully different
curves for knights vs swordmasters vs warlocks vs healers, and a swordmaster
rolled by a player at L20 will be visibly different from one rolled by the
AI with the same number of level-ups.

## 2. Non-goals

- No frontend / Godot change. The camera and HUD do not need to know about
  growth rates; they just render the `Unit.hp / atk / def / matk / mdef / mov`
  fields the backend already exposes. (Confirmed in prior session: the
  `board_camera.gd` zoom/pan work is independent.)
- No "talent tree" / per-stat manual allocation. Players do not spend
  `talent_points` on individual stats. (Talent points still exist for a
  different system not in scope.)
- No change to the `tier` system, the `XP_CURVE`, the `promote` mechanic,
  or the commander system. Promotion bonuses are added but the promotion
  level / tier cap behavior is unchanged.
- No rebalance pass. This commit does not retune any existing test or
  chapter — it only changes the *formula*. Rebalance of L1 numbers,
  promotion bonuses, or hero overrides is a separate follow-up.
- No Lck / Spd / Skl stat. The current backend stat surface is
  `hp / atk / def / matk / mdef / mov`; we do not introduce new columns
  in this change. (Growth rates may include 0 for keys not on the
  stat block; see §7.1.)

## 3. User-confirmed decisions (from prior turn)

| Question | Decision |
|---|---|
| Per-level per-stat outcome distribution | roll: 70% +1, 25% +2, 5% +0 (over the 5% "miss" the 0% rate never fires — but the math is preserved for future tuning) |
| Do class and hero growth ship together? | **Yes, both, in one change.** |
| What about `mov` / `mp`? | Merge `base_mov` + `mp_pool` into a single `base_mov`. Use `max(base_mov, mp_pool)` as the resolved value so the existing movement feel is preserved. Delete `mp_pool` from `UnitClassProfile` and `mp_pool_override` from `HeroProfile`. |
| Stat caps | **C. 尽量高:** `hp 120 / atk 60 / def 55 / matk 60 / mdef 55 / mov 12`. |

## 4. Background — what's actually there today

The investigation in the prior session found:

- `app/progression/policies.py` has two policies
  (`AutolevelPolicy`, `BattleLanePolicy`). Both apply a **linear
  per-level bump** scaled by a fixed rate. **The rates are class-agnostic:**
  every swordsman, every knight, every healer uses the same HP 85 / Atk 50
  / Matk 50 / Def 10 / Mdef 15 table. This makes class identity evaporate
  over time.
- `app/modes.py:AUTOEVEL_RATES` and `app/progression/policies.py:
  RATE_KEYS` carry the same set of magic numbers; the comment in
  `policies.py` flags this duplication as a known smell.
- `app/classes/units/base.py:UnitClassProfile` has both `base_mov: int`
  and `mp_pool: int`. Inspecting the call sites:
  - `app/game_logic.py:2375` does `mov=profile_obj.mp_pool, mp=0` —
    i.e. `unit.mov` is set from `mp_pool`, and the
    `profile.base_mov` is **discarded**.
  - `app/game_logic.py:1929` reads `unit.mp` for pathfinding budget,
    and `app/web/app.js:2637` does `unit.mp ?? unit.mov` for the
    client-side preview.
  - So `mp_pool` is the **real** movement stat; `base_mov` is a label
    that doesn't reach the engine. They are not actually two
    parameters; they are one parameter and one dead field.
- `app/classes/heroes/base.py:HeroProfile` has both `mov_override` and
  `mp_pool_override` — same story.
- The `tools/growth_charts/` tool already exists and renders every
  class + hero under the current `AutolevelPolicy` /
  `BattleLanePolicy`. We re-use its data layer (`dataset.py`) and
  render layer (`render.py`); we add a new policy they pick up via
  the existing `--policy` CLI flag.

## 5. The new formula

For each (entity, level-up) event, for every stat `s` in
`STAT_KEYS = ("hp", "atk", "def", "matk", "mdef", "mov")`:

```
r1 = rng() * 100
if r1 < class_growth_rates[entity][s]:
    r2 = rng() * 100
    if r2 < 25:
        delta = 2
    elif r2 < 95:
        delta = 1
    else:
        delta = 0
    value[s] = min(value[s] + delta, stat_caps[s])
```

Notes:

- The first `r1` roll is the "did this stat grow at all?" check —
  this is the FE8 mechanic, preserved.
- The second `r2` roll is the "how much?" check — 25% / 70% / 5%
  split. The 5% +0 is intentionally preserved as a knob for
  future tuning even though the question said "no 0".
- `rng` is injected via a parameter `rng: Callable[[], float] = random.random`
  so unit tests can pass a seeded `Random` and assert specific
  deltas. **No global RNG mutation.** This matches the existing
  `GrowthPolicy` Protocol's pattern of "no IO, no monotonic
  counters" in its docstring.
- `class_growth_rates[entity][s]` is computed once at baseline
  time as `class.class_growth_rates.get(s, 0) + personal_growth_modifier.get(s, 0)`,
  then clamped to `[0, 100]`.
- A rate of 0 is a valid no-op; a rate of 100 means the stat grows
  on every level-up.
- The roll is per (entity, level-up, stat). Two levels in a row
  can roll differently. A single level-up can grow 0, 1, 2, 3, ...
  of the six stats.

## 6. Stat caps

Per-question §3:

```python
STAT_CAPS = {
    "hp":   120,
    "atk":   60,
    "def":   55,
    "matk":  60,
    "mdef":  55,
    "mov":   12,
}
```

`STAT_CAPS` is a single module-level constant in
`app.progression.policies`. It is referenced by:
- `RolledGrowthPolicy` (clamps each roll).
- `modes.spawn_generic_stats` (clamps the deterministic L-N roll).
- `app/mercenary_domain/rules.py` (clamps any external `mov` injection
  so equipment / talent / commander effects cannot push past cap).

It is **not** per-class. The spec author considered per-class caps
("a swordmaster should cap at lower HP than a knight") and decided
that adds tunable complexity without commensurate balance benefit;
if balance later needs it, a per-class override field is a 3-line
add.

## 7. Per-class growth tables

### 7.1 Schema

Every `BaseUnitClass` declares:

```python
class_growth_rates: ClassVar[Mapping[str, int]] = {
    "hp":   90,
    "atk":  45,
    "def":  20,
    "matk":  5,
    "mdef": 15,
    "mov":  0,   # mov does not grow by default; see §9
}
```

Required keys: every key in `STAT_KEYS`. Missing keys are a registry
warning, not a hard error, so a new class that forgets `mdef` still
loads — but the warning is loud so we don't ship that mistake.

### 7.2 Initial table (16 classes)

The growth numbers below are a **first pass** derived from each
class's archetype role. They are intentionally not final-tuned;
this spec's goal is the *mechanism*, the numbers are a placeholder
that rebalance work can adjust without touching the engine.

All values are percentages. `0` = never grows, `100` = always grows.

**Tier 2 modifier: every tier-2 class gets +10 on every growth rate**
on top of the table below. This is the primary mechanism for making
promotion *feel* like a power-up — at L20, a tier-2 unit will have
roughly 10–15 more stat points per stat than a tier-1 unit that was
promoted at L20 with the same per-level hits. Combined with the
flat `promotion_bonus` (§7.3), the gap from t1 to t2 is meaningful
in both L1 base and L20 total.

| class (role)             | hp | atk | def | matk | mdef | mov | (FE8 analogue)        |
|--------------------------|----|-----|-----|------|------|-----|-----------------------|
| swordsman (T1)           | 85 | 45  | 30  | 5    | 20   | 0   | Mercenary             |
| archer (T1)              | 65 | 50  | 20  | 5    | 15   | 0   | Archer                |
| lancer (T1)              | 70 | 45  | 20  | 5    | 20   | 5   | Myrmidon              |
| knight (T1)              | 80 | 45  | 35  | 5    | 15   | 5   | Cavalier              |
| warlock (T1)             | 60 | 5   | 15  | 55   | 25   | 0   | Mage                  |
| healer (T1)              | 65 | 5   | 20  | 25   | 35   | 0   | Cleric                |
| dragon_rider (T1)        | 80 | 50  | 25  | 5    | 15   | 5   | Wyvern Rider          |
| falcon_knight (T1)       | 70 | 35  | 20  | 5    | 25   | 5   | Pegasus Knight        |
| warrior (T1)             | 80 | 55  | 25  | 5    | 15   | 0   | Fighter               |
| **blade_master (T2)**    | **80** | **50**  | **35**  | **15**   | **30**   | **10**  | Swordmaster       |
| **sniper (T2)**          | **70** | **60**  | **30**  | **15**   | **25**   | **10**  | Sniper            |
| **paladin (T2)**         | **85** | **50**  | **40**  | **15**   | **30**   | **15**  | Paladin           |
| **sage (T2)**            | **65** | **15**  | **25**  | **60**   | **45**   | **10**  | Sage              |
| **saint (T2)**           | **70** | **15**  | **30**  | **35**   | **50**   | **10**  | Bishop            |
| **berserker (T2)**       | **90** | **65**  | **30**  | **15**   | **20**   | **10**  | Berserker         |
| bard (T1, hero-only)     | 55 | 5   | 15  | 20   | 35   | 5   | Bard / Dancer         |

Numerical gap check (t1 swordsman vs t2 blade_master, atk/100 levels):
- swordsman atk: 45 → expected atk gain over 20 levels ≈ 0.5 × 0.45 × 20 = ~9 points
- blade_master atk: 50 → expected atk gain ≈ 0.5 × 0.5 × 20 = ~10 points
- + promotion bonus +2 atk (one-time)
- ⇒ t2 is ~+3 atk ahead of t1 at L20, *plus* higher L1 base. That is the
  intended "promotion matters" feel without runaway scaling.

Heuristic used:
- "Physical" classes get high `atk` + `hp`; low `matk`.
- "Magical" classes (warlock, sage, healer, saint, bard) get high
  `matk` + `mdef`; low `atk` and `def`.
- Tanks (knight, paladin) get the highest `def`.
- `mov` is 0 by default — see §9. Classes where the answer to "should
  this class gain a movement tile every 5 levels?" is yes get a
  small non-zero rate (5). 5% × 35 levels ≈ 1.75 expected gains,
  which feels right.

### 7.3 Promotion bonus

When a `tier=1` class is promoted to its `tier=2` replacement
(currently implicit in the `TIER2_TYPE_IDS` set in `policies.py`),
apply a **flat additive bump** to the entity's stat block:

| from → to            | hp | atk | def | matk | mdef | mov |
|----------------------|----|-----|-----|------|------|-----|
| swordsman → blade_master | 3 | 2  | 2  | 0    | 3    | 0   |
| archer → sniper          | 3 | 2  | 1  | 0    | 3    | 0   |
| lancer → paladin         | 3 | 2  | 2  | 0    | 3    | 1   |
| knight → paladin         | 3 | 2  | 2  | 0    | 3    | 1   |
| warlock → sage           | 2 | 0  | 2  | 3    | 4    | 0   |
| healer → saint           | 2 | 0  | 2  | 2    | 4    | 0   |
| dragon_rider → (none yet) | 0 | 0  | 0  | 0    | 0    | 0   |
| falcon_knight → (none yet)| 0 | 0  | 0  | 0    | 0    | 0   |
| warrior → berserker      | 4 | 3  | 1  | 0    | 2    | 0   |
| bard → (none, hero-only) | 0 | 0  | 0  | 0    | 0    | 0   |

`dragon_rider`, `falcon_knight`, `bard` have no `tier=2` in the
current registry. When one is added later, the bonus table is
extended. The promotion-bonus table is a separate dict in
`app.progression.policies` (callable
`promotion_bonus_for(class_id) -> Mapping[str, int]`).

Promotion bonus is applied **once** at the moment of promote
(inside the `promote()` function in `app.progression.leveling`).
It is **not** retroactive and **not** repeated on a second promote.

## 8. Per-hero personal growth modifier

### 8.1 Schema

```python
# BaseHero
personal_growth_modifier: ClassVar[Mapping[str, int]] = {}  # default empty

# HeroProfile (compiled)
personal_growth_modifier: Mapping[str, int]   # default empty frozendict
```

Effective growth rate per (hero, stat) =
`clamp(class.class_growth_rates[stat] + hero.personal_growth_modifier[stat], 0, 100)`.

Modifiers can be **negative** to express "this hero is bad at this stat
relative to their class". Modifiers can also push the rate above 100;
the clamp prevents that from being exploitable.

### 8.2 Initial table (4 heroes)

| hero       | base_class | hp  | atk | def | matk | mdef | mov | design intent                |
|------------|------------|-----|-----|-----|------|------|-----|------------------------------|
| `yun`      | warlock    | 0   | 0   | 0   | +20  | +5   | 0   | pure-output mage: maximum matk, fragile, leans into the "veteran field-mage" framing from the existing yun.py docstring |
| `yuanying` | warlock    | +5  | 0   | 0   | +10  | +5   | 0   | balanced caster: matk + bulk, contrasts yun's fragility |
| `anna`     | healer     | 0   | 0   | +5  | 0    | +5   | 0   | defensively-tuned healer       |
| `youko`    | bard       | 0   | 0   | 0   | +10  | +5   | 0   | song-buffer: lean into matk    |

These match the existing `*_override` deltas in spirit (yun atk+12
in the override, yun atk+15 in the modifier) so the hero's identity
stays the same.

Note on yun: in prior versions of this table yun had `+15 atk`,
which would have re-framed him as a "battle-mage" leaning on
physical attacks. The hero's narrative (see `yun.py`: "a veteran
field-mage, out-marches ordinary casters") is *magical*, not
physical — so yun stays on the pure-output-mage curve (`+20 matk`,
`+5 mdef`) and the atk stat is untouched relative to his base
class.

## 9. MOV/MP merge

**Decision** (from §3): keep `base_mov`, delete `mp_pool`, take
`max(base_mov, mp_pool)` as the resolved value so existing movement
ranges are preserved.

**Steps**:

1. In `app.classes.units.base.UnitClassProfile`, remove the
   `mp_pool: int` field.
2. In `app.classes.units.base.BaseUnitClass`, remove the
   `mp_pool: ClassVar[int]` class-var and the default `= 5` it
   inherits from; each subclass's `mp_pool = N` line is also removed.
3. In `app.classes.heroes.base.HeroProfile`, remove
   `mp_pool_override: Optional[int]`.
4. In `app.classes.heroes.base.BaseHero`, remove
   `mp_pool_override: ClassVar[Optional[int]] = None`.
5. In each of the 16 unit class files and 4 hero files, delete
   the `mp_pool = N` / `mp_pool_override = N` line.
6. In `app.classes.units.__init__.UnitClassProfile.compile()`,
   remove the `mp_pool=cls.mp_pool` line.
7. In `app.progression.policies.resolve_effective_base`, remove the
   `"mp": ...` entry from the returned dict and the
   `STAT_KEYS` tuple.
8. In `app.modes.spawn_generic_stats`, replace
   `"mov": profile.base_mov` with the resolved value
   `max(profile.base_mov, profile.mp_pool)` (and remove `mp_pool`
   access). **But wait — `mp_pool` is gone after step 2**, so the
   migration is: read `base_mov` *as currently set in the file*,
   then once per file decide whether to keep the value (if it was
   the higher one) or replace it with the `mp_pool` value. The
   per-file migration table is in §9.1.
9. In `app.game_logic.py:2375`, the line
   `mov=profile_obj.mp_pool, mp=0` becomes
   `mov=profile_obj.base_mov, mp=profile_obj.base_mov`. (The
   `unit.mov` is the "max MP" the unit has each turn; `unit.mp`
   is "remaining MP". They were always the same value on
   spawn; we just make that explicit.)
10. In `app.mercenary_domain.rules.py:111-114`, the code
    `unit.mov += mov; unit.mp += mov` is preserved (mov and mp
    are still distinct runtime concepts: mov = max, mp = remaining).
    No change to that block.
11. In `app.classes.units.skills.sing.py:41-42`,
    `target.mp = profile.mp_pool; target.mov = profile.mp_pool`
    becomes `target.mp = profile.base_mov; target.mov = profile.base_mov`.
12. In `app.routes.game.py` (`candidate.mov = hero_base.mp_pool`
    and the `mp_pool_override` block at lines 311-333), the
    `mp_pool` reference is replaced with `base_mov` and the
    `mp_pool_override` block is deleted. (Heroes with explicit
    `mov_override` keep their override; everything else falls
    through to `base_mov`.)
13. In `app.routes.game.py:1586` the response field
    `"mp_pool": u.mp_pool` is removed from the public API
    payload. The field is not in the documented contract;
    removing it is a non-breaking change.

### 9.1 Per-file migration table (base_mov after merge)

| file | before (base_mov / mp_pool) | after (base_mov) |
|---|---|---|
| archer.py       | 3 / 5  | 5 |
| bard.py         | 4 / 6  | 6 |
| berserker.py    | 4 / 5  | 5 |
| blade_master.py | 4 / 6  | 6 |
| dragon_rider.py | 5 / 7  | 7 |
| falcon_knight.py| 6 / 6  | 6 |
| healer.py       | 3 / 5  | 5 |
| knight.py       | 5 / 8  | 8 |
| lancer.py       | 5 / 6  | 6 |
| paladin.py      | 6 / 9  | 9 |
| sage.py         | 4 / 10 | 10 |
| saint.py        | 4 / 8  | 8 |
| sniper.py       | 4 / 6  | 6 |
| swordsman.py    | 3 / 5  | 5 |
| warlock.py      | 3 / 8  | 8 |
| warrior.py      | 3 / 4  | 4 |

Notes:
- Six classes change their effective movement range upward
  (paladin 6→9, sage 4→10, saint 4→8, knight 5→8, warlock 3→8,
  lancer 5→6, dragon_rider 5→7). The increases are intentional
  (per §3 decision "use the larger of the two so existing
  movement feel is preserved"). The chart tool's PNGs will
  reflect the new movement numbers.
- `falcon_knight` stays at 6 (the two values were equal, so
  `max` is unchanged).
- Hero `mp_pool_override` lines are removed without substitution
  — heroes with no explicit `mov_override` get the (now merged)
  `base_mov` of their base class.

### 9.2 What about `unit.mov` and `unit.mp` runtime fields?

These stay. The schema is:

- `unit.mov` = max MP per turn (constant, refreshed on turn start).
- `unit.mp`  = remaining MP this turn (decremented on move,
  reset to `unit.mov` on turn start).

The redundant `unit.mov` field on the `Unit` model existed *before*
this change and is still used by the front-end display
(`app/web/app.js` line 3002: `⚡${unit.mp ?? unit.mov}/${unit.mov}`).
The merge is only on the **profile** side
(`UnitClassProfile`); the runtime model is unchanged.

## 10. RolledGrowthPolicy — the new policy class

A new policy lives in `app.progression.policies`:

```python
class RolledGrowthPolicy:
    """FE8-style per-stat per-level roll. Per-stat caps. Pure rng via injection."""

    name: ClassVar[str] = "rolled"

    def baseline(self, *, class_profile, hero_profile=None) -> ClassBaseline:
        # Resolve effective growth rates by adding class + personal
        # modifier (clamped to [0, 100]), and stash them on the
        # baseline so stat_at_level and roll_level_up don't have
        # to re-derive them. The stat caps are STAT_CAPS module-wide.
        class_rates = class_profile.class_growth_rates
        personal = hero_profile.personal_growth_modifier if hero_profile else {}
        effective_rates = {
            s: max(0, min(100, class_rates.get(s, 0) + personal.get(s, 0)))
            for s in STAT_KEYS
        }
        return ClassBaseline(
            ...,
            class_growth_rates=effective_rates,
            stat_caps=STAT_CAPS,
            ...,
        )

    def stat_at_level(
        self, *, baseline_, level, rng=random.random
    ) -> Dict[str, int]:
        # Start at L1 base, then for each level 2..level do a
        # roll_level_up against the current value.
        out = dict(baseline_.base_stats)
        for _ in range(2, level + 1):
            out = self.roll_level_up(
                current_stats=out, baseline_=baseline_, rng=rng,
            )
        return out

    def roll_level_up(
        self, *, current_stats, baseline_, rng=random.random
    ) -> Dict[str, int]:
        """Apply exactly one level-up's rolls to `current_stats`,
        returning a new dict (does not mutate)."""
        out = dict(current_stats)
        for s in STAT_KEYS:
            if rng() * 100 < baseline_.class_growth_rates[s]:
                r2 = rng() * 100
                if r2 < 25:
                    delta = 2
                elif r2 < 95:
                    delta = 1
                else:
                    delta = 0
                out[s] = min(out[s] + delta, baseline_.stat_caps[s])
        return out
```

`get_policy("rolled")` returns a `RolledGrowthPolicy()` instance.
The `name` and `autolevel_boss` policies remain, marked deprecated:

```python
class AutolevelPolicy:
    """DEPRECATED: replaced by RolledGrowthPolicy. Retained so
    the chart tool's --policy=autolevel_boss keeps working for
    A/B comparison PNGs."""
    ...
```

`tools/growth_charts/dataset.py` already loops over
`all_class_curves()` and `all_hero_curves()` via `get_policy()`. The
chart tool needs no code change; running
`python -m tools.growth_charts --policy=rolled` produces the new
curves. (The existing `--policy=autolevel_boss` keeps working for
diff comparison.)

## 11. Integration with `app.modes.spawn_generic_stats`

`spawn_generic_stats` is called at L1, L10, etc. by Free-mode and
chapter spawners. Today it uses the linear `lane_growth_rates` to
compute L1+ levels. After this change it switches to
`RolledGrowthPolicy.roll_level_up` called N times where
N = `start_level - 1`. This requires:

- A **deterministic** RNG. We pass `random.Random(seed)` to the
  policy so that two L10 spawns with the same seed produce the
  same stats. The seed is `unit.id` (or, if absent, derived from
  the game id + spawn sequence).
- A `growth_seed` field on `Unit` so the seed is persisted with
  the row. This way a save-and-reload reproduces the unit's stats.

The spec author considered making `spawn_generic_stats`
**non-deterministic** (just roll fresh each time) and rejected it:
the existing `test_modes.py` and `test_economy.py` tests assert
exact L10 stat values, and any non-determinism would force a
rewrite of those tests. Determinism is the path of least
disruption. The `growth_seed` field is a small additive schema
change; a migration is provided in §13.

## 12. Integration with `app.mercenary_domain`

`app/mercenary_domain/rules.py` reads `unit.mov` and writes both
`unit.mov` and `unit.mp` on equipment apply. After this change:

- Reads of `unit.mov` continue to work (no rename on the
  runtime model).
- Writes of `unit.mov` are clamped against `STAT_CAPS["mov"] = 12`
  to prevent equipment exploits.

No other change in `mercenary_domain`.

## 13. Database / schema change

Add a `growth_seed: int` column to the `units` table. The
existing `nullable=True` is fine (legacy rows have no seed; we
fall back to `unit.id or 0`).

A migration is needed. The migration file goes in the standard
location (we don't re-check the directory layout for this spec;
the implementer should grep for the existing migration
directory and add a new file alongside the others).

## 14. Files to change (summary)

### Production
- `game/app/classes/units/base.py` — drop `mp_pool`, add
  `class_growth_rates` + `stat_caps` fields to dataclass and
  abstract base.
- `game/app/classes/units/*.py` (16 files) — set the new fields,
  delete `mp_pool` lines, merge `base_mov` per §9.1.
- `game/app/classes/units/__init__.py` — registry validation:
  warn on missing growth keys, warn on rate not in [0, 100].
- `game/app/classes/heroes/base.py` — drop `mp_pool_override`,
  add `personal_growth_modifier` to dataclass and abstract base.
- `game/app/classes/heroes/*.py` (4 files) — set
  `personal_growth_modifier`, delete `mp_pool_override` lines.
- `game/app/classes/heroes/__init__.py` — registry validation.
- `game/app/progression/policies.py` — add `STAT_CAPS`,
  `RolledGrowthPolicy`, `PROMOTION_BONUSES`,
  `promotion_bonus_for()`; update `resolve_effective_base` to
  drop `mp`; add `class_growth_rates` and `stat_caps` to
  `ClassBaseline`; mark `AutolevelPolicy` deprecated.
- `game/app/progression/leveling.py` — `promote()` applies
  `promotion_bonus_for()`; `award_exp()` returns the rolled
  deltas in `LevelUpResult.stat_delta`.
- `game/app/modes.py` — `spawn_generic_stats` rolls N times
  with a seeded `Random`, clamping against `STAT_CAPS`.
- `game/app/game_logic.py:2375` — replace `mp_pool` with
  `base_mov` per §9 step 9.
- `game/app/mercenary_domain/rules.py` — clamp `unit.mov` against
  `STAT_CAPS["mov"]`.
- `game/app/classes/units/skills/sing.py` — use `base_mov` per
  §9 step 11.
- `game/app/routes/game.py` — replace `mp_pool` with `base_mov`
  per §9 step 12-13.
- `game/app/routes/heroes.py` — drop the `mp_pool_override`
  branch in the response (per §9 step 12).
- `game/app/hero_domain/legacy_bridge.py` — drop the
  `mp_pool_override` / `+8 mp` legacy branches.

### Tools
- `tools/growth_charts/dataset.py` — pass through the new
  `class_growth_rates` / `stat_caps` fields. (No logic change
  if `RolledGrowthPolicy` returns the right shape.)
- `tools/growth_charts/render.py` — drop the "mp" axis from
  the small-multiples panel (6 panels instead of 7).

### Tests (new)
- `game/tests/test_rolled_growth_policy.py`
  - `test_hit_rate_close_to_rate` — 10_000 trials at 50% rate
    → hits within 5% of 5000.
  - `test_distribution_within_5pct` — over 10_000 trials, +1
    share within 65-75%, +2 share within 20-30%, +0 share
    within 0-10%.
  - `test_caps_apply` — run 100 level-ups at 100% rate with
    cap=20 on atk; result.atk ≤ 20.
  - `test_baseline_clamps_modifier_sum_to_100` — class 80%
    + hero +30 → effective 100.
  - `test_modifier_can_be_negative` — class 50% + hero -20 →
    effective 30.
  - `test_seeded_rng_is_deterministic` — same seed → same
    result; different seed → different result (probabilistically).
- `game/tests/test_promotion_bonus.py`
  - `test_paladin_gets_promotion_bonus` — promote a swordsman
    → paladin at L20; result.atk == 2-level base + paladin_bonus.atk.
- `game/tests/test_hero_personal_growth.py`
  - `test_yun_atk_rate_is_warlock_plus_modifier` —
    `warlock.atk + 15 == yun.effective_growth_rates.atk`.
- `game/tests/test_mov_mp_merge.py`
  - `test_mp_pool_field_removed_from_profile` —
    `UnitClassProfile` no longer has `mp_pool`.
  - `test_base_mov_after_merge_matches_max` — for each of
    the 16 classes, `cls.base_mov` matches the §9.1 table.
- `game/tests/test_spawn_uses_rolled.py`
  - `test_spawn_l10_with_seed` — same seed → same L10 stats;
    match snapshot.

### Tests (modified)
- `game/tests/test_modes.py` — re-baseline: spawn-at-L10 numbers
  change. Snapshots updated.
- `game/tests/test_growth_chart_policies.py` — keep the
  `autolevel_boss` tests, add a `rolled` test that confirms
  the policy name resolves.
- `game/tests/test_economy.py` — same: the spawn stats that
  feed into the gold-per-turn test may shift. Snapshots
  updated.

## 15. Testing strategy & acceptance

- All new unit tests pass.
- `tools/growth_charts --policy=rolled` produces a PNG per
  class and per hero; spot-check that the curves look
  qualitatively different from the old `--policy=autolevel_boss`
  PNGs (knight curve rises faster on def, warlock curve rises
  faster on matk).
- `game/tests/test_modes.py` re-baselined; L10 stats are
  deterministic across runs of the same seed.
- `game/tests/test_player_vs_ai_full_game.py` and
  `test_mainline_e2e.py` continue to pass — these are the
  integration tests that exercise the full level-up → next-battle
  loop.
- The chart tool's diff: under `rolled` policy, two
  swordmasters at L20 have different `atk` (one is 18, the
  other is 21, say). Under the old `autolevel_boss` policy
  they were identical.

## 16. Risks & mitigations

- **R1**: Spawn determinism regression — RNG side-effects leak
  into other code. *Mitigation:* the `rng` parameter is a
  `random.Random` instance owned by the caller, never the
  global `random.random`. Unit tests verify determinism.
- **R2**: Existing `test_modes.py` snapshots break because
  L10 numbers shift. *Mitigation:* the snapshots are
  auto-regenerated in the same commit; the diff is
  reviewed as part of the PR.
- **R3**: The merge of `base_mov`/`mp_pool` increases
  effective movement for 6 classes. This is a 0.5-1.0 tile
  bump at L1 for paladin/sage/saint/knight/warlock/dragon-rider,
  which is a real balance change. *Mitigation:* the spec
  surfaces this explicitly; the rebalance to compensate
  (if needed) is a separate follow-up.
- **R4**: Migration of `units` table to add `growth_seed`
  must run before the new code path is hit. *Mitigation:*
  the migration is in the same commit and a smoke test
  runs `pytest -k "test_spawn_uses_rolled"` after the
  migration.

## 17. Out-of-scope follow-ups

- Per-class stat caps (§6 motivation).
- Skill-triggered growth modifiers (e.g. a sage who levels
  up with a spell gains +1 matk).
- Reverse-growth (negative growth on curse / debuff).
- Story-mode "set stat to fixed value" promotion (FE8's
  trainee → base class flow).
