# Growth-chart tool — design spec

| | |
|---|---|
| **Date** | 2026-07-23 |
| **Status** | implemented |
| **Owner** | balance / tooling |
| **Scope** | a one-shot PNG visualization for every registered unit class and hero, against the current growth formula. |

---

## Goal

For every registered `BaseUnitClass` subclass and every `BaseHero` subclass,
emit a single PNG that, in one image, tells the reader:

1. What 7-dim stat block does this entity have at Lv 1, mid (Lv 10), and Lv max (Lv 20)?
2. What is the full Lv 1..max growth curve per dim?
3. What is the headline total-stats number at max level?

The tool must be **independent of the current growth formula**. The team
expects to change formulas twice more before launch (character-roll growth,
then per-talent-tree growth), and a chart-tool rewrite each time is unacceptable.

## Non-goals

- No in-game embedded chart (no HTML / JS / WebSocket surface).
- No interactive / hover-tooltip layer (matplotlib PNG only).
- No tier-promotion curves ("what does a L20 swordsman look like as a
  blade_master"). The chart shows the *final class identity* at each
  level, not the in-place promotion moment.
- No headless server-side rendering under FastAPI (pure CLI tool).

## Architecture

```
        Backend layer                       Tool layers
        ─────────────                       ────────────
game/app/progression/policies.py ◀─────┐   tools/growth_charts/
   · ClassBaseline                     │     · dataset.py   (pure data)
   · GrowthPolicy (Protocol)            ├─────▶   · render.py    (matplotlib)
   · AutolevelPolicy (default)          │     · __main__.py  (CLI)
   · get_policy(name)                   │
                                        │
                                        │   Output:
                                        │   tools/growth_charts/
                                        │     classes/<type_id>.png     (15)
                                        │     heroes/<hero_id>.png      (2)
                                        │     index.json
```

Why this shape:

- **The Protocol lives on the backend side, not the tool side.** The
  chart tool is a *consumer* of growth policies; the formula choice is
  a game-data decision and belongs next to the spawn path
  (`app.modes.spawn_generic_stats`).
- **The renderer is dumb.** It consumes frozen `ClassGrowthCurve`
  dataclasses and emits PNGs.  No I/O, no plugin discovery at render
  time.
- **Dataset is pure.** Importing `tools.growth_charts.dataset` does not
  require matplotlib, so unit tests can run headless under CI.

## Data contract

```python
@dataclass(frozen=True)
class ClassBaseline:
    type_id: str         # "blade_master" or "yun"
    label_cn: str        # "剑圣" / "云"
    label_en: str        # "Blade Master" / "Yun"  (hero uses type_id.title())
    tier: int            # 1 / 2  (heroes currently always 1)
    attack_kind: str     # "physical" | "magic"
    is_hero: bool
    base_class_id: Optional[str]      # hero only
    base_stats: Mapping[str, int]     # 7 keys: hp/atk/def/matk/mdef/mov/mp
    formula_note: str                 # human note stamped on title

class GrowthPolicy(Protocol):
    name: ClassVar[str]
    def baseline(self, *, class_profile, hero_profile=None) -> ClassBaseline: ...
    def stat_at_level(self, *, baseline_, level: int) -> Mapping[str, int]: ...
```

`STAT_KEYS = ("hp", "atk", "def", "matk", "mdef", "mov", "mp")` is the
single source of truth for the 7-dim canonical order.  Every chart
panel and the dataset helpers read it.

## Current formula — `autolevel_boss`

The default `AutolevelPolicy` mirrors `app.modes.spawn_generic_stats`
exactly: L_v value = base + int((level − 1) × rate / 100), with rates

| stat | rate per level above L1 |
|---|---|
| hp   | 85  |
| atk  | 50  |
| matk | 50  |
| def  | 10  |
| mdef | 15  |
| mov  | 0   |
| mp   | 0   |

The chart test `test_autolevel_stat_at_level_matches_spawn_helper`
asserts that the two paths agree at every level — this guard catches
any drift between the spawn formula and the chart formula.  **They
must agree unless intentionally separated.**

## Hero formula — current state

`spawn_hero_stats()` is a `NotImplementedError` placeholder pending a
character-design draft.  Until that lands, **hero charts reuse the
generic autolevel formula** with the hero's L1 baseline baked in
(base class's L1 + hero.*\_override, never None for an overridden
slot).  The chart title prefixes "(英雄)" and the formula_note
explicitly reads:

> 英雄暂沿用 generic 公式 (autolevel_boss),等待 HeroDesign 落地后切到独立公式

When HeroDesign lands:

1. Add a `HeroAutolevelPolicy` (or whatever the new formula is) —
   one new class implementing the `GrowthPolicy` Protocol, registered
   in `get_policy()`.
2. The CLI gains `--policy <name>` to switch (already wired).
3. The chart tool does not need to be edited.

## Renderer — layout A (per chart)

- 14×9 inch figure @ 200 DPI (~ 2800 × 1800 px).
- 3×4 outer `GridSpec`:
  - **Row 0 (full width)**: 3-line title block — entity + tier/attack kind + hero flag, policy line, formula_note line.
  - **Row 1 (full width)**: 2×4 inner `GridSpec` →
    - Cells (0,0)(0,1)(0,2)(0,3): HP / ATK / DEF / MATK small multiples.
    - Cells (1,0)(1,1)(1,2)(1,3): MDEF / MOV / MP / "static dims" note.
    Each panel: 2 px line, ≥8 px filled dot markers at Lv 1 / Lv 10 / Lv max with numeric labels, recessive 0.5 px grid.
  - **Row 2 (3 col)**: heat-graded comparison table — 7 rows × (1 + N cols + Δ%).  Δ% cell uses the Yellow-Orange sequential colormap, normalized across the chart.
  - **Row 2 (last col)**: total-stats panel — neutral 2 px line, headline big number, "% vs L1" subtitle.

### Style choices

- Tableau-10 first 7 hues as the categorical palette (one hue per stat
  panel).  No cycling.  Validate via dataviz `scripts/validate_palette.js`
  before tuning.
- Sequential colormap `YlOrRd` for Δ% heat-graded cells.
- Total-stats panel reserves 35% extra headroom at top so the headline
  number doesn't visually overlap the Lv 20 marker.
- "Static dimensions" note automatically lists any stat key whose value
  is identical across Lv 1..max (i.e. a flat line) — gives the reader
  an explicit signal that "MOV/MP don't grow".

## Files & entry points

```
game/app/progression/policies.py     # Protocol + dataclass + default impl
tools/growth_charts/
    __init__.py
    dataset.py                       # pure data layer (testable)
    render.py                        # matplotlib layout A
    __main__.py                      # `python -m tools.growth_charts`
game/tests/test_growth_chart_policies.py   # 15 tests
tools/growth_charts/
    classes/<id>.png                 # 15 entries (auto-discovered)
    heroes/<id>.png                  # 2 entries (auto-discovered)
    index.json                       # metadata index for future web gallery
```

CLI:

```
python -m tools.growth_charts                         # default: all, Lv 1..20, autolevel_boss
python -m tools.growth_charts --out docs/foo          # custom output dir
python -m tools.growth_charts --policy <name>         # future formula switch
python -m tools.growth_charts --entities classes      # subset
python -m tools.growth_charts --entities heroes --max-level 50   # alt range
```

## Test surface

15 tests under `game/tests/test_growth_chart_policies.py`:

- `resolve_effective_base` correctness (class only / hero overrides / all None).
- `AutolevelPolicy.baseline` for class and hero paths.
- **`AutolevelPolicy` cross-checks `app.modes.spawn_generic_stats`** — the most important guard, since the two must agree.
- `compute_class_growth` / `compute_hero_growth` produce a full Lv 1..max curve.
- `total_at()` and `delta_pct()` helpers compute correctly.
- `all_class_curves` / `all_hero_curves` discover and sort deterministically.
- `get_policy` registry resolves known names, rejects unknown.
- `infer_tier` honors the static Tier-2 type-id set.

## Future formula hook — checklist for future PRs

When the team adopts a new formula:

1. Implement a new class under `app/progression/policies.py` satisfying
   the `GrowthPolicy` Protocol (2 methods: `baseline`, `stat_at_level`).
2. Register it in `get_policy()`'s name-dispatch.
3. Add CLI flag pass-through if needed (already exists, `--policy`).
4. Update `test_autolevel_stat_at_level_matches_spawn_helper` (or write
   a similar cross-check if the new formula is *not* `spawn_*`).
5. Re-run `python -m tools.growth_charts` to regenerate.

No other files need touching.  Renderer, dataset, layout, output paths,
tests for the *tooling itself* are all formula-agnostic.

## Known limitations

- **Integer truncation visible on charts.** `int(levels_above * rate/100)`
  produces visible stair-step on low-rate stats (DEF at 10/level).
  Designers see this on the chart and may lobby to change `int()` to
  `round()`.  This is a downstream design decision, not a tool bug.
- **Hero formula is generic.** Reflected explicitly in chart title
  note.  Will fix when HeroDesign lands.
- **Per-class growth-rate overrides are NOT supported.** Currently
  every class gets the same set of rates.  The Protocol and dataclass
  are shaped to accept per-profile rate overrides, but the
  `AutolevelPolicy` doesn't read them yet.  If the team adds per-class
  rates to the unit class file, a `RatesByClass` policy variant can be
  written in < 30 LoC without touching the tool.
- **Palette is hand-picked, not yet validated.** Run
  `scripts/validate_palette.js` to check CVD compliance before any
  future tuning.
- **Headline overlap early version.** Fixed by reserving 35% top
  headroom in `_draw_total`; if max stat ranges vary widely, re-tune.
