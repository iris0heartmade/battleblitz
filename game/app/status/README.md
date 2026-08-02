# Status Effect 通用框架

BattleBlitz 后端的"异常状态 / Buff / Debuff"基础设施。本文档说明
**为什么有这个框架、它的数据形状、钩子如何工作、以及怎么加新 effect**。

---

## 为什么

之前的状态实现散落在 `app/commanders/effects.py` 里的一个特例(`silence_until_turn` 字段 +
`apply_silence_aura` 函数),只够支撑鸢影 CO power 的沉默领域。要加毒、麻痹、致盲、减速等
常规 SRPG 状态,继续按特例复制会变成 N 个并行字段 + N 套钩子逻辑,维护成本高。

所以先建一个 **通用框架**:Unit 上挂一个 `status_effects: list[dict]`,每项是一个 effect,
所有 effect 走 **同一组钩子**(`turn_start` / `should_skip_action` / `modify_hit_chance` /
`modify_mov` / `should_block_attack`)。加新 effect 只在注册表加一行,不改 schema。

---

## 数据形状

`Unit.status_effects`: `list[dict]`,每个 dict:

```python
{
    "type": str,             # "poison" / "paralyze" / "blind" / "slow" / "silence"
    "remaining_turns": int,  # 剩余大回合;每次 turn_start -1,<=0 时过期
    "applied_turn": int,     # 施加时的 game.turn_number(审计 / 排序)
    "applied_by": int | None,# 施加者 player_id
    "params": dict,          # type-specific 参数(见下表)
}
```

### 注册的 effect 与默认参数

| Type     | 中文 | Glyph | 默认参数 / 行为 |
|----------|------|-------|----------------|
| poison   | 毒   | ☠    | `dmg_pct=0.05`,3 回合;turn_start 扣 `max_hp × dmg_pct` |
| paralyze | 麻痹 | ⚡    | `miss_pct=0.25`,2 回合;turn_start 概率 skip 行动 |
| blind    | 致盲 | 👁    | `miss_pct=0.50`,2 回合;attack 命中率 ×(1-miss_pct) |
| slow     | 减速 | ❄    | `mov_mult=0.50`,2 回合;MOV 减半(最低 1) |
| silence  | 沉默 | 🔇    | 1 回合(鸢影沉默领域迁移);attack / counter 阻止 |

---

## 钩子函数(`app/status/engine.py`)

| 钩子 | 时机 | 返回 |
|---|---|---|
| `tick_effects_at_turn_start(unit, game_turn_number)` | 单位 owner 回合开始 | 本回合过期 / 消耗的 effect types |
| `should_skip_action(unit, rng=None)` | 单位回合开始(决策能否行动) | `(bool, str_reason)` |
| `modify_hit_chance(unit, base=1.0)` | 攻击命中计算 | `float` 乘子 |
| `modify_mov(unit, base)` | 移动范围计算 | `int` 调整后 MOV |
| `should_block_attack(unit, kind)` | 主动攻击 / 反击前 | `(bool, str_reason)`,kind ∈ `{"outgoing", "incoming"}` |
| `is_silenced(unit)` | 快速判断沉默 | `bool`(只读 status_effects,不读旧字段) |
| `get_status_summary(unit)` | UI tooltip | `list[dict]`,含 type / display_cn / glyph / remaining |

---

## 怎么加新 effect(典型流程)

例:加 **stun** —— 受击 50% 概率跳过下回合行动。

1. **改 schemas** (`game/app/schemas.py`):无需修改,数据形状通用。
2. **注册 effect** (`game/app/status/effects.py` `EFFECT_DEFS`):

   ```python
   "stun": EffectDef("stun", "眩晕", "💫", 1, {"skip_pct": 0.50}),
   ```
3. **写钩子**(若需要):多数情况现有钩子已够用;若新逻辑(比如"读 remaining 时按 hit / per-turn 触发 X 事件"),
   在 `engine.py` 加函数,在调用方接入。
4. **应用**:`add_effect(unit, "stun", applied_turn=game.turn_number, applied_by=player_id)`
5. **godot 端**(`godot-client/scripts/board/unit_node.gd` `_STATUS_GLYPH`):加 `"stun": "💫"`。
6. **测试**(`game/tests/test_status_effects.py`):加新 effect 的 add/tick/钩子测试。

---

## 接入情况(本 PR 范围)

| effect | 框架 + 测试 | game_logic / routes 实时钩子 |
|---|---|---|
| silence | ✅ 已就位 | ✅ 通过 `commanders/effects.py:is_unit_silenced` 接入 attack / counter |
| poison | ✅ 已就位 | ✅ turn_start 扣 HP(`tick_effects_at_turn_start` 钩入 `on_player_turn_start`) |
| paralyze | ✅ 已就位 | ✅ turn_start 概率 skip(`should_skip_action` 钩入 `on_player_turn_start`) |
| blind | ✅ 已就位 | ✅ attack 每 hit 独立判定 miss(`modify_hit_chance` 钩入 `attack_with_double_strike`) |
| slow | ✅ 已就位 | ✅ turn_start 减半 mov(`_refresh_mov_debuff` 钩入 `on_player_turn_start`) |

**实时钩子调用顺序**(`on_player_turn_start`):

```
对每个 owner_unit:
  should_skip_action(unit)         # paralyze 在 tick 前判断,过期清理后会查不到
    → 若 skip: has_acted=True + paralyzed_until_turn=game_turn_number
  _refresh_mov_debuff(unit)       # slow 的 mov 调整在 tick 前(slow effect 还没被清)
  tick_effects_at_turn_start(unit) # 最后扣 remaining_turns,过期清理
```

盲打 / 沉默 / 反击拦截:`attack_with_double_strike` 内 `_maybe_miss` wrap 一次
blind 判定,沉默通过 `is_unit_silenced` 在 `routes/actions.py` 入口拦截。

---

## 过渡期:silence 迁移

- **旧**:`Unit.silence_until_turn: int`(0 = 未沉默)
- **新**:`Unit.status_effects[].type == "silence"`(remaining_turns > 0)

`apply_silence_aura` 同时写两个字段。`commanders.effects.is_unit_silenced` 优先读新字段、
fallback 旧字段,确保:
- 旧 `silence_until_turn` 数据存档可读(默认值 0 不影响)
- 新 `status_effects` 写入即时生效
- 沉默领域 power 行为完全一致(旧测试 `test_silence_aura.py` 全部通过)

待 status_effects 在所有调用方稳定后,可删除 `silence_until_turn` 字段。