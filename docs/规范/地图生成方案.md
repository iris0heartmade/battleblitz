# 随机地图生成策略 - 实现计划

**创建日期**：2026-07-04  
**优先级**：P1  
**预计工作量**：3-5 天  
**依赖文档**：`docs/superpowers/specs/2026-07-01-random-map-generation-spec.md`（592 行）

---

## 📋 项目概述

重构 BattleBlitz 的随机地图生成器，从当前的简单随机生成升级为**基于规则的过程化生成系统**，确保生成的地图：

1. **公平性**：所有玩家起始位置对称等价
2. **可玩性**：城堡间有路径，地形分布合理
3. **多样性**：每次生成不同，但符合生态特征
4. **美观性**：地形成片、河流连贯、布局自然

---

## 🎯 核心目标

### 当前问题
- 现有生成器（`game_logic.py:generate_map()`）过于简单，只是随机填充
- 缺少地形簇、河流连贯性、对称性保证
- 城堡位置固定，缺少变化
- 没有利用 `MAP_STYLES` 配置的多样化权重

### 目标成果
- 5 种地图风格（草地/雪地/沙漠/小城/城堡内部）
- 地形成片生成（森林簇、山脉带）
- 河流网络算法（连贯流动，不断头）
- 道路网络连接关键建筑
- 玩家城堡旋转对称布局（2/4 人地图）

---

## 🗂️ 实现分解（5 个阶段）

### 阶段 1：架构重构（0.5 天）

**目标**：建立清晰的生成器架构，分离关注点

#### 任务
1. **创建新模块** `game/app/map_generation/`
   - `__init__.py` - 导出主入口
   - `generator.py` - 主生成器类 `MapGenerator`
   - `terrain_clusters.py` - 地形簇生成（森林、山地）
   - `river_network.py` - 河流网络生成
   - `road_network.py` - 道路网络生成
   - `castle_layout.py` - 城堡结构生成
   - `symmetry.py` - 对称性工具函数

2. **设计生成器接口**
```python
class MapGenerator:
    def __init__(self, 
                 size: int = 15,
                 player_count: int = 4,
                 style: str = "grass_outer",
                 seed: Optional[int] = None):
        """初始化生成器"""
        
    def generate(self) -> List[List[str]]:
        """生成地图，返回 size×size 的地形网格"""
        
    def get_castle_positions(self) -> List[Tuple[int, int]]:
        """返回各玩家城堡位置（按座位号顺序）"""
```

3. **保持向后兼容**
   - 保留 `game_logic.py:generate_map()` 作为包装器
   - 内部调用新的 `MapGenerator`

**输出**：模块结构 + 接口定义

---

### 阶段 2：基础地形生成（1 天）

**目标**：实现带权重的地形填充 + 城堡安全区

#### 任务

1. **权重随机生成器**
```python
def fill_base_terrain(grid: Grid, style: str, rng: Random) -> None:
    """
    使用 MAP_STYLES[style]["weights"] 填充地图
    - 避开城堡安全区（2 格半径）
    - 使用加权随机选择地形
    """
```

2. **城堡位置计算**
```python
def calculate_castle_positions(size: int, player_count: int) -> List[Pos]:
    """
    计算城堡位置（旋转对称）
    - 2 人：对角（左上 vs 右下）
    - 3 人：三角布局（120° 间隔）
    - 4 人：四角布局（90° 间隔）
    """
```

3. **安全区清理**
```python
def clear_safe_zones(grid: Grid, castles: List[Pos], radius: int = 2) -> None:
    """
    将城堡周围 radius 格内强制设为 plain
    """
```

**输出**：基础地形 + 城堡位置

---

### 阶段 3：地形簇生成（1 天）

**目标**：森林、山地成片生成，避免孤立单格

#### 任务

1. **森林簇算法**（Flood Fill + 噪声）
```python
def generate_forest_clusters(grid: Grid, 
                              target_ratio: float = 0.18,
                              cluster_size: Tuple[int, int] = (2, 8)) -> None:
    """
    - 随机选择种子点
    - 以种子为中心，向周围扩散 2-8 格
    - 使用 Perlin 噪声或 BFS 控制形状
    - 达到目标比例后停止
    """
```

2. **山地簇算法**（类似森林，但更紧凑）
```python
def generate_mountain_clusters(grid: Grid,
                                target_ratio: float = 0.10,
                                cluster_size: Tuple[int, int] = (2, 6)) -> None:
    """
    - 山地簇更紧凑（2-6 格）
    - 避免阻断主要路径（检查连通性）
    """
```

3. **连通性检查**
```python
def verify_connectivity(grid: Grid, castles: List[Pos]) -> bool:
    """
    BFS 检查所有城堡之间是否连通
    - 如果不连通，回退并重新生成
    """
```

**输出**：自然成片的森林、山地

---

### 阶段 4：河流 & 道路网络（1.5 天）

**目标**：河流连贯流动，道路连接关键建筑

#### 任务

1. **河流网络生成**（Random Walk + 连接）
```python
def generate_river_network(grid: Grid, 
                            target_ratio: float = 0.10,
                            seed_count: int = 2) -> None:
    """
    河流生成算法（两阶段）：
    
    阶段 1：主干生成
    - 从地图边缘选择 seed_count 个起点
    - 使用 Random Walk 向地图中心延伸
    - 每步有 70% 概率继续前进，30% 分叉
    - 遇到另一条河流时合并
    
    阶段 2：连通性修复
    - 扫描所有孤立的 1-2 格河流
    - 连接到最近的河流主干
    - 删除完全孤立的河流片段
    
    约束：
    - 不穿过城堡安全区
    - 不与道路重叠
    - 河流宽度为 1 格（不生成湖泊）
    """
```

2. **道路网络生成**（A* 连接）
```python
def generate_road_network(grid: Grid, castles: List[Pos]) -> None:
    """
    道路生成算法：
    
    1. 找到所有关键建筑（castles + villages + barracks）
    2. 使用 A* 算法连接：
       - 每个 castle ↔ 最近的 village
       - 每个 castle ↔ 最近的 barracks
       - 跨越 castle 的对角线路径
    3. 道路不穿过河流、山地
    4. 道路优先走平地（移动代价低）
    
    结果：形成放射状 + 环形的道路网
    """
```

3. **村庄/兵营位置生成**
```python
def place_buildings(grid: Grid, 
                     castles: List[Pos],
                     village_count: int = 4,
                     barracks_count: int = 2) -> None:
    """
    - 在远离城堡的区域放置村庄/兵营
    - 村庄间距至少 3 格
    - 避开河流、山地、森林
    - 确保每个玩家附近至少有 1 个村庄
    """
```

**输出**：连贯河流 + 道路网络

---

### 阶段 5：城堡内部结构（1 天）

**目标**：支持 `castle_internal` 模式，生成完整城堡室内地图

#### 任务

1. **城堡内部生成器**
```python
def generate_castle_internal(size: int, 
                              player_count: int,
                              style_config: Dict) -> Grid:
    """
    城堡内部模式（整张地图都是城堡内部）：
    
    1. 基础填充：80% castle_floor + 20% castle_wall
    2. 为每个玩家生成一个"房间"：
       - 中心放置 castle_throne（王座）
       - 周围 2x2 放置 castle_door（门）
       - 附近放置 castle_vault（宝库）
       - 附近放置 castle_stairs（楼梯）
    3. 使用 BSP（二叉空间分割）算法分割房间
    4. 走廊连接各房间
    5. 确保所有房间连通
    """
```

2. **BSP 房间分割**
```python
def bsp_partition(rect: Rect, min_size: int = 5, depth: int = 3) -> List[Rect]:
    """
    递归二分地图，生成多个房间
    - depth=3 → 最多 8 个房间
    - 每个房间最小 5x5
    """
```

3. **走廊生成**
```python
def generate_corridors(rooms: List[Rect]) -> List[Line]:
    """
    连接相邻房间，生成 L 型走廊
    """
```

**输出**：完整的城堡内部地图

---

## 🧪 测试与验证

### 单元测试（每阶段）

```python
# tests/test_map_generation.py

def test_castle_positions_2p():
    """2 人地图城堡位置对角"""
    
def test_castle_positions_4p():
    """4 人地图城堡位置四角"""

def test_connectivity():
    """所有城堡之间连通"""
    
def test_forest_cluster_size():
    """森林簇 2-8 格，孤立森林 ≤5%"""
    
def test_river_connectivity():
    """河流不断头，孤立河流 ≤1 格"""
    
def test_safe_zone_clear():
    """城堡安全区内无障碍"""
    
def test_terrain_ratio():
    """地形比例符合 MAP_STYLES 配置"""
```

### 集成测试

```python
def test_generate_all_styles():
    """生成所有 5 种风格的地图，验证可玩性"""
    for style in MAP_STYLES.keys():
        gen = MapGenerator(size=15, player_count=4, style=style)
        grid = gen.generate()
        assert verify_playable(grid)
```

### 手动验证

- 生成 10 张地图，目视检查美观性
- 用 matplotlib 可视化地形分布
- 检查对称性（2/4 人地图镜像）

---

## 📦 交付物

| 阶段 | 文件 | 说明 |
|------|------|------|
| 1 | `map_generation/__init__.py` | 模块入口 |
| 1 | `map_generation/generator.py` | 主生成器类 |
| 2 | `map_generation/generator.py` | 基础地形填充 |
| 3 | `map_generation/terrain_clusters.py` | 森林、山地簇 |
| 4 | `map_generation/river_network.py` | 河流生成 |
| 4 | `map_generation/road_network.py` | 道路生成 |
| 5 | `map_generation/castle_layout.py` | 城堡内部 |
| 全 | `tests/test_map_generation.py` | 单元测试 |
| 全 | `tools/visualize_map.py` | 可视化工具 |

---

## 🚀 实施建议

### 第 1 天：架构 + 基础地形
- 上午：创建模块结构，定义接口
- 下午：实现基础地形填充 + 城堡位置

### 第 2 天：地形簇
- 上午：实现森林簇算法
- 下午：实现山地簇 + 连通性检查

### 第 3 天：河流网络
- 全天：实现河流生成 + 连通性修复

### 第 4 天：道路 + 建筑
- 上午：实现道路网络（A*）
- 下午：放置村庄/兵营 + 整合测试

### 第 5 天：城堡内部 + 收尾
- 上午：实现城堡内部生成（BSP）
- 下午：单元测试 + 文档 + 可视化工具

---

## 🔧 技术要点

### 算法选择

| 需求 | 算法 | 理由 |
|------|------|------|
| 地形簇 | Flood Fill + 随机种子 | 简单高效，形状自然 |
| 河流 | Random Walk + 连接 | 模拟自然河流流向 |
| 道路 | A* 最短路径 | 高效连接关键点 |
| 城堡内部 | BSP（二叉空间分割） | 生成对称房间 |
| 对称性 | 旋转变换矩阵 | 数学精确 |
| 连通性 | BFS | 快速验证可达性 |

### 性能优化

- 使用 `numpy` 加速网格操作（如果可用）
- 缓存城堡位置计算结果
- 限制河流/道路迭代次数（避免死循环）
- 预计算地形权重累积分布（加速随机抽样）

### 扩展性考虑

- 支持自定义权重配置
- 支持导入外部噪声图（Perlin noise）
- 支持手动编辑生成后的地图
- 支持保存/加载种子（可复现地图）

---

## 📝 配置示例

生成器配置（融入现有 `MAP_STYLES`）：

```python
# config.py

MAP_STYLES = {
    "grass_outer": {
        "display_cn": "草地 外圈",
        "biome": "grass",
        "mode": "single_hq",
        "safe_zone_radius": 2,
        "weights": {
            TERRAIN_PLAIN: 55,
            TERRAIN_FOREST: 14,
            TERRAIN_MOUNTAIN: 8,
            TERRAIN_RIVER: 10,
            TERRAIN_VILLAGE: 5,
            TERRAIN_BARRACKS: 2,
            TERRAIN_ROAD: 5,
        },
        # 新增：簇生成参数
        "cluster_config": {
            "forest": {"size_range": (2, 8), "isolation_max": 0.05},
            "mountain": {"size_range": (2, 6), "isolation_max": 0.05},
        },
        # 新增：河流参数
        "river_config": {
            "seed_count": 2,
            "min_length": 5,
            "branch_probability": 0.3,
        },
        # 新增：道路参数
        "road_config": {
            "connect_all_castles": True,
            "connect_villages": True,
            "connect_barracks": True,
        },
    },
    # ... 其他风格
}
```

---

## ⚠️ 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| 生成算法不收敛（死循环） | 高 | 设置迭代次数上限，超时后回退 |
| 地图不连通 | 高 | BFS 验证，失败后重新生成 |
| 地形比例失衡 | 中 | 生成后统计，偏差 >10% 重试 |
| 性能问题（大地图） | 中 | 使用 numpy，或限制最大尺寸 |
| 美观性主观 | 低 | 人工评审 + 可调参数 |

---

## 📚 参考资料

- 规格文档：`docs/superpowers/specs/2026-07-01-random-map-generation-spec.md`
- 当前实现：`game/app/game_logic.py:generate_map()`
- 配置：`game/app/config.py:MAP_STYLES`
- 类似项目：
  - [Advance Wars map generator](https://github.com/topics/advance-wars)
  - [Roguelike dungeon generation](http://www.roguebasin.com/index.php/Articles)
  - [Perlin noise terrain](https://adrianb.io/2014/08/09/perlinnoise.html)

---

**最后更新**：2026-07-04  
**负责人**：待定  
**审核人**：待定
