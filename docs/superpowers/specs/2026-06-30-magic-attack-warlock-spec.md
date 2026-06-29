# Magic Attack / Magic Defense + Warlock + Chinese Stat Labels

**Status:** Draft (awaiting owner review)
**Date:** 2026-06-30
**Owner:** BattleBlitz user
**Approach chosen:** Plan A — physical/magic split (no accumulation, no double-roll)

---

## 1. Background and motivation

BattleBlitz currently models only physical combat. Every unit has
`atk` (physical attack) and `def_` (physical defense), and the damage
formula `eff_atk * (eff_atk / (eff_atk + eff_df))` always uses those
two values. This means a "magic" career concept would be cosmetic —
the underlying math has no notion of magic.

The user wants three concrete changes, all in one feature:

1. **Real magic combat.** Add `matk` (magic attack) and `mdef` (magic
   defense) stats so a unit's effectiveness against a magic attacker is
   determined by its magic defense, not its physical defense.
2. **A Warlock class** that mirrors the Swordsman in role (melee
   single-target damage dealer) but uses magic damage instead of
   physical damage.
3. **Localize the side panel.** Replace every remaining English stat
   label ("ATK", "DEF", "MOV", "HP", "Lv.") with Chinese, including
   the new "魔攻 / 魔防" labels and the reference panel's
   `default_users` list (which currently shows raw type_ids like
   `swordsman,knight`).

---

## 2. Approach: physical/magic split (Approach A)

We tag every `BaseUnitClass` with `attack_kind: "physical" | "magic"`.
The damage formula picks which pair of stats to use based on the
attacker's `attack_kind`:

```
attacker.attack_kind == "physical"  →  eff_atk = atk,    eff_df = def_ + tile
attacker.attack_kind == "magic"     →  eff_atk = matk,   eff_df = mdef + tile
```

**Why split, not accumulate (Approach B) and not double-roll
(Approach C):**
- **Split** keeps each career self-consistent — a Warlock that has
  high `matk` and low `atk` deals magic damage and is countered by
  magic defense; a Swordsman is countered by physical defense. This
  is the natural mental model for Fire Emblem-style games.
- **Accumulate** (atk + matk as total attack) would make magic-only
  careers weaker than physical-only careers with the same total
  number because they can't benefit from physical synergies, and
  vice versa, without that being meaningful.
- **Double-roll** doubles the calculation cost for marginal benefit.

---

## 3. Data model changes

### 3.1 Unit ORM (`game/app/models.py:131-176`)

Add two columns to the `Unit` model:

```python
matk: Mapped[int] = mapped_column(default=0)   # magic attack
mdef: Mapped[int] = mapped_column(default=0)   # magic defense
```

Both default to `0` so existing saves keep working.

### 3.2 Database migration (`game/app/database.py`)

Extend `_run_legacy_migrations()` with two more ALTERs, matching the
existing `map_biome` / `phase` pattern:

```python
cols = {row[1] for row in await session.execute(text("PRAGMA table_info(units)"))}
if "matk" not in cols:
    await session.execute(text("ALTER TABLE units ADD COLUMN matk INTEGER NOT NULL DEFAULT 0"))
if "mdef" not in cols:
    await session.execute(text("ALTER TABLE units ADD COLUMN mdef INTEGER NOT NULL DEFAULT 0"))
```

### 3.3 API schema (`game/app/schemas.py:93-115`)

Add to `UnitOut`:

```python
matk: int = 0
mdef: int = 0
```

### 3.4 Unit factory — 4 sites to update

There is no central factory function; the user spec calls for adding
two fields to every site that constructs a `Unit(...)`. All four sites
must add `matk=uc.base_matk` and `mdef=uc.base_mdef` (or `0` where no
profile is available, e.g. the custom-map editor):

1. `game/app/game_logic.py:126-165` `create_initial_units`
2. `game/app/game_logic.py:627-666` `create_initial_units_with_roster`
3. `game/app/routes/game.py:191-211` `_start_battle_internal`
4. `game/app/routes/game.py:230-243` custom-map editor unit creation

`UnitClassProfile` (compiled from `BaseUnitClass`) needs the two new
base values, so each of these sites reads them via the profile.

**Targeted refactor:** introduce a tiny helper
`_apply_base_stats(unit, profile)` that fills in `hp`, `max_hp`,
`atk`, `def_`, `matk`, `mdef`, `mov`, `mp`, `mp_pool`, `level`,
`exp`. Use it from all four sites. Keep this strictly scoped — no
unrelated cleanup.

---

## 4. Class profile changes

### 4.1 Base class (`game/app/classes/units/base.py`)

Add to `BaseUnitClass`:

```python
attack_kind: ClassVar[str] = "physical"   # "physical" | "magic"
base_matk: ClassVar[int] = 0
base_mdef: ClassVar[int] = 0
```

Add to `UnitClassProfile` dataclass:

```python
attack_kind: str
base_matk: int
base_mdef: int
```

Extend `compile()` (lines 81-99) to copy all three fields into the
profile.

### 4.2 Warlock class (new file `warlock.py`)

Mirror Swordsman numerically with adjustments that express the
"magic" identity:

| Field            | Swordsman | Warlock | Why                                         |
|------------------|-----------|---------|---------------------------------------------|
| `type_id`        | swordsman | warlock | internal id                                 |
| `display_cn`     | 剑士       | 术士     | UI label                                    |
| `display_en`     | Swordsman | Warlock | fallback                                    |
| `glyph`          | 剑         | 咒       | board glyph                                 |
| `base_hp`        | 45        | 45      | same                                        |
| `base_atk`       | 18        | 8       | lower — magic damage comes from `matk`      |
| `base_def`       | 12        | 10      | slightly lower                              |
| `base_matk`      | 0         | 22      | primary damage source                       |
| `base_mdef`      | 0         | 12      | same as Swordsman's def_                    |
| `base_mov`       | 3         | 3       | same                                        |
| `mp_pool`        | 5         | 8       | more MP — magic career                      |
| `default_skills` | []        | []      | none, matching Swordsman                    |
| `attack_range`   | 1         | 1       | melee                                       |
| `min_attack_range` | 0       | 0       | melee                                       |
| `can_move_after_action` | False | False | same                                        |
| `attack_kind`    | physical  | magic   | the magic tag                               |
| `strong_against` | [knight]  | [healer]| type-advantage built automatically         |

The magic-tag means:
- A Warlock dealing damage uses its `matk` vs the defender's `mdef`
  (+ terrain bonus).
- A Swordsman hitting a Warlock uses its `atk` vs the Warlock's
  physical `def_` (10), normal damage.
- A Warlock hitting a Swordsman uses its `matk` vs the Swordsman's
  `mdef` (0), so damage will be near-max — magic bypasses physical
  defense.

### 4.3 Default roster

Keep `default_roster()` unchanged for now (剑士 2 + 弓 1 + 骑 1 + 疗 1).
Players can still pick Warlock via `custom roster`. This is a
deliberate YAGNI decision: don't add Warlock to the default until
playtesting confirms balance.

---

## 5. Combat formula (`game/app/game_logic.py`)

`calculate_damage` (lines 218-256) becomes:

```python
if attacker.attack_kind == "magic":
    eff_atk = attacker.matk * (1 + attacker.morale * MORALE_ATK_PER_STAR)
    eff_df  = (defender.mdef + tile_def_bonus) * (1 + defender.morale * MORALE_DEF_PER_STAR)
else:
    eff_atk = attacker.atk * (1 + attacker.morale * MORALE_ATK_PER_STAR)
    eff_df  = (defender.def_ + tile_def_bonus) * (1 + defender.morale * MORALE_DEF_PER_STAR)
```

`attack_with_double_strike` and counter-attack logic do not need to
change — they only orchestrate hits, not compute damage per hit.

`getTypeMultiplier` (frontend, `app.js:1073`) does not need to
change — the type-advantage table is built from `strong_against` per
profile, and `attack_kind` does not affect it.

---

## 6. Frontend changes (`game/app/web/app.js`)

### 6.1 Stat label dictionary

At the top of `app.js`, add:

```js
const UNIT_STAT_LABEL = {
  hp: "生命", atk: "攻击", def_: "防御",
  mov: "移动", matk: "魔攻", mdef: "魔防",
  level: "等级", morale: "士气", range: "射程",
};
```

### 6.2 Side panel — `renderUnitHtml` (line 1257)

| Before                          | After                                                 |
|---------------------------------|-------------------------------------------------------|
| `Lv.${u.level}`                 | `${UNIT_STAT_LABEL.level} ${u.level}`                 |
| `HP ${u.hp}/${u.max_hp}`        | `${UNIT_STAT_LABEL.hp} ${u.hp}/${u.max_hp}`            |
| `ATK ${u.atk}`                  | `攻击 ${u.atk} · 魔攻 ${u.matk ?? 0}`                  |
| `DEF ${u.def_}`                 | `防御 ${u.def_} · 魔防 ${u.mdef ?? 0}`                  |
| `MOV ${u.mov}`                  | `移动 ${u.mov}`                                        |
| `MP ${u.mp ?? u.mov}/${u.mov}`  | `移动力 ${u.mp ?? u.mov}/${u.mov}`                     |

### 6.3 Unit title tooltip (line 871)

`${u.name} (Lv.${u.level}) HP ${u.hp}/${u.max_hp} MP ${u.mp ?? u.mov}/${u.mov} 士气 ${u.morale ?? 0}/3`
→ `${u.name}（等级 ${u.level}） 生命 ${u.hp}/${u.max_hp} 移动力 ${u.mp ?? u.mov}/${u.mov} 士气 ${u.morale ?? 0}/3`

### 6.4 Forecast card (`showAttackConfirmBubble`, line 1337-1385)

Replace `ATK` / `DEF` / `HP` in the forecast-stat and forecast-hp
blocks with the Chinese labels. Add `魔攻` / `魔防` for completeness
when the attacker / defender has non-zero magic stats. Reuse the
existing `.forecast-stat` CSS class — no new styles needed.

### 6.5 Forecast formula (`forecastSingleHit`, line 1086-1117)

Mirror the server-side split using the attacker's `attack_kind` (read
from `UNIT_CLASSES[u.unit_type].attack_kind`, fetched from the
existing `/units` endpoint that the client already calls at startup).

### 6.6 Reference panel — class tab (line 2051-2065)

```
${UNIT_STAT_LABEL.hp} ${u.base_hp} · 攻击 ${u.base_atk} · 防御 ${u.base_def} · 魔攻 ${u.base_matk ?? 0} · 魔防 ${u.base_mdef ?? 0} · 移动 ${u.base_mov} · 射程 ${u.attack_range}
```

### 6.7 Reference panel — skill tab `default_users` (line 2066-2073)

Convert each raw type_id to `display_cn` using `UNIT_CLASSES`:

```js
const users = (s.default_users || []).map(t => UNIT_CLASSES[t]?.display_cn || t).join("、");
```

Then show `默认拥有：${users}`.

---

## 7. Out of scope (explicit YAGNI)

- **Magic-only skills** (e.g. an `arcane_bolt` skill on Warlock).
  Warlock ships with `default_skills = []` matching Swordsman. Skill
  authoring is a separate feature.
- **Adding Warlock to default roster.** Playtesting first.
- **Magic terrain bonuses.** Keep the existing `TERRAIN_DEF_BONUS`
  applying to both `def_` and `mdef` uniformly — split terrain effects
  would be a follow-up.
- **Magic resistance on castle tiles.** A natural future extension
  (castle adds +5 to both physical and magic def). Not in this spec.

---

## 8. Testing strategy

- Add a unit test in `tests/test_game_logic.py`:
  `test_warlock_uses_mdef_when_attacked_by_swordsman` and
  `test_warlock_deals_magic_damage`. These should create a Warlock
  with `matk=22, mdef=12, def_=10` and a Swordsman with `atk=18,
  mdef=0, def_=12`, then assert:
  - Sword hits Warlock → damage uses Sword's `atk` vs Warlock's
    `def_` (10), confirming physical path.
  - Warlock hits Sword → damage uses Warlock's `matk` vs Sword's
    `mdef` (0), confirming magic path.
- Re-run `pytest tests/test_game_logic.py tests/test_integration_smoke.py` — must stay green.
- Smoke-test the new class via the existing `_start_battle_internal`
  endpoint with `warlock` in the roster — verify it appears in
  `players[*].units[*]` with non-zero `matk`.

---

## 9. Migration safety

- `models.py` adds columns with `default=0`.
- `_run_legacy_migrations` runs `ALTER TABLE ... DEFAULT 0` so old rows
  get `matk=0, mdef=0`.
- `UnitOut` defaults `matk: int = 0, mdef: int = 0` so the API stays
  backward-compatible.
- The frontend reads `u.matk ?? 0` so even if an older payload omits
  the fields it degrades gracefully.

---

## 10. Spec self-review

- **Placeholders:** none — every section has concrete values.
- **Internal consistency:** stats in §3 and §4 match; UI labels in §6
  match the dictionary; formula in §5 mirrors the forecast changes in
  §6.5.
- **Scope:** one feature, one implementation plan, no decomposition
  needed.
- **Ambiguity:** "magic defense includes terrain bonus" is explicit
  in §5 (matching physical defense). "Swordsman hitting Warlock uses
  physical defense" is explicit in §4.2 row 3.