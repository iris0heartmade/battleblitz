# Fire Emblem 8u + FreeWars + Advance-Wars-v2 借鉴报告 v2

> **来源**：`ref/fireemblem8u/` 8 系统 + `ref/FreeWars/` 指挥官/升级/章节机制 + `ref/Advance-Wars-v2/` CO modifier 模式
> **GitHub**：https://github.com/FireEmblemUniverse/fireemblem8u · https://github.com/MtDesert/FreeWars · https://github.com/fxspec06/Advance-Wars-v2
> **目标**：提取 BattleBlitz 可借鉴的 2004 年商业级 SRPG + 2010s 高级战争复刻设计

---

## 🎯 v2 重要修订：BattleBlitz 单位模型定位

> **2026-07-13 用户设计澄清**：
> "我们的单位分布和火纹不太一样... 英雄单位（即火纹里的己方人物）+ 佣兵（杂兵）...
> 这个杂兵可招募，更贴合敌方单位逻辑，设计上接近高级战争，
> 其实不太需要升级设定，更需要的是随主线难度增加而来的敌方数值上升，
> 我方要设计兵种升级选择（有限点数分配给特定类型的单位）。
> 这是我所想的区别于火纹和高战两个游戏的独特点之一。"

### BattleBlitz 双轨制单位模型

| 单位类型 | 数量 | 升级方式 | 借鉴对象 | 备注 |
|---|---|---|---|---|
| **英雄单位 (Hero)** | 极少（剧情核心 3-8 个） | **FE8 式**：成长 + 100 EXP + 转职 | fireemblem8u | 限定名角色，火纹式培养 |
| **佣兵 (Mercenary)** | 主力（可招募扩展） | **AW 式**：技能点分配 / 不升级 | FreeWars Skill 系统 | **这是 BattleBlitz 的差异化定位** |

### 双轨制带来的设计约束

| 维度 | 火纹模式（FE8） | 高级战争模式（AW） | BattleBlitz 选择 |
|---|---|---|---|
| 升级触发 | 战斗获 EXP | 无（Veteran 击杀） | **Hero 走 FE8，Mercenary 不升级** |
| 转职 | L10/L20 + Item | 无 | **仅 Hero 可转职** |
| 兵种升级 | 无 | CO Power + HQ 出产 | **我方走有限点数分配** |
| 敌人变强 | autolevel + 角色属性 | 章节 multiplier | **章节 multiplier 路线** |
| 可招募 | 无（NPC 加入剧情） | 无中立单位 | **中立佣兵可招募** |

### 借鉴优先级重排

| 优先级 | 设计点 | 主要参考 |
|:---:|---|---|
| 🔥 P0 | 多胜利条件 + 追击阈值 4 + 1RN/2RN 区分 | FE8 |
| 🔥 P0 | **章节难度 multiplier 配置系统** | **FreeWars（新增）** |
| 🔥 P0 | **有限技能点分配系统（100 点上限）** | **FreeWars Skill（新增）** |
| ⭐ P1 | 脚本化 AI 人格 + 危险图 | FE8 |
| ⭐ P1 | CO modifier 模式（4 个乘子） | Advance-Wars-v2 |
| ⭐ P1 | 警戒范围多源叠加 | FE8 |
| 💎 P2 | 三层人物模型（**仅 Hero**） | FE8 |
| 💎 P2 | 2 层 tile 映射 | FE8 |
| 💎 P2 | 雾战三态状态机 | FE8 |
| 💎 P2 | 完整 ItemData + 武器三角 | FE8 |
| 💎 P2 | **Veteran 击杀升级机制（Mercenary 可选）** | **FreeWars Promotable（新增）** |
| 🎁 P3 | 事件字节码脚本 | FE8 |
| 🎁 P3 | Boss 多阶段 AI 切换 | FE8 |
| 🎁 P3 | Hero 转职系统 | FE8 |
| 🎁 P3 | **中立佣兵招募 + 数值生成** | **自研（无现成参考）** |

---

## 📊 8 个子系统速览（按双轨制定位重新评级）

| 系统 | FE8 核心抽象 | 对 BattleBlitz 双轨的价值 | 评级 |
|---|---|---|---|
| 🗺️ **地图** | 2 层 tile 映射 + 7 个并行 2D 缓冲 | 全部单位共用 | ⭐⭐⭐ |
| ⚔️ **战斗** | 8 公式 + 武器三角 + 1RN/2RN | 全部单位共用，公式直接照搬 | ⭐⭐⭐ |
| 🧑‍⚔️ **人物** | CharacterData/ClassData/Unit 三层模型 | **仅 Hero 用**，Mercenary 走 AW 式 | ⭐⭐ (降级) |
| 🤖 **AI** | 脚本虚拟机 + 22+19 人格 + 危险图 | **全部敌人共用**，无关升级 | ⭐⭐⭐ |
| 🛡️ **装备** | ItemData 22 位属性 + 武器三角 + 16 位紧凑编码 | Hero 装备、Mercenary 用轻量武器 | ⭐⭐ |
| 📜 **事件** | 字节码脚本 + 17 触发器 + 5 种胜利条件 | 全部单位共用 | ⭐⭐⭐ |
| 🌫️ **雾战** | 双层地图 + 三态状态机 | 全部单位共用 | ⭐⭐ |
| 🚶 **移动** | 4 邻居 BFS + 梯度下降回溯 + 警戒范围多源叠加 | 全部单位共用 | ⭐⭐ |

**重评级说明**：
- 🧑‍⚔️ 人物从 ⭐⭐⭐ 降到 ⭐⭐：FE8 的成长/转职/EXP 机制只覆盖 Hero 部分，Mercenary 大军不适用
- ⚔️ 战斗保持 ⭐⭐⭐：公式无关单位类型，照搬
- 🤖 AI 保持 ⭐⭐⭐：FE8 的脚本 VM 是战术引擎层抽象，与单位升级体系完全解耦
- 📜 事件保持 ⭐⭐⭐：5 种胜利条件、触发器系统全部通用

---

## 🎯 一句话总结

**BattleBlitz 的最优借鉴组合 = FE8 的战术引擎 + FreeWars 的指挥官/章节系统 + 自研的中立佣兵招募**。

- **FE8** 提供：地图/战斗/AI 脚本/事件/雾战/移动 的成熟 SRPG 内核
- **FreeWars** 提供：**有限点数分配给特定类型单位** 的直接模板
- **BattleBlitz 独特点**：可招募佣兵（FE8/AW 都没有现成实现，需要自研）

---

## 1️⃣ 地图系统（🗺️）

**FE8 核心数据结构**：
```c
// 7 个并行 2D 缓冲，全部 [gBmMapSize.x + 2][gBmMapSize.y + 4]
u8** gBmMapUnit;       // 单位 id
u8** gBmMapTerrain;    // 地形 id
u8** gBmMapMovement;   // 移动剩余 MP（不是距离！）
u8** gBmMapRange;      // 攻击/技能范围
u8** gBmMapFog;        // 雾战
u8** gBmMapHidden;     // 隐藏位
u8** gBmMapOther;      // 临时/危险图
```

**编码方式**：tilemap 的 16-bit tile 索引 `>> 2` → 查 `gTilesetTerrainLookup[256]` → 地形 ID。**视觉层与逻辑层解耦**。

**地图数组 ±2/±4 padding**：写入 `map[-1][x]` 不会爆栈，移动算法可省去所有越界判断。

**地形表**：每个职业 3 张表（晴/雨/雪），用 C99 designated initializer：
```c
CONST_DATA s8 TerrainTable_MovCost_CommonT2Normal[] = {
    [TERRAIN_PLAINS]   = 1,
    [TERRAIN_FOREST]   = 2,
    [TERRAIN_RIVER]    = 5,
    [TERRAIN_MOUNTAIN] = 4,
    [TERRAIN_WALL]     = -1,  // 不可通行
};
```

### BattleBlitz 借鉴要点（双轨制）

✅ **直接照搬**（全部单位共用）：
- `Dict<TerrainId, TerrainDef>` 替代 switch case
- 给 Grid 加 padding `[x+2][y+4]`
- 用 `sbyte` 存移动剩余值，约定 `>= 120` 为边界、`-1` 为不可达
- 7 个并行缓冲：unit/terrain/movement/range/fog/hidden/other 完全够用

⚠️ **不必照搬**：
- 不需要 `>> 2` + 查表（你 JSON 直接存 terrain id）
- ARM 汇编洪水填充（C# / Python 足够快）

**双轨特化**：地形表 × 单位类型分两张（Hero 类 / Mercenary 类）— Hero 受地形惩罚小，Mercenary 严格。

---

## 2️⃣ 战斗计算（⚔️）

**8 个核心公式**（`src/bmbattle.c`）：

```
attack   = item.might + wTriangleDmgBonus + unit.pow
defense  = (IA_MAGIC ? res : def) + terrainBonus
speed    = max(0, unit.spd - max(0, item.wt - con))
hitRate  = skl*2 + item.hit + lck/2 + wTriangleHitBonus
avoidRate= max(0, speed*2 + terrainAvoid + lck)
critRate = item.crit + skl/2  // 狙击手职业 +15
damage   = max(0, attack - defense)
critDmg  = damage * 3
```

**武器三角**（12 条规则数据表）：
```c
{ ITYPE_SWORD, ITYPE_LANCE, hit=-15, dmg=-1 },  // 剑攻枪：剑方 -15/-1
{ ITYPE_SWORD, ITYPE_AXE,   hit=+15, dmg=+1 },  // 斧克剑
... // 物理三角 + 魔法三角（理/光/暗）
```

**1RN vs 2RN RNG**：
```c
// 命中用 2RN（两次取平均 → 分布更集中，更"公平"）
s8 Roll2RN(int threshold) { return threshold > (NextRN_100() + NextRN_100()) / 2; }
// 暴击用 1RN（标准均匀 → 低概率很稀有，符合直觉）
s8 Roll1RN(int threshold) { return threshold > NextRN_100(); }
```

**追击**：`|spdA - spdB| >= 4` 且更快方未击杀 → 追击

**Brave 武器**：`hitCount = 1 << 1 = 2`，每次独立判定命中/暴击

### BattleBlitz 借鉴要点（双轨制）

✅ **直接照搬**（全部单位共用）：
- 追击阈值 4（**你当前没有追击机制**！）
- 1RN/2RN RNG 区分（**你当前 `Roll1RN` 单一方式**）
- 武器三角查表模式（数据驱动）

✅ **可简化后照搬**：
- Brave = `1 << braveLevel` 算出 hitCount
- 暴击 3 倍（FE8 标准）

⚠️ **不必照搬**：
- 暗杀即死（Silencer）— 太凶残
- 三角攻击（三连击）— 太复杂
- 武器特效 DEVIL/PETRIFY — 玩家不易理解

**双轨特化**：
- **Hero 攻击伤害**走完整 8 公式（武器熟练度加成、技能加成）
- **Mercenary 攻击伤害**走简化公式（无熟练度，但可叠加兵种等级系数 = FreeWars promotionBonus × 当前等级）

---

## 3️⃣ 人物/数值系统（🧑‍⚔️）— ⚠️ 仅适用 Hero

> **⚠️ 双轨制声明**：本章内容**只适用于 BattleBlitz 的 Hero 子集**（剧情核心 3-8 个）。
> **佣兵 (Mercenary) 不走此系统**，详见第 9 章「章节难度 multiplier」和第 10 章「技能点分配」。

**FE8 三层模型**：

```c
struct CharacterData {  // 人物（永久）
    u8  defaultClass;        // 出身职业
    s8  baseHP, basePow, baseSkl, baseSpd, baseDef, baseRes, baseLck, baseCon;
    u8  baseRanks[8];        // 8 种武器初始熟练
    u8  growthHP, growthPow, growthSkl, growthSpd, growthDef, growthRes, growthLck;
    u8  attributes;          // 人物标记
};

struct ClassData {        // 职业（永久）
    s8  baseHP, basePow, ..., baseMov;
    u8  maxHP, maxPow, ...; // 职业上限
    u8  growthHP, ...;       // 职业成长（普通敌人用）
    s8  promotionHp, promotionPow, ...; // 转职加成
    u32 attributes;         // CA_MOUNTED/CA_FLYER/CA_THIEF ...
    const s8 * pMovCostTable[3]; // 晴/雨/雪移动消耗表
};

struct Unit {             // 运行时实例
    u8  level, exp;
    s8  maxHP, curHP, pow, skl, spd, def, res, lck, conBonus, movBonus;
    u16 items[5];
    u8  ranks[8];
    u8  state;
    u8  ai1, ai2;
    // ...
};
```

**初始化**：`UnitLoadStatsFromChracter` = CharacterData.base + ClassData.base；玩家用 CharacterData 成长，敌人用 ClassData 成长 + autolevel 批量估算。

**升级**：每级**固定 100 EXP**（不是递增门槛）。升级时 7 项成长独立掷骰：
```c
result = 0;
while (growth > 100) { result++; growth -= 100; }   // 120% → 必 +1，剩 20%
if (Roll1RN(growth)) result++;                      // 再概率 +1
```
全 0 时**零成长补偿**：按 HP→Pow→Skl→Spd→Def→Res→Lck 顺序重掷，最多 2 轮，命中即停。**HP 优先补偿**（这是关键设计选择）。

**有效等级**（经验公式用）：
```c
effectiveLevel = displayLevel;
if (promoted) effectiveLevel += 20;
```
转职后 L1 在经验计算中按 L21 处理，所以转职后升级变慢。

**转职**：保留累计属性 + 目标职业 `promotionHp/Pow/...` + 新 cap。

**早转 vs 晚转的代价（Eirika 个人成长 70/40/60/60/30/30/60 实测）**：
```
未转职 L1 → L20：19 次成长
L20 转职 → 已转职 L1 → L20：再 19 次成长
总计 38 次成长 + 1 次转职 bonus

L10 早转：9 + 19 = 28 次成长
少 10 轮 ≈ HP -7 / 力 -4 / 技 -6 / 速 -6 / 守 -3 / 魔防 -3 / 幸运 -6
```

**Eirika 完整培养 L1→20+转职+L1→20 理论期望**：
```
HP   16 + 38×0.70 + 4 = 46.6
力    4 + 38×0.40 + 2 = 21.2
技    8 + 38×0.60 + 2 = 32.8（受上限 29 限制）
速    9 + 38×0.60 + 1 = 32.8（受上限 30 限制）
守    3 + 38×0.30 + 3 = 17.4
魔防  1 + 38×0.30 + 5 = 17.4
幸运  5 + 38×0.60     = 27.8
```

### BattleBlitz 借鉴要点（**仅 Hero**）

✅ **最小改造**（**仅 Hero 类**）：
```python
# Hero 子集（剧情核心）
class HeroUnit:
    base: CharacterData   # 人物固定值
    template: ClassData   # 职业模板
    level, exp, cur_hp
    # ... 运行时数据（FE8 三层模型直接搬）

class CharacterTemplate:
    name, default_class
    base_stats: {hp, pow, skl, spd, def, res, lck, con}
    growth_rates: {hp: 70, pow: 40, ...}  # 7 项 %
    attributes: flags

class ClassTemplate:
    name
    base_stats, max_stats, growth_rates  # 职业成长给普通敌人用
    promotion_bonus: {hp, pow, ...}
    pMovCostTable: [晴, 雨, 雪]  # 9x 地形
    mov, con

# Mercenary 子集（主力佣兵，**完全不走此系统**）
class MercenaryUnit:
    unit_type: str                    # 兵种 ID
    level: int = 1                    # 固定 L1
    base_stats: dict                  # 来自 UnitTypeData 配置表
    cur_hp: int
    recruited_at_chapter: int         # 招募章节（用于计算加入强度）
```

✅ **直接照搬**（Hero）：
- 100 EXP/级（替代递增门槛）
- 转职公式：累计 + bonus + cap
- 玩家用 CharacterData 成长、敌人用 ClassData autolevel（**但只有 Boss 敌人用**）

⚠️ **不必照搬**：
- 8 种武器熟练度（Hero 用 5 兵种）
- 物理/魔法共用 pow（你的设计独立 ATK/MATK，更清晰）

---

## 4️⃣ AI 系统（🤖）

**架构**：3 个 Proc 串行 + 4 阶段决策主循环 + 脚本虚拟机

```
CpPhase (初始化)
  ↓
CpOrder (按优先级排序待决策单位)
  ↓
CpDecide (每个单位 4 阶段决策)
  ├── DecideHealOrEscape   # 逃跑/治疗优先
  ├── DecideScriptA        # 执行 ai_a 脚本（攻击逻辑）
  ├── DecideScriptB        # 执行 ai_b 脚本（移动逻辑）
  └── DecideSpecialItems   # 钥匙/开锁/解毒
  ↓
CpPerform (动画执行)
```

**脚本虚拟机（28 条 op）**：
```c
AI_CMD_CONDITIONAL = 0x00  // 比较 + 跳转
AI_CMD_CALLFUNC    = 0x01  // 调用 C 函数
AI_CMD_CHANGE_AI   = 0x02  // **运行时切性格**！boss 多阶段用
AI_CMD_GOTO        = 0x03
AI_CMD_ACTION      = 0x05  // 概率攻击（unk_01 = 0~100）
AI_CMD_ACTION_IN_PLACE = 0x07
AI_CMD_MOVE_TOWARDS_CHAR = 0x0D
AI_CMD_MOVE_TO_SAFETY    = 0x11
AI_CMD_MOVE_TO_ENEMY     = 0x12
AI_CMD_RANDOM_MOVE       = 0x16
AI_CMD_ESCAPE            = 0x17
AI_CMD_PILLAGE           = 0x10
// ...
```

**22 种 AI-A 性格 + 19 种 AI-B 性格**（数据表查表）：
- `ActionInRange_80Perc` — 80% 攻击
- `PillageThenPursue` — 先抢村后追敌
- `MoveToChar_Eirika` — boss 必追主角
- `MoveToTerrain` — 守特定地形（王座）
- `Escape` — 跑去撤离点

**动态性格切换示例**：
```c
struct AiScr AiScr_AiB_PillageThenPursue[] = {
    AI_PILLAGE,                       // 抢村
    AI_SET_AI(AI_A_00, AI_B_00),      // 抢完切：100% 攻击 + 追敌
    AI_GOTO_START,
};
```

**战斗评分公式**（8 项加权 + 钳位）：
```c
score = + 伤害期望 (cap 40)
      + 敌 HP 低奖励 (cap 20)
      + 周围友军奖励 (cap 10)
      + 目标职业奖励 (cap 20)
      + 回合压力 (cap ?)
      - 自己受伤期望 (cap ?)
      - 危险图值
      - 自己 HP 低惩罚
if (score == 0) score = backup;
score *= 40;  // 放大
```

**危险图 `gBmMapOther[y][x]`**：每个格子累计"被多少敌人打到"，AI 决策时拒绝 `danger > threshold` 的格子。

### BattleBlitz 借鉴要点（双轨制）

> **AI 系统对双轨制完全透明** —— Hero 和 Mercenary 走同一套 AI，因为 AI 是行为决策，与单位升级体系解耦。

✅ **最高优先级借鉴**：**脚本虚拟机代替 if-else 山**

```python
# BattleBlitz 当前：C 里硬编码"5 档难度 + 多种人格"
def ai_decide(unit, state):
    if difficulty == "easy":
        return random_move(unit)
    elif difficulty == "hard":
        return best_combat(unit, state)
    # ... 几十个分支

# FE8 模式：数据驱动
AI_SCRIPT_BERSERKER = [
    AI_ACTION(100),                # 100% 攻击
    AI_GOTO_START,
]

AI_SCRIPT_COWARD_NECRO = [
    AI_HEAL_IF_LOW_HP,
    AI_GOTO_IF_HP_HIGH(LABEL_ATTACK),
    AI_ESCAPE,
    AI_GOTO_START,
    LABEL_ATTACK,
    AI_MOVE_TO_ENEMY,
    AI_GOTO_START,
]

AI_SCRIPT_BOSS_DEMON_KING = [
    AI_MOVE_TO_CHAR(PLAYER_LEADER),   # 必追主角
    AI_GOTO_IF_IN_RANGE(LABEL_FIGHT),
    AI_GOTO_START,
    LABEL_FIGHT,
    AI_CAST_ULTIMATE_IF_READY,
    AI_ACTION(100),
]

# 双轨特化：佣兵用更简单的脚本（勇猛型 + 守备型）
AI_SCRIPT_MERC_AGGRESSIVE = [AI_ACTION(80), AI_GOTO_START]
AI_SCRIPT_MERC_DEFENSIVE  = [AI_MOVE_TO_NEAREST_ENEMY, AI_GOTO_START]
```

✅ **直接照搬**：
- 8 项评分公式 + 钳位（防"HP=1 杂兵分爆表"）
- 危险图（预计算 + 决策时查询）
- `CHANGE_AI` 运行时切性格（**boss 多阶段必用**！）
- 单位优先级排序（杖兵 > 领主 > 远程 > 肉盾）

---

## 5️⃣ 装备系统（🛡️）

**ItemData 结构**（16+ 字段）：
```c
struct ItemData {
    u16 nameTextId, descTextId;
    u8  number, weaponType;          // ITYPE_SWORD=0 / LANCE / AXE / BOW / ...
    u32 attributes;                  // 22 个 IA_* 位
    u8  maxUses, might, hit, weight, crit;
    u8  encodedRange;                // 0x11=近1 / 0x22=远程2 / 0x3F=1~15
    u16 costPerUse;
    u8  weaponRank, iconId, useEffectId, weaponExp;
    const struct ItemStatBonuses* pStatBonuses;
    const u8* pEffectiveness;        // 有效目标职业列表
};
```

**22 个 IA_* 属性位**：
```
IA_WEAPON       1    是武器
IA_MAGIC        2    是魔法
IA_STAFF        4    是杖
IA_UNBREAKABLE  8    不可破坏
IA_BRAVE        32   勇者武器（×2 攻击）
IA_MAGICDAMAGE  64   按魔力计算伤害
IA_UNCOUNTERABLE 128 不可反击
IA_REVERTTRIANGLE 256 反转武器三角
IA_NEGATE_FLYING  飞行克制无效
IA_NEGATE_CRIT    必杀无效
IA_LOCK_1~7       职业/角色独占锁
...
```

**5 装备槽 + 100 仓库 + 商店货架**：
```c
struct Unit { u16 items[5]; }                  // 身上
extern u16 gConvoyItemArray[100];              // 仓库
extern u8  shopItems[];                        // 商店
```

**16 位紧凑编码**：
- 高 8 位 = 剩余使用次数（`0xFF` = 无耐久）
- 低 8 位 = 物品索引

**武器三角数据驱动查表**（同战斗系统）。

### BattleBlitz 借鉴要点（双轨制）

✅ **MVP（最小可玩武器系统）**（Hero 完整版）：
```python
@dataclass
class WeaponData:
    id: int
    name: str
    weapon_type: WeaponType   # SWORD/LANCE/AXE/BOW/...
    attributes: int            # 22 个 bitflags
    max_uses: int              # 耐久
    might: int                 # 攻击力
    hit: int                   # 命中
    weight: int                # 重量
    crit: int                  # 必杀
    min_range: int
    max_range: int
    cost_per_use: int
    required_rank: int         # E=1 ... S=251

class Hero:
    items: List[WeaponInstance]   # 5 槽
    ranks: List[int]              # 8 种武器熟练度

# Mercenary 走简化版（共用 WeaponData 但无熟练度）
class Mercenary:
    items: List[WeaponInstance]   # 1-2 槽（轻量）
    # 无熟练度字段
```

✅ **直接照搬**：
- 武器三角查表（同战斗）
- 耐久度 `useItem()` 7 行实现
- `IA_*` 位属性 + TypeScript 联合类型
- `CanUnitUseWeapon` 两段式判断：属性锁 → 熟练度

⚠️ **不必照搬**：
- 8 种武器熟练度（你只 5 兵种，Mercenary 完全不要）
- 100 仓库上限（按需调整）
- 修理菜单（用商店代替）

**双轨特化**：Hero 用完整装备系统，Mercenary 用"按兵种预绑定武器"模式（每种兵种自带 1-2 个默认武器槽，无熟练度）。

---

## 6️⃣ 事件系统（📜）

**字节码脚本格式**（每条指令 = 1 个 u16 + N 个 u16 参数）：
```
bits: [ cmd(8) | len(4) | sub(4) ]   ← 第 1 个 u16
       [ arg1 ] [ arg2 ] [ arg3 ] ...  ← 后续 N 个 u16 参数
```

**调度**：主循环 + 单槽位队列 + 状态机 + 寄存器槽位

```c
// 引擎主循环（src/event.c）
while (TRUE) {
    gEventSlots[0] = 0;                          // 0 槽每条指令重置
    evCode = (*proc->pEventCurrent) >> 8;
    evFunc = (evCode < 0x80) ? loTable[evCode] : hiTable[evCode - 0x80];
    switch (evFunc(proc)) {
    case ADVANCE_CONTINUE: cursor += len; break;
    case ADVANCE_YIELD:    cursor += len; return;
    case END:              proc_break(); return;
    }
}

// 队列（避免事件重入）
void CallEvent(events, execType) {
    if (engine_running) EnqueueEventCall(events, execType);
    else                EventEngine_Create(events, execType);
}
```

**17 种触发器类型**：
```
EVT_LIST_CMD_TURN   = 0x02  // 第 N 回合 [faction]
EVT_LIST_CMD_CHAR   = 0x03  // 与 PID X 对话
EVT_LIST_CMD_LOCA   = 0x05  // 走到 (x,y) 并 VISIT/SEIZE
EVT_LIST_CMD_VILL   = 0x06  // 村庄
EVT_LIST_CMD_CHES   = 0x07  // 宝箱
EVT_LIST_CMD_DOOR   = 0x08  // 门
EVT_LIST_CMD_AREA   = 0x0B  // 进入矩形区域
...
```

**5 种胜利条件**（`enum GOAL_TYPE_*`）：
```c
GOAL_TYPE_SEIZE       = 0,  // 占领指定格子
GOAL_TYPE_DEFEAT_ALL  = 1,  // 歼灭所有敌人
GOAL_TYPE_DEFENSE     = 2,  // 防守 N 回合
GOAL_TYPE_DEFEAT_BOSS = 3,  // 击败指定 BOSS
GOAL_TYPE_SPECIAL     = 4,  // 自定义（由 AFEV 设 EVFLAG_WIN）
```

**90+ 事件动作**：MOV/LOAD/KILL/CHANGE_WEATHER/CHANGE_FOG_VISION/DISPLAY_TEXT/...

**寄存器槽位**（14 个）：`gEventSlots[0..D]`，脚本作者用 SVAL/EVT_SLOT_X 读写。

### BattleBlitz 借鉴要点

✅ **最高优先级借鉴**：**多胜利条件**（你当前只有"占领所有城堡"）

```python
class ChapterConfig:
    id: ChapterId
    victory_conditions: List[VictoryCondition]  # OR 关系
    defeat_conditions: List[DefeatCondition]     # OR 关系

class VictoryCondition:
    type: Literal["seize", "defeat_all", "defeat_boss", "defense", "special"]
    x: int = None
    y: int = None
    boss_unit_id: UnitId = None
    turns_to_survive: int = None
    event_flag: EventFlag = None

def check_victory(chapter, state):
    return any(c.matches(state) for c in chapter.victory_conditions)
```

✅ **直接照搬**：
- 4 类触发器（`onTurnStart` / `onTileEnter` / `onAreaEnter` / `onDialog`）
- 开场 / 结束事件脚本
- "跳过"机制（玩家按 START 加速）

⚠️ **不必照搬**：
- 完整的 90+ 指令字节码（用 Python/JSON 配置更直观）
- 14 个寄存器槽位（简单场景用不到）

**双轨特化**：事件触发器对双轨制透明 — Hero 和 Mercenary 都受事件系统影响（招募事件、剧情触发等）。

---

## 7️⃣ 雾战系统（🌫️）

**双层地图 + 三态状态机**：
```c
u8** gBmMapFog;     // 0=被雾遮蔽 / 1=可见
u8** gBmMapHidden;  // 位标志：bit0=UNIT, bit1=TRAP

// 单位状态
US_HIDDEN   = (1<<0)   // 完全不可见（死了/未部署/剧情隐藏）
US_BIT8     = (1<<8)   // "曾经被看见过"
US_BIT9     = (1<<9)   // "当前正被雾遮蔽"
```

**视野公式**：
```c
int GetUnitFogViewRange(unit) {
    int result = chapterVisionRange;          // 章节基础
    if (CA_THIEF) result += 5;               // 盗贼加成
    return result + unit->torchDuration;     // 火把剩余回合
}
```

**算法本质**：把每个我方单位当"光源"，菱形光环覆盖目标格子 `gBmMapFog`。敌方查询自己脚下格子即可。**地形完全不影响遮挡**。

**小地图自动隐藏**：复用 `gBmMapUnit`（雾下不写入）→ 小地图天然不显示。

### BattleBlitz 借鉴要点

✅ **直接照搬**：
- 双层数据结构：`visibilityMap[y][x] ∈ {UNEXPLORED, EXPLORED, VISIBLE}` + `hiddenMap[y][x]`
- 单位三态：`UNSEEN` / `SPOTTED_BEFORE` / `CURRENTLY_VISIBLE`
- 小地图复用主地图的 unitMap

✅ **可走得更远**：
- **FE8 没做地形 LOS 遮挡**，但你有"森林/山/河阻挡远程视线"的物理规则 → 用 rot.js shadow casting
- `lightPassesCallback: (x,y) => !isOpaque(terrain[x][y])` 直接搞定

⚠️ **必须重新设计**：
- 视觉表现：FE8 是切换 tile 调色板；Web 用 `globalAlpha` 或半透明黑色叠层

**双轨特化**：Hero 和 Mercenary 视野范围可不同（Hero 通常更远 = 章节基础值；Mercenary 视野范围可能 +1 来自 FreeWars `visionModifier`）。

---

## 8️⃣ 移动系统（🚶）

**4 邻居 BFS 填充 + 梯度下降回溯**（不是 A*！）

```c
// 入口
void GenerateUnitMovementMap(unit) {
    SetWorkingMoveCosts(GetUnitMovementCost(unit));   // 选职业 + 天气的成本表
    GenerateMovementMap(unit.x, unit.y, UNIT_MOV(unit), unit.id);
}

// 核心 BFS（ARM 汇编实现，C 版本叫 MapFloodCore）
while (frontier not empty) {
    for each (x, y, cost) in frontier:
        for each dir in {右,左,下,上} (剔除入边):
            tileCost = costTbl[gBmMapTerrain[ny][nx]];
            if (tileCost < 0 || cost + tileCost > mp) continue;
            if (map[ny][nx] >= 0 && map[ny][nx] <= cost + tileCost) continue;
            map[ny][nx] = cost + tileCost;
            push nextFrontier(nx, ny, cost + tileCost);
}

// 关键设计：map[y][x] = 剩余 MP（不是距离！）
//   可走 = map[y][x] >= 0 && map[y][x] != MAP_MOVEMENT_EXTENDED(124)
//   还剩多少 MP = map[y][x]
//   距离原点 = mp - map[y][x]
```

**回溯找最优路径**（梯度下降 + 同代价随机）：
```c
i = 0; outX = x; outY = y;
while (map[outY][outX] != 0) {
    ncost = { L=map[y][x+1], R=map[y][x-1], D=map[y+1][x], U=map[y-1][x] };
    best = min(ncost);
    candidates = all dirs where ncost == best;
    dir = candidates[NextRN_N(len(candidates))];  // 同代价随机打破对称
    scriptOut[i++] = dir;
    // 沿 dir 反向移动 outX/outY
}
RevertMovementScript(scriptOut);  // 翻转 + HALT
```

**地形表 × 职业 × 天气**：
```c
// 每个职业持有 3 张表
const s8 * pMovCostTable[3];  // [0]=晴 [1]=雨 [2]=雪

// 选表
switch (chapterWeatherId) {
    case RAIN:     return pMovCostTable[1];
    case SNOW:     return pMovCostTable[2];
    default:       return pMovCostTable[0];
}
```

**警戒范围多源叠加**：
```c
void GenerateDangerZoneRange() {
    BmMapFill(gBmMapRange, 0);
    for each enemy unit:
        GenerateUnitMovementMapExt(enemy);    // 敌人能走到哪
        GenerateUnitCompleteAttackRange(enemy); // 在能走到的格子上叠攻击范围
        // gBmMapRange[y][x] 自动累加 = "被 N 个敌人覆盖"
}
```

**移动脚本指令流**（`<= 0x40` opcodes）：
```c
enum {
    MOVE_CMD_MOVE_LEFT, MOVE_CMD_MOVE_RIGHT, MOVE_CMD_MOVE_DOWN, MOVE_CMD_MOVE_UP,
    MOVE_CMD_HALT, MOVE_CMD_FACE_LEFT, ...
};
gWorkingMovementScript[] = [Dir, Dir, ..., HALT];
```

**`US_HAS_MOVED` 单 bit 状态机**：行动一次就置位，控制 UI 是否显示攻击范围。

### BattleBlitz 借鉴要点

✅ **直接照搬**：
- `map[y][x] = 剩余 MP` 替代 `map[y][x] = 距离`
- `MAP_MOVEMENT_MAX = 120` sentinel 模式
- 警戒范围多源叠加（每个敌方 `+=1` 叠加）
- 移动脚本指令流（`[Dir, Dir, ..., HALT]`）
- `MovedThisTurn` 单字段状态机
- 地形表 × 职业 × 天气

⚠️ **不必照搬**：
- A* → 4 邻居 BFS（FE8 选择 BFS 是因为 2004 ARM 内存约束）
- 梯度下降回溯：你不缺内存，A* 父链更清晰

✅ **可简化**：
- 8 邻居（斜向）只需 `MapFloodCoreStep` 加 case
- 不需要 ARM 汇编优化

**双轨特化**：移动规则对双轨制透明 — Hero 和 Mercenary 用同一套 BFS，但移动力 (MP) 来自不同数据源（Hero 来自等级 + 装备加成；Mercenary 来自章节 multiplier + 兵种基础值）。

---

## 9️⃣ 章节难度递增（🔥 NEW - 双轨制关键）— 来自 FreeWars

> **v2 新增章节**！这是 BattleBlitz 双轨制的核心：Mercenary 数值不靠成长，靠章节 multiplier 缩放。

### FreeWars 的设计（替代 FE8 的 autolevel）

**FreeWars 没有"线性递增公式"**——每个 PVE 章节地图自带 **6 个全局 multiplier 旋钮**（`res/data/templateWarField/PVE_*.lua`）：

```lua
advancedSettings = {
    attackModifier        = 0,     -- 全局攻击力加成（百分比）
    energyGainModifier    = 100,   -- 全局能量获取速度倍率
    incomeModifier        = 100,   -- 全局收入倍率
    isActiveSkillEnabled  = true,
    isFogOfWarByDefault   = false,
    isPassiveSkillEnabled = true,
    playerIndex           = 1,
    moveRangeModifier     = 0,     -- 全局部队移动力加成（整数）
    startingEnergy        = 0,
    startingFund          = 0,     -- 起始资金
    visionModifier        = 0,
    targetTurnsCount      = 15,    -- 速度 100 分目标天数
}
```

**Campaign 列表**（按顺序排列）：
```lua
Campaign = {
    "PVE_YiDongYuJinGong",  -- 教程（multiplier 全 0）
    "PVE_JianZhuWu",         -- 建筑
    "PVE_BaoChiWeiXiao",     -- 保持位小
    "PVE_DieLianHua",        -- 蝶恋花
    ...
    "PVE_YongChuangAnGeLuo", -- 第 15 章
}
```

**章节难度 = 策划手调 multiplier**，没有"递增公式"。**这跟 FE8 的"敌人 autolevel"完全相反**：
- FE8：每个敌人 unit 携带 `autolevel` 字段，根据角色属性 + 敌人等级批量估算
- FreeWars：每张地图单独配 multiplier，所有敌人共享一个全局系数

### BattleBlitz 借鉴要点（**双轨制核心**）

✅ **直接照搬 FreeWars 模式**（章节驱动，不是 unit 驱动）：

```python
# config/chapters/chapter_15.json
{
    "id": 15,
    "name": "永闯安格罗",
    "advancedSettings": {
        "attackModifier":      20,      # 敌人 +20% 攻击
        "defenseModifier":     10,      # 敌人 +10% 防御（FreeWars 没拆，BattleBlitz 拆出来）
        "incomeModifier":      80,      # 玩家收入 × 0.8（更难攒钱）
        "moveRangeModifier":   2,       # 敌人 +2 MP
        "visionModifier":      1,       # 敌人 +1 视野
        "startingFund":        500,     # 玩家起始资金减半
        "maxRecruitCount":     5,       # 本章最多招募 5 个佣兵（双轨制特化）
        "recruitCostMultiplier": 150,   # 招募成本 × 1.5
        "targetTurnsCount":    20,
    }
}

# 战斗时实际伤害计算
def compute_damage(attacker, defender, weapon, chapter_settings):
    base_damage = attack_formula(attacker, weapon) - defense_formula(defender)
    if attacker.faction == "enemy":
        base_damage *= (1 + chapter_settings.attackModifier / 100)
    return base_damage
```

✅ **关键优势**：
- **数据驱动**：策划不用懂代码，改 JSON 即可调难度
- **配置可热更新**：做关卡平衡测试时不用重启
- **支持任意非线性曲线**：第 5 章比第 4 章简单（剧情需要），改 multiplier 而非改公式
- **可与"剧情难度"解耦**：玩家可自由选章节难度，multiplier 在基础值上叠加难度系数

⚠️ **与 FE8 autolevel 的关键区别**：

| 维度 | FE8 autolevel | FreeWars multiplier | BattleBlitz 选择 |
|---|---|---|---|
| 难度在哪 | 每个敌人 unit 字段 | 每张地图字段 | **地图字段**（双轨制需要） |
| 平衡方式 | 调几十个 unit 数据 | 调 6 个全局旋钮 | **后者**（成本低 10×） |
| 章节 vs 个体 | 个体差异化 | 全章节统一 | **章节 multiplier + Boss 个体差异化** |
| 数值复制 | 不易复制（每个 unit 不同） | 易复制（多张地图共用 multiplier 模板） | **多模板**（普通章 / Boss 章 / 精英章） |

---

## 🔟 有限技能点分配系统（⭐ NEW - 双轨制核心）— 来自 FreeWars

> **v2 新增章节**！这是 BattleBlitz 用户设计的**直接模板**：有限点数分配给特定类型的单位。

### FreeWars 的设计（去掉 CO 后的解构）

**FreeWars 显式移除了 CO 概念**，改为「技能槽 + 100 点上限 + 自由组合」（`src/app/models/common/ModelPlayer.lua:9-16`）：

```lua
-- 玩家、co与技能
-- 原版中有co的概念，而本作将取消co的概念，以技能的概念作为代替。
-- 技能的概念源于AWDS中的co技能槽。原作中每个co有4个技能槽，允许玩家自由搭配技能。
-- 本作中没有co，但同样存在技能的概念...每个可用技能都将消耗特定的技能点数，
-- 玩家可以任意组合技能，但技能总点数不能超过100点。
```

**Skill 系统架构**：
- 4 个槽位：`m_ModelSkillGroupPassive` / `Researching` / `Active` / `Reserve`
- 每个技能：`pointsActive` / `pointsPassive`（能量消耗）+ `modifierActive` / `modifierPassive`（效果数值）
- 16 个技能 ID：`res/data/SkillData.lua:1-273`
- 能量获取：攻击造成伤害时累加（`ActionExecutorForWarNative.lua:206-248`）

### Advance-Wars-v2 的 CO Modifier（补充）

**Advance-Wars-v2 用更轻量的"4 modifier"模式**（`players/Base.java:14-27`）：
- `CostBonus`（建造成本乘子，Colin=0.8 便宜）
- `ArmorBonus`（防御乘子）
- `WeaponBonus`（武器伤害乘子，Max=1.2 暴力）
- `CaptureBonus`（占领速度乘子，Sammi=1.5 抢地快）

**关键借鉴点**：把"经济曲线"和"CO 个性"解耦 — `Battle.Buyunit()` 扣 `unit.cost * player.CostBonus`。

### BattleBlitz 借鉴要点（**用户设计的直接模板**）

✅ **核心模式：100 点上限 + 技能点分配**

```python
# config/commander_points.json — 玩家可分配的"兵种升级"点数
{
    "player_total_points": 100,
    "upgrade_costs": {
        "infantry_atk_+1":   10,
        "infantry_def_+1":   12,
        "infantry_mov_+1":   25,
        "infantry_hp_+10":   15,
        "vehicle_atk_+1":    15,
        "vehicle_def_+1":    18,
        "vehicle_mov_+1":    30,
        "ranged_atk_+1":     20,
        "ranged_range_+1":   35,
        "air_atk_+1":        25,
        "air_mov_+1":        20,
        # ... 每兵种每属性一个升级
    },
    "applied_modifiers": {}   # 玩家选择后写入
}

# 招募佣兵时的应用
def apply_commander_points(merc_unit, player_points_config):
    unit_type = merc_unit.unit_type
    for stat, bonus in player_points_config["applied_modifiers"].items():
        if stat.startswith(unit_type):
            stat_name = stat.split("_", 1)[1]  # "atk" / "def" / ...
            merc_unit.stats[stat_name] += bonus
    return merc_unit
```

✅ **直接照搬的 4 个 modifier 模式**（Advance-Wars-v2 风格，更轻量）：

```python
# 比 FreeWars 100 点更直接：4 个乘子全局生效
class CommanderTraits:
    cost_modifier: float = 1.0      # 类似 AW Colin
    attack_modifier: float = 1.0    # 类似 AW Max
    defense_modifier: float = 1.0   # 类似 AW Olaf
    income_modifier: float = 1.0    # 类似 AW Grit
    
    def apply_to_unit(self, unit):
        unit.attack = int(unit.attack * self.attack_modifier)
        unit.defense = int(unit.defense * self.defense_modifier)
        unit.cost = int(unit.cost * self.cost_modifier)
```

✅ **完整 FreeWars 100 点模式 + AW 4 modifier 混合方案**：

```python
@dataclass
class ChapterCommanderConfig:
    """每章可重新分配 100 技能点"""
    total_points: int = 100
    spent_points: int = 0
    
    # 4 个全局 modifier（AWD 风格）
    global_modifiers: Dict[str, float] = field(default_factory=lambda: {
        "cost": 1.0,
        "attack": 1.0,
        "defense": 1.0,
        "income": 1.0,
    })
    
    # 100 点分配的兵种升级（FreeWars 风格）
    unit_type_upgrades: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # 例：{"infantry": {"atk": 2, "def": 1}, "vehicle": {"atk": 1}}
    
    def add_upgrade(self, unit_type: str, stat: str, value: int, cost: int):
        if self.spent_points + cost > self.total_points:
            raise ValueError(f"点数不足：需要 {cost}，剩余 {self.total_points - self.spent_points}")
        self.unit_type_upgrades.setdefault(unit_type, {})[stat] = \
            self.unit_type_upgrades.get(unit_type, {}).get(stat, 0) + value
        self.spent_points += cost
    
    def apply_to_mercenary(self, merc: MercenaryUnit):
        unit_type = merc.unit_type
        if unit_type in self.unit_type_upgrades:
            for stat, bonus in self.unit_type_upgrades[unit_type].items():
                merc.stats[stat] += bonus
        # 全局 modifier
        merc.attack = int(merc.attack * self.global_modifiers["attack"])
        merc.defense = int(merc.defense * self.global_modifiers["defense"])
        return merc
```

**UI 设想**：每章开始前显示一个"指挥官面板"：
- 顶部：剩余点数 100 / 100
- 中部：每兵种 × 每属性 × 当前等级 + 升级按钮（显示消耗）
- 底部：4 个全局 modifier 滑块（cost / attack / defense / income）

⚠️ **不必照搬**：
- FreeWars 的"被动/主动技能槽"分类（BattleBlitz 简化版只做"兵种升级"）
- Advance-Wars-v2 的 powers（System.out.println 占位）— 太早期
- 多个 CO 角色（BattleBlitz 用单指挥官，避免复杂度过高）

**双轨特化**：
- Hero 不走技能点系统（走 FE8 式升级）
- Mercenary 走技能点系统（每章可重新分配）
- 全局 modifier 同时影响 Hero 和 Mercenary（公平起见）

---

## 1️⃣1️⃣ Veteran 击杀升级机制（💎 NEW - Mercenary 可选）— 来自 FreeWars

> **v2 新增章节**！如果你想让 Mercenary 有"成长感"又不想走 FE8 路线，这是 FreeWars 的最佳模板。

### FreeWars 的设计

**Promotable 组件按需挂载**（`src/app/components/Promotable.lua:1-93`）：
```lua
-- Promotable是ModelUnit可用的组件。只有绑定了本组件，宿主才具有"等级"的属性、以及可升级。
-- unit默认等级为0，每摧毁一个敌方unit则升一级，最高3级
-- 不能进行攻击的单位无法升级，因此无需绑定本组件
```

**升级数值表**（`res/data/GameConstant.lua:815-820`）：
```lua
maxPromotion = 3
promotionBonus = {
    {atk=5,  def=0},   -- L1 → L2：+5 攻
    {atk=10, def=0},   -- L2 → L3：+10 攻
    {atk=20, def=20},  -- L3 → L4：+20 攻 +20 防
}
```

**触发时机**：
- 攻击命中造成击杀 → 攻击者 +1 等级（`ActionExecutorForWarNative.lua:420`）
- 反击杀敌 → 也 +1（`ActionExecutorForWarNative.lua:399`）
- 合流时取 `max(focus, target)` 等级（`ActionExecutorForWarNative.lua:782-787`）

### BattleBlitz 借鉴要点

✅ **如果想要 Mercenary 成长感**（用户未明确要求，但作为可选项）：

```python
# 是否启用 Veteran 升级（用户可在战役配置中开关）
@dataclass
class MercenaryConfig:
    enable_veteran_promotion: bool = True
    max_promotion_level: int = 3
    promotion_bonus: List[Dict[str, int]] = field(default_factory=lambda: [
        {"atk": 5,  "def": 0},
        {"atk": 10, "def": 0},
        {"atk": 20, "def": 20},
    ])

class MercenaryUnit:
    promotion_level: int = 0  # 0-3
    
    def on_kill(self, killed_unit):
        if self.promotion_level < self.config.max_promotion_level:
            self.promotion_level += 1
            bonus = self.config.promotion_bonus[self.promotion_level - 1]
            for stat, value in bonus.items():
                self.stats[stat] += value
```

✅ **可走的两条路**：

| 路线 | 描述 | 适合 |
|---|---|---|
| **A. 纯配置驱动** | 不做 Veteran，敌人数值完全靠章节 multiplier | **用户当前设计（推荐）** |
| **B. Veteran + 配置驱动混合** | 章节 multiplier 是基础，Veteran 是额外奖励 | **如果玩家抱怨"佣兵没成长感"** |

⚠️ **不必照搬**：
- FreeWars 合流 (Join) 机制 — 太复杂，BattleBlitz 可不做
- 组件式按需挂载 — BattleBlitz 用 dataclass 更直接

---

## 1️⃣2️⃣ 中立佣兵招募（🎁 自研 - BattleBlitz 独特点）— **无现成参考**

> **v2 新增章节**！**FE8 没有、AWD 没有、FreeWars 也没有**——这是 BattleBlitz 的独特设计。

### 设计挑战

FE8 的"加入玩家阵营"是通过剧情触发（指定 NPC 在某章加入），没有"中立可招募"机制。
FreeWars 的"Join"是合流（同种友军合并），不是招募。
AW 原版有中立建筑占领，但不会产出可加入的单位。

**BattleBlitz 需要自研**：
1. 中立佣兵出现在地图特定位置（中立城镇、营寨、野外？）
2. 玩家单位接触 + 付费（或任务条件）→ 加入
3. 加入时根据章节 multiplier 生成数值
4. 加入后归玩家控制，但保留"佣兵"身份（无 Hero 转职）

### 推荐架构

```python
# data/mercenaries/recruit_pools.json — 每章可招募的佣兵池
{
    "chapter_5": {
        "neutral_mercenaries": [
            {
                "id": "mercenary_infantry_veteran",
                "unit_type": "infantry",
                "level": 1,
                "base_stats": {"hp": 20, "atk": 8, "def": 6, "mov": 4},
                "recruit_cost": 500,
                "recruit_condition": "talk_to_tile",  # 或 "defeat_in_battle"
                "appears_at": {"x": 10, "y": 15},
                "respawn_after_chapter": False
            }
        ]
    }
}

# data/mercenaries/recruited_mercenaries.json — 已招募的佣兵（跨章节保留）
{
    "mercenary_infantry_veteran": {
        "original_chapter": 5,
        "current_level": 2,  # Veteran 升级（如果启用）
        "kills": 5,
        "veteran_bonus_applied": {"atk": 5}  # L1 → L2 奖励
    }
}
```

### 数值生成策略

```python
def generate_mercenary_stats(unit_type: str, chapter: int, recruit_chapter: int):
    """招募佣兵时的数值生成"""
    base = UnitTypeData[unit_type].base_stats
    chapter_settings = load_chapter_config(chapter).advancedSettings
    
    # 章节 multiplier 应用
    stats = {}
    for stat, value in base.items():
        if stat == "atk":
            stats[stat] = int(value * (1 + chapter_settings["attackModifier"] / 100))
        elif stat == "def":
            stats[stat] = int(value * (1 + chapter_settings["defenseModifier"] / 100))
        else:
            stats[stat] = value
    
    # 招募章节 vs 当前章节的"时间衰减"
    chapters_passed = chapter - recruit_chapter
    decay_factor = max(0.5, 1 - chapters_passed * 0.1)  # 每章衰减 10%，最低 50%
    for stat in stats:
        stats[stat] = int(stats[stat] * decay_factor)
    
    return stats
```

✅ **推荐做法**：
- 中立佣兵用独特视觉（区别 Hero：没名字、显示 "佣兵"）
- 招募成本 = 基础成本 × `recruitCostMultiplier` × 佣兵等级
- 招募条件：付费无条件 / 完成支线任务 / 击败后说服（多选项）
- 跨章节保留：写 `recruited_mercenaries.json`，下章可继续用

⚠️ **设计风险**：
- 招募太便宜 → 玩家无脑招，佣兵海淹死 Boss
- 招募太贵 → 玩家不招，浪费设计
- 数值衰减太狠 → 老佣兵完全没用，玩家只招新佣兵

---

## 🚀 BattleBlitz 落地路线图（按 ROI 排序 — 双轨制版）

### 🔥 P0（必须做，1 周内）
1. **多胜利条件**（事件系统）
   - 5 种类型枚举
   - `check_victory(state) → bool`
   - **理由**：当前单一"占领城堡"是最大设计瓶颈

2. **追击阈值 4**（战斗系统）
   - `|spdA - spdB| >= 4` 触发
   - **理由**：让速度属性有意义

3. **1RN/2RN RNG 区分**（战斗系统）
   - 命中用 2RN，暴击用 1RN
   - **理由**：修复"低命中/低暴击"体验

4. **🆕 章节难度 multiplier 配置系统**（FreeWars 借鉴）
   - 6 个全局旋钮 + `targetTurnsCount`
   - 每章 JSON 配置
   - **理由**：双轨制核心 — 让敌人难度按章节提升，不靠成长

5. **🆕 技能点分配系统**（FreeWars 借鉴 / 用户设计核心）
   - 100 点上限 + 兵种升级选择
   - 每章开始前 UI 配置
   - **理由**：BattleBlitz 区别于 FE8 和 AW 的独特点

### ⭐ P1（强烈推荐，2 周内）
6. **脚本化 AI 人格**（AI 系统）
   - 用数据代替 C 里 if-else 山
   - `AI_SET_AI` 运行时切性格（boss 多阶段）

7. **危险图**（AI 系统）
   - 每回合预计算 `dangerMap[y][x]`
   - AI 决策拒绝 `danger > threshold`

8. **🆕 CO Modifier 模式**（Advance-Wars-v2 借鉴）
   - 4 个全局 modifier：cost/attack/defense/income
   - 用更轻量的方式做"指挥官个性"
   - **理由**：补充技能点系统之外的"全局调优"

9. **3 武器熟练度**（装备系统，**仅 Hero**）
   - 给 5 兵种加熟练度等级（E → S）
   - **理由**：玩家有"成长"感（Hero 限定）

10. **警戒范围多源叠加**（移动系统）
    - 每个敌方 `+=1` 叠加到 dangerMap
    - **理由**：提升玩家战术感

### 💎 P2（值得做，1 月内）
11. **三层人物模型**（人物系统，**仅 Hero**）
    - `CharacterData` / `ClassData` / `Unit` 分层
    - 100 EXP/级
    - 转职系统

12. **2 层 tile 映射**（地图系统）
    - JSON 地图 → tile_id → terrain_id 查表
    - 给 Grid 加 padding

13. **雾战系统**（雾战）
    - 三态状态机
    - shadow casting（rot.js `lightPassesCallback`）

14. **完整 ItemData 系统**（装备）
    - 22 个 IA_* 位属性
    - 5 装备槽 + 仓库

15. **🆕 Veteran 击杀升级**（Mercenary 可选，FreeWars 借鉴）
    - `Promotable` 组件式按需挂载
    - 3 档升级曲线（+5/+10/+20 atk）
    - **理由**：如果玩家反馈"佣兵没成长感"

### 🎁 P3（高级特性，未来）
16. **事件字节码脚本**（事件系统）
    - 90+ 指令
    - 17 触发器
    - 用 Python DSL 而非真字节码

17. **Boss 多阶段 AI 切换**
    - HP < 50% → `AI_SET_AI(BERSERK_FINAL_FORM)`

18. **🆕 中立佣兵招募系统**（自研）
    - `recruit_pools.json` 配置
    - 招募时数值生成 + 章节衰减
    - **理由**：BattleBlitz 独特点，但工作量大

19. **🆕 Hero 转职系统**（FE8 借鉴，**仅 Hero**）
    - 转职道具 + 转职目标职业
    - 转职 bonus + 等级重置
    - **理由**：给 Hero 长期培养目标

---

## 💎 四个最容易移植的"开箱即用"模式

### 模式 1：双层真相源地图（FE8）
```python
# 主地图和小地图都查同一个 visibilityMap
def render_main_map(state):
    for (x, y) in state.tiles:
        if state.visibility[y][x] == VISIBLE:
            draw_full(state.units[y][x])  # 完全可见
        elif state.explored[y][x]:
            draw_dark(state.terrain[y][x])  # 探索过的暗色地形
        else:
            draw_black()  # 完全黑

def render_minimap(state):
    for (x, y) in state.tiles:
        if state.visibility[y][x] and state.units[y][x]:
            draw_unit_dot(state.units[y][x])  # 只画"当前可见 + 有单位"
```

### 模式 2：8 项加权评分（FE8）
```python
def compute_combat_score(actor, target, move_to, weapon):
    score = 0
    score += min(40, expected_damage(actor, target, weapon) * hit_rate / 100)
    score += min(20, 20 - target.cur_hp / target.max_hp * 20)
    score += min(10, friend_zone_bonus(move_to) * coef)
    score += min(20, class_rank_bonus(actor, target))
    score -= min(?, expected_damage_taken(actor, target, move_to) * coef)
    score -= state.danger_map[move_to.y][move_to.x] // 8
    score -= min(?, 20 - actor.cur_hp / actor.max_hp * 20)
    return max(0, score)
```

### 模式 3：5 种胜利条件 OR 组合（FE8）
```python
@dataclass
class ChapterConfig:
    victory: List[VictoryCondition]
    defeat: List[DefeatCondition]

def check_victory(chapter, state) -> bool:
    return any(c.matches(state) for c in chapter.victory)

def check_defeat(chapter, state) -> bool:
    return any(c.matches(state) for c in chapter.defeat)
```

### 模式 4：🆕 100 技能点 + 章节 multiplier 双层配置（FreeWars）
```python
@dataclass
class ChapterConfig:
    # 第一层：章节 multiplier（敌人难度）
    advanced_settings: Dict[str, float] = field(default_factory=lambda: {
        "attackModifier": 0,
        "defenseModifier": 0,
        "incomeModifier": 100,
        "moveRangeModifier": 0,
        "visionModifier": 0,
        "startingFund": 1000,
        "maxRecruitCount": 5,
    })

    # 第二层：我方技能点（玩家策略）
    commander_points: CommanderPoints = field(default_factory=lambda: CommanderPoints())

@dataclass
class CommanderPoints:
    total: int = 100
    spent: int = 0
    unit_upgrades: Dict[str, Dict[str, int]] = field(default_factory=dict)
    global_modifiers: Dict[str, float] = field(default_factory=dict)

def apply_chapter_to_unit(unit, chapter_config: ChapterConfig, is_enemy: bool):
    """应用章节 multiplier 到单位"""
    settings = chapter_config.advanced_settings
    if is_enemy:
        unit.attack = int(unit.attack * (1 + settings["attackModifier"] / 100))
        unit.defense = int(unit.defense * (1 + settings["defenseModifier"] / 100))
        unit.mov += settings["moveRangeModifier"]
        unit.vision += settings["visionModifier"]
    else:
        # 我方应用技能点升级
        cp = chapter_config.commander_points
        for stat, bonus in cp.unit_upgrades.get(unit.unit_type, {}).items():
            unit.stats[stat] += bonus
```

---

## 📚 关键文件索引（绝对路径）

### fireemblem8u（8 系统）

| 系统 | 核心文件 |
|---|---|
| 地图 | `ref/fireemblem8u/src/bmmap.c` (705 行) · `include/bmmap.h` · `include/chapterdata.h` · `src/data_terrains.c` (7416 行) |
| 战斗 | `ref/fireemblem8u/src/bmbattle.c` (2461 行) · `include/bmbattle.h` · `src/rng.c` (1RN/2RN) |
| 人物 | `ref/fireemblem8u/include/bmunit.h` · `src/bmunit.c` · `src/data_characters.c` · `src/data_classes.c` · `src/bmbattle.c:1227` (成长) |
| AI | `ref/fireemblem8u/src/cp_decide.c` · `src/cp_script.c` (861 行 VM) · `src/cp_data.c` (1604 行性格表) · `src/cp_battle.c` (评分) |
| 装备 | `ref/fireemblem8u/include/bmitem.h` · `src/data_items.c` · `src/bmitem.c` · `src/bmbattle.c` (三角) |
| 事件 | `ref/fireemblem8u/include/event.h` · `include/eventscript.h` · `src/event.c` · `src/eventinfo.c` |
| 雾战 | `ref/fireemblem8u/src/bmmap.c` · `src/bmidoten.c` · `include/constants/event-flags.h` · `data/chapter_settings.json` |
| 移动 | `ref/fireemblem8u/src/bmidoten.c` (848 行) · `asm/arm.s:552-841` (ARM 汇编核心) · `src/bmpatharrowdisp.c` |

### FreeWars（指挥官/章节/升级）

| 机制 | 核心文件 |
|---|---|
| Skill 系统 | `ref/FreeWars/src/app/models/common/ModelPlayer.lua:9-16` · `ModelSkillConfiguration.lua:1-89` |
| Skill 数据 | `ref/FreeWars/res/data/SkillData.lua:1-273` |
| 能量获取 | `ref/FreeWars/src/app/utilities/actionExecutors/ActionExecutorForWarNative.lua:206-248` |
| Veteran 升级 | `ref/FreeWars/src/app/components/Promotable.lua:1-93` · `res/data/GameConstant.lua:815-820` |
| 升级触发 | `ref/FreeWars/src/app/utilities/actionExecutors/ActionExecutorForWarNative.lua:399,420,782-787` |
| 章节 multiplier | `ref/FreeWars/res/data/templateWarField/PVE_*.lua:9-23` · `WarFieldFilenameLists.lua:1-19` |
| 合流 (Join) | `ref/FreeWars/src/app/components/Joinable.lua:1-55` |

### Advance-Wars-v2（CO Modifier）

| 机制 | 核心文件 |
|---|---|
| CO Modifier | `ref/Advance-Wars-v2/src/players/Base.java:14-27`（CostBonus/ArmorBonus/WeaponBonus/CaptureBonus） |
| CO Power 触发 | `ref/Advance-Wars-v2/src/players/Base.java:64-77`（System.out.println 占位） |
| 经济循环 | `ref/Advance-Wars-v2/src/Battle.java:50-68`（每建筑 50/回合） |

---

## 📝 一句话教训（v2 更新版）

> **FE8 + FreeWars + AW 联合教会 BattleBlitz 最重要的事：把"行为"做成"数据"，把"难度"做成"配置"，把"单位"做成"双轨"**。
>
> - **数据驱动**：AI 性格、装备类型、事件触发、胜利条件 — JSON/Python 配置表，不是 C 里硬编码的 if-else 山
> - **难度配置化**：敌人变强靠章节 multiplier，不靠 unit 成长 — 策划可调、玩家可感知
> - **双轨制**：Hero 走 FE8 路线（深成长），Mercenary 走 AW 路线（配置驱动）— 这是 BattleBlitz 的独特设计
>
> 这才是 2004-2010s 商业级 SRPG/AW 沉淀 10-20 年的设计遗产 + 用户的差异化定位。

---

**报告生成时间**：2026-07-13（v2 重写）
**研究范围**：FE8 8 系统 + FreeWars 5 机制 + Advance-Wars-v2 1 模式 · 32 个核心源文件
**借鉴价值**：P0-P3 共 19 个落地项（v1 13 个 + v2 新增 6 个）· 4 个开箱即用模式（v1 3 个 + v2 新增 1 个）
**核心更新**：明确双轨制定位，新增 4 章专门讲 AW 路线 + 自研路线