# BattleBlitz 地图渲染梯度方案（best → fastest）

> 调研日期：2026-07-13 · 引擎：Godot 4.7-stable
> 目标：从"商业级 3D 感"到"移动端跑满 60fps"5 个梯度，给 BattleBlitz 客户端的当前/未来路线做对照

## TL;DR

| 梯度 | 名称 | 一句话 | 帧率参考 (1080p) | 实现复杂度 |
|:----:|------|--------|:-----------------:|:----------:|
| **S** | 商业级 2.5D | `TileMap` + 3D 投影 + 双 `Parallax` + 多 layer 2D 灯 + GLSL shader | RTX 3060：120+fps；移动端：30fps | 1.5 周 |
| **A** | 高分 TileMap | `TileMap` + `TileSet` autotile + 自定义水波 shader + 2D 灯 + `AnimatedTexture` | 桌面 60fps；移动：45fps | 0.5 周 |
| **B** | 标准 TileMap（**当前 M1.5**） | `TileMap` + `add_terrain_set` 16 bitmask autotile（FE8 美术已用上） | 桌面 60fps；移动：60fps | ✅ 已完成 |
| **C** | 低配扁平 | 单一 `TileMapLayer`，无 autotile，1-2 帧循环，色板 const | 全部 60fps+，5000 tile 满帧 | 0.5 天 |
| **D** | 极简 sprite | 不上 `TileMap`，每格 `Sprite2D` 直接摆 | 500 tile 满帧，更高掉帧 | 1 小时 |

---

## Tier S：商业级 2.5D（参考 Fire Emblem Engage / Advance Wars 1+2 Re-Boot Camp / 现代 SRPG 复刻）

### 技术栈
```
Root (Node2D)
├── World (Node2D, y_sort_enabled = true)
│   ├── Terrain (TileMap)          # 主地形，autotile 16 套
│   ├── Decor (TileMap y=+0.5)    # 地表装饰（草/石/花），每帧不变
│   ├── Water (TileMap y=+0.3, AnimatedTexture 8 帧)
│   ├── Units (Node2D, y_sort_enabled, 每个单位一个 Node2D 容器)
│   └── Light (Node2D, PointLight2D 4-8 个, LightOccluder2D 配山)
├── BackFog (ParallaxBackground, motion_scale = Vector2(0.2, 0.1))
│   └── Fog (TextureRect, ColorRect 渐变)
└── BackSky (ParallaxBackground, motion_scale = Vector2(0.05, 0.02))
    └── Sky (TextureRect, 大尺寸贴图)
```

### 关键节点
| 节点 | 作用 | 文档 |
|------|------|------|
| `ParallaxBackground` + `ParallaxLayer` | 远景视差滚，零 shader 成本 | [Godot Parallax 教程](https://docs.godotengine.org/en/stable/tutorials/2d/2d_parallax.html) |
| `PointLight2D` + `LightOccluder2D` | 局部光 + 山的轮廓 shadow | [2D Lights & Shadows](https://docs.godotengine.org/en/stable/tutorials/2d/2d_lights_and_shadows.html) |
| `AnimatedTexture` + `TileSet` 的 `animation_frames` | 河流/火焰循环 | Godot 4 `TileData` 文档 |
| `CanvasModulate` 整屏颜色偏移 | 白天/夜晚/雾天滤镜 | `CanvasItem.modulate` |
| `ShaderMaterial` (`shader_type canvas_item`) | 水波 noise / 草地 Perlin | [Godot 4 水波 shader 示例](https://blog.csdn.net/berry/article/details/154004253) |
| `y_sort_enabled = true` + 单位 Node2D | 自动按 Y 高度排序（避免遮挡错乱） | `Node2D.y_sort_enabled` |

### 性能预算（1080p，15×15 棋盘）
| 元素 | 实例数 | GPU 占比 |
|------|--------|---------:|
| 主 TileMap | 1 source × 15×15 cells | 5% |
| Decor TileMap | 1 source × 225 cells (含 0.5 跳过) | 5% |
| 水 TileMap + AnimatedTexture | 30 cells × 8 帧 | 10% |
| PointLight2D | 6 个 | 5% |
| 单位 sprite + Y-sort | 10-20 个 | 10% |
| Parallax 远景 | 2 个 1920×1080 纹理 | 5% |
| CanvasModulate | 屏级 pass | <1% |
| **合计** | | **~40%** + shader 20% |

桌面 RTX 3060 → 120+ fps。中端移动端（Adreno 730 等）→ 30 fps。

### 实现周期估算
- 主 TileMap + autotile：M1.5 已完成
- 装饰层 + Y-sort：1 天
- Parallax 远/中景：1 天
- 2D 灯 + 山的轮廓：1 天
- 自定义 shader (水/草)：2 天
- 光照/天气切换（CanvasModulate）：0.5 天
- **总计：6-8 天**

参考：[godot4-open-rpg 全流程](https://github.com/food-please/godot4-open-rpg)、[Godot 4.3 等距游戏中文教程](https://www.up58.net/55795.html)、[水波 + 折射 shader](https://blog.csdn.net/weixin_29015051/article/details/158198622)

---

## Tier A：高分 TileMap（成熟 SRPG 主流路线）

### 技术栈
```
Root (Node2D)
├── TileMap (terrain)         # 一层即可，autotile 已覆盖视觉
│   └── (可选 Decor TileMap y=+0.5)
├── Units (Node2D, y_sort)
└── (可选) BackFog (单层视差或纯色背景)
```

### 与 Tier S 的取舍
- ❌ 去掉 PointLight2D（性能敏感场景，如 60+ 单位同屏）
- ❌ 去掉 CanvasModulate 实时天气切换
- ✅ 保留 autotile + 自定义水/草 shader
- ✅ 保留 AnimatedTexture 4 帧循环（水）

### 帧率参考
- 桌面：60 fps
- 移动端：45 fps（30+ 单位、1080p）

### 实现周期
- 1-2 天（在当前 M1.5 基础上加 2D 灯 + shader）

---

## Tier B：标准 TileMap（**当前 M1.5**）

### 已实现
- `TileSet.add_terrain_set()` + 16 bitmask autotile
- 4 套地形：plain / forest / mountain / river，每套 16 tile 块
- FE8 OverworldRegularFE8.png 完整美术套件（已占位）
- 全部地形 atlas 路径映射（4 主 + 9 副）

### 缺什么
- 装饰层（Decor：碎石 / 花 / 树苗）
- 水波 / 草 shader
- 2D 灯光
- 远景视差

### 何时该升级到 A/S
- 同屏单位超过 30
- 用户反馈"地图太静/没气氛"
- 想要夜景/雨天切换

---

## Tier C：低配扁平（缺美术/赶工 fallback）

### 技术栈
```
TileMap (单层, no autotile, 每格固定 1 tile)
+ 1 张全图背景（CanvasLayer 1 层）
```

### 牺牲
- 无边缘混合（每格硬切）
- 无动画
- 无 2D 光

### 帧率
- 任何平台 60 fps+，棋盘 100×100 也能满帧

### 用途
- 临时占位
- 移动端低端机
- 大量地图的列表/缩略图

---

## Tier D：极简（个人项目/原型/MVP）

### 直接画
每个格一个 `Sprite2D`，用 `Sprite2D.set_position(Vector2(x*48, y*48))`。完全不用 `TileMap`。

### 优点
- 0 配置，5 分钟搭好
- 每个 sprite 独立可点
- 适合 < 200 格的迷你地图

### 缺点
- 250 节点后开始掉帧
- 无 occlusion culling
- 无批渲染

---

## 渲染技术清单（按"对 SRPG 价值"排序）

| # | 技术 | Godot API | 价值 | 性能影响 | 学习曲线 |
|---|------|-----------|:----:|:--------:|:--------:|
| 1 | TileSet autotile | `add_terrain_set()` + `set_terrain_peering_bit()` | ★★★★★ | 0% | 🟢 中 |
| 2 | 2D 灯 + Shadow | `PointLight2D` + `LightOccluder2D` | ★★★★★ | 5-15% | 🟢 易 |
| 3 | AnimatedTile | `TileSet` 的 `animation_frames` | ★★★★ | 5% | 🟢 易 |
| 4 | CanvasModulate | `CanvasModulate.color` | ★★★★ | <1% | 🟢 易 |
| 5 | Parallax 远景 | `ParallaxBackground` + `ParallaxLayer` | ★★★★ | <1% | 🟢 易 |
| 6 | Y-sort 单位 | `Node2D.y_sort_enabled = true` | ★★★★ | <1% | 🟢 易 |
| 7 | Decor 装饰层 | 多 `TileMapLayer` | ★★★ | 5% | 🟢 易 |
| 8 | 水波 shader | `ShaderMaterial` | ★★★ | 3-8% | 🟡 中 |
| 9 | 草地 Perlin | `noise()` in shader | ★★ | 3-8% | 🟡 中 |
| 10 | 法线贴图/凹凸 | `NormalMap` + shader | ★★ | 10% | 🟡 中 |
| 11 | LightOccluder2D | 山的轮廓 shadow | ★★ | 5% | 🟢 易 |
| 12 | 3D 投影（顶点 shader）| `placeholder_3d_mesh` | ★★ | 15% | 🔴 高 |
| 13 | Full 3D 棋盘 | `MeshInstance3D` + `PlaneMesh` | ★ | 50%+ | 🔴 高 |

---

## 推荐：BattleBlitz 客户端路线

### 现状（M1.5 commit `df39cbc`） = Tier B
- 4 套地形 autotile 已工作
- 缺：装饰层 / 灯 / shader

### 短期目标（**升级到 Tier A**）
1. 装饰层 TileMap（碎石/花苗），1 天
2. 水 TileMap + AnimatedTexture 4 帧循环，1 天
3. CanvasModulate 时间/天气切换，0.5 天
4. ❓ 2D 灯（性能预算紧，建议 M3 再加）

### 中期目标（**到 Tier S**）= M5 路线
5. ParallaxBackground 远景，1 天
6. PointLight2D + LightOccluder2D（4-8 个灯），2 天
7. 自定义 shader（水 noise + 草 Perlin），3 天

**预计 Tier B→S 全周期：~10 天**，可分批做（M3 加装饰、M4 加灯、M5 加 shader+Parallax）。

### 何时不动
- 没有用户反馈"地图太丑" → 停在 Tier B 已足够
- 60+ 单位同屏卡顿 → 退回 Tier C（关 autotile、合并 layer）
- 优化目标 300ms 加载 ≤ 50 个地图 → Tier D 直接画散图缩略图

---

## 参考案例（源码可读）

| 项目 | 引擎 | 链接 | 看点 |
|------|------|------|------|
| godot4-open-rpg | Godot 4.5 | [GitHub](https://github.com/food-please/godot4-open-rpg) | 完整回合制 + 网格移动 + UI |
| godot-2.5D-isometric-course | Godot 4.3 | [教程](https://www.up58.net/55795.html) | 39 节中文教程 |
| qarmin Qarminer | Godot 4 | [GitHub](https://github.com/qarmin/Qarminer) | 像素 RPG + 水反射 + 远景 |
| fireemblem8u (ref) | GBA 汇编 | `ref/fireemblem8u/` | 战役地图与 TileSet 编排逻辑 |
| Advance-Wars-v2 (ref) | Java | `ref/Advance-Wars-v2/` | CO 能量条 + 回合制 + 攻击预览 |
| TileMap benchmark (Talos) | Godot 4 | [docs.godotengine.org](https://docs.godotengine.org/en/stable/tutorials/2d/using_tilemaps.html) | 性能测试 + 100×100 棋盘基准 |

---

## 决策树

```
Q: 棋盘多大？
├── < 20×20 → 任何 Tier 都行，建议 A
├── 20×20 - 60×60 → A 或 B（性能开始敏感）
└── > 60×60 → C（关闭 autotile、合并 layer）

Q: 同屏多少单位？
├── < 20 → 可上 S（含 2D 灯 + shader）
├── 20-60 → A
└── > 60 → B/C（关 autotile 省 fillrate）

Q: 是否需要夜景/天气？
├── 是 → Tier S（CanvasModulate + 2D 灯必上）
└── 否 → 留在 B 即可

Q: 移动端目标？
├── iOS/Android 高端 → A
└── 低端 / 浏览器 → C
```

---

*本文档由代码层经验 + 官方文档 + CSDN/YouTube 教程综合而成。*
*持续更新：新 tile 集到位（48×48 标准）后，可无缝从 Tier B 跳到 Tier A，加 shader+Decor 即可。*
