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

**All 4 existing classes also need MATK/MDEF/attack_kind set**, not
just Warlock. Per §5.1:

- `swordsman.py`: `attack_kind = "physical"`, `base_matk = 4`,
  `base_mdef = 4`
- `knight.py`: `attack_kind = "physical"`, `base_matk = 4`,
  `base_mdef = 4`
- `archer.py`: `attack_kind = "physical"`, `base_matk = 4`,
  `base_mdef = 4`. Existing `strong_against = []` stays empty —
  natural counter via stats now that Warlock exists. The
  "reserved for future mage" comment is still accurate (it now points
  to Warlock rather than a hypothetical mage).
- `healer.py`: `attack_kind = "magic"`, `base_matk = 8`, `base_mdef = 12`,
  `attack_range = 2` (was `0`). See §4.3 for the rationale.

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
| `base_matk`      | 4         | 22      | primary damage source                       |
| `base_mdef`      | 4         | 12      | same as Swordsman's def_                    |
| `base_mov`       | 3         | 3       | same                                        |
| `mp_pool`        | 5         | 8       | more MP — magic career                      |
| `default_skills` | []        | []      | none, matching Swordsman                    |
| `attack_range`   | 1         | 2       | Manhattan 1–2 (sword+archer combined)       |
| `min_attack_range` | 0       | 0       | can attack adjacent                         |
| `can_move_after_action` | False | False | same                                        |
| `attack_kind`    | physical  | magic   | the magic tag                               |
| `strong_against` | [knight]  | []      | empty — natural counter via stats           |

The "sword + archer combined" attack range means Warlock can hit any
target whose Manhattan distance is 1 (adjacent) or 2 (diagonal /
two-step orthogonal). This is the Fire Emblem classic mage range.
See §5.1 for the cross-archetype damage dynamics this produces.

### 4.3 Healer class (`healer.py`) — reclassification

The user explicitly reclassified the Healer as a magic-type unit
during brainstorming. This means:

1. **Delete the `rally` skill** — Healer keeps only `heal` as a
   default skill. Delete `game/app/classes/units/skills/rally.py`.
2. **Healer can now attack** — `attack_range` changes from `0` to
   `2` (matching Warlock's sword+archer combined range) so it can
   defend itself or finish weakened targets.
3. **`attack_kind = "magic"`** — Healer joins the magic archetype.
4. **MATK and MDEF filled in** — `base_matk = 8` (low — not a primary
   attacker, just gains the magic offense option), `base_mdef = 12`
   (matching Warlock's MDEF — Healer stands in the backline and
   shouldn't get one-shotted by other magic units).

The `strong_against = []` on Healer stays empty — same reasoning as
Warlock (natural counter via stats).

### 4.4 Default roster

Keep `default_roster()` unchanged for now (剑士 2 + 弓 1 + 骑 1 + 疗 1).
Players can still pick Warlock via `custom roster`. This is a
deliberate YAGNI decision: don't add Warlock to the default until
playtesting confirms balance.

---

## 5. Combat formula (`game/app/game_logic.py`)

`calculate_damage` (lines 218-256) becomes:

```python
# Attacker picks which stat to attack with (its own attack_kind).
# Defender's resistance type follows the DEFENSE archetype — physical
# attacks are blocked by the defender's def_ (low for magic units),
# magic attacks are blocked by the defender's mdef (low for physical
# units). This is what produces "天生相克": physical units naturally
# have low mdef so magic hits them hard; magic units naturally have
# low def_ so physical hits them hard.
if attacker.attack_kind == "magic":
    eff_atk = attacker.matk * (1 + attacker.morale * MORALE_ATK_PER_STAR)
    eff_df  = (defender.mdef + tile_def_bonus) * (1 + defender.morale * MORALE_DEF_PER_STAR)
else:  # "physical"
    eff_atk = attacker.atk * (1 + attacker.morale * MORALE_ATK_PER_STAR)
    eff_df  = (defender.def_ + tile_def_bonus) * (1 + defender.morale * MORALE_DEF_PER_STAR)
```

**Why this design is correct:**
- A Swordsman attacks a Warlock: Swordsman uses its ATK (high, 18),
  Warlock defends with its DEF (low, 10). Damage is high — physical
  beats magic because magic units invest in MATK/MDEF at the cost of
  DEF.
- A Warlock attacks a Swordsman: Warlock uses its MATK (high, 22),
  Swordsman defends with its MDEF (low, 4). Damage is high — magic
  beats physical because physical units invest in ATK/DEF at the cost
  of MDEF.
- Same-archetype matchups (sword vs sword, warlock vs warlock) deal
  moderate damage because both sides have invested in their archetype's
  defense.

`attack_with_double_strike` and counter-attack logic do not need to
change — they only orchestrate hits, not compute damage per hit.

`strong_against` table is left in place but **no longer matters for
the new Warlock** — the spec no longer sets `strong_against = ["healer"]`
on the Warlock. The natural counter (Healer's low DEF) is already
captured by the defender's stat choice.

---

## 5.1 Updated class profiles

The new "natural counter" model means the four classes get balanced
MATK/MDEF profiles:

| Class       | ATK | DEF | MATK | MDEF | attack_kind |
|-------------|-----|-----|------|------|-------------|
| Swordsman   | 18  | 12  | 4    | 4    | physical    |
| Knight      | 22  | 8   | 4    | 4    | physical    |
| Archer      | 20  | 6   | 4    | 4    | physical    |
| Warlock     | 8   | 10  | 22   | 12   | magic       |
| Healer      | 5   | 9   | 8    | 12   | magic       |

Physical classes get a small flat MATK/MDEF (4 each) so the value
is non-zero for UI display but low enough that magic-vs-physical
matchups hurt the physical unit a lot. Magic classes have low ATK/DEF
(intentionally — they don't have a strong physical fallback).

Healer is a magic class but with lower MATK (8) than Warlock (22) —
it's not a primary attacker, just gains the magic-type magic defense
archetype. It also keeps its healing role.

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
- **Removing the `strong_against` system entirely.** We keep the
  field and the type-advantage multiplier for now (Swordsman still
  has `strong_against = ["knight"]`, etc.) — it just stops mattering
  for the new Warlock since the natural counter via stats already
  produces the desired balance. We can revisit once playtesting shows
  whether the explicit table is still pulling weight.

---

## 8. Testing strategy

- Add unit tests in `tests/test_game_logic.py`:
  - `test_warlock_deals_magic_damage_to_swordsman` — Warlock attacks
    Swordsman: confirms damage is computed from `attacker.matk` vs
    `defender.mdef + tile_bonus` (Swordsman's low MDEF means high
    damage).
  - `test_swordsman_deals_physical_damage_to_warlock` — Swordsman
    attacks Warlock: confirms damage is computed from `attacker.atk`
    vs `defender.def_ + tile_bonus` (Warlock's low DEF means high
    damage — natural counter).
  - `test_healer_uses_magic_defense` — Healer takes a Warlock hit,
    damage uses Healer.mdef (12) — confirms Healer is now magic-type.
- Re-run `pytest tests/test_game_logic.py tests/test_integration_smoke.py` — must stay green.
- Smoke-test the new class via the existing `_start_battle_internal`
  endpoint with `warlock` in the roster — verify it appears in
  `players[*].units[*]` with `matk=22, mdef=12, attack_range=2`.

---

## 9. Migration safety

- `models.py` adds columns with `default=0`.
- `_run_legacy_migrations` runs `ALTER TABLE ... DEFAULT 0` so old rows
  get `matk=0, mdef=0`.
- `UnitOut` defaults `matk: int = 0, mdef: int = 0` so the API stays
  backward-compatible.
- The frontend reads `u.matk ?? 0` so even if an older payload omits
  the fields it degrades gracefully.
- The Healer class change (`attack_range: 0 → 2`, `default_skills:
  ["heal","rally"] → ["heal"]`) is a class-level change only; existing
  Healer's `skills` JSON column already stores the skill list
  per-unit so old saves with `["heal","rally"]` will simply have the
  rally skill listed but unusable (we can also add a server-side
  filter that drops `rally` from any Healer unit on load — to be
  confirmed in the plan step).

---

## 10. Spec self-review

- **Placeholders:** none — every section has concrete values.
- **Internal consistency:** stats in §4.1 and §5.1 match; UI labels in
  §6 match the dictionary; formula in §5 mirrors the forecast changes
  in §6.5. Healer classification is consistent across §4.3, §5.1, §8.
- **Scope:** one feature, one implementation plan, no decomposition
  needed.
- **Ambiguity:** "magic defense includes terrain bonus" is explicit
  in §5 (matching physical defense). "Swordsman hitting Warlock uses
  physical defense" is explicit in §5.1 row 1. "Warlock attack range
  = Manhattan 1–2" is explicit in §4.2 and §5.1.