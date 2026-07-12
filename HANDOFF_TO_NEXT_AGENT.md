# 🤝 HANDOFF: P2.6 Data-Driven Initial Units — Continuation

**From:** Claude (session #2402e46c-df72-44b8-a438-de41fb61138c)
**To:** Next Claude agent
**Date:** 2026-07-07
**Working directory:** `D:/PyCharm Community Edition 2024.3.3/PycharmProjects/BattleBlitz`
**Branch:** `feat/p2.6-data-driven-initial-units`
**Status:** Pushed to GitHub. Core refactor done. Tests: 515 passed, 1 skipped, 0 failed. **Tasks 13–15 not finished.**

## 📍 Where We Are

16 commits on the feature branch already pushed to GitHub remote `github/feat/p2.6-data-driven-initial-units`. The data-driven initial_units refactor mostly works — the engine, all 41 maps, the test map, and the mainline battle flow are all migrated. Web UI has had the composition dropdown removed.

What's left is paperwork + manual verification:

| Task | Status | Brief path |
|---|---|---|
| Task 13 (test fixtures) | ✅ Effectively done — Task 6 handled it; only one reverse-assertion test (`test_integration_smoke.py:69` asserts `"unit_compositions" not in body`) remains, which is the *intended* new behavior | `.superpowers/sdd/briefs/task-13-brief.md` |
| Task 14 (docs) | ⏳ **NOT DONE** | `.superpowers/sdd/briefs/task-14-brief.md` |
| Task 15 (final e2e) | ⏳ **NOT DONE** | `.superpowers/sdd/briefs/task-15-brief.md` |

Plus one bug fix I caught mid-wrap-up but never committed:

- File `game/app/web/app.js` around lines 442-448 had a dangling `for (const u of presets.unit_compositions)` loop. Task 12 fixed most of the Web UI, but my latest patch removed that loop entirely. **Verify it's in `c8f5cb3` and there's no `unit_compositions` reference anywhere in `game/app/web/`.** (If not, the dropdown removal is broken at runtime.)

## 🎯 Concrete Remaining Tasks (in priority order)

### 1. Verify the `app.js` patch landed cleanly

Open `game/app/web/app.js`, search for `unit_compositions`. Expect zero matches. If found, run the patch I added:

```javascript
// at line ~441, before "// P2.6 — unit_composition dropdown removed":
for (const u of presets.unit_compositions) {
    const opt = document.createElement("option");
    opt.value = u.id;
    opt.textContent = `${u.name} — ${u.description}`;
    opt.dataset.desc = u.description;
    unitsSel.appendChild(opt);
}
// DELETE these 6 lines entirely.
```

Then verify with `cd game && python -m pytest -q` (should still be 515 passed).

### 2. Task 14 — update docs

Read the brief: `.superpowers/sdd/briefs/task-14-brief.md`

Files to touch:
- `README.md` — line 308 API table: remove `unit_composition` from `POST /games` body
- `docs/架构.md` — line ~239 schema table: drop `unit_composition` column; lines ~760/762: drop `"composition": "..."` examples
- `docs/路线.md` — line 169: drop example payload `"unit_composition": "classic"`
- `docs/superpowers/specs/2026-06-30-victory-conditions-spec.md` — line ~242: `CreateGameRequest` example
- `docs/superpowers/specs/2026-06-30-magic-attack-warlock-spec.md` — lines 101/102/206/207/386/416: replace `default_roster()` references with a note about being superseded by P2.6

Commit: `git commit -m "docs(p2.6): remove unit_composition/default_roster references"`

Then **push to GitHub**:
```bash
git push github feat/p2.6-data-driven-initial-units
```

### 3. Task 15 — final e2e verification

Read brief: `.superpowers/sdd/briefs/task-15-brief.md`

Steps:
1. `cd game && python -m pytest -q` — expect 515+ passed
2. Start server: `cd game && uvicorn app.main:app --port 8001 &`
3. `curl -s http://localhost:8001/games/presets | jq '.unit_compositions'` — expect `null`
4. `curl -s http://localhost:8001/games/presets | jq '.maps[] | select(.id=="test_arena_10x10_2v2") | .initial_units | length'` — expect `20`
5. Run AI demo: `cd game && python tools/ai_battle_demo.py --map test_arena_10x10_2v2 --players 4 --max-turns 30` — should complete cleanly
6. (Optional but recommended) Manual browser smoke test of `test_arena_10x10_2v2`

If anything fails, file a new task with diagnostic info.

## 📚 Reference Reading

- **Spec:** `docs/superpowers/specs/2026-07-07-data-driven-initial-units.md` — what we built toward
- **Plan:** `docs/superpowers/plans/2026-07-07-data-driven-initial-units.md` — the 15-task blueprint
- **Final report:** `.superpowers/sdd/FINAL_REPORT.md` — what got done, by what commit, with what test result
- **All task briefs:** `.superpowers/sdd/briefs/task-{N}-brief.md` (1-15)

## 🗂️ Files Most Likely to Need Attention

Already touched in this refactor — verify they stay clean:
- `game/app/game_logic.py` — `_resolve_size()`, `MapPresetResult`, validation, `_classic_initial_units`
- `game/app/routes/game.py` — new spawn loop, no more rosters_by_seat
- `game/app/routes/mainline.py` — uses `battle.map_id`
- `game/app/mainline/schemas.py` — `BattleSpec` rewritten
- `game/app/classes/units/__init__.py` — should have NO `_COMPOSITIONS` / `default_roster` / `list_compositions` / `get_roster_for_composition`
- `game/app/schemas.py` — `unit_composition` should be gone from `CreateGameRequest`
- `game/app/models.py` — `unit_composition` column should be gone
- `game/maps/*.json` — 41 maps should all have `initial_units`
- `game/app/web/{index.html,app.js}` — `#new-unit-composition` dropdown should be gone

## ⚠️ Tricky Bits

1. **`test_arena_10x10_2v2` AI demo sometimes deadlocks at T=1** because the AI tries to move an occupying unit off itself (the squad ends up blocking itself in corner HQs). **This is pre-existing** — the map is small enough that AIs collide. If the demo hangs, that's not a regression.

2. **The procedural `"classic"` fallback generates 5 units per player at fixed offsets from castles.** If a player count > 4 is requested, the extra players fall through to castle positions. Don't change this without a unit test.

3. **The `size` JSON field accepts both `int` and `{width, height}` dict.** Task 1's `_resolve_size()` handles both. The new `test_arena_10x10_2v2.json` uses dict form; the 40 legacy maps were migrated keeping their original `int` form (e.g. `"size": 15`).

4. **`game/app/database.py:_run_legacy_migrations` has a hardcoded `2026-07-07` block** that issues `ALTER TABLE games DROP COLUMN unit_composition` because this project doesn't run Alembic. Don't delete that block — existing databases still have the column.

## 📞 Quick Commands

```bash
# Check git state
cd D:/PyCharm/Community/Edition/2024.3.3/PycharmProjects/BattleBlitz
git log --oneline -20
git branch -v

# Run tests
cd game && python -m pytest -q

# Start server
cd game && uvicorn app.main:app --port 8001

# Push to GitHub
git push github feat/p2.6-data-driven-initial-units
```

## 🎨 If You Want to Continue Using Subagent-Driven Development

The plan at `docs/superpowers/plans/2026-07-07-data-driven-initial-units.md` has 15 tasks. Tasks 1-12 are done (16 commits). Tasks 13-15 are small remaining work — you can either:
- Do them inline (they're short)
- Dispatch 1 subagent to do Task 14 + verify Task 15 (about 15 minutes)

I recommend inline since they're small. Whichever you choose, just remember to push at the end.

## 🐾 Closing Notes

The hard part is done. Map data drives initial units; engine respects it; legacy fallback is graceful. Web and DB have been migrated. The remaining work is documentation polish + final manual verification + a final `git push`. You got this.

— Claude (giving you the baton)
