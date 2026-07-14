# Top-Down 2D Map Patterns — Open-Source Godot Games

> 调研日期：2026-07-14 · 引擎：Godot 4.7
> 目的：参考真实 Godot 4 项目的 **2D 平面地图** 实现，给 BattleBlitz 客户端地图层（M2+）抄作业。
> 调研对象：clone 到 `godot-client/ref/games/` 的 4 个 top-down / grid 项目。

---

## TL;DR — 4 个项目哪些有用？

| 项目 | 引擎 | 类型 | 平面地图相关性 | 重点参考 |
|------|------|------|:---:|---------|
| [**godot-open-rpg** (GDQuest)](https://github.com/gdquest-demos/godot-open-rpg) | Godot 4.6 | top-down RPG，**多层 TileMapLayer** + `AStar2D` | ✅✅✅ | **主参考** — 完整的 grid + 镜头 + 状态机 |
| [**godot4-open-rpg** (food-please)](https://github.com/food-please/godot4-open-rpg) | Godot 4.6 | top-down RPG + Dialogic | ✅✅✅ | **结构同 GDQuest**，Dialogic 集成范例 |
| [TowDownGame (Glen0011)](https://github.com/Glen0011/TowDownGame) | Godot 4.2 | 等距 2D 射击（**legacy TileMap**，无 TileMapLayer） | ⚠️ 部分 | 镜头跟随 + 鼠标偏移 + 屏幕震动 |
| [godot-open-rts (GeorgeS2019)](https://github.com/GeorgeS2019/godot-open-rts) | Godot 4 | **3D 等距 RTS**（Node3D + NavigationServer3D） | ❌ | 跳过 — 不是 2D tile 地图 |

**结论**：BattleBlitz 的 2D 平面地图实现，**直接抄 GDQuest 的 6 个 pattern** 即可。TowDownGame 的 Camera 跟随 + 鼠标偏移值得参考。godot-open-rts 是 3D，不要浪费时间。

---

## 1. godot-open-rpg (GDQuest) — 主参考 ✅✅✅

源码路径：`godot-client/ref/games/godot-open-rpg/`
引擎：Godot 4.6 · 美术：Kenney Tiny Town

### 1.1 多层 TileMapLayer 结构（**核心**）

整个游戏地图是 6 个 `TileMapLayer`，按"地形 / 装饰 / 玩家 / 前景"分层，全部共享同一份 `TileSet.tres`：

| 层级名 | 作用 | y_sort_enabled |
|--------|------|:---:|
| `Ground` / `Terrain` | 主地形（autotile） | ❌ |
| `Buildings` / `Walls` | 房屋墙体 | ❌ |
| `Trees` | 树干 | ❌ |
| `TreeTops` | 树冠（盖在角色头上） | ✅ |
| `Decoration` | 花草小装饰 | ✅ |
| `Gamepieces` | 角色 + 可交互物（玩家/NPC/宝箱） | ✅ |

代码定位（`src/main.tscn:335-732`）：3 个区域 `Town` / `House` / `Forest`，每区域都是同一套 `Ground + Buildings + Trees + TreeTops + Gamepieces`。

**关键 insight**：树冠分到独立 `TileMapLayer` 且 `y_sort_enabled = true`，这样玩家走到树下时会被树冠遮挡，正确。

### 1.2 TileSet 资源（`.tres` 文件）

```tres
; overworld/maps/tilesets/kenney_terrain.tres:455-470
terrain_set_0/mode = 2        ; MATCH corners — 树
terrain_set_0/terrain_0/name = "GreenTrees 0"
terrain_set_0/terrain_1/name = "YellowTrees"
terrain_set_1/mode = 1        ; MATCH sides — 地面
terrain_set_1/terrain_0/name = "Dirt"
terrain_set_1/terrain_1/name = "Grass"
terrain_set_1/terrain_2/name = "Cobblestone"
custom_data_layer_0/name = "IsCellBlocked"
custom_data_layer_0/type = 1  ; bool
```

**关键 insight**：地形通行性（collision）通过 TileSet 的 **custom data layer** 而**不是物理层**。每个格子挂一个 `IsCellBlocked: bool`，寻路时 `tile_data.get_custom_data("IsCellBlocked")` 即可。这样比物理层高效得多。

### 1.3 GameboardProperties 资源（地图元数据）

```gdscript
; src/field/gameboard/gameboard_properties.gd
class_name GameboardProperties extends Resource
@export var extents: Rect2i = Rect2i(0, 0, 10, 10)  ; 格子范围
@export var cell_size: Vector2i = Vector2i(16, 16)  ; 格子像素
var half_cell_size: Vector2 = cell_size / 2.0
```

实例在 `overworld/maps/gbprops.tres`：
```tres
extents = Rect2i(0, 0, 70, 35)
cell_size = Vector2i(16, 16)
```

**关键 insight**：把地图尺寸 + 格子大小封装成 Resource，**比 JSON 多一层类型检查**，编辑器里可以直接拖到节点上。BattleBlitz 可以做一个 `MapProperties` resource，绑定每张地图的 `width/height/cell_size/biome`。

### 1.4 Gameboard autoload — 网格核心

```gdscript
; src/field/gameboard/gameboard.gd:39-99
func cell_to_pixel(cell: Vector2i) -> Vector2:
    return Vector2(cell * properties.cell_size) + properties.half_cell_size

func pixel_to_cell(pixel: Vector2) -> Vector2i:
    return Vector2i(
        floori(pixel.x / properties.cell_size.x),
        floori(pixel.y / properties.cell_size.y)
    )

func get_cell_under_node(node: Node2D) -> Vector2i:
    return pixel_to_cell(node.global_position / node.global_scale)
```

加 `cell_to_index`、`index_to_cell`、`get_adjacent_cell(s)` 配套 AStar2D 寻路。

**关键 insight**：**网格逻辑挂在 autoload**（不是场景节点），所有需要网格转换的地方 `Gameboard.cell_to_pixel()` 一行调用。BattleBlitz 完全可以照抄这个 autoload。

### 1.5 Camera 跟随 — autoload + 动态 limit

```gdscript
; src/field/field_camera.gd:38-84 — FieldCamera extends Camera2D
class_name FieldCamera extends Camera2D
@export var gamepiece: Gamepiece     ; 玩家单位

func _on_viewport_resized() -> void:
    var boundary_left = gameboard_properties.extents.position.x * cell_size.x
    var boundary_right = gameboard_properties.extents.end.x * cell_size.x
    var vp_size = get_viewport_rect().size / global_scale
    if boundary_width < vp_size.x:
        ; 地图比视口小 — 锁定居中
        position.x = (extents.position.x + extents.size.x / 2.0) * cell_size.x
        limit_left = (position.x - vp_size.x/2.0) * global_scale.x as int
        limit_right = (position.x + vp_size.x/2.0) * global_scale.x as int
    else:
        limit_left = boundary_left * global_scale.x as int
        limit_right = boundary_right * global_scale.x as int
```

跟随通过 `Gamepiece.animation_transform.remote_path` 接 `RemoteTransform2D` 实现，玩家移动 → 相机平滑跟随。

**关键 insight**：相机作为 autoload 注册，**`limit_left/right/top/bottom` 全部从 Gameboard 动态算出**，分两种情况：地图大（边界跟地图走）vs 地图小（居中锁定）。这就是 BattleBlitz 当前缺的。

### 1.6 GameboardLayer — 通用 TileMapLayer 子类

```gdscript
; src/field/gameboard/gameboard_layer.gd
class_name GameboardLayer extends TileMapLayer

const BLOCKED_CELL_DATA_LAYER := &"IsCellBlocked"

func is_cell_clear(coord: Vector2i) -> bool:
    var tile_data = get_cell_tile_data(coord)
    if tile_data:
        var blocked = tile_data.get_custom_data(BLOCKED_CELL_DATA_LAYER) as bool
        return not blocked
    return false
```

每个 TileMapLayer 都挂这个脚本，加到 `GameboardTileMapLayers` group，Gameboard 收集所有 group 成员聚合通行性。

**关键 insight**：**继承 TileMapLayer 而不是裸用**。给 TileMapLayer 加一个 `is_cell_clear()` 方法就是干净 OO。BattleBlitz 可以做 `BoardTileLayer` 子类，把 `terrain_layer` / `castle_layer` 都换成它。

### 1.7 移动用 Path2D + Curve2D

```gdscript
; src/field/gamepieces/gamepiece.gd:13
class_name Gamepiece extends Path2D
```

角色沿 `Curve2D` 走，每帧推进到下一个 `Vector2` 控制点。比 Tween 平滑且容易插入中途停止/改变方向。

**关键 insight**：**2D 战棋移动用 Path2D 远比 Tween 优雅**。BattleBlitz 单位移动可以学这个，每个 Unit 节点是 `Path2D` + sprite 子节点。

---

## 2. godot4-open-rpg (food-please) — Dialogic + 同结构 ✅✅✅

源码路径：`godot-client/ref/games/godot4-open-rpg/`
引擎：Godot 4.6

**和 GDQuest 的关系**：高度相似（看起来是同源 fork），结构几乎一样：`Gameboard` autoload、`GameboardProperties` resource、相同的 TileMapLayer 命名（`Ground / Buildings / Trees / TreeTops / Decoration / Terrain / Walls / Gamepieces`）、相同的 `IsCellBlocked` 自定义数据层、相同的相机算法。

### 唯一的关键差异：Dialogic 集成

```gdscript
; src/field/cutscenes/templates/conversations/conversation_template.gd
class_name InteractionTemplateConversation extends Interaction
@export var timeline: DialogicTimeline

func _execute() -> void:
    if timeline:
        Dialogic.start_timeline(timeline)
        Dialogic.signal_event.connect(_on_dialogic_signal_event)
        await Dialogic.timeline_ended
        Dialogic.signal_event.disconnect(_on_dialogic_signal_event)
```

触发器（碰撞区域）→ `InteractionTemplateConversation._execute()` → `Dialogic.start_timeline()` → `await Dialogic.timeline_ended` → 继续游戏。`Dialogic.signal_event` 用来在对话中插入代码（例如在 `wand_pedestal_interaction.gd:126-132` 写 `Dialogic.VAR.set_variable("RedWandCount", ...)`）。

**关键 insight**：Dialogic 触发模式是 `start + await timeline_ended + optional signal_event`。BattleBlitz M3 主线剧情可以直接抄这个模式。Dialogic 是 autoload（`project.godot:32`：`Dialogic="*uid://..."`）。

---

## 3. TowDownGame (Glen0011) — 镜头 + 鼠标偏移 ⚠️

源码路径：`godot-client/ref/games/TowDownGame/`
引擎：Godot 4.2

### 为什么是 ⚠️

- 这是 Godot 4.2 项目，**没有 TileMapLayer**（还在用旧 `TileMap` 节点）
- 美术是**等距 32×16**（`tile_shape = 1`），不是平面
- TileSet `terrain_set/mode = 0`（**非 autotile**，纯散图）

但**有价值的部分**是相机。

### 3.1 Camera 跟随 + 鼠标偏移

```gdscript
; game/map/Camera2D.gd:11-29
var max_offset = 5
var t = distance / max_distance
var new_offset = (get_global_mouse_position() - camera_pos).normalized() * max_offset * t
```

镜头会向鼠标方向轻微偏移，让玩家有"瞄准感"。最多偏 5 px。

### 3.2 屏幕震动

```gdscript
; game/map/Camera2D.gd:33-44 — shootShake()
; 用 Tween 抖动 camera.position 0.1s
```

开火时调用，0.1 秒震屏。

### 3.3 Anchor 节点 lerp 跟随

```gdscript
; game/map/Anchor._physics_process (Town.tscn:1798-1808)
func _physics_process(delta):
    var target = Utils.player.global_position
    var x = int(lerp(global_position.x, target.x, 0.2))
    var y = int(lerp(global_position.y, target.y, 0.2))
    global_position = Vector2(x, y)
```

Anchor 节点 lerp(0.2) 跟随玩家，Camera2D 作为 Anchor 的子节点 —— 这样改 Anchor 时相机自然平滑跟随。

**BattleBlitz 可借鉴**：
- M4 战斗镜头的"鼠标偏移瞄准"效果
- M4 受击震屏
- 用 Anchor 节点中转比直接改 Camera2D.position 更平滑

---

## 4. godot-open-rts (GeorgeS2019) — 跳过 ❌

源码路径：`godot-client/ref/games/godot-open-rts/`
引擎：Godot 4

**这是一个 3D 项目**，用 `Node3D` + `PlaneMesh` + `Camera3D` (orthographic) + `NavigationServer3D`。整个 codebase 里**没有任何 TileMapLayer / TileSet / AStar2D**（grep 验证过）。

虽然 README 写 "showcase Godot 4 capabilities for RTS games"，但它是 3D iso，不是 BattleBlitz 需要的 2D tile 地图。**不要花时间看**。

如果以后 BattleBlitz 要做 3D 视图再回来看 —— `NavigationRegion3D` 的 baking 流程 + `NavigationAgent3D` + `Match._recalculate_camera_bounding_planes` 的镜头 bounding planes 算法值得借鉴。

---

## 📊 4 个项目模式对比表

| 维度 | godot-open-rpg | godot4-open-rpg | TowDownGame | godot-open-rts |
|------|:---:|:---:|:---:|:---:|
| **平面 2D** | ✅ | ✅ | ⚠️ iso | ❌ 3D |
| **TileMapLayer** | ✅ 多层 | ✅ 多层 | ❌ 旧 TileMap | ❌ 3D mesh |
| **autotile / terrain_set** | ✅ 2 套 | ✅ 2 套 | ❌ mode=0 | ❌ |
| **Custom data layer** | ✅ IsCellBlocked | ✅ IsCellBlocked | ❌ | ❌ |
| **Map 资源** | ✅ GameboardProperties | ✅ GameboardProperties | ❌ | ⚠️ plane size |
| **Grid autoload** | ✅ Gameboard | ✅ Gameboard | ❌ | ❌ |
| **Camera autoload** | ✅ FieldCamera | ✅ FieldCamera | ❌ Anchor+C2D | ⚠️ IsometricCamera3D |
| **A* 寻路** | ✅ AStar2D | ✅ AStar2D | ❌ | ✅ NavigationServer3D |
| **Map 文件格式** | `.tscn` 内嵌 | `.tscn` 内嵌 | `.tscn` 内嵌 | `.tscn` 子场景 |
| **Y-sort 单位** | ✅ Gamepiece.Path2D | ✅ 同 | ✅ | ✅ 3D depth |
| **Dialogic 集成** | ✅ | ✅ | ❌ | ❌ |

---

## 🎯 BattleBlitz 可以抄的 6 个 pattern

### Pattern 1: 多层 TileMapLayer（地形 + 装饰 + 玩家）

```gdscript
# Board.tscn 当前已有 4 层：terrain_layer / castle_layer / highlights / effects
# 但高层抽象不够。加一层 decor_layer（M3 用）：
# Board
# ├── terrain_layer: BoardTileLayer (autotile)
# ├── castle_layer:  BoardTileLayer (sub-features)
# ├── decor_layer:   BoardTileLayer (花/石/树苗)
# ├── highlights:    HighlightsLayer (M2 移动范围高亮)
# ├── effects:       EffectsLayer (M4 攻击特效)
# └── units:         Node2D (y_sort_enabled = true)
```

**对比 BattleBlitz 当前**：`scripts/board.gd` 已有 `terrain_layer` / `castle_layer` / `highlights` / `effects`，**已经做对了 80%**。M3 加 `decor_layer`。

### Pattern 2: Gameboard autoload + cell_to_pixel / pixel_to_cell

```gdscript
# scripts/autoload/gameboard.gd — 新建 autoload
class_name Gameboard
var cell_size := Vector2i(48, 48)
func cell_to_pixel(c: Vector2i) -> Vector2:
    return Vector2(c * cell_size)
func pixel_to_cell(p: Vector2) -> Vector2i:
    return Vector2i(p / cell_size)
```

**对比 BattleBlitz 当前**：`MapLoader.apply_to_board()` 里直接 `Vector2i(x, y)` → atlas coord，**没有显式 cell_size 常量**。建议把 `Config.TILE_SIZE` 提到 Gameboard autoload。

### Pattern 3: GameboardProperties resource

```gdscript
# scripts/core/map_properties.gd
class_name MapProperties extends Resource
@export var width: int = 15
@export var height: int = 15
@export var cell_size: Vector2i = Vector2i(48, 48)
@export var biome: String = "grass"
@export var terrain_lookup: Dictionary = {}
```

**对比 BattleBlitz 当前**：每张地图用 JSON (`game/maps/*.json`) 已经有 `size.width` / `size.height` / `biome` / `terrain_lookup` 等字段。**可以做成 Resource + JSON 双格式**：运行时用 JSON（已有），编辑器里用 Resource（关卡设计师友好）。

### Pattern 4: Camera autoload + 动态 limit

```gdscript
# scripts/autoload/camera.gd
class_name GameCamera extends Camera2D
func _on_viewport_resized() -> void:
    var bounds := Gameboard.map_bounds  # Rect2i in pixel coords
    var vp_size := get_viewport_rect().size
    if bounds.size.x < vp_size.x:
        # 地图比视口小 — 居中锁定
        position.x = bounds.position.x + bounds.size.x / 2.0
        limit_left = position.x - vp_size.x / 2.0
        limit_right = position.x + vp_size.x / 2.0
    else:
        limit_left = bounds.position.x
        limit_right = bounds.end.x
    # y 同理
```

**对比 BattleBlitz 当前**：`scenes/board.tscn` 里 Camera2D 没有任何 limit，地图大时镜头会出界。**这是必须补的**。

### Pattern 5: TileSet custom data layer（通行性）

```gdscript
# TileSetBuilder._build_fe8_atlas_source() 已构建 TileSet，但缺 custom data layer
# 加一行：
ts.add_custom_data_layer()
ts.set_custom_data_layer_name(0, "IsBlocked")
ts.set_custom_data_layer_type(0, TileSet.CUSTOM_DATA_TYPE_BOOL)
# 然后每个 tile_data：
tile_data.set_custom_data("IsBlocked", true)
```

**对比 BattleBlitz 当前**：TileSetBuilder 只配了 terrain_peering_bits，**没有 IsBlocked 自定义数据层**。寻路时只能假设"地形 = 通行性"，没法区分"山不可过 vs 平原可过"。M2 寻路前必须加。

### Pattern 6: Gamepiece extends Path2D（移动）

```gdscript
# scripts/core/unit.gd
class_name Unit extends Path2D
@export var sprite: Sprite2D
var _progress: float = 0.0
var _speed: float = 200.0  # px/s
func move_to_path(points: PackedVector2Array) -> void:
    var curve := Curve2D.new()
    for p in points:
        curve.add_point(p)
    curve = curve
    _progress = 0.0
func _process(delta: float) -> void:
    if curve == null or _progress >= curve.get_baked_length():
        return
    _progress = _speed * delta
    sprite.position = curve.sample_baked(_progress)
```

**对比 BattleBlitz 当前**：Unit 节点用 `set_position()` 直接跳格，**没有路径动画**。M2 单位移动可以借鉴这个，做平滑走格而不是瞬移。

---

## 🛠 行动建议（M2 实现路径）

```
M2 第一步 (1-2 天):
  1. 加 Gameboard autoload (cell_to_pixel/pixel_to_cell)        ← Pattern 2
  2. 改 TileSetBuilder 加 "IsBlocked" custom data layer           ← Pattern 5
  3. 加 Camera autoload + 动态 limit                              ← Pattern 4

M2 第二步 (2-3 天):
  4. 加 GameboardLayer 子类,挂在 terrain_layer / castle_layer   ← Pattern 1
  5. 改 MapLoader 用 Gameboard cell_size 而非硬编码 48          ← Pattern 2

M2 第三步 (1-2 天):
  6. Unit extends Path2D,实现 Curve2D 走格                       ← Pattern 6
  7. AStar2D 寻路 + 移动范围高亮 (HighlightsLayer)               ← GDQuest pathfinder

M3 (剧情):
  8. 装 Dialogic 2,抄 food-please 的 ConversationTemplate       ← Pattern from §2

M4 (战斗):
  9. TowDownGame 的鼠标偏移 + 屏幕震动镜头                       ← Pattern from §3
```

---

## 📦 Cloned 项目信息

| 项目 | 大小 | 状态 | 是否在 git |
|------|----:|:---:|:---:|
| godot-open-rpg | 41M | ✅ 已 clone | ❌ (`godot-client/.gitignore` 加了 `ref/games/`) |
| godot4-open-rpg | 41M | ✅ 已 clone | ❌ |
| godot-open-rts | 12M | ✅ 已 clone | ❌ |
| TowDownGame | 287M | ✅ 已 clone | ❌ |

**重新 clone 命令**（如需重置）：
```bash
cd "D:/PyCharm Community Edition 2024.3.3/PycharmProjects/BattleBlitz/godot-client/ref/games"
git clone --depth 1 https://github.com/gdquest-demos/godot-open-rpg.git godot-open-rpg
git clone --depth 1 https://github.com/food-please/godot4-open-rpg.git godot4-open-rpg
git clone --depth 1 https://github.com/GeorgeS2019/godot-open-rts.git godot-open-rts
git clone --depth 1 https://github.com/Glen0011/TowDownGame.git TowDownGame
```

---

## 📚 引用源

- [GDQuest godot-open-rpg](https://github.com/gdquest-demos/godot-open-rpg) — 主参考
- [food-please godot4-open-rpg](https://github.com/food-please/godot4-open-rpg) — Dialogic 范例
- [Glen0011 TowDownGame](https://github.com/Glen0011/TowDownGame) — Camera 跟随 / 鼠标偏移
- [GeorgeS2019 godot-open-rts](https://github.com/GeorgeS2019/godot-open-rts) — 3D 跳过
- [GDQuest Open RPG Tutorial](https://www.gdquest.com/) — 同源官方教程
- [Dialogic 文档](https://github.com/dialogic-godot/dialogic) — `start_timeline` + `timeline_ended` 模式
- [Godot 官方 TileMapLayer 文档](https://docs.godotengine.org/en/stable/tutorials/2d/using_tilemaps.html)
- [Godot 官方 Camera2D 文档](https://docs.godotengine.org/en/stable/tutorials/2d/2d_transforms.html)

---

*本文档基于 4 个 cloned 项目的实际源码阅读（2026-07-14）。所有引用的文件路径和行号都是真实可查的。BattleBlitz M2 可以直接按"行动建议"小节抄作业。*