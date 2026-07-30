# 2026-07-23 成长强弱侧公式调整

## 背景

成长图表暴露出法师职业和法师英雄的 `ATK` 按 generic autolevel 公式强成长，导致 Yun/Anna 的成长线误导设计判断。

## 调整

- 新增 `BattleLanePolicy`，作为成长图表默认 policy。
- `battle_lane` 根据职业 `attack_kind` 分配强弱侧：
  - 物理职业：`ATK/DEF` 强成长，`MATK/MDEF` 弱成长。
  - 魔法职业：`MATK/MDEF` 强成长，`ATK/DEF` 弱成长。
- 英雄单位不单独定义成长表，先继承其基础职业的 `attack_kind`。
- generic 出生等级公式改为读取 lane-aware rates。
- 战斗内升级补上弱侧攻击成长：魔法单位 `ATK` 慢涨，物理单位 `MATK` 慢涨。
- 旧 `autolevel_boss` policy 保留，可用于显式旧公式对照。

## 暂缓

- 暂不启用 per-hero growth rate。
- T2/T3 等级上限仍需后续统一：当前长期 progression 为 T1=20、T2=35、T3=50，战斗内 `MAX_LEVEL` 仍为 20。

## 追加：职业 tier 与基础值校正

- `berserker` 校正为 T2 职业，基础值调整为 HP 48 / ATK 28 / DEF 8 / MOV 4 / MP 5 / MATK 4 / MDEF 5。
- `dragon_rider` 校正为 T1 职业，基础值调整为 HP 42 / ATK 16 / DEF 7 / MOV 5 / MP 7 / MATK 3 / MDEF 6。
- 已重新生成 `tools/growth_charts/classes/`、`tools/growth_charts/heroes/` 与 `tools/growth_charts/index.json`。
