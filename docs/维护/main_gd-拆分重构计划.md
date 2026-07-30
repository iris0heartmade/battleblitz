# main.gd 拆分重构计划

> 状态:**待执行**(计划文档,非立即执行)
> 创建:2026-07-23
> 目标文件:`godot-client/scripts/main.gd`(8373 行)

---

## 1. 背景与问题

`main.gd` 是 Godot 客户端顶层 UI 状态机,`extends Node` 挂在场景根上。经过多轮(V2 第 1~7 轮)功能追加,已膨胀为**上帝 Node**:

| 指标 | 数值 | 诊断 |
|------|------|------|
| 总行数 | **8373** | 🔴 单文件顶整个 UI 层 |
| 函数数 | 452 | 职责严重堆积 |
| 成员变量 | 327 | 状态全裸露在同一命名空间 |
| signal 数 | **0** | 🔴 无信号解耦,全靠直接调用/穿参 |

**核心症状:同一功能域的函数按"追加轮次"散布,不成块。**
例:lobby 域 102 个函数散落在 3418→6346 行之间,与 editor / theme / mainline 交错。

**风险:**
- 任何改动都要在 8000 行里定位,回归面不可控。
- Godot headless 解析慢,`class_name` 跨引用易撞 Parse Error(见 memory `godot-class_name-headless-cache`)。
- 状态变量全局共享,move/attack/skill/recruit 4 套模式机的 `_pending_*` 互相污染风险高。

---

## 2. 职责分域(现状盘点)

按函数名/变量前缀 + 行号归类,8373 行可切成 ~13 个域:

| 功能域 | func 数 | 成员 var | 大致行段 | 说明 |
|--------|--------:|--------:|---------|------|
| 初始化 / `_ready` / dev hook | ~15 | menu/connecting/board | 1–766 | 节点绑定、`BB_AUTO_PLAY` 自动开局 |
| View 切换调度 | ~12 | view 状态 | 767–1513 | `_show_view` 顶层状态机 |
| GameState → HUD 渲染 | ~20 | turn/hud/battle | 1514–1858 | |
| Event-delta handlers | ~25 | — | 1859–2461 | WS 事件增量应用 |
| 战斗行动状态机 | ~90 | `_move`/`_attack`/`_skill`/`_pending`/`_recruit` | 2462+ 散布 | move/attack/skill/招募 4 套模式机 |
| **Lobby 准房间** | **102** | 39 | 3418–6346 | 🔴 最大块:座位/AI/join/room/开局 |
| 地图编辑器 | 47 | 36 | 3681–4505 | editor 绘制/工具 |
| Prepare 备战 | 37 | — | 6669–7372 | 招募/出战编队 |
| Mainline 主线 | 31 | 36 | 1341–7564 | `ml_` 剧情/引擎交互 |
| Settings / Pause | 15 | 22 | 2485–3116 | 设置 + 暂停面板 |
| Dialog / Tutorial / 结算 | 20 | 13 | 3117–3428 | |
| GBA 火纹主题注入 / font | ~14 | — | 3429–3677 | theme pill 样式 |
| ActionBubble + ConfirmDialog | ~12 | — | 7601–8373 | 通用弹窗 helper |

> 行段为"首现~末现"范围,实际交错;迁移时以**函数名前缀**为准,不以行段为准。

---

## 3. 目标结构

采用 Godot 惯用的**组件化 Node**:每个域抽成挂在对应 UI 子节点上的组件脚本,`main.gd` 退化为纯 view 调度器。

```
godot-client/scripts/
  main.gd                    # 只留 _ready + _show_view 调度        (目标 ~400 行)
  ui/
    lobby_controller.gd      # 🔴 优先:102 func,座位/AI/join/room
    editor_controller.gd     # 地图编辑器
    prepare_controller.gd    # 备战编队/招募
    settings_pause.gd        # 设置 + 暂停面板
    dialog_tutorial.gd       # 对话/教程/结算弹窗
    hud_renderer.gd          # GameState→HUD + 火纹主题注入
    action_bubble.gd         # 行动气泡 + ConfirmDialog(通用)
  mainline/
    mainline_controller.gd   # ml_ 主线交互(mainline/ 目录已存在)
  core/
    battle_action_fsm.gd     # move/attack/skill/recruit 状态机
    event_delta.gd           # WS event-delta handlers
```

**设计原则:**
1. 每个组件 `extends Node`,挂到它管理的 UI 子节点下(如 `$Lobby` 挂 `lobby_controller.gd`)。
2. 组件间**用 signal 解耦**(当前 0 signal 是重症):
   例 lobby「点开始」`emit` 信号 → main 接住 → `_show_view("game")`。
3. 共享的 NetworkClient / GameState 走 autoload,组件直接引用,**不穿 main 传参**。
4. 组件引用彼此用 `const X = preload("res://...")`,**禁用 `class_name`**(headless 撞 Parse Error)。

---

## 4. 执行顺序(逐域搬,每域独立可验证)

按"收益 / 边界清晰度"排序,一次搬一个域,搬完立即回归再进下一个:

| 阶段 | 域 | 预计砍行 | 理由 |
|:----:|-----|--------:|------|
| P1 | **Lobby** → `lobby_controller.gd` | ~2500–3000 | 最大、边界最清晰,一战砍掉 1/3 |
| P2 | Editor → `editor_controller.gd` | ~800 | 独立子系统,与游戏主流程弱耦合 |
| P3 | Prepare → `prepare_controller.gd` | ~700 | 独立 view |
| P4 | Settings/Pause + Dialog/Tutorial | ~900 | 通用面板,可合可分 |
| P5 | 战斗行动状态机 → `core/battle_action_fsm.gd` | ~1200 | 需先理清 `_pending_*` 共享状态 |
| P6 | Event-delta + HUD + Theme | ~1000 | 渲染层收尾 |
| P7 | Mainline → `mainline/mainline_controller.gd` | ~600 | 归位到已有 mainline 目录 |

> 完成后 `main.gd` 目标 ≤ 500 行,仅保留 `_ready` / `_show_view` / 组件装配。

**每阶段标准流程:**
1. 新建组件脚本,搬入该域全部 func + 相关成员 var。
2. 把域内跨调用改成组件内调用;跨域调用改成 signal / autoload 引用。
3. 在场景里把组件挂到对应节点,接线信号。
4. 跑 `godot-client/tools/smoke_test.gd` 回归;必要时跑相关 `chapter_*_verify_*.gd`。
5. 绿灯后再进下一阶段,单独提交。

---

## 5. 风险与踩坑清单(结合项目 memory)

- **禁用 `class_name` 跨引用** → 用 `const X = preload(...)`(memory: `godot-class_name-headless-cache`)。
- **NetworkClient callback 必须 `(body, code)` 两参** → 搬 handler 时别漏 `_code`,否则 `flow_screenshot` 卡死(memory: `callback-signature-match`)。
- **autoload 接线方向**:跨 autoload 信号从"后加载方"接线(GameState ← NetworkClient)(memory: `autoload-order-ws-wiring`)。
- **服务端权威**:搬战斗行动状态机时,client 只做 UI/请求,别把 damage/规则逻辑重写进来(memory: `server-authority-no-duplicate-logic`)。
- **Unicode lookalike**:Edit 对不上时用 `cat -A` 看字节,`->`(U+2192)/`—`(U+2014)会被渲染成 ASCII(memory: `unicode-lookalike-chars`)。
- **`_pending_*` 共享状态**:P5 拆状态机前,先确认 move/attack/skill 的 pending 变量没有跨模式复用,否则拆开会引入状态泄漏。

---

## 6. 验收标准

- [ ] `main.gd` ≤ 500 行,仅含 `_ready` / view 调度 / 组件装配。
- [ ] 每个新组件 ≤ ~800 行,单一职责。
- [ ] 组件间零直接跨调用,全部走 signal / autoload。
- [ ] 无 `class_name`,全部 `preload` const 引用。
- [ ] `smoke_test.gd` 全绿;主线 `chapter_*_verify_*.gd` 回归通过。
- [ ] 每阶段一个独立 commit,可单独回滚。

---

## 附:如何复现本次盘点

```bash
f=godot-client/scripts/main.gd
wc -l "$f"                                        # 总行数
grep -cE "^\s*func " "$f"                         # 函数数
grep -cE "^(var|const|@onready|@export) " "$f"    # 成员变量数
# 按域统计函数:
for kw in lobby editor prepare mainline save settings pause dialog unit attack ai_ seat; do
  printf "%-10s %s\n" "$kw" "$(grep -cE "^\s*func .*$kw" "$f")"
done
```
