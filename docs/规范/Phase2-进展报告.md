# Phase 2 双轨制落地 · 进展报告

> **日期**:2026-07-23  
> **Branch**:`refactor/extract-mainline-modules`  
> **基线**:`master fea0066`  
> **依据**:`docs/规范/双轨制单位模型设计方案.md`

---

## 0. 一句话总结

> **Generic 单位 L1 spawn 已跑通,新增 4 类可上棋盘;Free mode L10 baseline 已接通。Hero 等设计稿。**

---

## 1. 已经完成(4 个 commit)

| Commit | 内容 | 测试 |
|---|---|---|
| `6c42913` | 4 个新 Generic 单位类(.py,auto-register) | pytest pass |
| `9e77e4f` | `game/app/modes.py` — GameMode/ModeConfig + `spawn_generic_stats()` + `spawn_hero_stats()` STUB | 21 tests / all pass |
| `2da2ef2` | `_start_battle_internal` 接 `apply_spawn_generic_to_unit` | 6 新 in-memory tests |
| `94d6c5f` | Free mode L10 baseline — `mode` 字段透传 spawn 路径 | 6 新 mode tests |

---

## 2. 现在能给普通单位什么

### 2.1 已可用的 15 个 Generic 兵种

```
BB 原 11 个(数值未动,保持向后兼容):
  swordsman, archer, knight, warlock, healer,
  blade_master, paladin, sage, saint, sniper, dragon_rider

Phase 2 新增 4 个(FE8 L10 expected 1:1 校准):
  lancer       HP 27 / Atk 8  / Def 7 / Mov 5   (枪 T1,Cavalier style)
  warrior      HP 28 / Atk 10 / Def 3 / Mov 3   (斧 T1,Fighter style)
  berserker    HP 30 / Atk 14 / Def 5 / Mov 4   (斧 T2,Berserker style)
  falcon_knight HP 25 / Atk 9 / Def 6 / Mov 6   (飞行 T2,Falcon style)
```

→ 用 auto-discovery 机制,不需在 `__init__.py` 注册,新增 .py 自动 pick up。

### 2.2 Free mode 端到端可走通

```python
# 客户端改 1 行字段
POST /games { mode: "free", name: "...", map_preset: "classic" }
# 全链路:FREE → start_level=10 → spawn_generic_stats(L10)
# → 每个 Generic 单位 HP/Atk/Def 按 Boss-autolevel 公式上涨
```

| 单位 | L1 hp | L10 hp | L1 atk | L10 atk |
|---|---|---|---|---|
| lancer | 27 | **34** (+7) | 8 | **12** (+4) |
| warrior | 28 | **36** (+8) | 10 | **14** (+4) |
| falcon_knight | 25 | **32** (+7) | 9 | **13** (+4) |
| swordsman(原有) | 45 | **52** (+7) | 18 | **22** (+4) |

→ Lancer L10 BP 跟 Generic "老兵" 差不多,主路线玩家玩起来不会觉得 free = 海量碾压。

### 2.3 ModalConfig + spawn 公式已经齐

```python
class ModeConfig:
  name: GameMode        # MAINLINE / FREE / TUTORIAL
  start_level: int = 1
  chapter_multiplier: float = 1.0
  autolevel_pace: Literal["boss", "class"] = "boss"

class GameMode(str, Enum):
  MAINLINE = "mainline"  # L1 baseline (FE8 L10 1:1)
  FREE = "free"          # L10 baseline (Boss-autolevel)
  TUTORIAL = "tutorial"

AUTOEVEL_RATES = {"hp":85,"atk":50,"matk":50,"def":10,"mdef":15}
# FE8 Boss pattern,Generic 不靠 per-class growth,改 autolevel cap
```

### 2.4 现有 spawn 公式 100% 沿用 FE8 Boss 模式

```
final_stat = base + (start_level - 1) × autolevel_rate / 100
```

→ Generic 单位永远可预测(不随机)。**chapter multiplier(attack_modifier 等)+ level_offset** 另算(没动)。

---

## 3. 当前测试覆盖

```
tests/test_modes.py:                         27/27 PASSED
  ├─ GameMode enum 3-mode
  ├─ ModeConfig builder + frozen
  ├─ AUTOEVEL_RATES = FE8 Boss
  ├─ spawn_generic L1 == class.base
  ├─ spawn_generic L10 = +9 × rate
  ├─ spawn_generic mov / attack_range 不缩放
  ├─ spawn_generic L20 caps 合理
  ├─ spawn_generic start_level < 1 clamp
  ├─ spawn_generic 全 15 type_id
  ├─ spawn_hero 抛 NotImplementedError
  ├─ apply_spawn_generic_to_unit:
  │    - L1 == class.base(4 新类逐项断言)
  │    - L10 + 7 HP / +4 Atk
  │    - clamp 子 L1
  │    - 保留 x/y/name/skills
  │    - 4 新类 spawn path in-memory
  └─ Free mode 派生:
       - ModeConfig.mainline → L1
       - ModeConfig.free → L10
       - ModeConfig.free(15) → L15
       - GameMode.value 跟 schema literal 对齐
       - apply_spawn L10 dict 同步
       - L10 > L1 数值断言

tests/test_mainline_api.py:                  35 passed
  └─ 老 mainline 流程零破坏(L1 spawn 等价于 class.base)

全套含 4 个文件 62 passed
```

---

## 4. 工作树状态

```
refactor/extract-mainline-modules /
├── docs/路线/FE8-vs-BattleBlitz-对照改进建议.md        (上一波 refactor 出的对照)
├── docs/路线/FE8-职业-角色成长参考表.md                  (FE8 growth 对照)
├── docs/规范/双轨制单位模型设计方案.md                    (Phase 2 design doc,4 commits 引用)
├── docs/规范/Phase2-进展报告.md                          (本文件)
├── game/app/modes.py                                      (3 个新文件 + 1 个 stub)
├── game/app/classes/units/lancer.py                        (
├── game/app/classes/units/warrior.py                       ( 新增 4 类
├── game/app/classes/units/berserker.py                     (
├── game/app/classes/units/falcon_knight.py                (
├── game/app/routes/game.py                                (改动 2 处 + 1 处)
├── game/app/schemas.py                                    (CreateGameRequest +mode)
└── game/tests/test_modes.py                                (27 tests)
```

---

## 5. 待办(分优先级)

### 5.1 待用户提供 Hero 设计稿(阻塞)

Phase 2 §4 / §6.5.3 的 `spawn_hero_stats()` 显式 raise NotImplementedError。要解锁:

- Hero 单位 10 名(yun/anna/seth/eirika/ephraim/colm/knoll/neimi/tana/oneill)
- 角色专属成长(替换 class.growth)
- 转职触发 timing / promotion line
- Hero L1 base 怎么定 / 受什么 modifier 影响

→ 用户给 design doc 后一次性接上。

### 5.2 客户端接 `mode` 字段(Godot 端,可不阻塞后端测试)

- 大厅页加 "Free 模式" / "主线模式" 切换按钮
- `create_room` payload 加 `mode` 字段
- 玩家进 free mode 大厅时显示"L10 数值匹配"

### 5.3 Godot client sprite(美术协作,长期)

- 4 个新单位 sprites 在 `godot-client/assets/tiles/`
- Per-class 小头像(swordsman/lancer/warrior/berserker/...)在 `godot-client/assets/units/`

### 5.4 ChapterDifficulty schema(可选)

Phase 2 §6.5 Free mode 用的 boss-autolevel 公式已稳。下一步 §3 chapter multiplier:

```jsonc
{
  "attack_modifier": 20,   // 敌方 attack +20%(整章节)
  "defense_modifier": 10,
  "income_modifier": 80,    // 玩家收入 × 0.8
  "move_range_modifier": 0,
  "vision_modifier": 1,
  "level_offset": 2,         // 章节 autolevel 基础 +2
  "max_recruit_count": 5,
  "recruit_cost_multiplier": 150,
  "starting_fund": 800
}
```

→ 可以加到 `mainline/schemas.py:ChapterConfig`,纯 Optional 字段,向后兼容。

### 5.5 Bug 3(敌方反击超距离)waiting log sample

```
routes/actions.py:attack and game_logic.py:_ai_attack
都加了 logger.info('attack: COUNTER-CHECK ...')
玩家下次玩到反击超距离时,把这两行贴给我:
  从 %USERPROFILE%\AppData\Roaming\Godot\app_userdata\BattleBlitz\logs\game.log 拉
不需要的话可以无限挂着。
```

---

## 6. 风险 + 缓解

| 风险 | 缓解 |
|---|---|
| Hero 设计稿延迟 → spawn_hero 抛 NotImplementedError | 已在 modes.py 显式 raise,后续可以直接补 |
| 数值玩家体感偏差(变低 / 变高) | 现在可以免费 mode 实测 4 个新类;调 class.base 就行 |
| Chapter modifier schema 未接 → chapter 难度无法调 | §6 是 Optional 字段,加上去向后兼容 |
| 旧 11 个单位 class 数值没动 → Phase 2 dual-track 没生效 | 玩家在新章节才会触发;chapter multiplier 加完后一起调 |
| Godot 端 mode 不接 → 现在客户端无法用 free mode | 后端 ready,但客户端没调用方 — 等前端 PR |

---

## 7. Phase 2 整体进度

| Step | 内容 | 状态 |
|---|---|---|
| 1A | 4 个新 Generic 单位类 | ✅ `6c42913` |
| 1B | ModeConfig + spawn_generic + apply_spawn | ✅ `9e77e4f` |
| 2 | 接入 _start_battle_internal,4 类可上棋盘 | ✅ `2da2ef2` |
| 3 | Free mode L10 baseline + mode 字段透传 | ✅ `94d6c5f` |
| 4 | Hero 10 名 roster + spawn_hero_stats | ⏸ 等用户设计稿 |
| 5 | UI 区分(Lv/Generic/Hero 标识)| ⏸ Phase 2 §5.4 |
| 6 | Player/Enemy 差异化 + ChapterDifficulty | ⏸ Phase 2 §6 |

**已完成:4 / 6**
**阻塞中:1 / 6(Hero)**
**设计上铺平:1 / 6(等 Player/Enemy 差异化设计)**

---

## 8. 学长下次回来时怎么继续

```
1. (有 Hero 设计稿) → 给我,我开 Step 4
2. (要 Free mode 自己玩) → 用 TestClient 跑:
   POST /games { mode: "free", ... }
   POST /games/{id}/join { ... }
   POST /games/{id}/start
   GET /games/{id}/state  → 验证 Generic L10 数值
3. (有数值问题) → 把客户端报的具体 case 给我(单位 class、Lv、攻防前/后)
4. (要做 chapter multiplier / player 差异化) → 直接点 §5.4 / §6 我开
```

---

报告完。commits 都已落库到 `refactor/extract-mainline-modules` 分支,主分支 `master` 没动。
