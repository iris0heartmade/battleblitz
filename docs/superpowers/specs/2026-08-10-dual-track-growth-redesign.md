# 双轨成长重构设计

**Date:** 2026-08-10
**Status:** Approved direction, awaiting implementation plan
**Scope:** 英雄成长、佣兵强化、敌方章节等级、自由模式 Lv10 基准、旧成长入口收口、第一版数值重标定。

---

## 1. 目标

本设计把 BattleBlitz 的单位成长重新收束为 **Hero / Mercenary 双轨制**：

- **英雄 Hero**：少量具名角色，走 FE8 式长期养成。每个英雄有独立 `character_growth_rates`，不是“职业成长 + 小修正”。
- **佣兵 Mercenary**：战斗主力和敌方杂兵，走章节配置与点数强化。佣兵没有经验条，不在战斗中升级。
- **自由模式 Free Mode**：英雄与佣兵都使用标准 Lv10 基准，不读主线存档，不污染主线存档。

设计目标不是把现有系统全推翻，而是把 2026-07-13 双轨策划重新落回主线，并纠正 2026-08-09 “所有单位 rolled growth”把佣兵也卷入成长系统的偏航。

---

## 2. 总体原则

| 原则 | 设计约束 | 蠢猪也能懂的说明 |
|---|---|---|
| 英雄是人 | 英雄成长由 `character_growth_rates` 决定 | 云就是云，不是法师职业贴了一张成长贴纸 |
| 职业是壳 | 职业提供基础修正、上限、转职 bonus、移动类型、技能许可 | 职业决定穿什么甲、能摸到多高的天花板 |
| 佣兵是军备 | 己方佣兵由存档点数强化，敌方佣兵由章节等级/修正决定 | 普通兵不刷经验，靠军费和关卡设计变强 |
| 自由模式标准化 | 默认 Lv10 基准，完全独立于主线 | 联机/沙盒要公平，别把主线肝度带进去 |
| MOV 是地图尺度 | 移动力不进随机成长 | 移动力乱涨，地图就会被撕开 |
| 一个真源 | 成长、生成、结算必须各有唯一入口 | 不允许公式在角落里自己开分店 |

---

## 3. 三条运行轨道

```text
BattleBlitzGrowth
├─ HeroTrack
│  ├─ HeroCharacterTemplate: base_stats + character_growth_rates
│  ├─ HeroClassTemplate: base_modifiers + caps + promotion_bonus
│  ├─ HeroCampaignState: level + exp + current_base_stats
│  └─ HeroGrowthPolicy: 100 EXP + FE8-style per-stat roll
├─ MercenaryTrack
│  ├─ PlayerMercenaryPolicy: class base + saved commander allocation
│  ├─ EnemyMercenaryPolicy: chapter level + deterministic class autolevel
│  └─ NoRuntimeExpPolicy: combat never levels mercenaries
└─ FreeModeTrack
   ├─ FreeHeroPreset: standard Lv10
   └─ FreeMercenaryPreset: standard Lv10
```

---

## 4. Hero Track

### 4.1 数据模型

#### `HeroCharacterTemplate`

定义“这个英雄是谁”：

- `hero_id`
- `display_cn`
- `default_class_id`
- `base_stats: dict[str, int]`
- `character_growth_rates: dict[str, int]`
- `base_weapon_ranks: dict[str, int]`
- `personal_tags: list[str]`
- `active_skills / passive_skills`
- 头像、立绘、指挥官能力等内容绑定

`character_growth_rates` 是英雄成长真源。旧的 `personal_growth_modifier` 迁移为完整成长表，然后废弃。

#### `HeroClassTemplate`

定义“这个职业是什么”：

- `class_id`
- `tier`
- `base_modifiers`
- `caps`
- `promotion_options`
- `promotion_bonuses`
- `movement_profile`
- `weapon_permissions`
- `default_skills`

英雄升级时不读取职业成长率。职业只影响基础修正、上限和转职。

#### `HeroCampaignState`

存档中的英雄长期状态：

- `hero_id`
- `class_id`
- `level`
- `exp`
- `base_stats`
- `weapon_ranks`
- `learned_skills`
- `promoted`
- `equipment`
- `equipment_initialized`

`base_stats` 是长期裸属性。装备、CO、临时 buff 不能写入这里。

### 4.2 英雄升级

- 固定 `100 EXP = 1 level`。
- 每次升级按 `character_growth_rates` 逐项掷骰。
- 成长统计轴为现有后端属性：`hp / atk / def / matk / mdef`。
- `mov` 不参与随机成长。
- 允许成长率大于 100：每满 100 必定 +1，余数再掷一次。示例：`120% = 必定 +1 + 20% 再 +1`。
- 若一次升级全 0，可启用 FE8 式零成长补偿：按 `hp -> atk -> def -> matk -> mdef` 顺序尝试一次补偿掷骰，命中即停。

### 4.3 英雄经验来源

| 来源 | 默认值 | 说明 |
|---|---:|---|
| 命中/有效行动 | 5 | 可后续按治疗、支援拆分 |
| 击杀 | 30 | 比当前 `10` 更像英雄养成节奏 |
| Boss 击杀 | 50 | 可从章节配置覆盖 |
| 章节通关奖励 | `hero_exp` | 只给英雄，不再叫 `exp_per_unit` |

旧字段 `rewards_on_clear.exp_per_unit` 迁移为兼容别名：读取旧字段时写入英雄经验，不给佣兵。

### 4.4 转职

- 英雄达到 Lv20 且有转职道具时可转职。
- 转职后 `level = 1`，`exp = 0`。
- 保留累计 `base_stats`，加目标职业 `promotion_bonuses`，再按目标职业 `caps` 截断。
- 转职不回放历史成长，不重掷。

---

## 5. Mercenary Track

### 5.1 己方佣兵

己方佣兵不拥有经验条。战斗表现可以给士气、CO 能量、金钱或战役资源，但不能触发等级成长。

己方佣兵强度来自：

1. 职业基础数值。
2. `PlayerProfile.mercenary_roster_state["allocation"]` 中的点数分配。
3. 当前章节允许的临时规则。

现有 `CommanderAllocation` 与 `apply_allocation_to_unit()` 保留，并作为己方佣兵强化入口。

### 5.2 敌方佣兵

敌方佣兵强度来自章节设计：

- 地图/章节 JSON 中每个敌方单位显式 `level`。
- 章节可配置 `mercenary_balance.enemy_modifiers`。
- 敌方普通兵使用确定性职业 autolevel，从职业基础值推导到章节等级。
- Boss / 精英敌人允许个体覆盖：`is_boss`, `stat_overrides`, `growth_seed`, `boss_modifiers`。

敌人等级是关卡策划工具，不是战斗成长结果。

### 5.3 佣兵无经验条

运行时规则：

- `Unit.exp` 对佣兵视为 legacy 字段，UI 不展示。
- `award_exp(unit, ...)` 不应再作用于非英雄单位。
- 攻击/击杀仍可调用 `award_morale()` 或 CO meter 逻辑。
- 主线通关奖励不再写佣兵经验。

---

## 6. Free Mode Track

自由模式默认规则写死为：

- 英雄标准 Lv10。
- 佣兵标准 Lv10。
- 不读取 `HeroCampaignState`。
- 不读取主线 `mercenary_roster_state`，除非未来明确做“非平衡沙盒导入”。
- 不写回任何主线成长。
- Lv10 生成必须确定性，可由 `game_id + player seat + unit index + unit_type` 派生 seed。

自由模式的 Lv10 是“战斗基准等级”，不是可持久化养成等级。

---

## 7. 数值设计第一版

### 7.1 属性尺度

| 阶段 | HP | 主攻 | 主防 | 副攻/副防 | MOV |
|---|---:|---:|---:|---:|---:|
| T1 Lv1 普通佣兵 | 28-50 | 8-22 | 3-12 | 3-12 | 4-6 |
| T1 Lv10 标准基准 | 35-58 | 12-27 | 6-16 | 4-16 | 4-6 |
| T1 Lv20 英雄 | 45-70 | 18-35 | 10-24 | 8-30 | 5-6 |
| T2 Lv1 英雄 | 55-78 | 24-42 | 14-28 | 12-38 | 5-7 |
| Boss | 按章节手写 | 高于同章普通兵 | 有明确弱点 | 可偏科 | 谨慎 |

### 7.2 英雄成长建议

| Hero | Class | HP | ATK | DEF | MATK | MDEF | 定位 |
|---|---|---:|---:|---:|---:|---:|---|
| `yun` | warlock | 65 | 20 | 20 | 75 | 35 | 高输出法师，物攻只是剧情调味 |
| `yuanying` | warlock | 70 | 10 | 25 | 65 | 40 | 稳定型法师，生存略好 |
| `anna` | healer | 65 | 5 | 30 | 35 | 55 | 防守型治疗者 |
| `youko` | bard | 60 | 5 | 20 | 40 | 50 | 支援/歌者，魔防和功能性突出 |

### 7.3 职业佣兵基准

| Class | HP | ATK | DEF | MATK | MDEF | MOV | 定位 |
|---|---:|---:|---:|---:|---:|---:|---|
| swordsman | 42 | 17 | 11 | 3 | 5 | 5 | 标准近战 |
| archer | 34 | 20 | 6 | 3 | 4 | 4 | 远程高攻低防 |
| knight | 52 | 20 | 14 | 3 | 4 | 4 | 重甲，低机动 |
| lancer | 38 | 16 | 9 | 3 | 6 | 6 | 高机动枪兵 |
| warrior | 46 | 22 | 6 | 3 | 4 | 5 | 高 HP 高攻低防 |
| warlock | 36 | 6 | 7 | 22 | 12 | 5 | 魔法输出 |
| healer | 34 | 4 | 8 | 10 | 16 | 5 | 治疗/低输出 |
| bard | 32 | 4 | 7 | 12 | 18 | 6 | 支援/脆弱 |
| dragon_rider | 44 | 18 | 10 | 3 | 6 | 6 | 飞行压制 |
| falcon_knight | 36 | 15 | 8 | 4 | 12 | 7 | 飞行高速/低耐久 |

T2 职业先作为英雄转职、Boss、精英敌配置使用，不默认出现在普通佣兵池。

---

## 8. 旧入口收口

| 现有入口 | 新处理 |
|---|---|
| `game_logic.level_up_if_ready()` | 改为英雄专用或废弃；非英雄不升级 |
| `game_logic.award_exp()` | 对英雄分发到 HeroGrowthPolicy；对佣兵只处理士气/CO |
| `progression.leveling.XP_CURVE` | 不用于英雄；保留给旧 `UnitInstance` 或后续删除 |
| `RolledGrowthPolicy` | 拆成 `HeroGrowthPolicy` 与 `EnemyAutolevelPolicy` |
| `personal_growth_modifier` | 迁移为 `character_growth_rates` |
| `class_growth_rates.mov` | 清零或从成长轴移除 |
| `rewards_on_clear.exp_per_unit` | 迁移为 `hero_exp`，旧字段兼容读取 |
| Web/Godot “EXP/单位” 文案 | 改为“英雄经验” |

---

## 9. 数据流

### 9.1 主线开战

1. 读取章节 JSON。
2. 读取 `HeroCampaignState`。
3. 读取 `mercenary_roster_state.allocation`。
4. 生成英雄单位：存档裸属性 + 职业/装备临时修正。
5. 生成己方佣兵：职业基础 + 存档点数分配。
6. 生成敌方佣兵：职业基础 + 章节等级 autolevel + 敌方章节修正。
7. 写入 `Unit` 战斗行。

### 9.2 战斗中

1. 英雄获得经验、成长和士气。
2. 佣兵不获得经验，只获得士气/CO 相关收益。
3. 临时 buff、装备 bonus、状态异常不污染长期裸属性。

### 9.3 战斗结算

1. 回写英雄 `level / exp / base_stats / weapon_ranks / learned_skills / promoted / equipment`。
2. 回写佣兵 allocation 或资源变化。
3. 不回写佣兵战斗等级。
4. 不回写当前 HP、当前 MP、临时状态。

---

## 10. 测试策略

| 测试 | 验证 |
|---|---|
| `test_hero_character_growth_rates_are_independent_from_class` | 英雄成长不等于职业成长 + modifier |
| `test_hero_level_up_uses_100_exp_threshold` | 英雄 100 EXP 升级 |
| `test_hero_level_up_does_not_roll_mov` | MOV 不随机成长 |
| `test_player_mercenary_award_exp_is_noop` | 己方佣兵无经验条 |
| `test_enemy_mercenary_uses_chapter_level` | 敌方等级来自章节配置 |
| `test_free_mode_units_are_standard_lv10` | 自由模式英雄/佣兵都是 Lv10 |
| `test_free_mode_does_not_read_campaign_state` | 自由模式不污染主线 |
| `test_mainline_reward_exp_applies_only_to_heroes` | 通关经验只给英雄 |

---

## 11. 实施顺序

1. 新增/修正 Hero 模板字段：`character_growth_rates`。
2. 新增 `HeroGrowthPolicy`，接管英雄升级。
3. 收口 `award_exp()`：非英雄不升级。
4. 新增/修正 `EnemyMercenaryPolicy`：章节等级确定性生成。
5. 固化己方佣兵 allocation 应用路径。
6. 固化自由模式 Lv10 preset。
7. 重标定英雄和职业基础数值。
8. 改 UI/API 文案：`exp_per_unit` -> `hero_exp`。
9. 更新成长图工具，使英雄/佣兵分轨展示。

---

## 12. 非目标

本设计不包含：

- 新武器熟练度完整系统。
- 新职业树完整扩展。
- Godot 大 UI 重做。
- 新章节内容设计。
- 自动生成全部数值图并人工审美调参。
- 删除旧数据库列。

---

## 13. 验收标准

- 英雄拥有完整 `character_growth_rates`。
- 任意佣兵战斗击杀后 `exp` 不再增长，等级不因战斗变化。
- 主线敌方单位按章节 `level` 得到确定性属性。
- 主线己方佣兵只吃存档点数分配。
- 自由模式英雄和佣兵都是标准 Lv10，且不读写主线成长。
- `mov` 不作为随机成长项。
- 旧的“所有单位 rolled growth”路径不再影响佣兵。

