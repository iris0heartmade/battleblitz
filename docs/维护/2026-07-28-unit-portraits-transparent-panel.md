# 2026-07-28 单位立绘与透明立绘区域

## 本次目标

| 项目 | 结果 | 说明 |
|---|---|---|
| 立绘显示 | 已接入英雄/普通单位双路径 | 英雄仍读 `assets/heroes/portrait_<hero_id>.png`，普通单位读 `assets/unit_portraits/portrait_<unit_type>.png` |
| 显示区域 | 已改为无边框透明 | Godot 选中单位立绘槽不再绘制底板和边框；Web 剧情立绘框也移除卡片背景 |
| 资产目录 | 已创建 | `godot-client/assets/unit_portraits/` 与 `game/app/web/assets/unit_portraits/` |
| 美术生成 | 已完成 | 已按注册单位清单生成 15 张普通单位立绘，并同步到 Godot/Web 两端 |

## 资源命名

```text
portrait_swordsman.png
portrait_archer.png
portrait_knight.png
portrait_healer.png
portrait_warlock.png
portrait_lancer.png
portrait_warrior.png
portrait_dragon_rider.png
portrait_falcon_knight.png
portrait_blade_master.png
portrait_paladin.png
portrait_sniper.png
portrait_sage.png
portrait_saint.png
portrait_berserker.png
```

## 分层

| 层级 | 单位 | 美术要求 |
|---|---|---|
| T1 | swordsman, archer, knight, healer, warlock, lancer, warrior, dragon_rider, falcon_knight | 造型清楚、装备朴素、职业剪影优先 |
| T2 | blade_master, paladin, sniper, sage, saint, berserker | 装备更精美、材质层次更多、姿态更有压迫感，但仍不能画可见眼睛 |

## 统一约束

- 输出 `800x1400` PNG。
- 普通单位不画可见眼睛，用帽檐、面甲、兜帽、刘海或上脸阴影遮挡。
- 不覆盖 `assets/classic/` 棋盘单位图。
- 透明背景优先；若使用内置图片工具，应先生成纯色 `#00ff00` 背景图，再做抠图。

## 验收

| 检查 | 结果 |
|---|---|
| 注册单位数 | 15 |
| Godot 立绘缺失 | 0 |
| Web 立绘缺失 | 0 |
| 尺寸/透明通道异常 | 0 |
