# Hero / Mercenary 实施记录

日期：2026-07-18

## 本次完成

### Hero 裸属性与战斗态分离

- `Unit.campaign_base_stats` 保存主线英雄在装备加成前的裸属性；旧 SQLite 启动时自动补列。
- 装备只修改本场 `Unit` 的有效属性。升级先计算裸属性成长，再把成长差值同步到有效属性。
- 主线结算只写回裸属性。旧战局没有快照时，按当前装备做一次兼容回退并记录 WARNING。
- 因此死亡、升级或重开战斗都不会把装备 HP/攻击等数值永久写进 HeroCampaignState。

### 可验证的主线入口

- 新增隔离浏览器 E2E：临时 SQLite、随机端口、独立 Uvicorn。
- 覆盖“准备页开始后进入地图”及“第二章进行中选择第一章必须确认”。
- E2E 是可选依赖：从 `game/` 执行

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-e2e.txt
python -m playwright install chromium
python -m pytest tests/e2e -m e2e -q
```

### 佣兵第一阶段闭环

- 主线 JSON 可使用 `mercenary_balance` 声明 `total_points`、`starting_fund`、`allowed_unit_types` 和每项属性的 `point_cost`/`max_bonus`。
- `POST /mainlines/{id}/mercenary/allocate` 不再接收或信任客户端 `cost`；服务端校验兵种、属性、上限和预算后计算价格。
- 开始主线战斗时，分配只作用于没有 `hero_id` 的初始单位；配置快照写入 `Game.battle_config.mercenary`。
- 本局在兵营招募的新泛用单位继续从该快照获得同一加成，不能通过中途修改档案改变已开始的战局。

示例见 `game/mainlines/chapter_test_01.json`：修改一个兵种名或数值即可改变该章节允许的分配规则，无需改 Python 代码。

## 尚未实现

- 跨章节保留已招募佣兵及 Veteran 进度：现有 `MercenaryRosterState` 仍未成为生成来源。
- `max_recruit_count`、敌军 income/vision 等章节 modifier 尚未进入实际战斗规则，不能在 JSON 中假定其已经生效。
- 精确半点 MP：当前 `Unit.mp` 仍为整数，路线中的 x2 成本在扣除时会向下取整。
- 正式章节内容扩展与 E2E 的删除存档、战后进入下一章覆盖。
