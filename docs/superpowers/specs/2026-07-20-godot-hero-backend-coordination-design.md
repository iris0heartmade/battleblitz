# Godot 与 Hero 后端协调设计（2026-07-20）

> Date: 2026-07-20
> Base branch: `godot-map-port`
> Source branch: `hero-mercenary-dual-track`
> Scope: 在保持 Godot 客户端完整可用的前提下，吸收 hero 分支的后端、游戏设计、数据和测试；第一阶段优先适配 Godot 客户端，旧 Web UI 保留并延后统一体验。

## 背景

`hero-mercenary-dual-track` 是后端和游戏设计持续开发分支，新增了英雄、职业晋升、装备、佣兵点数分配、主线准备、商店、存档/挂起恢复等能力。`godot-map-port` 主要新增 Godot 客户端和地图编辑体验，同时也对后端做了攻击预测、地图编辑、BGM/WS/主线接口等适配。

两个分支不能用简单“谁覆盖谁”的方式合并。目标是让 `godot-map-port` 成为双客户端时代的承载分支：后端业务设计完整吸收 hero 分支，Godot 客户端追上新流程，旧 Web UI 源码和可运行性保留，后续再做视觉和交互统一。

## 目标

1. 保持 `godot-map-port` 自身完整性：`godot-client/`、Godot 素材、场景、网络客户端、地图编辑流程、截图和 smoke/e2e 工具都要保留。
2. 引入 `hero-mercenary-dual-track` 的全部游戏和后端设计：hero、mercenary、save、mainline prepare/shop、items、stories、tests 都进入目标分支。
3. 让 Godot 客户端第一阶段适配新后端设计，能完成新主线流程的核心闭环。
4. 保留旧 Web UI 的源码、资源、静态入口和后端路由兼容性，但不把 Web UI 视觉/流程精修放进第一阶段。
5. 为冲突文件建立明确解决规则，使后续代码合并可被审查、测试和回滚。

## 非目标

- 第一阶段不追求 Godot 与 Web UI 的完全界面等价。
- 第一阶段不重写旧 Web UI，也不重新设计双客户端视觉系统。
- 不新增第二套后端 API。Godot 和 Web UI 应共享同一组业务端点；只在必要时增加薄兼容字段。
- 不移除 hero 分支新增测试来换取快速通过；测试失败应暴露真实协调问题。

## 推荐路径

采用“后端先统一，Godot 先适配，Web UI 延后精修”。

第一阶段把 `hero-mercenary-dual-track` 的后端业务作为权威来源合入 `godot-map-port`，同时保留 Godot 分支独有的客户端和后端适配能力。随后补齐 Godot 客户端对新主线准备流程的 REST 包装和基础 UI 状态，让它能使用 hero 分支的新设计。旧 Web UI 在本阶段作为兼容目标：代码必须存在，入口必须可访问，接口不能被破坏。

## 冲突解决原则

### 后端业务真相

以下路径以 `hero-mercenary-dual-track` 为准：

- `game/app/hero_domain/**`
- `game/app/mercenary_domain/**`
- `game/app/save/**`
- `game/app/routes/save.py`
- `game/app/item_catalog.py`
- `game/items/**`
- `game/shops/**`
- `game/mainlines/chapter_test_*.json`
- `game/stories/chapter_test_*`
- hero、mercenary、save、mainline 相关测试文件

这些模块代表新游戏设计，不应因为 Godot 分支暂时未接入而删减。

### Godot 专属资产与客户端

以下路径完整保留 `godot-map-port`：

- `godot-client/**`
- `godot-client/assets/**`
- `godot-client/audio/**`
- `godot-client/scenes/**`
- `godot-client/scripts/**`
- `godot-client/tools/**`
- Godot 相关路线、审计和移植文档

这些内容不在 hero 分支存在，合并时不应被后端分支覆盖。

### 共享后端文件

`game/app/main.py` 必须同时 include hero 分支的 `save_routes.router` 与 Godot 分支已有的 audio、commanders、editor、ws、mainline 路由。

`game/app/routes/mainline.py` 以 hero 分支完整流程为基底，保留或回补 Godot 分支已有能力：

- `GET /mainlines`
- `GET /mainlines/dialogue`
- `GET /mainlines/{mainline_id}`
- `GET /mainlines/{mainline_id}/prepare`
- `POST /mainlines/{mainline_id}/prepare/promote`
- `POST /mainlines/{mainline_id}/prepare/equipment`
- `GET /mainlines/{mainline_id}/shop`
- `POST /mainlines/{mainline_id}/shop/purchase`
- `POST /mainlines/{mainline_id}/prepare/complete`
- `POST /mainlines/{mainline_id}/start`
- `POST /mainlines/{mainline_id}/advance`
- `POST /mainlines/{mainline_id}/next-battle`
- `POST /mainlines/{mainline_id}/abandon`
- `GET /mainlines/{mainline_id}/mercenary/config`
- `POST /mainlines/{mainline_id}/mercenary/allocate`

`game/app/mainline/schemas.py` 以 hero 分支 schema 为基底，保留 Godot 分支需要的 BGM metadata、battle config、dialogue key、`disabled_unit_indices`、`force` 等兼容字段。

`game/app/routes/actions.py` 以 hero 分支战斗行为为基底，回补 Godot 分支 `/games/{game_id}/forecast-attack`。该端点只做读预测，不应改变游戏状态。

`game/app/routes/editor.py` 保留 Godot 分支地图编辑增强，包括 custom map 创建、读取、删除和容量校验；如果 hero 分支没有相同功能，不视为冲突。

`game/app/routes/ws_gateway.py` 保留双方对 WS 鉴权、事件序列、snapshot、heartbeat 的能力。Godot 客户端当前依赖 `/ws/games/{game_id}?player_id={pid}&since_seq={N}`。

`game/app/game_logic.py`、`game/app/classes/units/base.py`、`game/app/classes/heroes/base.py`、`game/app/database.py`、`game/app/models.py`、`game/app/schemas.py`、`game/app/utils.py` 采用逐函数合并：业务模型、字段、持久化结构以 hero 分支为准；Godot 分支引入的预测、地图、BGM、WS 或客户端兼容字段必须保留。

### Web UI

`game/app/web/**` 第一阶段保留完整 Web UI。发生冲突时，以 hero 分支包含新 hero/mercenary/save/mainline 流程的 Web UI 为基底，回补 Godot 分支近期修复中不依赖 Godot 的通用能力，例如 BGM、地图编辑、攻击预测、WS 安全网。第一阶段只要求 Web UI 可被后端静态入口加载并继续使用核心功能。

## Godot 第一阶段适配范围

### 网络层

在 `godot-client/scripts/autoload/network_client.gd` 增加以下 API 包装：

- `get_mainline_prepare(mainline_id, user_name, callback)`
- `promote_mainline_hero(mainline_id, user_name, hero_id, target_class_id, callback)`
- `equip_mainline_hero(mainline_id, user_name, hero_id, slot, equipment_id, callback)`
- `get_post_battle_shop(mainline_id, user_name, callback)`
- `purchase_post_battle_shop_item(mainline_id, user_name, item_id, quantity, callback)`
- `complete_mainline_prepare(mainline_id, user_name, disabled_unit_indices, callback)`
- `get_mercenary_config(mainline_id, user_name, callback)`
- `allocate_mercenary_points(mainline_id, user_name, unit_type, stat, value, callback)`
- `list_saves(user_name, callback)`
- `save_manual(user_name, game_id, slot_kind, name, callback)`
- `load_save(user_name, save_id, callback)`
- `load_suspend(user_name, callback)`
- `erase_save(user_name, save_id, callback)`
- `capture_suspend(game_id, user_name, player_id, reason, callback)`

Existing `start_mainline` and `next_battle_mainline` should include `disabled_unit_indices` and, where needed, `force`.

### Mainline UI

Godot 主线视图增加一个可用的战前准备状态，不要求首版完全等价 Web UI。它需要展示：

- 当前章节、战斗序号、胜利条件、BGM metadata。
- 英雄列表：等级、职业、是否可晋升、装备摘要、装备加成。
- 可部署单位列表：至少支持勾选/禁用单位，并将 `disabled_unit_indices` 传给 start/next battle。
- 佣兵配置：总点数、已花费、剩余点数、每个兵种/属性升级。
- 商店入口：显示金币、商品、购买结果。

### 存档 UI

现有 Godot 存档视图不能继续把 save id 当作 game id 直接 `rejoin_by_name` 或 `DELETE /games/{id}`。第一阶段改为调用新 save API：

- 列表使用 `GET /saves?user_name=...`。
- 继续游戏使用 `POST /saves/load` 或 `POST /saves/load_suspend`。
- 删除使用 `POST /saves/erase`。
- 战斗中挂起使用 `POST /games/{game_id}/suspend`。

### Battle Flow

Godot 进入战斗后继续使用现有 `/games`、`/games/{id}/state`、actions、turns、WS 事件。战后推进使用 hero 分支的 `advance`、`next-battle`、prepare、shop 流程，而不是直接跳下一场。

## 数据和模型协调

`PlayerProfile` 需要同时承载：

- hero campaign state
- mercenary allocation
- mainline progress
- commander choices
- inventory / gold
- save metadata

如果两个分支对字段名或 JSON shape 有差异，保留 hero 分支字段作为存储真相，并在 route response 中提供 Godot 现有读取所需的兼容字段。

地图数据采用双方并集。`game/maps/custom/433_a4fef0.json` 属于 Godot 地图编辑产物，应保留。hero 分支 test chapters、items、shops、stories 必须恢复。

## 测试策略

后端必须至少运行：

- `pytest game/tests/test_mainline_api.py`
- `pytest game/tests/test_mainline_engine.py`
- `pytest game/tests/test_mainline_mercenary.py`
- `pytest game/tests/test_hero_domain_models.py`
- `pytest game/tests/test_hero_equipment.py`
- `pytest game/tests/test_hero_promotion.py`
- `pytest game/tests/test_save_api.py`
- `pytest game/tests/test_save_resume_fixes.py`
- `pytest game/tests/test_castle_unit_placement.py`
- `pytest game/tests/test_player_vs_ai_full_game.py`
- `pytest game/tests/test_map_capacity.py`

Godot 必须至少运行现有 smoke/e2e 工具，覆盖：

- free play 创建、加 AI、开始、WS snapshot。
- mainline 列表、详情、prepare、start。
- save list 不报错。
- editor map list/save/load 基础流程。

Web UI 第一阶段验证：

- `/ui/` 可加载。
- Web UI 依赖的 `/mainlines`、`/saves`、`/heroes`、`/games`、actions endpoint 返回 shape 不破坏。
- 不要求进行完整视觉统一验收。

## 风险

最大风险是 `game/app/routes/mainline.py` 和 `game/app/web/app.js` 都是大文件，直接手工合并容易遗漏函数。实施时应先接受 hero 分支业务基底，再逐项回补 Godot 端点和字段，并用测试锁定。

第二个风险是 Godot 当前 UI 已经有保存视图，但语义偏向“游戏列表/恢复”。新 save API 引入后必须调整命名和按钮语义，否则会出现 UI 看似正常但实际删错对象的风险。

第三个风险是 profile、save、mainline 三者共享状态较多。所有 profile 写回都应通过已有 repository/service 或 route 中一致的 session commit，避免 Godot 流程和 Web UI 流程写入不同结构。

## 验收标准

第一阶段完成时：

- `godot-map-port` 包含 hero 分支全部后端/游戏设计模块、数据和测试。
- `godot-client/` 完整保留，可启动，现有基础战斗流程不倒退。
- Godot 可通过新 prepare 流程进入主线战斗，能处理英雄/佣兵/商店/存档的基本 API 返回。
- 旧 Web UI 文件和静态入口保留，不因路由缺失或 schema 删除而崩溃。
- 后端相关 pytest 通过；Godot smoke/e2e 通过或明确记录非代码环境阻塞。
