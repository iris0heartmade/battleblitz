# BattleBlitz 后骨架工作计划 (2026-07-13)

> 上下文: 上一个 agent 完成了 `hero-mercenary-dual-track` 骨架 (commit 9b76ec5)
> 后续两条核心问题需要继续推进
> 同时 `refs/` 已拉取 11 个参考项目(见 `refs/INDEX.md`)

---

## A. 上一个 agent 已完成(可复用)

✅ Hero 域骨架: `app/hero_domain/{templates,state,materialize,free_mode,promotion,spawn,legacy_bridge}.py`
✅ Mercenary 域骨架: `app/mercenary_domain/{templates,state}.py` —— **纯模型,无任何调用方**
✅ PlayerProfile 新增 JSON 列: `hero_campaign_states / hero_inventory / mercenary_roster_state`
✅ ProgressionService 新增: `get_hero_campaign_state / set_hero_campaign_state / get_hero_inventory / set_hero_inventory_item`
✅ DB migration 自动加列 (`database.py` `_run_legacy_migrations`)
✅ `routes/mainline.py`:
  - `GET /mainlines/{id}/prepare` —— 战前准备(展示 hero 成长、库存、转职选项)
  - `POST /mainlines/{id}/prepare/promote` —— 转职(消耗 hero_crest)
  - `/start` 支持 `disabled_unit_indices` 灰名单
  - `_persist_mainline_hero_results` —— 战斗结束把 hero 长期成长写回 profile
  - Hero spawn 时读取 `campaign_state`,覆盖基础职业 / 等级 / 属性
✅ `routes/game.py`: `_apply_hero_overrides` 接受 `campaign_state` 字段, 应用持久化数值
✅ Web app.js: 111 处 prepare/promote/hero_crest 钩入
✅ 新增 promoted 职业类: `blade_master / paladin / sage / saint / sniper` (`game/app/classes/units/`)
✅ 测试: **13 个域单测 + 32 个 mainline API 集成测全部通过**

## B. 已识别的缺口(下一轮工作)

### B1. 🔴 Mercenary 域零集成
`mercenary_domain` 只有模型,**没有任何 route / mainline / spawn 调用方**。
意味着章节 multiplier、兵种点数分配、佣兵跨章保留、Veteran 升级全都停留在内存里。

影响: 第三阶段任务 8 (Spec §8 "Mercenary 主力体系") 整段没开始。

### B2. 🟡 Hero 战终写回的边界
当前 `_persist_mainline_hero_results` 已能:
- 把存活 hero 的成长 / 转职写回 ✅
- MP 取 long-term pool 而非战斗中临时值 ✅
- promoted class 标志正确同步 ✅

但**未处理**:
- 🟠 Hero 在战斗中阵亡 —— 写不写回?等级会丢吗?
- 🟠 Hero 在战斗中被降级(?)
- 🟠 战斗中变更的 `equipment` 是否被覆盖?
- 🟠 主动技能的 `cooldown` 不应写回

### B3. 🟡 `VALID_CLASS_IDS` 与新 promoted 职业不一致
`app/mainline/schemas.py:25-27`:
```python
VALID_CLASS_IDS = ("swordsman", "archer", "knight", "warlock", "healer")
```
但 `blade_master / paladin / sage / saint / sniper` 已是合法职业且 hero 持久化允许使用这些 class_id。
**当前 mainline JSON 不允许**用 promoted 职业作为 `starting_units[i].class_id`,但 `/start` 后的运行时能写入 promoted class_id。
→ Spec 没说要禁,但要确认这是设计意图(还是 bug)。

### B4. 🟡 `routes/game.py` `_apply_hero_overrides` 的 promoted class 分支
当 `campaign_state["class_id"]` 是 promoted class 时,代码:
```python
candidate.unit_type = campaign_class_id
candidate.skills = list(campaign_class.default_skills)  # ← 会覆盖前面 hero 已有 skills
```
技能覆盖顺序需要 review:已加 `merged_skills` 循环,但**默认技能合并在前还是后**?有重复风险。

### B5. 🟢 自由模式 Hero 规则
`build_standardized_hero_state` 存在,但**没有 route 暴露**:
- `GET /free-mode/heroes` 给前端选择
- 没有 UI 接入

## C. 优先执行两个任务(学长不在时)

学长让小喵"开始执行两个任务"。基于缺口重要性和可验证性,小喵选这两条:

### 任务 #1: Mercenary 域主线集成(最大缺口)

**目标**: 让 `mercenary_domain` 不再是孤儿,打通"章节配置 → 战斗生成 → 跨章保留"。

**步骤**:
1. 扩展 `MainlineRewards` 或新增 `MainlineMercenaryConfig` schema(读取章节 multiplier / 兵种点数)
2. 新增 `routes/mainline.py::get_mainline_mercenary_alloc` 与 `POST .../mercenary/allocate`
3. 战斗生成时,根据 `ChapterBalanceConfig` 调整敌方 stat multiplier
4. 战斗结束把 `MercenaryRosterState` 写回 profile
5. 测试: 4 个集成测(读取 / 分配 / 战斗应用 / 跨章保留)

**可验证性**: 新增 `test_mainline_mercenary.py`,跟现有 mainline_api 风格一致

### 任务 #2: Hero 战终写回边界补全

**目标**: 让 `_persist_mainline_hero_results` 对边界 case 行为明确、可测试、不丢数据。

**步骤**:
1. 决定 hero 阵亡策略(暂定:仍写回,但 `level -= 1`, `learned_skills` 不变,前端显示 "DEAD")
2. 明确 equipment / cooldown 处理
3. 写 4 个新 test:
   - `test_advance_persists_dead_hero_state` —— 阵亡后状态保留
   - `test_advance_does_not_overwrite_equipment_with_temporary_swap` —— 装备不写回(只读)
   - `test_advance_promotes_class_id_consistent_with_unit_type` —— 边界强化
   - `test_advance_unaffected_by_human_ai_swap` —— 不串数据
4. 调整 `_persist_mainline_hero_results` 内部,补 `if not unit.is_alive:` 分支

**可验证性**: 复用 `ml_client` fixture

## D. 不在今晚范围

- Hero 域与 command 系统整合
- `VALID_CLASS_IDS` 是否扩展
- 自由模式 Hero UI
- `libs` 缺失问题
- 单元 `lib` 配套扩展(单元模板/技能)
- Godot 客户端集成

## E. 风险与回滚

- 任务 #1 改 schema 字段,**要 migration test**
- 任务 #1 改写回逻辑,**要全量 mainline_api 跑通**
- 任务 #2 涉及边界,**先全量测,再加新测**

## F. 完成后产出

- `game/tests/test_mainline_mercenary.py` (新增,任务 #1)
- `game/tests/test_hero_writeback_edges.py` (新增,任务 #2)
- 增量 commit: 2 个,分别在 hero / mercenary 任务完成时
- 全量测试: `pytest tests/ -k "hero or mercenary or mainline"` 全绿
