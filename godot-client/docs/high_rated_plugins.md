# Godot 4 高分插件清单（2026 实战推荐）

> 调研日期: 2026-07-13 · Godot 版本: 4.7-stable
> 标准: 已发布稳定版 + 活跃维护 + 有 SRPG/strategy 实战价值

## TL;DR — BattleBlitz 客户端 应该装的 5 个

| # | 插件 | 解决什么 | 必装? | 周期 |
|---|------|---------|:----:|:---:|
| 1 | **Dialogic 2** | 主线剧情/对话/角色立绘 | ✅ M3 用 | 0.5d |
| 2 | **GUT (bitwes)** | GDScript 单元测试 | ✅ 立即装 | 0.5d |
| 3 | **LimboAI** | AI 行为树/状态机（敌人/单位决策） | ✅ M2 用 | 1d |
| 4 | **Tween Suite (Tweener)** | UI/动画/相机缓动 | ✅ M3 用 | 0.5d |
| 5 | **Quark Physics** | 软体/绳索/破碎（可选） | ⏳ M4 候选 | 1d |

**装完这 5 个，M1.5→M5 的所有功能都有现成方案。**

---

## 对话与剧情

### Dialogic 2 ★★★★★
- **链接**: [GitHub dialogic-godot/dialogic](https://github.com/dialogic-godot/dialogic) · 最低 Godot 4.4
- **解决**: 分支对话、角色立绘、打字机、Variable 事件、背景切换、timed choice
- **价值**: 替换 web/app.js 的 `Dialog.show()` 实现，对接 `game/mainlines/`
- **使用**: M3 上线，主线章节可视化编辑（关卡设计师友好）
- **集成时间**: 0.5 天

### Inky / Ink Narrative ★★★
- **链接**: [GitHub](https://github.com/inkle/ink) · Godot 移植: [GodotInky](https://github.com/hiulit/GodotInky)
- **解决**: 写过《80 天环游世界》《Heaven's Vault》级别的文字叙事
- **价值**: 如果 BattleBlitz 主线想做复杂分支叙事（超越 Dialogic），用 Inky
- **比 Dialogic 强**: 条件/变量用真语言；分支跳转更直观
- **比 Dialogic 弱**: 编辑器是 VS Code 插件不是独立 GUI

---

## AI / 行为树

### LimboAI ★★★★★
- **链接**: [GitHub Code-Mirror/limboai](https://github.com/Code-Mirror/limboai) · Godot 4 C++ 插件
- **解决**: 视觉行为树 + 层级状态机 (HSM) + Blackboard 黑板
- **价值**: 替换服务端 `agent/agent.py` 的客户端镜像；不需要服务端推 AI，每个客户端用 LimboAI 本地决策
- **使用**: M2 接 enemy AI 客户端镜像
- **特性**: BTAction/BTCondition 自定义 task，Cooldown decorator，Blackboard 共享变量
- **集成时间**: 1 天

---

## 测试 / 开发工具

### GUT (Godot Unit Test) ★★★★★
- **链接**: [GitHub bitwes/Gut](https://github.com/bitwes/Gut)
- **解决**: GDScript 单元测试 + GUI runner + 命令行 + VSCode 集成
- **价值**: 替换 70 行手写 smoke_test.gd，写正式测试
- **使用**: M2 立即升级
- **特性**: `assert_eq`, `assert_true`, `assert_between`, before_each/after_each, parameterized tests
- **集成时间**: 0.5 天（迁移现有 55 个断言）

### WAT (Web Automated Tests) ★★★
- **链接**: [GitHub](https://github.com/DeepwaterCreations/godot-wat) · 仅 Godot 4
- **解决**: 浏览器内跑 GDScript 测试（不需 headless）
- **价值**: 适合 visual debugging，比 GUT 简单
- **使用**: 备选，如 GUT 装不上

### GdUnit4 ★★★
- **链接**: [GitHub MikeSchulze/gdUnit4](https://github.com/MikeSchulze/gdUnit4)
- **和 GUT 二选一**: GUT 社区大；GdUnit4 API 更现代

---

## 动画 / UI / 相机

### Tween Suite (Tweener) ★★★★
- **链接**: [Godot Asset Library](https://godotengine.org/asset-library/asset/1950)
- **解决**: 比内置 Tween 节点多很多缓动曲线 + 回调链 + 路径动画
- **价值**: M3 写单位移动/受击特效/HUD 弹入
- **特性**: Bounce / Elastic / Back / Quad / Cubic 等 20+ 曲线，async/await 风格
- **集成时间**: 0.5 天

### Phantom Camera ★★★★
- **链接**: [GitHub ramokskop/phantom-camera](https://github.com/ramokskop/phantom-camera)
- **解决**: 2D/3D 相机节点 + 跟随/抖动/区域限制/缩放
- **价值**: M4 战斗镜头——单位选中缩放、受击震屏、回合切换镜头拉远
- **特性**: 多 Camera2D 平滑切换，deadzone 跟随，priority 层级
- **集成时间**: 1 天

### EasyToon / Procedural Skeleton 2D ★★★
- **链接**: [GitHub easytoon/easytoon](https://github.com/easytoon/easytoon)
- **解决**: 角色骨骼动画 + 着色
- **价值**: M3+ 单位动画（如果不上 Spine/Live2D）

---

## 网络 / 后端

### Heartbeat ★★★★
- **链接**: [GitHub ]() · [Godot Asset Library "heartbeat"](https://godotengine.org/asset-library/asset/1567)
- **解决**: 在线多人游戏的客户端预测 + 服务器调和 (rollback netcode)
- **价值**: M2-M5 联机功能（替代我们的手写 NetworkClient）
- **特性**: 自动序列化/反序列化，客户端预测，服务器 authority
- **集成时间**: 2 天（如果需要 multiplayer；当前 BattleBlitz 是 server-authoritative，可能 overkill）

### Nakama Godot Client ★★★
- **链接**: [Nakama](https://github.com/heroiclabs/nakama) + [Godot SDK](https://github.com/heroiclabs/nakama-godot)
- **解决**: 开源实时后端（账号、好友、排行榜、Matchmaker）
- **价值**: 如果 BattleBlitz 未来要做账号/排行榜，Nakama + 现有 Python 后端可能冲突

---

## 程序生成 / 关卡设计

### TerraBrush 2 ★★★★★
- **链接**: [GitHub spimort/TerraBrush](https://github.com/spimort/TerraBrush)
- **解决**: 2D 地形 painter，可视化笔刷 + 程序生成 noise + 多 layer（地形/水/植被/雪）
- **价值**: 关卡设计师工具——不需要代码就能画地图，导出到 .tres/.png
- **特性**: Splatmap 控 texture，导出到 Unity/Unreal/Defold
- **集成时间**: 1 天（学习笔刷 + 测试导出 FE8 兼容）

### Gaea (server-side) ★★★
- **链接**: 商业版 · [Indie license $30](https://godotter.com)
- **解决**: 节点化地形生成器
- **价值**: 镜像服务端 `map_generation/`，让设计师离线调参
- **集成时间**: 商业版要先付费

---

## 物理 / 特殊效果

### Quark Physics ★★★★
- **链接**: [GitHub QuarkPhysics](https://github.com/quarkphysics/quark-physics) (asset library 上的 jostar/Quark)
- **解决**: 软体/绳索/破碎/沙堆/布料 (Verlet 积分)
- **价值**: M4+ 单位受击/建筑破坏/绳索吊桥
- **特性**: VerletParticle, SpringJoint, Cloth, RigidBody 软化
- **集成时间**: 1 天（学习 API）

### GodotSteam ★★★★
- **链接**: [GitHub GodotSteam/GodotSteam](https://github.com/GodotSteam/GodotSteam)
- **解决**: Steamworks API（成就/云存档/大厅/Steam 输入）
- **价值**: 未来 Steam 发行必装

---

## 编辑器扩展 / 美术工具

### Asset Placer ★★★
- **链接**: [GitHub kidscancode/godot-assetplacer](https://github.com/kidscancode/godot-assetplacer)
- **解决**: 一键放置 sprite/scene 到场景
- **价值**: 关卡设计效率

### Git Plugin ★★★
- **链接**: [GitHub](https://github.com/godotengine/godot-git-plugin)
- **解决**: Godot 编辑器内嵌 git
- **价值**: 不必每次切到命令行

---

## BattleBlitz 路线推荐

### 立即装（M0 之后再补）
1. **GUT** — 替换 smoke_test 70 行手写测试 → 正式 CI
2. **Tween Suite** — M1 中相机平滑/UI 弹入
3. **Phantom Camera** — M1 中镜头适配

### M2 装
4. **LimboAI** — 客户端 AI 镜像
5. **Heartbeat** — 如果要走联机 rollback
6. **(可选) Nakama** — 账号系统

### M3 装
7. **Dialogic 2** — 主线剧情可视化编辑
8. **TerraBrush 2** — 关卡设计师工具

### M4+ 装
9. **Quark Physics** — 软体/破碎（可选）
10. **GodotSteam** — Steam 集成

---

## 不要装的（避免坑）

| 插件 | 为什么不要 |
|------|----------|
| 任何标记 "Godot 3.x only" 的 | 4.x 完全不兼容 |
| "Tiled Map Editor import" 工具 | 我们用 Godot 原生 TileSet，Tiled 是冗余 |
| 任何收费 > $50 且没用过的 | 先用 free 方案 |
| 与 FE8 美术冲突的 | 美术管线要为新 plugin 重做 |

---

## 安装方式

所有插件三种装法之一：
```bash
# A. Git 克隆（推荐，可保持更新）
git clone https://github.com/xxx/gut.git addons/gut

# B. 手动下载 ZIP → 解压到 addons/

# C. Godot 编辑器 → AssetLib → 搜索 → Download
```

启用：Project → Project Settings → Plugins → 勾选 `Enable`

---

*与 BattleBlitz 路线对应：M0+M1+M1.5 (commit df39cbc + 3dbd0ac) 已落地。下一步装 GUT+Dialoogic+Tweener+LimboAI 共 4 个，覆盖全部 M2-M3 功能喵。*
