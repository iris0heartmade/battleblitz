# Realistic Procedural Terrain — P2.7

**Date:** 2026-07-08
**Status:** Draft (awaiting implementation)
**Supersedes:** P2.4 polish (snow purity) + MAP_GENERATION_PLAN.md outer-style weights

---

## 🎯 Motivation

The current procedural generator (MAP_GENERATION_PLAN.md + `map_generation/`) lays
terrain using per-cell weighted random fill plus a few cluster passes. The result
is *visually scattered* — small islands of forest, lone mountains, rivers that
dead-end at a single plain tile. Players who try 3-4 random maps in a row end
up with the impression that "every random map is the same soup with slight
variation." The hand-authored `balanced_*_Np` maps (P2.6+) feel much more like
*real* places; this spec is the bridge: make the procedural generator feel
the same.

The hard part is that "real" is not one number — it's a set of soft rules
about how Earth's surface organizes itself. We make those rules explicit so
both the implementation and the visual review have a checklist.

---

## 🌍 What "realistic" means in this context

A map feels real when a player can imagine an in-fiction reason for every
feature. The four pillars, ranked by perceptual impact:

### 1. **Terrain clustering** (most important)

> "Forests are *forests*, not 'the green tile biome'."

| Real | Fake |
|---|---|
| 30+ connected trees in one patch | 5-6 isolated trees scattered |
| Mountains form a *ridge* you can trace on the map | 3 mountains in three corners |
| Rivers flow from mountain → plain → edge (connected path) | One river cell in the middle of nowhere |
| Snow biome has a single mountain type, not snow-dusted random hills | Mixed grey/brown mountains mixed with silver peaks |

Implementation: **minimum cluster size** for every terrain type, and a
*target ratio* that the generator must hit before considering the map done.
Random-fill-with-clusters is OK; random-fill-without-clusters is not.

### 2. **Biome consistency**

> "You don't find palm trees in a snow biome."

The four outer biomes (grass, snow, desert, compact) get *allow lists*:

| Biome | Allowed | Forbidden |
|---|---|---|
| **grass** | plain, forest, mountain, river, village, barracks, road, gate | (everything else fine) |
| **snow** | plain (as tundra), forest (sparse), snow_peak, river, village, barracks, road | **mountain** (grey-brown doesn't match), desert motifs |
| **desert** | plain (as sand), river, road, village, barracks | **snow_peak**, **forest** (too lush for arid), **mountain** (rocky outcrops OK but rare) |
| **compact** | anything except snow_peak and forest-mixed-with-river (per style guide) | (broad) |

The generator must *re-roll* a cell whose weighted sample violated the biome
allow list. This is cheap (just re-sample until the result is in-allow) and
prevents the snow biome from sneaking in a forest.

### 3. **Resource distribution**

> "Villages cluster near roads and rivers; vaults sit behind castle walls."

- Each player HQ gets **1 village + 1 barracks within 4 cells** (a "spawn
  cluster").  The current `place_buildings` does something like this but
  greedily; we tighten the radius.
- **Vaults** (4 total) sit on the map such that the Voronoi partition
  between castles gives roughly equal vault count to each player.  The
  current spec is "place 4 vaults" which is too loose; the new rule is
  "at least one vault within 6 cells of every HQ."
- **Roads** form connected paths (not random walks that end mid-field).
  Each HQ has at least one road leading to a *distant* village (≥5 cells
  away) so units can use the movement-cost halving.

### 4. **HQ placement by geographic logic** (random maps only)

> "Castles aren't placed in the middle of a forest; they sit on clearings
> near resources."

The current generator places castles on the four corners via
`calculate_castle_positions(size, player_count)`. This is **fine for
competitive maps** (the 4 corner castles are the AW/FE standard) but
suffocating for "realistic" mode where players expect the HQs to feel
*grounded* in terrain.

For the realistic procedural generator (P2.7+), HQs are placed via:

1. **Pick HQ archetype per seat** based on the map biome:
   - grass → "lowland clearing" (plain-heavy surroundings, near forest edge)
   - snow → "frozen keep" (snow_peak ridge on one side, tundra on the other)
   - desert → "oasis" (river crossing, surrounded by plain-as-sand)
   - compact → "fortress" (5×5 castle_internal template, road exits)
2. **Score candidate cells** by:
   - distance to map edge (closer = more "frontier")
   - distance to map center (farther = more "own territory")
   - distance to nearest forest/mountain (closer = terrain-rich)
   - **avoid** cells that are inside dense forest (visibility penalty)
   - **avoid** cells that are in a road's path (would be cleared)
3. **Pick the top-N by score**, ensuring **pairwise distance ≥ 8 cells**
   (so two HQs can't spawn 2 cells apart).

The 2v2 / 3v3 / 4p layouts in `symmetry.calculate_castle_positions` are kept
**only for the hand-authored `balanced_*_Np` maps** and for the
`map_id=balanced_2p_15` style of lobby filter. The procedural generator
bypasses them.

### 5. **Procedural roster variety** (new)

> "An Advance Wars CO never starts with exactly 5 swordsmen."

Currently every unit spawns 5 units (2 swordsman + 1 archer + 1 knight +
1 healer), per `_CLASSIC_ROSTER` in `game_logic.py`. The new rule:

For each HQ:
- **Count**: pick a random integer in **[3, 7]** (uniform).
- **Composition**: pick from a pool of "balanced" templates:
  - **defensive** (2 swordsman + 1 archer + 1 healer)  — weight 2
  - **offensive** (1 swordsman + 1 knight + 1 archer + 1 warlock) — weight 2
  - **fast** (2 knight + 1 archer + 1 swordsman) — weight 1
  - **magic** (1 warlock + 1 healer + 1 archer + 1 swordsman) — weight 1
  - **siege** (1 knight + 1 warlock + 1 swordsman) — weight 1
- **Level**: with 30% chance, promote one swordsman to Lv2 (currently
  hand-authored maps hardcode this; for procedural, randomize per HQ so
  the player can't predict which one has the elite).

This gives 1-of-7 templates × {3-7 units} × Lv-up-roll = ~35 distinct
starting rosters per HQ. **Warlocks now appear in 4 of 7 templates**
(up from 0% before).

---

## 📋 Implementation plan

The spec breaks down into 5 tasks (mirrored to the task list):

1. **`spec`** — this document; the engineering contract.
2. **terrain_clusters** — tighten cluster min-size and isolation rules.
3. **biome consistency** — allow-list + re-sample in `_fill_base_terrain`.
4. **HQ placement by geographic logic** — new function in `symmetry.py`.
5. **procedural roster variety** — extend `_build_initial_units_from_castles`.
6. **regenerate + delete old random maps** — re-run `gen_style_presets.py`,
   re-render previews, commit.

Each task lands as a separate commit so review is granular.

---

## 🧪 Acceptance criteria

A new procedural map passes review if a tester (the human) can answer YES
to all of these:

- [ ] No single isolated terrain tile of a type that should cluster
      (forest, mountain). An "isolated" = 4-connected neighbours of
      different terrain. **Target: zero isolated trees/mountains.**
- [ ] Every HQ is within 4 cells of at least 1 village and 1 barracks.
- [ ] Every player has at least 1 vault within 6 cells of their HQ.
- [ ] Snow biome has zero `mountain` tiles; desert biome has zero
      `forest` / `snow_peak` tiles.
- [ ] At least one road segment connects each HQ to a *distant* village
      (≥ 5 cells away).
- [ ] Starting roster has 3-7 units; at least 20% of generated maps
      contain a warlock; 2p maps have at most one Lv2 unit per player.
- [ ] HQ pairwise distance ≥ 8 cells (no two HQs adjacent).
- [ ] Map is symmetric under 180° rotation **only** for the 4-corner
      and 2-diagonal layout; realistic mode can be asymmetric.

A map that fails any criterion is re-rolled (max 5 retries, then
accept and log "warning" to stdout so the test suite can flag it).

---

## 🔬 Out of scope (for this iteration)

- Per-biome music / palette changes (UI work).
- Story-driven naming ("The Frostfang Pass" etc) — just descriptive names.
- Dynamic weather / season (would need save-state changes).
- Custom user-authored realism rules (the `recommended_players: 4` field
  on a map is enough; per-tile "must be road" overrides are not yet).

---

## 📚 References

- MAP_GENERATION_PLAN.md §阶段 3-5 (clusters / rivers / roads) — what
  exists, what we keep.
- P2.6 spec `2026-07-07-data-driven-initial-units.md` — the
  `initial_units` schema that the new roster variety hooks into.
- P2.6 hand-authored `balanced_2p_15.json` / `balanced_3p_15.json` /
  `balanced_4p_20.json` — visual reference for "what real looks like."
- `tools/render_map_preview.py` — the test harness for visual review.
