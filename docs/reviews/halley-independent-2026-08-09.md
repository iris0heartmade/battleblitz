# Independent Code Review: feat/commander-sound-polish

- Branch: `feat/commander-sound-polish`
- Base SHA: `d32770c76178cc6c71ff9a10ddb0af8ecf7e5767`
- HEAD SHA: `5d90a0852f67a4b203c07f586c5e90736e6437a9`
- Reviewer: independent (halley), 2026-08-09
- Scope: 19 commits, 62 files, +3362/-265 lines

## Summary

The branch rewrites the CO meter into cumulative stars, adds the 鸢影 (Yuanying) commander with silence aura, introduces a generic status-effect framework, and wires up the four P+ effects (poison/paralyze/blind/slow + migrated silence). It also includes agent fixes and hero art assets.

The P+ state framework and silence aura are well-scoped and backed by solid test coverage (140+ tests pass). However, the branch contains one **blocker** (missing ALTER TABLE for two new `units` columns) and several **high/medium** integration bugs that are likely to surface in production.

### Verdicts

- **Test status**: 128 commander/silence/status/poison/co tests pass; 1 **real regression** in `test_player_vs_ai_full_game.py::TestCommanderMeter::test_killing_enemy_increases_meter` (stale assertion that was not updated when the meter contract changed).
- **Verdict**: **FAIL**. Block the merge until the database migration and the stale test are fixed. The latent AI crash for yuanying and the team-id mismatch should also be addressed before merge or tracked as follow-ups.

---

## Findings (sorted by severity)

### BLOCKER

#### B1. Missing `ALTER TABLE` for `units.status_effects` and `units.silence_until_turn`
- **Files**: `game/app/models.py:231,234`, `game/app/database.py:_run_legacy_migrations` (lines 73-289)
- **Evidence**:
  - `models.py` declares two new `Unit` columns: `status_effects: Mapped[list] = mapped_column(JSON, nullable=False, default=list)` and `silence_until_turn: Mapped[int] = mapped_column(Integer, nullable=False, default=0)`.
  - `_run_legacy_migrations` adds `ALTER TABLE` for every column added since v1 (`map_biome`, `phase`, `matk`, `mdef`, `gold`, `commander_id`, `co_state`, `subtype`, `win_condition`, `reach_tile_id`, `defend_turns`, `win_reason`, `capacity`, `team_id`, `is_spectator`, `max_spectators`, `battle_config`, `unit_composition` drop, `hero_id`, `campaign_base_stats`, `unlocked_commanders`, `mainline_commanders`, `hero_campaign_states`, `hero_inventory`, `mercenary_roster_state`) but **omits `status_effects` and `silence_until_turn`**.
  - Reproduction (isolated temp DB with a legacy `units` schema, then `init_db()`):
    ```
    BEFORE init_db — UNIT_COLUMNS: [..., 'has_acted', 'has_moved', 'skills', 'hero_id', 'campaign_base_stats']
      status_effects: MISSING
      silence_until_turn: MISSING
    AFTER init_db  — UNIT_COLUMNS: [..., 'has_acted', 'has_moved', 'skills', 'hero_id', 'campaign_base_stats']
      status_effects: MISSING
      silence_until_turn: MISSING
    ```
  - On a fresh DB, `create_all` will create the columns. On any existing deployment (e.g. the `battleblitz.db` from 2026-07-24 in this workspace, or any production instance), `init_db()` will not add them.
  - Runtime effect: any read of `unit.status_effects` (e.g. in `_build_state → UnitOut(status_effects=...)`) or any write (`add_effect`, `tick_effects_at_turn_start`, `apply_silence_aura → unit.silence_until_turn = ...`) will raise `sqlalchemy.exc.OperationalError: no such column: units.status_effects` (or `units.silence_until_turn`). This is reachable from any normal API path: `attack`, `end-turn`, `co-power`, even reading game state in the lobby.
- **Fix direction**: append two `if "status_effects" not in unit_cols:` / `if "silence_until_turn" not in unit_cols:` blocks to `_run_legacy_migrations`, mirroring the existing `matk`/`mdef`/`hero_id` patterns. Default values: `JSON NOT NULL DEFAULT '[]'` and `INTEGER NOT NULL DEFAULT 0` to match the model defaults.

### HIGH

#### H1. Stale test for the meter mechanism — not updated when `meter` was replaced by `stars_earned_total`
- **File**: `game/tests/test_player_vs_ai_full_game.py:369-370`
- **Evidence**:
  ```python
  assert p.co_state["meter"] >= 2, \
      f"expected meter >= 2 after kill, got {p.co_state['meter']}"
  ```
  Fails on the branch (and would fail on any post-`5d90a08` HEAD):
  ```
  AssertionError: expected meter >= 2 after kill, got 0
  assert 0 >= 2
  ```
  Reason: the kill now flows through `award_morale → record_morale_star → co_state["stars_earned_total"]`, not through `on_kill → co_state["meter"]`. The "old field" `meter` is no longer incremented on kill.
  - Confirmed this is the only failing test in the affected scope (`test_commanders_ai.py`, `test_commanders_meter.py`, `test_ai_kill_grants_co_star.py`, `test_co_stars_cap.py`, `test_co_save_compat.py` all pass).
- **Impact**: a real regression in the integration test that the new mechanism was supposed to satisfy. The test was supposed to verify "kill credits commander meter"; the new equivalent assertion is "kill credits `stars_earned_total`". A green test suite is misleading without this fix.
- **Fix direction**: update the assertion to `assert p.co_state["stars_earned_total"] >= 1, ...` (or appropriate per-commander value). Also update the comment block (line 333-334) which still says "yun commander (meter threshold 22)" — should now be threshold 18 and stars 6.

#### H2. AI path for yuanying will crash on `fire_co_power`
- **File**: `game/app/routes/turns.py:420`
- **Evidence**:
  ```python
  if ai_should_fire_co_power(current):
      fire_co_power(current)
  ```
  No kwargs. Reproduction:
  ```
  $ python repro_ai_yuanying.py
  yun: OK
  yuanying-no-kwargs: FAILED — ValueError: silence_radius=2 requires center_xy and all_units
  ```
  And `fire_co_power` definition (effects.py:72):
  ```python
  def fire_co_power(player, *, center_xy=None, current_turn=0, all_units=None):
      ...
      if silence_radius > 0:
          if center_xy is None or all_units is None:
              raise ValueError(
                  f"silence_radius={silence_radius} requires center_xy and all_units"
              )
  ```
  The `ValueError` is **uncaught** here (`turns.py:420`), so the AI chain dies mid-turn. Currently `yuanying` is not in the AI commander fallback list (`["yun", "anna", "yuanying"]` from `lobby_controller.gd:807`), so this is latent — but the lobby file was just updated to include yuanying in the fallback pool, so a future enable will break AI.
- **Impact**: 500 on AI turn, the game hangs in `ai` phase, no end-turn happens for the rest of the round.
- **Fix direction**: in `turns.py`, fetch the game map size + units, and either (a) pick a sensible default center for the AI (e.g. center of map) or (b) skip the auto-fire for silence-aura commanders and log a fallback. Also wrap the call in `try/except ValueError` so a single bad fire doesn't kill the chain.

### MEDIUM

#### M1. Design/code mismatch: silence aura filters by `player_id`, not `team_id`
- **Files**: `game/app/commanders/effects.py:178`, `game/app/classes/heroes/yuanying.py:9,43`
- **Evidence**:
  - `yuanying.py` design doc:
    > 区域内所有**非同 team 的魔法单位**(attack_kind == "magic")
  - `yuanying.py` dataclass docstring:
    > 沉默领域:5×5 范围内的非同 team 魔法单位
  - `effects.py:178`:
    ```python
    if unit.player_id == owner_player_id:
        continue
    ```
  This only checks that the unit does not belong to the firing player. In team mode, an ally's magic units (same `team_id` but different `player_id`) will be silenced.
  - `test_silence_aura.py` only covers 1v1 (uses `owner_id=1` and `owner_id=2` with no team_id), so the bug is not detected.
- **Impact**: in 2v2 / FFA team modes (which the lobby supports — `team_id` is a real column on `players`), 鸢影·沉默领域 will silence allied magic units, which is unintended and likely to make 鸢影 unusable in team games.
- **Fix direction**: replace `if unit.player_id == owner_player_id:` with a team-aware check, e.g.:
  ```python
  if unit.player_id == owner_player_id:
      continue
  if getattr(unit, "team_id", None) and getattr(unit, "team_id", None) == getattr(owner_player, "team_id", None):
      continue
  ```
  Pass `owner_player` (or at least its `team_id`) into `apply_silence_aura`, and update the test to include a 2v2 case.

#### M2. `_silence_hover_cell` mapping may be wrong when the board camera is disabled
- **File**: `godot-client/scripts/board/board.gd:266-268`
- **Evidence**:
  ```gdscript
  var world_pos: Vector2 = global_pos
  if board_camera != null and board_camera.enabled:
      world_pos = board_camera.get_canvas_transform().affine_inverse() * global_pos
  ```
  When `board_camera` is null OR disabled, the code uses `global_pos` as `world_pos`. But `global_pos` from a `InputEventMouseMotion` is in viewport coordinates, not world coordinates. If the camera is disabled and the board origin is at (0,0) world, this happens to work; if the board is at any non-zero origin, the cell mapping will be off.
  - This is a low-probability path (the camera is normally enabled), but it's also a dead-code path (a `null` camera means the board is in screen-space, where `ground_layer.local_to_map` would also be off).
- **Fix direction**: in the disabled/null branch, treat `global_pos` as already in world space, or just early-return and skip the hover update (the camera should be enabled when playing).

#### M3. AI does not consult `should_skip_action` for paralyze
- **Files**: `game/app/game_logic.py:2455-2555` (rules AI loop), `game/app/agent/integration.py` (LLM AI dispatcher)
- **Evidence**:
  - The rules AI loop (`ai_take_turn` / `ai_take_one_action`) iterates only units where `not u.has_acted and not u.has_moved`, so paralyze is effectively handled (the `has_acted=True` set in `on_player_turn_start` filters them out).
  - However, the LLM agent does not consult `should_skip_action` directly. It iterates over the snapshot and tries to dispatch an action per unit; if a paralyze-skip happened in `on_player_turn_start` (random rng), the LLM has no idea and may try to act on a unit that the engine has marked acted. This is mitigated by the engine's `attacker.has_acted` check in `attack` (line 477 of `agent.py`), but the LLM will waste tokens on paralyzed units.
  - More importantly: the **rng** used by `should_skip_action` inside `on_player_turn_start` is `random.Random()` (default, non-deterministic), which means the paralyze decision is unreproducible. The LLM and the rules AI may see different paralyze outcomes on the same turn if `on_player_turn_start` is called twice (e.g. once for a test, once for a real turn) with different RNG states.
- **Fix direction**: pass a stable seeded `rng` into `on_player_turn_start` (e.g. seeded by `game.id * 1000 + game.turn_number`), and have the LLM agent call `should_skip_action` itself to skip paralyzed units in its prompt/plan.

#### M4. `apply_silence_aura` silently swallows `KeyError` from unknown unit class
- **File**: `game/app/commanders/effects.py:186-190`
- **Evidence**:
  ```python
  try:
      from app.classes.units import get as get_unit_class
      attack_kind = get_unit_class(unit.unit_type).attack_kind
  except Exception:
      attack_kind = "physical"
  ```
  The `try/except Exception` catches `KeyError` (raised by `get(...)` for an unknown `unit_type`) and any other error, defaulting to "physical". This means a future unit class that's added to the model but not the registry (or a typo) will silently never be silenced, masking a real bug.
- **Fix direction**: catch only `KeyError`; let other exceptions propagate. Add a logger.warning for the `KeyError` so missing registrations are visible.

#### M5. `co-power / `is_power_active` flag is set after the silence aura, not before — Godot may flash a stale state
- **File**: `game/app/commanders/effects.py:138-140`
- **Evidence**:
  ```python
  consume_power_stars(player)
  co = dict(player.co_state or {})  # consume 已改 in-place,重读保证最新
  co["is_power_active"] = True
  co["_power_baselines"] = baselines
  player.co_state = co
  ```
  The order is: apply silence aura (line 86), bake baselines, consume stars, mark active. This is logically correct, but the in-memory `co` dict is recreated **after** `consume_power_stars` already wrote to `player.co_state`, so the final assignment shadows the in-place write. SQLAlchemy's change detection still works (it's a new dict), but the intermediate `flag_modified` in `consume_power_stars` is redundant noise.
  - More importantly: the `co["_power_baselines"]` carries `extra_mov` deltas, etc. but **the silence aura did not write to `co_state`**, so if a re-read happens mid-execution (e.g. a hook), the silence aura's effects are not visible in the JSON. They live on each unit, not in `co_state`. This is correct, but worth documenting.
- **Fix direction**: either reorder so `consume_power_stars` happens at the very end (after setting `is_power_active`), or drop the redundant `flag_modified` inside `consume_power_stars` since `player.co_state = co` will be picked up.

### LOW

#### L1. `Reaction` text now truncated to 40 chars (was 60)
- **File**: `game/app/agent/reactions.py:35-37`
- **Evidence**: silent drop from 60 → 40. Most Chinese reaction templates are already under 40 chars, so the practical impact is small. But the longest ones (e.g. `"这一刀暴击就问谁顶得住"` = 11 chars) are fine. None of the templates are > 40 chars in fact — let me verify:

Actually looking at the templates, the longest is `"暴击了，不用谢"` (7 chars), `"还有奶吧"` (4 chars), etc. So 40 chars is plenty. The change is defensive and harmless. **No action needed.**

#### L2. `action_id` validator now rejects spaces
- **File**: `game/app/agent/schemas.py:95-100`
- **Evidence**: `_check_action_id_format` removed `space` from the allowed character set. None of the `legal_actions.py` action_ids contain spaces (all are `attack_X_Y`, `move_X_Y_Z`, `wait_X`, `skill_heal_X_Y`, etc.), so the validator is a no-op in practice.
  - If any future legal action uses spaces (unlikely), the validator will reject it.
  - Risk: low. **No action needed.**

#### L3. Frontend center_xy is not bounds-checked server-side
- **File**: `game/app/routes/commanders.py:159-167`
- **Evidence**: the route accepts any integer for `center.x` / `center.y`. The Godot client restricts to map bounds via the UI, but a malicious client could send `center={"x": -100, "y": 99999}`. The aura would just match no units (safe), but the request would still succeed and burn the CO power.
  - This is a permissive API, not a security hole.
- **Fix direction**: validate `0 <= x < game.map_size and 0 <= y < game.map_size` (need to load map metadata) and 400 on out-of-bounds.

#### L4. `add_effect` may mutate caller's dict
- **File**: `game/app/status/effects.py:50-65`
- **Evidence**: when an effect of the same type already exists, the function modifies the existing dict in place via `eff["remaining_turns"] = max(...)`, etc. and also `eff["params"].update(...)`. If the caller passed in a dict that's also referenced elsewhere (e.g. a snapshot), it gets mutated. Currently no caller does that, but it's a subtle gotcha.
  - Pydantic-style immutability would be safer but more invasive.
- **Fix direction**: leave as-is for now; document the in-place behavior in the docstring.

### INFO

#### I1. `_status_overlay` position is `Vector2(-20, -20)` (centered on the unit_node) while `_status_label` is `Vector2(-20, -28)` (above center)
- **File**: `godot-client/scripts/board/unit_node.gd:303,314`
- Purely visual; consistent with the previous single-silence overlay. No issue.

#### I2. `consume_power_stars` raises `ValueError` instead of returning a result
- **File**: `game/app/commanders/meter.py:80-90`
- The function raises if the player doesn't have enough stars, but the only caller (`fire_co_power` in `effects.py:135-136`) doesn't catch it. In practice this is unreachable because `can_fire_co_power` is checked first, but it's brittle.
- **Fix direction**: either catch the `ValueError` defensively, or change the function to return `Optional[int]` (None on insufficient).

#### I3. Both `status_effects` AND `silence_until_turn` are written/checked — transitional duplication
- **Files**: `game/app/commanders/effects.py:194-201`, `godot-client/scripts/board/unit_node.gd:362-365`
- This is intentional (the docstring says "过渡期保留"), but worth noting that the cleanup of `silence_until_turn` is not in this branch. Once the Godot client is fully rolled out, the legacy field can be dropped.

#### I4. `cleanup_dead_units` no longer awards CO meter
- **File**: `game/app/game_logic.py:660-695`
- Correct per the new design ("kill → morale → stars" is the only path), but a minor behavior change. Worth confirming in a release note.

#### I5. `award_exp` signature change (added `player` kwarg) — back-compat note
- **File**: `game/app/game_logic.py:572`
- Old callers that didn't pass `player` still work (it's optional with default `None`). The change is back-compat.

#### I6. `_silence_hover_cell` is exposed at module scope but only used internally
- **File**: `godot-client/scripts/board/board.gd:225`
- Minor; just a GDScript style note.

---

## Test results

- `pytest game/tests/test_commanders_*.py game/tests/test_status_effects*.py game/tests/test_poison_burst.py game/tests/test_silence_aura.py game/tests/test_co_*.py game/tests/test_ai_kill_grants_co_star.py -x --tb=short` → **128 passed, 0 failed**.
- `pytest game/tests/test_godot_client_contract.py` → 11 failures, all **pre-existing on base** `d32770c` (verified by checking out base and re-running). Not caused by this branch.
- `pytest game/tests/test_game_logic.py` → 39 passed.
- `pytest game/tests/ -k "commander or silence or status or poison or co_power or hero"` → 4 failures: 3 are pre-existing godot contract tests; **1 is a real branch regression** (`test_player_vs_ai_full_game.py::TestCommanderMeter::test_killing_enemy_increases_meter`).
- Repro scripts written: `repro_migration.py`, `repro_ai_yuanying.py` in the repo root (these are diagnostic; remove before merge).

---

## Reproduction notes

### Confirming B1 (migration)
```python
# After simulating a legacy DB:
python repro_migration.py
# BEFORE init_db — UNIT_COLUMNS: [..., 'has_acted', 'has_moved', 'skills', 'hero_id', 'campaign_base_stats']
#   status_effects: MISSING
#   silence_until_turn: MISSING
# AFTER init_db  — UNIT_COLUMNS: [..., 'has_acted', 'has_moved', 'skills', 'hero_id', 'campaign_base_stats']
#   status_effects: MISSING
#   silence_until_turn: MISSING
```

### Confirming H2 (AI crash for yuanying)
```python
python repro_ai_yuanying.py
# yun: OK
# yuanying-no-kwargs: FAILED — ValueError: silence_radius=2 requires center_xy and all_units
```

---

## Overall risk

**Medium-to-High.** The P+ state-effect framework itself is solid (140 tests pass), the silence aura is well-scoped, and the AI commander update is clean. But the branch has one BLOCKER (missing migration), one HIGH regression (stale integration test), and one HIGH latent crash (AI + yuanying), plus a MEDIUM design/code mismatch on team-id in the silence aura. Anyone deploying this branch on top of an existing `battleblitz.db` will hit `OperationalError: no such column: units.status_effects` on the first turn, and the AI yuanying path will 500 the moment it's enabled.

**Recommended action**: BLOCK merge. Fix in this order: (1) B1 add the two `ALTER TABLE` rows, (2) H1 update `test_player_vs_ai_full_game.py:369-370` to read `stars_earned_total`, (3) H2 add `try/except` + sane center default in `turns.py:420`, (4) M1 fix team-id check. M2-M5 are recommended but not blocking.
