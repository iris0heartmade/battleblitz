# 2026-07-28 红方全兵种 4P 地图与佣兵站扩容

## 目标

- 新增一张 4 人自由模式地图，红方开局拥有当前全部注册单位类型各一个。
- 红方 HQ 周边配齐村庄、佣兵站、金库。
- 蓝、绿、黄三方只保留 HQ 英雄位，进入自由模式后由现有指挥官英雄逻辑替换。
- 新增单位同步入驻佣兵站，避免后端/网页/Godot 招募列表漂移。

## 实现

- 新增地图：`game/maps/red_full_roster_4p_20.json`。
- 后端招募价格表：`game/app/config.py::RECRUIT_COST` 覆盖全部注册单位类型。
- Web 招募弹窗：`game/app/web/app.js::RECRUIT_UNIT_TYPES` 覆盖全部招募类型。
- Godot 招募面板：`godot-client/scripts/main.gd::_RECRUIT_OPTIONS` 覆盖全部招募类型，并改为复用 `_unit_type_cn` 显示名称。
- Godot 常量镜像：`godot-client/scripts/autoload/config.gd::RECRUIT_COST` 同步价格。

## 验证点

- 地图 ID 可被 `MAP_PRESETS` 加载。
- 地图尺寸为 20x20，推荐人数为 4。
- 红方 `initial_units` 的类型集合等于当前单位注册表。
- 蓝、绿、黄每方只有一个 HQ 占位单位。
- 红方 8x8 初始区域包含 `b` 佣兵站、`v` 村庄、`$` 金库。
- 后端、Web、Godot 三端招募列表覆盖全部后端招募类型。
