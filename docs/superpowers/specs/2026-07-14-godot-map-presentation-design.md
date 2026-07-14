# BattleBlitz Godot 64x64 地图表现规范

- 日期：2026-07-14
- 分支：`godot-map-port`
- 范围：仅 Godot 前端地图表现层；不修改 Python 后端规则、协议、路由和数据结构
- 目标：为 BattleBlitz 建立一套可扩展的 64x64 Godot 战棋地图客户端基座

## 1. 目标与非目标

### 1.1 本轮目标

本轮只解决 Godot 客户端的“地图看起来像个正式游戏”这件事，优先级高于完整可玩交互。交付结果应满足：

1. 读取现有 `game/maps/*.json` 地图数据，不引入新地图格式。
2. 用 Godot 4.7 将地图改造为 64x64 网格渲染体系。
3. 借鉴 `godot-open-rpg` 的多层 TileMap 结构，但保留战棋游戏的强格子可读性。
4. 支持基础地表、建筑、装饰、单位静态摆放、镜头浏览和选中高亮。
5. 为后续移动、攻击、路径预览、HUD 和联网交互保留清晰扩展点。

### 1.2 本轮非目标

以下内容不在本轮交付范围内：

1. 不改 `game/app/` 下任意后端代码。
2. 不改 WebSocket 协议、REST 路由、数据库或游戏规则判定。
3. 不承诺本轮完成完整对战流程。
4. 不要求本轮完成正式 64x64 美术资源，只要求过渡素材能支撑新渲染体系。
5. 不在本轮引入新的地图编辑器或移动端适配。

## 2. 设计取向

### 2.1 风格结论

前端地图表现采用“工程结构学 `godot-open-rpg`，视觉可读性偏 Fire Emblem/战棋”的折中方案：

1. 结构上学习多层 `TileMapLayer`、地图度量抽象和镜头边界管理。
2. 视觉上保持 BattleBlitz 当前战棋地图的快速识别能力，避免被 RPG 风格装饰吞掉格子感。
3. 每个格子的占位、边界和单位站位必须一眼可辨，优先级高于纯装饰细节。

### 2.2 尺寸结论

地图标准 tile 基准统一提升为 `64x64`。这是渲染层规范，不要求后端地图坐标、地图 JSON 或规则计算发生任何变化。

## 3. 架构规范

### 3.1 场景层次

`Board` 场景重组为下列结构：

```text
BoardRoot (Node2D)
|- GroundLayer      (TileMapLayer)
|- StructureLayer   (TileMapLayer)
|- DecorLayer       (TileMapLayer)
|- HighlightLayer   (Node2D)
|- UnitLayer        (Node2D)
|- EffectsLayer     (Node2D)
`- BoardCamera      (Camera2D)
```

### 3.2 各层职责

1. `GroundLayer`
   只负责基础地表：`plain/forest/mountain/river/road/snow/desert/bridge` 等。
2. `StructureLayer`
   只负责强语义建筑与城堡子类型：`castle/village/barracks/gate/castle_wall/castle_door/castle_throne/...`。
3. `DecorLayer`
   只负责纯视觉装饰，如边缘修饰、树冠、石块、碎草、地表变化。该层不参与规则判定。
4. `HighlightLayer`
   负责选中框、hover 框、格子描边、未来路径点和范围底纹。它只渲染，不计算规则。
5. `UnitLayer`
   负责单位节点、站位、排序、未来 HP 条和状态图标。单位不放进 `TileMapLayer`。
6. `EffectsLayer`
   负责将来的飘字、受击、镜头反馈等效果，本轮只保留接口和节点位。
7. `BoardCamera`
   负责初始定位、边界限制、浏览缩放和未来的平滑跟随，不把镜头逻辑塞进地图脚本。

### 3.3 公共抽象

新增两个公共层对象：

1. `MapMetrics`
   统一维护 `tile_size = 64`、`cell_to_pixel`、`pixel_to_cell`、地图像素矩形边界和单元格中心点换算。
2. `MapTheme`
   统一维护 terrain/subtype 到 TileSet source、atlas coord、fallback 颜色、装饰规则的映射。

禁止在 `board.gd`、`map_loader.gd`、`tile_set_builder.gd` 中散落写死 `48` 或重复坐标换算逻辑。

## 4. 资源与素材规范

### 4.1 过渡策略

本轮采用“渲染体系先到位，素材允许过渡”的策略：

1. 先建立正式 `64x64` 渲染规范。
2. 现有 `48x48` PNG、FE8 `16x16` atlas 和占位素材允许通过放大、居中、填边、外框处理进入 64x64 体系。
3. 后续替换正式美术时，不应改地图加载逻辑和场景结构，只更新 `MapTheme`/TileSet 资源。

### 4.2 64x64 过渡规则

1. 所有地图格子的逻辑尺寸固定为 `64x64`。
2. `48x48` 旧资产进入 64x64 时优先采用“像素整数倍放大 + 居中/补边”的方式，避免模糊缩放。
3. FE8 `16x16` atlas 若继续使用，优先按整数倍扩成 `64x64` 等效切片，不使用双线性缩放。
4. 对过渡素材允许保留留白，但不允许格子中心漂移或站位歪斜。
5. 缺图时使用统一 fallback 贴图或纯色 tile，不允许 silent fail 直接空白。

### 4.3 可读性规则

为保持战棋感，本轮视觉必须满足：

1. 地形边界清晰，格子轮廓可快速定位。
2. 建筑语义强于地表纹理，村庄、兵营、城堡特征必须一眼可分。
3. 单位站位中心稳定，不被装饰层遮挡主体。
4. 镜头拉远时仍可快速识别森林、山、河、道路、据点。

## 5. 地图绘制规则

### 5.1 数据来源

仍然使用现有 `game/maps/*.json`：

1. `size`
2. `biome`
3. `layout`
4. `initial_units`
5. 已有 terrain/subtype 编码

本轮不增加新 schema。Godot 客户端必须兼容现有地图数据。

### 5.2 图层分配

地图写入规则固定如下：

1. 基础地表写入 `GroundLayer`。
2. `castle_*` 子类型、`village`、`barracks`、`gate` 等写入 `StructureLayer`。
3. 装饰性附加元素写入 `DecorLayer`，其存在与否不改变 terrain 语义。
4. 单位从 `initial_units` 解析后实例化到 `UnitLayer`，不参与 tile set cell 写入。

### 5.3 主题与 biome

1. `biome` 继续决定草地、雪地、沙地及相关城堡/森林变体。
2. `MapTheme` 负责把同一 terrain 在不同 biome 下解析到不同 source 或 atlas region。
3. 地图逻辑层不关心素材来自 FE8 atlas、旧 PNG 还是未来正式素材。

### 5.4 装饰策略

`DecorLayer` 采用保守策略：

1. 本轮允许先空实现或只提供少量 deterministic decor。
2. 装饰不能遮挡格子中心、建筑主体和单位主体。
3. 装饰选择必须稳定，不能每次加载随机得不一样。推荐沿用 `(terrain, x, y)` 哈希决定变体。

## 6. 交互与镜头规范

### 6.1 本轮交互下限

本轮最小交互只要求：

1. 鼠标点击能命中格子。
2. 显示 hover/selected 高亮。
3. 单位静态展示能按地图坐标摆放。
4. 支持基础镜头浏览与缩放。

### 6.2 镜头规则

1. 镜头边界由地图像素尺寸自动计算。
2. 小地图居中，大地图限制边界，避免露出地图外空白。
3. 默认行为优先服务“看清整图”，不是追求戏剧化镜头运动。
4. 镜头逻辑必须从 `Board` 脚本中抽离到专用组件或明确方法集合。

## 7. 代码迁移规范

### 7.1 保留与重构边界

保留：

1. 现有 `godot-client` 工程骨架。
2. 现有 `MapLoader` 对地图 JSON 的基础解析思路。
3. 现有 `Highlights`、`Units`、`Effects` 的节点职责方向。

重构：

1. `TileSetBuilder.TILE_SIZE = 48` 必须迁移为 64 体系。
2. `board.gd` 中依赖 `TileSetBuilder.TILE_SIZE` 的镜头与坐标逻辑必须迁出到 `MapMetrics`。
3. `CastleLayer` 命名升级为 `StructureLayer`，以容纳城堡以外建筑语义。
4. `MapLoader.apply_to_board()` 从“直接往两层抹 cell”升级为“按 theme/metrics/scene layers 写入”。
5. `main.gd` 演示入口允许保留，但应适配新的场景和状态显示。

### 7.2 禁止事项

1. 不把单位也塞进 tilemap。
2. 不把 64 像素逻辑继续散落在多个脚本常量里。
3. 不为赶进度把装饰逻辑塞进规则层或地图 JSON schema。
4. 不改后端地图生成器来迎合前端原型缺陷。

## 8. 数据流规范

### 8.1 加载流程

标准地图加载流程为：

1. `main.gd` 或未来入口选择 map id。
2. 读取 `game/maps/<id>.json`。
3. `MapLoader` 解析 `size/layout/biome/initial_units`。
4. `MapMetrics` 计算尺寸、像素边界和中心点。
5. `MapTheme` 解析 tile 来源与变体。
6. 依次写入 `GroundLayer`、`StructureLayer`、`DecorLayer`。
7. `UnitLayer` 根据 `initial_units` 摆放单位节点。
8. `BoardCamera` 根据地图尺寸设置初始位置与可视边界。
9. `HighlightLayer` 绑定 metrics，处理 hover/selected 渲染。

### 8.2 错误处理

1. 地图文件缺失：界面明确提示，禁止静默失败。
2. terrain/source 缺图：落 fallback tile 并打印 warning。
3. 非法 biome：回退到默认 biome 并提示。
4. 行列尺寸与 layout 不匹配：允许容错，但输出 warning。

## 9. 验收标准

本轮完成标准定义为：

1. 至少能正确渲染 3 张不同 biome 或不同尺寸地图。
2. 地图格逻辑尺寸全部为 64x64。
3. 能看出 `Ground/Structure/Decor/Unit/Highlight` 的层级职责已经分离。
4. 相机不会轻易露出地图外无效区域。
5. `initial_units` 能以静态节点形式正确落位。
6. 从代码结构上看，后续接移动动画、路径预览和 HUD 时无需推翻地图层设计。

## 10. 风险与后续

### 10.1 主要风险

1. 旧 48x48 资产在 64x64 体系里可能出现视觉稀疏，这属于已接受的过渡成本。
2. FE8 atlas 与 BattleBlitz 原地形语义不完全一致，短期内可能需要 fallback 或替代图。
3. 若继续沿用当前原型式 `board.gd` 而不抽公共层，后续功能会迅速返工。

### 10.2 下一阶段建议

本规范落地后，下一阶段应进入实现计划，优先顺序如下：

1. 引入 `MapMetrics` 与 `MapTheme`。
2. 把 tile 渲染体系迁到 64x64。
3. 重组 `Board` 场景层级与命名。
4. 接入 `initial_units` 静态摆放。
5. 补基础镜头边界与 highlight 表现。

---

这份规范的核心结论只有一句：先把 BattleBlitz 的 Godot 地图前端从“能画 JSON 的原型”提升成“64x64、多层、可扩展的战棋地图基座”，素材可以过渡，结构不能再凑合。
