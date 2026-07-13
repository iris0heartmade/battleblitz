# Spec: Hero / Mercenary 双轨制系统

**Date:** 2026-07-13  
**Status:** Approved for implementation  
**Scope:** Hero 深成长体系、Mercenary 主力体系、主线持久化、自由模式 Hero 规则、与现有 `progression/`/`mainline/`/`routes/game.py` 的集成边界

---

## 1. 目标

BattleBlitz 后续开发采用**双轨制单位模型**：

- **Hero**：少量具名角色，服务主线剧情，按 Fire Emblem 式进行 RPG 成长、转职、熟练度与长期培养。
- **Mercenary**：主力军与可招募杂兵，按 Advance Wars / FreeWars 式进行章节配置、兵种强化、招募与扩张，不走 Hero 式长期等级成长。

本设计的目标不是把现有系统全部推翻，而是把现有“具名英雄内容层”和“progression 持久化层”重新分工，让：

1. Hero 深成长有独立、清晰、稳定的战斗内核。
2. Mercenary 不被误拉进 Hero 规则。
3. 主线存档能稳定保存 Hero 的长期成长结果。
4. 自由模式 Hero 有明确、可解释、可平衡的数值来源。

---

## 2. 总体原则

### 2.1 三层分工

系统分为三层：

1. **持久化层（保留现有 `progression/`）**
   - 保存玩家档案、主线进度、Hero 长期成长结果、解锁、奖励。
   - 不直接承担 Hero 战斗公式。

2. **Hero 战斗内核（新增）**
   - 提供 FE 式 `CharacterTemplate / ClassTemplate / HeroCampaignState / HeroBattleState`。
   - 负责 Hero 等级、EXP、成长率、转职、熟练度、专属技能挂载。

3. **Mercenary 体系（新增）**
   - 提供 `MercenaryTemplate / MercenaryRosterState / ChapterBalanceConfig / CommanderAllocation`。
   - 负责章节 multiplier、兵种点数分配、中立佣兵招募、可选 Veteran 增强。

### 2.2 不把地图当存档

主线 Hero 的成长结果**不保存在地图 JSON**，也**不保存在单场战斗临时 Unit 上**。  
地图只提供“这一章谁会出场、站在哪、归属哪边”，真正成长结果来自主线存档中的 Hero 持久化实例。

### 2.3 不把战斗临时状态带进下一章

跨章节保留：

- 等级
- EXP
- 当前职业/转职状态
- 基础属性成长结果
- 武器熟练度
- 已学技能
- 长期装备栏

默认不跨章节保留：

- 当前 HP
- 当前 MP
- 士气
- 行动状态
- 临时 buff/debuff
- 战斗地图位置

---

## 3. Hero 体系设计

### 3.1 Hero 模型分层

#### A. `HeroCharacterTemplate`

定义“这个人是谁”，包含：

- `hero_id`
- `display_name`
- `base_class_id`
- 初始基础属性
- 个人成长率
- 初始武器熟练度
- 可选转职路线
- 专属标记 / 剧情标记
- 美术绑定

这层相当于 FE8 的 `CharacterData`。

#### B. `HeroClassTemplate`

定义“这个职业是什么”，包含：

- `class_id`
- 基础职业属性修正
- 该职业成长修正
- 属性上限
- 转职加成
- 移动类型/移动代价表
- 武器类型许可
- 是否 promoted

这层相当于 FE8 的 `ClassData`。

#### C. `HeroCampaignState`

这是**主线存档里的真实 Hero 成长结果**，必须持久化，包含：

- `hero_id`
- 当前 `class_id`
- 当前 `level`
- 当前 `exp`
- 当前基础能力值
- 当前武器熟练度
- 已学技能
- 是否已转职
- 长期装备
- 剧情状态（是否加入、是否永久离队等）

这是主线 Hero 的核心持久化对象。

#### D. `HeroBattleState`

每章战斗开始时，从 `HeroCampaignState` 展开出的临时战斗态，包含：

- 战斗中 HP/MP
- 当章起始位置
- 当章临时状态
- 当前回合资源
- 与现有 `Unit` 的映射字段

战斗结束后，成长结算结果回写 `HeroCampaignState`。

### 3.2 Hero 成长规则

- 固定 **100 EXP / 级**
- Hero 专属成长率结算
- 转职仅 Hero 可用
- 武器熟练度、职业路线主要服务 Hero
- 剧情敌将/Boss 可复用 Hero 模型的部分能力，但不要求都持久化

### 3.3 主线 Hero 生命周期

1. 主线章节开始。
2. 从 `PlayerProfile` / `HeroCampaignState` 读取该玩家 Hero 数据。
3. 结合章节配置生成 `HeroBattleState`。
4. 战斗中按 Hero 规则计算升级、EXP、熟练度、转职条件。
5. 战斗结束后，仅把长期成长结果写回 `HeroCampaignState`。
6. 下一章再次从 `HeroCampaignState` 生成，保证连续性。

---

## 4. Mercenary 体系设计

### 4.1 Mercenary 模型分层

#### A. `MercenaryTemplate`

定义兵种模板：

- `unit_type`
- 基础数值
- 招募成本
- 阵营归类
- 基础武器/行动类型
- 是否可被招募

#### B. `CommanderAllocation`

定义我方每章可重分配的兵种点数：

- 总点数（默认 100）
- 已分配点数
- 各兵种升级项
- 可选全局 modifier

#### C. `ChapterBalanceConfig`

定义当前章节对敌我双方佣兵层的规则：

- 敌方 attack/defense/income/move/vision modifier
- 起始资源
- 招募数限制
- 可选中立佣兵池引用

#### D. `MercenaryRosterState`

保存本档案已拥有的佣兵信息：

- 当前招募到的佣兵列表
- 原始招募章节
- 是否跨章节保留
- 可选 Veteran 等级/击杀记录

### 4.2 Mercenary 原则

- 默认不走 Hero 式等级/转职/成长率
- 主强度来自章节配置与兵种点数分配
- 中立佣兵招募是 BattleBlitz 独特玩法
- Veteran 击杀升级是**可选增强**，不是主规则

---

## 5. 主线存档规则

### 5.1 Hero 持久化

主线存档需要新增或重构为：

- `PlayerProfile`：保存全局主线进度与解锁
- `HeroCampaignState`：保存每个 Hero 的长期成长结果
- `MercenaryRosterState`：保存跨章节保留的佣兵与分配结果

### 5.2 每章战斗的正确生成流程

进入主线战斗时：

1. 加载章节配置。
2. 读取该档案 HeroCampaignState。
3. 读取 MercenaryRosterState 与当前章节配置。
4. 将 Hero 生成到对应 Hero 出场位。
5. 将 Mercenary 生成到佣兵/中立/敌方位置。
6. 初始化临时战斗状态（HP/MP 满、临时状态清空）。

这样可以避免：

- 地图把 Hero 等级写死
- 战斗升级没写回存档
- 临时状态污染下一章

---

## 6. 自由模式 Hero 规则

### 6.1 默认规则：标准化 Hero

自由模式默认**不读取主线成长结果**。  
自由模式 Hero 应使用标准化数值，以保证平衡、联机与调试可控。

建议配置：

- `disabled`
- `standard_lv1`
- `standard_lv5`
- `standard_lv10`

默认建议：`standard_lv1` 或 `standard_lv5`

### 6.2 可选规则：导入主线 Hero

允许在**单机 / 沙盒 / 非平衡模式**下，使用主线存档导入 Hero：

- 读取 `HeroCampaignState`
- 转换为自由模式单位
- 在 UI 上明确标注“非平衡 / 读取主线成长”

这条路线不建议作为默认多人自由模式规则。

### 6.3 自由模式 Hero 数据来源

自由模式新增 `HeroPresetState`：

- 按档位预设 Hero 的等级、职业、属性和装备
- 不污染主线持久化
- 作为多人或平衡模式的 Hero 来源

---

## 7. 与现有系统的关系

### 7.1 `app/classes/heroes/`

保留作为 Hero 内容注册入口，但其职责变为：

- 提供 Hero 模板内容
- 不再直接充当 Hero 长期成长真相源

### 7.2 `app/progression/`

保留，但职责收缩为：

- 玩家档案
- 主线进度
- HeroCampaignState / MercenaryRosterState 的持久化协调
- 奖励、结算、解锁

不继续扩张成“什么都管”的通用成长大箱子。

### 7.3 `routes/game.py` / `mainline/`

后续需要从：

- “按地图 spawn 再覆盖 hero_id”

转为：

- “按章节与存档状态，分别生成 HeroBattleState 与 Mercenary 战斗单位”

---

## 8. 开发顺序

### 第一阶段：骨架分层

- 新增 Hero 战斗内核目录与模型
- 新增 Mercenary 体系目录与模型
- 明确 `progression` 持久化层和新内核的接口

### 第二阶段：主线 Hero 持久化闭环

- 引入 `HeroCampaignState`
- 主线开始/结束读写闭环
- 确保跨章节成长正确

### 第三阶段：Mercenary 主力体系

- 引入章节 multiplier
- 引入 CommanderAllocation
- 引入 MercenaryRosterState
- 打通招募与跨章节保留

### 第四阶段：自由模式 Hero 规则

- 标准化 Hero 预设
- 可选主线导入模式

---

## 9. 非目标

本阶段不直接解决：

- Godot 前端替换
- WS e2e
- 武器耐久完整系统
- 支援系统
- 动态地形

这些在双轨制主骨架稳定后再进入。

