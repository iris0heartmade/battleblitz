# BattleBlitz Godot Client Changelog

## [未发布] - 2026-11-10

### 新增
- 正式地图编辑器加入−5～+5高度绘制、键盘选格、遮挡格修改与撤销重做；高度可保存、读回并带入实际对局，旧地图与旧快照兼容。
- 正式高差地图支持四方阵营、队伍徽标、英雄立绘、血量、移动力、士气、异常状态、占领进度及城堡内部地貌。
- 高差地图Demo接入原后端基础战斗：支持同机双人选人、权威移动范围、逐格移动、伤害与反击预览、确认攻击、生命显示、待机、回合交接、阵亡移除和胜负结算。
- 新增只读移动预览接口，复用原寻路、占位、移动力及兵种地形规则；新增对应接口测试。
- 启动器可自动运行独立试战服务和独立数据库，退出试战可恢复原编辑地图；断线时冻结战斗操作，重新同步后恢复。
- 将「2人标准图」完整移植到独立高差Demo：保留225格布局、2座城堡、4个村庄、2个佣兵站和48格森林，加入红蓝双方各5个原图预设单位；建筑与单位独立于地形，支持选中查看与升降同步。
- 新增标准图/高度试验场切换、红蓝阵营定位、完整地貌与单位存档；旧版高度图仍可加载。
- 新增标准图专项验证：三档GPU各289项通过，无窗口284项通过；逐格核对225格、逐人核对原图10人阵容，并实际测试建筑点击与驻军显隐。
- 新增8张非像素手绘地形资源，四种地形各自拥有顶面与侧面；草地根土、岩壁、沙岩、湿岩按地形切换，并增加顶部收边。
- 新增高差地图自由环绕：右键拖动改变方位/俯角，Q/E或按钮平滑左右转动45°，显示实时角度；新增方向键选格、聚焦选格与透视选中，方便检查被高地遮挡的位置。
- 新增可独立启动的12×12高差地图Demo：支持每格-5至+5高度、相邻10级悬崖、顶面选格、地形切换、撤销重做、保存加载、相机平移缩放旋转与现有角色展示；旧地图系统保留。
- 新增根目录 `高差地图Demo.bat` 入口、外部比例配置、设计文档与专项验收记录。手绘材质与近景迭代后GPU三档窗口各85项检查通过，无窗口82项检查通过，原有616项冒烟测试通过。
- 新增等距高度地图来源复核补充，列出官方 2D、2.5D、GridMap 和开源战棋模板，区分资料核对与实机验证。

### 变更
- 按反馈将战斗房间/大厅地图预览恢复为二维俯视部署图，继续从同一份地图JSON展示地形、建筑及预设单位；正式战场与编辑器保留高差3D表现。
- “开始游戏”入口接入统一启动器：自动查找引擎、校验服务兼容性，启动正式服务前备份原数据库；退出后仅关闭本次自行启动的服务。
- 正式战场、主线与自由对战、地图编辑器、大厅地图预览统一使用高差3D地图，原有战斗、AI、招募与存档流程继续使用；手绘素材与共享绘制代码迁入正式资源目录。
- 将旧地图呈现方式的源码字符串检查改为实际运行3D棋盘的行为验证，并迁移相机、菜单切换与移动反馈测试。
- 将高差Demo默认镜头拉近为局部游玩视野，初始取景围绕角色光标；方向键连续移动时镜头在安全区边缘平滑跟随，支持左键拖动平移，保留中键平移和右键旋转。
- 地形采用平滑纹理过滤与远近层级贴图，替换旧像素顶面与统一侧面；减弱网格描边，降低重复纹理排列感。旧地图资源保留。

### 修复
- 修复正式编辑器背景吞掉地图点击、空子类型导致地图构建中断、相邻村庄被误读为城堡子类型、快照刷新释放移动中单位等迁移兼容问题。
- 区分地图点击与左键拖动，避免拖动浏览时误提交单位移动；战斗中锁住地图编辑，避免画面与权威规则不一致。
- 修复隐藏单位后仍拦截后方建筑点击的问题；修复地图加载时JSON版本号数字类型差异导致读档被拒绝的问题；确保启动时光标与首个预设单位一致。
- 修复点击地图后键盘焦点仍停留在编辑按钮、导致方向键不能选格的问题；缩紧编辑面板以完整显示新增控制项；专项测试按进程隔离存档，避免多窗口验证争用临时文件。
- 补充说明此前地图预研的结论限制：3D 地形可复用 2D 角色图片与屏幕 UI；按高度设置绘制层级并不能保证所有遮挡正确；未核实的项目与历史断言不能作为立项依据。详见 `docs/路线/参考调研/2026-11-10-等距高度地图-来源复核补充.md`。

> 2026-10-06 补记：8/13 → 10/03 期间有 13 次提交（8 次功能/修复 + 5 次合并）此前未记入本文件，
> 现依据 `git log` 逐条回填，内容均可追溯到对应 commit hash。

## 2026-11-10 地图风格大改预研（等距 + 高度差）

### 新增
- 新增调研文档 `docs/路线/参考调研/2026-11-10-等距高度地块地图风格调研.md`，给出「45° 等距 + 方形地块 + 地块高度差」这一目标风格的完整技术路线对比、开源项目与资产清单、以及对现有代码的具体改动点定位。

### 说明（对老大的需求拆解）
- 需求里的三个特征不是一回事：**等距视角**和**方形地块**只是重新包装，真正解决「山脉在 2D 上难画」的是**地块高度差**——有了真实 elevation，山脉就是一叠高低不同的立方体，侧面落差由几何自动生成，不再靠手绘硬凑。
- 已核实：GBA 版《最终幻想战略版 Advance》本身**没有**高度差（平地），有高低地形的是 SFC/GBA《皇家骑士团》与 PS1《最终幻想战略版》（含 Jump 跳跃属性）。GBA 能跑出高低地形靠的是手工预渲染的立方体贴图 + 像素级遮挡排序，引擎层面并无原生支持。

### 结论
- **有成熟开源方案**，Godot 4 `TileMapLayer` 原生支持等距网格（Isometric / Diamond Down / 2:1 tile），高度用「按高度分层 + z_index + y_sort」模拟，是社区已验证的标准做法；已找到 4 个可参考的 Godot 等距开源项目与 3 套可用资产包。
- 推荐路线 A（2D 等距 + 分层高度），保留现有 2D 精灵 / UI / Python 后端；路线 B（3D GridMap + 正交相机）效果最好但等于重写客户端渲染层。
- 关键约束：**Godot 4 的 2D TileMap 没有原生的 per-cell elevation 字段**，高度必须靠分层或自研渲染器解决。
- 已定位现有代码的改动面：`scripts/core/map_metrics.gd`（正交坐标换算必须重写）、`scripts/core/tile_set_builder.gd`（TileShape + 换图集）、`scripts/core/map_loader.gd`（按高度分层写入）、`scripts/board/board.gd` 与 `board_camera.gd`（菱形包围盒的边界算法）。

### 下一步建议
- 先做 **Phase 0 隔离验证**（2-3 天）：在 `godot-client` 下开独立 demo 场景，导入等距资产，验证高度分层的遮挡排序、鼠标拾取、单位走格。**不要先动主工程**——高度差遮挡在 Godot 里有已知坑（Y-sort 单独用不够），不在隔离环境验证就改主工程，返工成本翻倍。

---

## 2026-11-10 推送 204 修复至远端 + 本地与远端文件全量对齐

### 变更
- 把本地 `master` 上此前未推送的修复提交 `483a94c`（给三个 204 删除接口显式声明「无响应体」）推送到 GitHub 远端 master。此后本地与远端 `master` 完全一致（远端 = `483a94c`），工作区全部受管文件与远端逐字节相同。

### 修复
- `删除自定义地图`、`删除存档`、`删除养成单位` 三个删除接口的装饰器补上 `response_model=None`，显式声明「本接口没有响应体」。接口对外行为完全不变（204 按 HTTP 规范本来就不带响应体），只是把语义写明确，不再依赖框架对返回注解的默认推断。

### 说明（对上一条记录的实测复核）
- 上一条记录写的是「FastAPI 从 0.115 起会把 `-> None` 误当成要返回数据」。本次用 FastAPI 0.138.0 + Python 3.13 逐个写法实测，结论需要更正：普通 `-> None`、字符串注解 `"None"`、以及不写返回注解，**都安全**（`response_model` 解析为 `None`）；**只有显式写成 `-> NoneType`（`types.NoneType`）才会触发 `Status code 204 must not have a response body` 断言**。全仓检索确认项目内没有任何 `NoneType` 写法。
- 因此这次改动属于「显式化 + 加固」，**不是修一个当前正在发生的崩溃**。另用 `git worktree` 检出远端 `812af3e` 实测，`import app.main` 成功、服务可正常启动，远端基线本身没有崩。
- 新增的回归测试仍然保留并有价值：它锁死了「以后新写的 204 接口必须显式声明无响应体」这条规则。

### 验证
- 逐文件校验：对远端 master 树的 **1102 个受管文件**逐一计算工作区实际内容哈希并与树的 blob SHA 比对，**不一致 0 个、缺失 0 个**。
- 后端全量测试：1199 项通过、16 项跳过、1 项预期失败、0 项失败。
- **Godot 客户端冒烟测试本次已实际执行**（Godot 4.7.stable）：`res://tools/smoke_test.tscn` → **616 项通过、0 项失败、PASS**。
- **Godot 端到端流程测试已实际执行**（后端跑在 `127.0.0.1:8000`）：`res://tools/entry_flow_e2e.tscn` → **PASS**，主线链路（开始章节 → 战前准备 → 开战 → 存档 → 剧情对话 → 棋盘就绪，225 格）与大厅链路（建房 → 加入 → 加 AI → 编队 → 开战 → 棋盘就绪）全部走通。
- 补充：`--headless --path godot-client --quit` 在**资源尚未导入**时会报一串「Failed loading resource」并连带触发 `main.gd` 的 `_main` 注入脚本报错。先跑一次 `--headless --path godot-client --import`（134 步，约 10 秒）建立导入缓存后，项目加载即零错误零告警。**这是环境初始化问题，不是代码缺陷**，但在全新克隆的机器上首次跑冒烟测试时必须先导入，否则会误判成失败。
- `git fsck` 零错误零告警。

## 2026-11-05 仓库同步收尾 + 本地分支对齐

### 变更
- 核对确认本地 `master` 与 GitHub 远端 `master` 完全对齐（远端基线 `812af3e`），工作区无残留改动。
- 清理两个远端已删除、本地却仍然留着的归档分支：`feat/p2.6-data-driven-initial-units`、`hero-mercenary-dual-track`。这两个分支的内容早已并入 master，删除后不丢任何代码。
- 把本地 `godot-map-port` 分支从旧的分叉状态重置到远端最新版本（`1b08d29`）。重置前已验证旧分支尖端是 `master` 的祖先，即提交内容全部包含在 master 中，不会丢失任何改动。
- 补齐本地 git 对象库中缺失的历史文件版本对象，仓库不再依赖「联网按需拉取历史文件」才能查看旧提交内容。
- 清理 partial clone 阶段残留的过期 commit-graph 缓存并重建，随后回收悬空对象；`git fsck` 现在零错误零告警。

### 验证
- 后端全量测试（同步后的代码）：**1199 项通过、16 项跳过、1 项预期失败、0 项失败**。
- 与上一条记录的「1192 通过 / 33 跳过」差异说明：本轮排除了 `tests/test_ws_gateway.py`（19 项，Windows 下 starlette TestClient 与 aiosqlite 线程泄漏会挂起，属环境限制）与 `tests/e2e/`，故跳过数由 33 降为 16、通过数由 1192 升为 1199。
- 跳过与预期失败全部是用例自身标注的「功能尚未实现」（观战者结束回合、地图王座布局接线、第 4/5 章难度修正等），非本次同步引入。
- Godot 客户端冒烟测试本次仍未执行：当前环境未安装 Godot 可执行文件，无法在本地跑起来。

## 2026-11-05 同步远端 master + 修复后端启动即崩溃

### 修复
- 修复「按 README 全新安装依赖后，后端一点就起不来」的问题：`删除自定义地图`、`删除存档`、`删除养成单位` 这三个「删除类」接口返回 204（无内容），但函数上写了 `-> None` 的返回注解，FastAPI 从 0.115 起会把 `None` 误当成「这个接口要返回数据」，于是直接断言失败。后果是**整个后端在导入阶段就崩**（不是单个接口报错，是服务根本起不来），玩家连主界面都打不开。
- 三个接口现在都显式声明「本接口没有返回内容」，接口对外行为跟以前一模一样（204 本来就不带数据），但后端恢复正常启动。

### 新增
- 新增回归测试《删除类接口 204 校验》：真实发出删除请求，确认状态码是 204、返回内容是空的、资源确实被删掉了；并额外加一条「全仓扫描」检查——以后不管谁新写一个 204 接口，只要忘了声明「无返回内容」，测试就会当场报错，不会再等到部署时才炸。

### 变更
- 同步 GitHub 远端 master 分支（提交号 `812af3e`）。
- 清理工作区里一批 2026-07 的旧版残留文件（其中 `mainline.py` 已被拆分包 `app/routes/mainline/` 取代，属重复旧代码），使本地工作区与远端 master 完全一致。

### 验证
- 后端全量测试：1192 项通过、33 项跳过、1 项预期失败（跳过与预期失败均为用例自身标注的「功能尚未实现」，非本次改动引入）。
- Godot 客户端冒烟测试本次**未执行**：当前环境未安装 Godot 可执行文件，无法在本地跑起来。

## 2026-10-03 合并遗留修复 + 冒烟测试 17 项失败全修（`2ed26f7` + `d2a162b`）

### 修复
- 修复地图编辑器面板在合并后被重新挂回主菜单 HUD 层的问题，恢复为独立 `EditorHud` 容器，避免编辑器工具面板污染主菜单。
- 修复合并后英雄注册表与指挥官效果模块的契约不一致（`anna` 英雄模板、`commanders/effects.py`）。
- 修复 Godot 冒烟测试里 17 项失败：根因是编辑器节点路径在 UI 改造后由 `EditorView/EditorPanel/*` 变为 `EditorView/EditorHud/EditorPanel/*`，测试断言与实际场景不同步。
- 补齐两张新增战斗 UI 资源（`battle_sidebar_drawer_refined_v3.png`、`top_battle_status_bar_refined_v3.png`）的 `.import` 配置。
- 清理工作区残留文件，`.gitignore` 补充忽略规则。

## 2026-09-28 战斗与战役界面响应式优化（`32adeb4`）

### 变更
- 战斗 HUD 与主线战役面板改为响应式布局：在 1280×720 紧凑屏折叠左翼并补偿字号，1600/1920 宽屏使用完整布局。
- 新增主线主题字号补偿逻辑（`mainline_theme.gd`）：极小窗口（≤1366）与宽屏（≥1600）字号 +1，中间段保留默认值，避免 1920 下视觉密度反而不敌 1280。
- 对话管理器（`dialog_manager.gd`）增强，剧情弹窗在不同分辨率下自适应。

## 2026-08-21 界面视觉评分提升到 9 分以上（`bfc94c6`）

### 新增
- 新增两张高精战斗 UI 资源：战斗侧栏抽屉、顶部战斗状态栏（refined_v3）。
- 新增《Godot UI 资产审美问卷》（`docs/validation/godot-ui-asset-aesthetic-questionnaire.md`），把"视觉好看"这种主观要求转成可执行的检查清单。

### 变更
- 主菜单与战斗 HUD 重新对齐视觉层次，主操作区权重提升。

## 2026-08-20 引入三分辨率强制验收评分卡（`2e27077`）

### 新增
- 新增《Godot UI 验收评分卡》（`docs/validation/godot-ui-scorecard.md`），把 UI 改动的完成标准从"能启动"升级为可重复的自动化门槛：
  - Godot 冒烟测试零失败；
  - `check_chinese_ui.py` 中文本地化扫描必须通过（白名单仅限按键、协议、数值等不可本地化术语）；
  - 1280×720 / 1600×900 / 1920×1080 三档分辨率，每档产出 11 张界面截图（共 33 张）；
  - 单张平均不低于 8.5/10，总平均不低于 8.5/10。
- 评分卡内固定了棋盘安全区、检视卡尺寸、行动菜单边距、席位卡最小高度等**硬性客观判据**，违反即不合格。

## 2026-08-19 中文本地化质量门禁（`6e3c946`）

### 修复
- 修复主菜单、主线控制器、大厅、存档、进行中等界面残留未本地化英文的问题。
- 收紧 `check_chinese_ui.py` 检查规则：不再允许屏蔽自然语言，只允许白名单内的按键名、协议名与数值。

## 2026-08-19 视觉评审工具加固（`c87af74`）

### 变更
- `ui_review_screenshot.gd` 增加失败重试与分辨率校验，避免截出灰屏或半渲染画面充当"通过"。

## 2026-08-19 冒烟测试 autoload 诊断修复（`a637224`）

### 修复
- 修复冒烟测试在 autoload 未完成初始化时报错并误判失败的问题。

## 2026-08-13 标题页按钮与子菜单背景修复

### 变更
- 将标题页可见游戏名统一为 “BIPOLAR”，避免把项目名 BattleBlitz 或旧名“战棋闪击”误显示成真实游戏名。
- 联机大厅、存档管理、进行中、主线存档等子菜单复用标题图作为暗化背景，子菜单视觉与标题页保持同一套风格。
- 标题页底部辅助按钮改为 4 列网格布局，避免按钮数量和文案变化后挤出安全区域。

### 修复
- 修复标题页底部按钮在近期改动后再次贴边/超出的问题。
- 修复联机大厅截图工具仍调用旧入口、导致误截标题页或灰屏的问题；现在会进入真实大厅子页面后再截图。
- 修复进行中截图脚本调用已移除的活动对局接口导致超时残留 Godot 进程的问题；现在脚本带自我超时并按当前“进行中只管理存档/中断”的设计截图。

## 2026-08-13 联机大厅入口紧急修复

### 修复
- 修复主页点击“联机大厅”时，如果中断存档检查接口临时失败会停留在主页、无法进入创房界面的问题；现在检查失败会降级进入联机大厅，并保留状态提示。
- 修复进入战斗棋盘时本方 HQ 光标初始化遇到异常 `owner_id` 值会触发 `Invalid call. Nonexistent 'int' constructor` 的崩溃；现在会安全转换地块与单位归属字段，异常值自动走后备落点。

## 2026-08-12 UI 截图评审修复

### 修复
- 修复主菜单标题与封面 Logo 争抢视觉焦点的问题，让入口按钮区下移并收窄，避免遮挡封面主体。
- 修复设置面板被棋盘相机拖偏、只露出半边的问题；设置弹窗保持在 HUD 层居中显示。
- 修复剧情/教程/战斗结算截图中多个弹窗叠在一起的问题；现在截图脚本会分别截取单个弹窗状态。
- 修复存档管理和主线存档在后端无响应时一直“加载中”的问题；超过约 3 秒会显示可重试的超时提示。
- 修复地图编辑器工具面板被棋盘相机带走导致界面只剩棋盘的问题；工具面板改挂到独立 CanvasLayer，保持固定在屏幕右侧。
- 修复地图编辑器 HUD 从 CanvasLayer 泄漏到主菜单的问题；现在只有进入地图编辑器时才显示编辑器工具层。
- 修复地图编辑器左侧默认灰底显得像调试画面的问题；现在使用深绿战棋背景色统一观感。

### 变更
- 更新菜单、设置、剧情、存档、主线、编辑器截图脚本，作为后续 UI 回归检查基准。
- 补充 UI 合同测试，覆盖弹窗互斥、设置面板 HUD 层级、加载超时兜底、主菜单视觉层级、编辑器工具面板层级。
- 统一主按钮视觉：从大块金底黑字调整为深蓝底、金色描边、暖白文字，并移除设置/主线/暂停按钮上的彩色 emoji 装饰。

## 2026-08-12 FE8 风格键盘操作支持

### 新增
- 棋盘和菜单新增 FE8 风格键盘键位:方向键或 WASD 移动,Z/Enter/Space 确认,X/Esc/Backspace 取消,Q/E 或 +/- 缩放。
- `InputHints` 的键盘提示改为显示 `Z/Enter`、`X/Esc`、`E/+`、`Q/-`,玩家不用猜实际可用键位。

### 变更
- 键盘继续复用现有 `board_*` / `ui_*` action,不改变鼠标和手柄的原有操作链路。

## 2026-08-10 异常状态图标移到棋子右下角

- 当前异常状态共 5 种:`poison` 毒 `☠`,`paralyze` 麻痹 `⚡`,`blind` 致盲 `◌`,`slow` 减速 `❄`,`silence` 沉默 `🔇`;Godot `unit_node.gd` 与后端注册表保持同名映射。
- `UnitNode` 不再绘制紫色异常状态蒙版,只把状态 glyph 放到右下角 30×16 小徽标,避免和士气星/阵营角标/角色脸重叠。
- 多异常状态时右下角最多显示前两个 glyph,保证 48px 棋子仍然可读;`yuanying_board_sprite_screenshot` 预览样本加入沉默+毒双状态叠加。

## 2026-08-10 建筑归属与占领中显示拆分

- 核查后端占领链路:`ClaimSession` 到期前不改 `Tile.owner_id`,单位死亡/离开会取消占领,到期或二次 claim 才完成过户;既有 `test_claim.py` 覆盖该设计。
- Godot `Board.rebuild_flags()` 现在把当前归属旗与 pending claim 徽标分开绘制:owner flag 只代表当前 `owner_id`,占领中另显示目标阵营色进度徽标与剩余/总回合数。
- 修复中立建筑占领中无任何提示、敌方建筑只闪旧旗导致语义不清的问题。
- 建筑归属旗从单片三角改为 AI 生成的像素风小旗 PNG;中立建筑也显示白旗,避免无主建筑和漏渲染建筑混淆。
- 新增 `assets/ui/building_flags/flag_{neutral,red,blue,green,yellow}.png` 与源图集 `owner_flags_sheet_chromakey_source.png`;`Board` 改为通过 `TextureLoader` 加载 18px 贴图旗,并锚定在建筑图标左下角。
- 新增 `tools/claim_badge_screenshot.tscn`,用于快速检查已有归属建筑与中立建筑的占领中徽标。

## 2026-08-10 鸢影棋盘棋子 Q 版化

- `assets/heroes/yuanying.png`: 从完整高精立绘缩放图替换为 768×768 透明 Q 版棋盘 sprite,48px 棋盘显示下保留银发、黑紫斗篷与镰刀轮廓。
- 同步 Web 与 Godot 两端 `yuanying.png`,保留 `portrait_yuanying.png` 作为详情/对话大立绘,`crest_yuanying.png` 作为小头像资源。
- 后端 `Yuanying` 资源注释清理为当前事实,并新增回归测试防止旧的完整立绘裁切图再次回流。
- 新增 `tools/yuanying_board_sprite_screenshot.tscn`,用于对比普通术士、鸢影正常态、鸢影行动/状态叠层的 48px 棋盘显示。

## 2026-08-10 手柄棋盘光标初始位置改为本方 HQ

- 根因:光标状态字段本身正常(`InputState.cursor_cell` / `board_focused` 都有 setter + signal),但 `_find_cursor_initial_cell()` 优先选择本方第一个单位。单位排序随地图/后端快照变化,导致手柄进入棋盘时落点不稳定。
- 修复:新增 `_find_local_hq_cell()`,优先从 `GameState.tiles` 查找 `owner_id == local_player_id` 的 HQ(`terrain == "castle"` 或 `subtype == "castle_throne"`),并让初始光标按 `本方 HQ -> 本方单位 -> 地图中心` 回退。
- 验证:新增 `test_godot_board_cursor_initializes_on_local_player_hq_before_units`,先红后绿。

## 2026-08-10 标题页按钮布局调整

- `assets/ui/title_cover_v1_undead_king.png` ~ `title_cover_v6_bard_market.png`：接入用户从旧 ChatGPT 会话下载的 6 张封面图；默认封面切到 `title_cover_v5_party_dawn.png`。
- `scripts/main.gd`：标题页封面候选列表从 5 张扩展到 6 张；图片加载器先走磁盘解码，避免新导入 PNG 在开发期预览时先触发 `No loader found` 噪音。
- `tools/smoke_test.gd` / `tools/title_cover_test.gd`：同步封面候选数为 6，覆盖开发期下拉框全部切换。
- `scenes/main.tscn`：主菜单标题与操作区从屏幕中央移到右侧标题安全区，左侧封面主体不再被两列按钮遮挡。
- 主入口改为竖向层级：`主线存档` 作为最高优先级按钮，`联机大厅` 与房间号加入位于其下；存档、进行中、玩法、地图编辑、设置、退出收束为右下辅助行。
- `tools/title_cover_test.gd`：新增布局断言，覆盖右侧锚点、紧凑宽度、主按钮竖排、辅助按钮横排和主按钮高度。
- 旧 ChatGPT 会话图片未重新生成；直接使用项目根目录中用户提供的原图复制为 Godot 资产。
- 验证：`Godot_v4.7-stable_win64_console.exe --headless --path godot-client --import --quit` 通过；`res://tools/title_cover_test.tscn` 23 passed / 0 failed。`tools/menu_screenshot.tscn` 在 headless dummy 渲染下无法读取 viewport 纹理，未产出截图。

## 2026-08-10 手柄 ActionBubble 焦点修复

- 根因:棋盘光标选中单位后会显示 `ActionBubble`,但 `_enter_board_focus()` 释放了所有 UI 焦点,导致手柄玩家能移动棋盘光标,却不能稳定选择"移动/攻击/待命"等行动按钮。
- 修复:`_show_action_bubble()` 打开时临时退出棋盘焦点并把焦点交给第一个可用行动按钮;`_hide_action_bubble()` 关闭后在游戏视图内恢复棋盘焦点,保证"选单位 -> 选命令 -> 选格子/目标"手柄链路不断。
- `project.godot`: `pause` action 新增手柄 Start 键(`button_index=6`)绑定,避免只能键盘 Esc 暂停。
- 验证:`test_godot_gamepad_action_bubble_temporarily_owns_focus` / `test_godot_gamepad_pause_has_start_button_binding` 先红后绿;`pytest game/tests/test_godot_client_contract.py -q` 38 passed;Godot headless import 与主场景短启动通过。

## 2026-08-10 标题页封面接入

- `scenes/main.tscn`：主菜单 `Menu` 下新增全屏 `TitleCover`，使用 `TextureRect.STRETCH_KEEP_ASPECT_COVERED` 铺满并裁切；新增半透明 `TitleCoverScrim` 保持标题与按钮可读；封面层 `mouse_filter=IGNORE`，不拦截既有标题交互。
- `scripts/main.gd`：接入 5 张 `title_cover_*` 候选图，默认封面可通过导出变量、`ProjectSettings["battleblitz/title_cover/default_path"]` 或环境变量 `BB_TITLE_COVER` 配置；`BB_TITLE_COVER_DEV=1` 或 `--title-cover-dev` 时显示开发期预览下拉框。
- `scripts/main.gd`：封面加载器兼容内容为 JPEG 但扩展名为 `.png` 的开发期图片，避免预览切换时因为 `.import valid=false` 失效。
- `tools/title_cover_test.tscn` / `.gd`：新增定向 headless 验证，覆盖默认加载、裁切模式、鼠标穿透、5 张预览候选与切换。
- 验证：`Godot_v4.7-stable_win64_console.exe --headless --path godot-client --import --quit` 通过；`res://tools/title_cover_test.tscn` 13 passed / 0 failed；主场景 `BB_AUTO_QUIT=1` headless 短启动通过。完整 `smoke_test.tscn` 本轮两次运行均超过 120s/180s 超时未产出结果，需另行拆分慢用例。

## 2026-08-09 键盘 + 手柄两个盲区修复(本轮)

上手柄接入后发现两处"有声无影"的断点,本次补上。

### 修复 1:棋盘光标永不激活 → 方向键/摇杆无法控制单位
- 根因:`_show_view("game")` 里 `call_deferred("_enter_board_focus")` 执行时棋盘还没
  加载地图(WS 快照未到,`board.map_size == 0`),`_enter_board_focus` 提前 return 且
  无人重试 → `InputState.board_focused` 永远 false → 光标不画、`board._handle_cursor_input`
  首行 return,方向键/摇杆全无效。
- 修复:`main.gd` 连接 `board.map_loaded` 信号 → `_on_board_map_loaded()`:当前是 game
  view 且尚未 board_focused 时补调 `_enter_board_focus()`。覆盖新建/重连/续档所有 load_map
  路径;已在焦点中则不动(不打断进行中的移动/攻击模式)。

### 修复 2:大厅(建房/加入/房内)控件无法用手柄操作
- 根因:`main._focus_default_for_view("lobby")` 是空 `pass`,lobby 各子视图切换
  (`_show_lobby_choose/_create_view/_join_view/_in_room`)从不 grab focus。Godot 手柄导航
  依赖某个 Control 先有焦点,否则十字键/确认键全无响应(主菜单能用正是因为抢了焦点)。
- 修复:`lobby_controller.gd` 新增 `_grab_focus_for_mode()`,按 `_lobby_mode` 抢默认焦点
  (choose→建房卡 / create→开启游戏 / join→加入 / in_room→开局),无可用按钮时兜底
  `UIPanelFocus.grab_first_focusable`。

### 后端连带:成长图表曲线下降波动(工具修复)
- `tools/growth_charts/dataset.py` 对 RolledGrowthPolicy 改为增量滚动 + 每主题固定种子
  (镜像 `app.modes.spawn_generic_stats`),曲线单调不减且两次运行 PNG 完全一致。旧实现每级
  独立重掷未播种随机数,L6 可能比 L5 低 → 图表锯齿下降。已更新 `test_growth_chart_policies.py`
  (含单调性回归)并给 full-roster 地图补上 `bard`。

### 后端连带:上一轮重构遗留的 ~23 条失败测试清理
成长/MOV-MP/组件化重构让一批旧测试失配,本次按新契约全部对齐:
- `test_modes.py` — spawn 断言从旧 autolevel 公式改为 rolled 播种契约(fix mov 静态断言)。
- `test_godot_client_contract.py` — 大厅函数已搬到 lobby_controller.gd,契约测试跟着改读
  LOBBY_GD;hero portrait 断言对齐"检视卡内嵌立绘"现行设计。
- `test_godot_ui_design_tokens.py` — battle/mainline 主题加入 Color 白名单。
- `test_commanders_integration.py` — passive 倍率断言改为反推预烘焙值(修 hero 单位 flaky)。
- `test_hero_promotion.py` / `test_mainline_hero_persistence.py` — yun 纯法师重做后 mp=4。
- `test_mainline_event_triggers.py` + `test_mainline_full_e2e.py` — **真 bug 修复**:
  `event_trigger._INSERT` 原始 SQL 漏了 NOT NULL 的 `growth_seed` / `status_effects`,
  wave 触发器 IntegrityError 崩掉 → 补齐两列。
- `test_ws_gateway.py` — Windows 上 sync TestClient + aiosqlite worker-thread leak 挂起
  (文件头已点名该限制),skip-on-win32,非 Windows CI 照常跑。

## 2026-08-09 键盘 + 手柄"返回上一级"补全(本轮 commit)

排查后发现 5 个 modal 缺键盘/手柄的"返回"快捷键,Connecting 面板缺"放弃"按钮。本次只补缺口,**不重构 view 栈**。

### 改动文件
- `scripts/main.gd`
  - `_unhandled_input` 顶部新增 modal-LIFO 分流:`ui_cancel` 触发时按优先级关最上层 modal。
  - `_try_close_topmost_modal()` 新方法:LIFO 顺序 Confirm → BattleResult → AttackConfirm → Recruit → WarReport → Tutorial → Settings → Pause → Connecting(放弃重连),命中即返回 true。
  - `_on_connecting_abort_pressed()` 新方法:ws_close + 切回 menu + 重置 _game_id/_player_id/_resume_*。
  - `@onready var connecting_abort_btn: Button` + `_ready` 里 connect 按钮事件。
  - `_focus_default_for_view("connecting")` 优先 focus 落 AbortButton(玩家进入该面板大概率想退出),fallback 到 ReconnectButton。
- `scenes/main.tscn` — `Connecting/ConnectingInner` 下新增 `AbortButton`(文字"放弃,返回主菜单")。

### 语义说明(务必读一下)

- **Esc / 手柄 A** = 全局"返回上一级 / 取消"键。
- 优先级:**最上层可见 modal 优先**(Confirm > BattleResult > AttackConfirm > Recruit > WarReport > Tutorial > Settings > Pause > Connecting)。
- 命中 modal → 关该 modal,后续逻辑(board.cancel / pause toggle)不再处理。
- 没 modal 可见时:
  - 棋盘光标模式 → `board.cancel_cursor`(取消行动模式 / 清高亮),这跟上次 commit 行为一致。
  - 非棋盘模式 → 走 `pause` action(暂停 toggle),老行为不变。

### ActionBubble 不走 ui_cancel

按 Esc 时,如果 ActionBubble 可见,ActionBubble 的 CancelBtn 不直接接 ui_cancel(避免和棋盘模式取消重复),仍由 `board._handle_cursor_input` 接管 — 它已经调 `_cursor_cancel_action` → `_cancel_action_mode + _hide_action_bubble`,等同于点 CancelBtn。

### Connecting 面板新行为

- 之前:重连失败时只能 Ctrl+W 强退。
- 现在:
  - 鼠标点 `放弃,返回主菜单` 按钮 → disconnect WS,回主菜单,清 _game_id/_player_id/_resume_*,避免下次进游戏误从中断存档续上。
  - 键盘按 Esc / 手柄 A → 走 `_try_close_topmost_modal` 命中 Abort 路径,等价于点按钮。
  - 面板打开时默认 focus 落 AbortButton(而不是 ReconnectButton),键盘玩家 Tab 一次就到了 ReconnectButton(更安全的"重试"留二选)。

### 测试

- `Godot --headless --quit-after 90 --path .` — 编译过、跑 1.5s 无 ERROR。
- `tools/button_smoke_test.tscn` — 116 pass / 0 fail(比上次 +2,新增 `connecting_abort_btn` 自动发现并 emit_signal 通过)。
- 后端 `game/tests/` 这次没动 backend,不受影响。

### 已知没动

- 顶层 view 之间没引入返回栈(menu → lobby → editor 等是单跳 back 按钮,按 Esc 在 GameView 不返回主菜单 — 得先开暂停 → 点退出战斗)。
- DialogManager(NPC 对话)的"继续"语义不是返回,没动。

## 2026-08-09 键盘 + 手柄操作模式接入

新增 Phase 1(UI 导航) + Phase 2(棋盘光标)。鼠标方案完全保留,新功能只是补充。

### 改动文件
- `project.godot` — `input` 段补全 5 个 ui_* 家族(`ui_accept` / `ui_cancel` / `ui_up/down/left/right`)和 10 个 board_* action;新增 `InputHints` autoload。
- `scripts/autoload/input_hints.gd`(新)— 平台感知的按键提示文字(KB / Xbox / PS / Switch),通过 `UserSettings` 的 `settings.v1.controller_style` 覆盖(`auto` / `keyboard` / `xbox` / `playstation` / `switch`)。
- `scripts/autoload/input_state.gd` — 加 `cursor_cell: Vector2i` + `board_focused: bool` + 两个对应 signal。
- `scripts/board/highlights.gd` — 新增 `Mode.CURSOR`(4 角带小三角 + 4px 厚白边的"虚拟光标"视觉,跟普通 hover 区分);`show_cursor_at(tile, color)` API 允许外部控制脉动 alpha。
- `scripts/board/board.gd`
  - `_process` 增加光标脉动 + 持续按方向键/摇杆 repeat timer。
  - `_handle_cursor_input` 路由 `board_cursor_*` / `board_zoom_*` / `board_confirm` / `board_cancel`。
  - `_handle_camera_input` 顶部:鼠标 hover 同步 `InputState.cursor_cell`(鼠标/手柄玩家看到一致的"当前格")。
  - `_zoom_at_viewport_center` — 手柄缩放改用屏幕中心为锚点(手柄玩家没鼠标)。
  - `_confirm_cursor` / `_cancel_cursor` — 复用现有 `emit_unit_clicked` / `emit_tile_clicked` / `_cursor_cancel_action` 路径,不绕过 main.gd 的状态机。
- `scripts/main.gd`
  - 7 个 panel(`pause_panel` / `settings_panel` / `recruit_panel` / `war_report_panel` / `attack_confirm_panel` / `confirm_dialog` / `battle_result_panel`)打开时调 `UIPanelFocus.grab_on_show` 抢焦点。
  - `_show_view` 切换时同步 `InputState.board_focused`:`game` 进 board_focus + 初始化光标(我方第一单位 > 地图中心);其它 view 退 board_focus + grab 该 view 主按钮。
  - `pause` action 在 board_focused 时让给 `board_cancel`(棋盘光标模式 Esc = 取消,不是暂停)。
  - `_update_path_dots_at_cell` + `_cursor_cancel_action` 两个薄包装给 board 调。
- `scripts/ui/_components/ui_panel_focus.gd`(新)— 纯静态工具,帮"打开 panel → grab focus 到默认按钮"。

### 玩家操作模式

**键盘(KB)**
| 场景 | 键位 |
| --- | --- |
| 菜单/面板 焦点跳转 | Tab / Shift+Tab |
| 菜单/面板 确认 | Enter / Space |
| 菜单/面板 取消 | Esc |
| 棋盘光标移动 | ↑ ↓ ← → / WASD |
| 棋盘光标确认 | Enter |
| 棋盘光标取消 | Esc / Backspace |
| 棋盘缩放 | `+` / `-`(或 `=` / `_`) |
| 暂停 | Esc(在 game view 顶层) |

**手柄(Switch 风格反转,默认)**

| 动作 | Switch | Xbox 等价 | PS 等价 |
| --- | --- | --- | --- |
| 确认 | B | A | × |
| 取消 | A | B | ○ |
| 光标移动 | 左摇杆 / D-pad | 同上 | 同上 |
| 缩放 | L / R | LB / RB | L1 / R1 |
| 暂停 | + | Start | Options |
| 结束回合 | X | Y | △ |

手柄按键文字会按 `UserSettings.controller_style` 自动调整。`auto` 模式下,只要 `Input.get_connected_joypads()` 看到手柄就显示 Switch 反转;否则显示键盘。

### 鼠标兼容性

- 完全保留。鼠标点击 / 滚轮缩放 / 左键拖拽 pan 行为不变。
- 鼠标 hover 时 `InputState.cursor_cell` 跟着鼠标走,所以鼠标/手柄玩家在棋盘上看到的"当前格"始终一致。
- 光标视觉(白色 outline + 4 角三角)只在 `InputState.board_focused = true` 时显示,纯鼠标玩家在主菜单看不到任何多余元素。

### 测试

- `Godot --headless --quit-after 120 --path .` — 编译过、跑 2 秒无 ERROR。
- `tools/button_smoke_test.tscn` — 114 pass / 0 fail,所有 button 引用 + `pressed` 信号没被新加的 autoload / panel focus 改动打乱。
- 后端 `game/tests/test_*.py` 这次没动 backend,不受影响(计划原则:这次只动 godot 前端)。

### 已知限制 / 后续增量

- 光标在棋盘边缘不自动滚屏(没用 scroll-at-edge 联动 camera)。需要玩家用 `+` / `-` 缩放,或手柄 L/R 调视野。
- 没接 CO Power / 技能快捷键(键位待定)。
- 主菜单 → 切到 game view 时,光标会从第一个我方单位起步;没找到我方单位则放地图中心。
- 多次"取消"会把光标重置回我方第一单位,避免取消后光标停在空地看起来像死锁。

## 2026-08-09 英雄美术资源登记(L4 review 补登记)

所有英雄美术资源均为 8-bit PNG,统一存放在 `godot-client/assets/heroes/`。

| Hero    | 单位立绘           | 大头贴 portrait          | 队徽 crest    | 备注 |
|---------|--------------------|--------------------------|----------------|------|
| anna    | `anna.png` 1254×1254 RGBA | `portrait_anna.png` 800×1400 RGBA | `crest_anna.png` 120×120 RGBA | 初始版 |
| anna_boss | (复用 anna)        | `portrait_anna_boss.png` 774×1355 **RGB** | (复用 anna)    | RGB 无 alpha,变体 BOSS 头像 |
| yun     | `yun.png` 717×781 RGBA    | `portrait_yun.png` 800×1400 RGBA  | `crest_yun.png` 120×120 RGBA  | |
| youko   | `youko.png` 1254×1254 RGBA | `portrait_youko.png` 800×1400 RGBA | `crest_youko.png` 120×120 RGBA | |
| yuanying | `yuanying.png` 768×768 RGBA | `portrait_yuanying.png` 948×1659 RGBA | `crest_yuanying.png` 256×256 RGBA | 鸢影;队徽比其它大一档(2× 边长) |

License / 来源:
- 当前批次均为项目内原创 / 委托绘制的占位与正式稿,版权属项目所有。
- 后续若引入外部素材(Free-license 库 / 委托 / 自制),需在每张资源同目录放
  `LICENSE.txt` / `CREDITS.md`,在 CHANGELOG 本节登记出处,license 类别
  (CC0 / CC-BY / MIT / 商业 等)。

格式约定(后续新增资源请遵守):
- 单位立绘 (`<hero>.png`):正方形 1024+ 边长,RGBA,带透明背景。
- 大头贴 (`portrait_<hero>.png`):近似 4:5(800×1400 或相近),RGBA。
- 队徽 (`crest_<hero>.png`):120×120,RGBA,适配小队栏 1× 显示。
- 不使用 JPG(WebP 在 Godot 4 已稳定,RGBA 不适用);PSD / AI 源文件不入库。

## 2026-08-02 资源收尾

- 鸢影美术资源二次收尾:
  - 同步更新 Web 与 Godot 两端的 `yuanying.png` / `portrait_yuanying.png` / `crest_yuanying.png`。
  - 已用 `game/tests/test_godot_unit_portrait_paths.py` 锁定资源路径与 Godot sprite registry，避免英雄图像资源缺失回流。

## 2026-08-02

- 鸢影正式可用化:
  - 补齐 `yuanying.png` / `crest_yuanying.png` / `portrait_yuanying.png` 在 Godot 与 Web 两端的英雄资源(Godot `.import` 旁文件由编辑器自动生成,被 `.gitignore` 排除,不入库)。
  - `unit_node.gd` hero sprite registry 加入 `yuanying`,鸢影英雄单位现在会在棋盘上使用专属立绘资源。
  - 大厅默认指挥官池 fallback 加入 `yuanying`,座位卡能力文案显示"5x5 沉默领域，术士压制"。
  - 新增集成测试锁定自由模式选择鸢影后:玩家 `commander_id=yuanying`,CO 阈值 16,HQ 生成 `hero_id=yuanying` 的 warlock,并继承 `poison_burst`。

- Agent 回归修复:
  - `_ask_llm_with_retry` 批量决策返回 list 的测试契约同步;单决策场景取首个 `ActionPlan`。
  - `Reaction` 文案重新按测试契约截断到 40 字。
  - `AgentAction.action_id` 禁止空格,防止 LLM 把合法动作 ID 改写成不可执行文本。
  - 未知 personality fallback 在 system prompt 中显式标注"均衡型人格"。

- 通用 status effect 框架(P+):
  - 后端 `game/app/status/` 新包:`effects.py` 注册表 + `engine.py` 钩子函数;`Unit.status_effects: list[dict]` JSON 字段,`UnitOut.status_effects` 公开字段;5 个 effect 注册(poison 毒 / paralyze 麻痹 / blind 致盲 / slow 减速 / silence 沉默,后者从 `silence_until_turn` 字段迁移)。
  - 钩子函数:`tick_effects_at_turn_start`(poison 扣 HP + 倒计时) / `should_skip_action`(paralyze 概率 skip) / `modify_hit_chance`(blind) / `modify_mov`(slow) / `should_block_attack`(silence) / `is_silenced` / `get_status_summary`。
  - `apply_silence_aura`(鸢影沉默领域)改用 `add_effect(unit, "silence", ...)` 写新字段,旧 `silence_until_turn` 字段保留作 fallback。
  - godot 端 `unit_node.gd` 把原单一 `silence_overlay`/`silence_label` 替换为通用 status overlay + glyph 行(`☠⚡👁❄🔇`);`core/types.gd:UNIT_KEYS` 加 `status_effects`。
  - 详细设计文档:`game/app/status/README.md`。27 个 pytest 全过(`game/tests/test_status_effects.py`),完整套件 140/140 全过。

- Status effect 实时接入(P+ 闭环):
  - `commanders.effects.on_player_turn_start` 集中钩子:每回合对玩家所有 unit 顺序执行 `should_skip_action`(paralyze → has_acted=True + paralyzed_until_turn) → `_refresh_mov_debuff`(slow 用 _base_mov 快照 + modify_mov 改 mov,过期自动恢复) → `tick_effects_at_turn_start`(poison 扣 HP / 倒计时 / 过期清理)。
  - `game_logic.attack_with_double_strike` 加 `_maybe_miss` wrap:每 hit 独立判定 `modify_hit_chance`,miss 时 `damage=0`;Double-Strike 两次 hit 各自掷骰。
  - 详细钩子调用顺序在 `commanders/effects.py:on_player_turn_start` 注释里(paralyze 在 tick 前判断,slow mov 在 tick 前生效)。
  - 13 个端到端测试覆盖:`test_status_effects_live.py`(poison/paralyze/blind/slow 各类型 + 同挂组合 + Double-Strike + blind 独立判定)。完整套件 153/153 全过。

- 沉默领域 godot 端 UI(鸢影 CO power 闭环):
  - `NetworkClient.action_co_power` 接可选 `center: Vector2i = (-1, -1)`,center 有效时附带 `body.center` 给后端。
  - `main.gd` 检测 `commander_id == "yuanying"` 时进入"选中心"模式(`_silence_pick_center_for_pid` 状态机),`_on_board_tile_clicked` 入口优先处理沉默选 center;右键 / ESC 取消。
  - `board.gd:highlight_silence_pick_mode(on)` 切换中央紫色提示气泡 + hover 时 `_refresh_silence_pick_outline` 实时绘制 5×5 紫色 outline(中心 ±2,地图边界裁剪);`main.gd:_unhandled_input` mouse_motion 转发 hover 给 board。
  - `highlights.gd` `Mode` 枚举加 `SILENCE_PICK`,紫色 `Color(0.75, 0.55, 1.0, 0.50)`。

- 鸢影 yuanying 基础注册:详见 commit `a672511` + `feat(heroes): 注册鸢影 yuanying - 沉默领域 CO, warlock 基础`。资产 `portrait_yuanying.png` 已就位,`sprite_path` / `crest_path` 仍待美术补。
## 2026-08-20

- 新增 UI 验收评分卡 `docs/validation/godot-ui-scorecard.md`：把 UI 改动完成条件固定为可重复的自动化门槛
  （烟测零失败 / 中文扫描通过 / 三档各 11 张截图 / 单图与总平均 ≥8.5）+ 截图评审，不以「能启动」作为完成标准。
- 加固评分工具链：
  - `tools/check_chinese_ui.py` 补齐 `popup/item_N/text`（OptionButton 菜单项）扫描，堵住菜单项英文漏报盲区。
  - `tools/ui_review_screenshot.gd` 地图路径改多候选解析、补全 11 张截图清单注释、`_review_size` 默认对齐 1920×1080、
    并给 `_save` 增加 viewport 纹理空值保护。
  - `tools/smoke_test.gd` 修复缺 `%s` 占位符的格式化 bug。
- 完成新版评分规则下的 UI 密度与响应式整改：补充战斗默认态操作/回合引导，接入墨蓝织纹战斗底幕，
  丰富英雄与装备核对信息，并提高 1280×720 主线档案的中文可读性。
- 验收结果：烟测 **608 通过 / 0 失败**；中文扫描通过；三档截图各 11/11；11 种画面全部达标，
  最低单图 8.50、总平均 8.56。

## 2026-07-31

- 修复棋盘 ↔ 主菜单的「瞬切错位」bug(游戏胜利 / 失败 / 中断 退出再回主菜单时,主菜单会被 BoardCamera 的 zoom/position/smoothing 残值拉飞一帧):
  - `main.gd` 重写 `_reset_board_cameras`: 先强制把每个 `Camera2D` 的 `zoom = (1,1)`、`position = (0,0)`、关掉 `position_smoothing_enabled` 与 `zoom_smoothing_enabled`,再 `enabled = false`,最后 `viewport.canvas_transform = IDENTITY`。
  - 新增 `_disable_all_cameras_in_tree`: 用 `find_children("Camera2D")` 兜底扫整棵树,防未来新增 Editor/UI 相机漏网。
  - 新增 `_post_frame_viewport_reset`(`call_deferred`): 帧末再 reset 一次,接住同帧内残留 tween / state_updated 回调又把 camera 设回去的情况。仅当 `_current_view != "game" / "editor"` 时生效,正常游戏视图不受影响。
  - 新增 `_current_view` 跟踪当前 view 状态,作为 _show_view 内 `_reset_board_cameras` 的开关依据。
  - `HUD` / `BattleBackdrop` 的 `CanvasLayer.transform` 同步归零,兜底 CanvasLayer 上的 transform 残值。
  - 同步修复两条之前漏掉 `_reset_game_state_for_main_menu` 的返回路径:`_on_battle_back_menu_pressed`(战报 → 主菜单)与 `_on_battle_back_lobby_pressed`(战报 → 大厅),补全 action bubble / recruit / move-attack-skill mode / GameState / Board 高亮 / WS / tween 清理,与 pause → 主菜单行为一致。

## 2026-07-30

- Added hero `youko` / 洋子 as a T1 special Bard (`bard`) with the active skill `sing` / 吟诗, Godot skill targeting, and hero assets (`youko.png`, `portrait_youko.png`, `crest_youko.png`). Bard is intentionally excluded from ordinary barracks recruitment.

- 修复主线开战前对白被跳过/不可见: `DialogManager` 播放时重新显示对话面板,主线 start 响应改为先等待 `pre_battle_dialogue_url` 播放完成,再进入棋盘并连接战斗。
- 修正 `entry_flow_e2e.gd` 的合并后入口调用: 主线改走 `MainlineView` 存档槽控制器,大厅改走 `$Lobby` 控制器,并在失败后停止误报 PASS。
- 修复 `main.gd` 模块化重构合并 `origin/feat/godot-mainline-fe-ui` 后的战斗 UI 回退: 恢复战斗专用背景层显隐、棋盘外深色 HUD 边界、行动气泡侧翼/避让定位、CO 顶栏中文化与紧凑排版、单位检视卡正式文案和地形移动消耗信息; 保留本地通用单位立绘路径与 `PortraitLoader` 加载逻辑。
- 新增 `test_godot_battle_hud_keeps_mainline_fe_ui_layout_rules` 防止旧版透明背景、贴单位气泡、`RED:<null>`/`Hero ID` 调试字段再次回流; 同步 `smoke_test.gd` 与 `portrait_check_screenshot.gd` 的立绘调用参数。
- 合并 `origin/feat/godot-mainline-fe-ui` 到 `refactor/extract-mainline-modules`,保留 UI 分支完整历史,同时延续本地 `main.gd` 模块化抽离成果。
- 接入主线响应式 `CampaignPanel` / `PreparePanel` 场景、战斗 HUD 美术素材、`battle_theme.gd` / `mainline_theme.gd` / `mainline_*_panel.gd` 新 UI 组件。
- 调和冲突点: `scenes/main.tscn` 采用 UI 分支的新场景结构并补回 `$Lobby` 的 `lobby_controller.gd` 挂载;`mainline_controller.gd` 保留存档优先渲染,英雄对话缓存切回 `DialogManager`;`main.gd` 保持对话/大厅/主题抽离,只补新增 HUD 节点引用与单位检视卡接线。
- 单位检视卡合并两边能力: UI 分支的紧凑右侧卡片 + 本地通用兵种立绘路径共存;透明无边框立绘槽断言迁移到抽离后的 `hud_theme.gd`。
- 验证: `python -m pytest game/tests/test_godot_unit_portrait_paths.py game/tests/test_save_resume_fixes.py game/tests/test_save_slot_independence.py` 16 passed;本机 PATH 未发现 `godot`,Godot headless 场景测试需在装有 Godot CLI 的环境补跑。

## 2026-07-29

- 对话系统抽离为 `DialogManager` 全局 autoload:新增 `scripts/autoload/dialog_manager.gd`(498 行),挂在 root 层 CanvasLayer(layer=50)上,跨 menu / lobby / game view 都可见。从 `scripts/main.gd` 删除 6 个 `@onready` 引用、3 个常量、9 个状态变量、13 个函数(~220 行),同步从 `scenes/main.tscn` 删除 DialogPanel 子树 62 行(7 个节点)。新增 `scripts/core/portrait_loader.gd` 共享头像加载器。
- 对话 API 重构为 async/await 范式:`DialogManager.play(scenes, context) -> Dictionary` 可 `await` 并返回 `{"choice_value": String}`;同时暴露 `signal scene_advanced / dialogue_finished / choice_made / dialogue_aborted` 供 fire-and-forget。配套 `show_dialog(scene)` / `hide_dialog()` / `reset()` / `is_playing()` / `load_portrait(path)` / `register_hero_speaker()` 公共方法。
- 首批 4 套触发点接入:`_on_state_updated` 末尾检测本地玩家回合起(去重 `(game_id, turn, player_id)` 避免 state poll 反复触发)、`GameState.unit_killed` 旁白、CO power 前后(由 `UserSettings` `dialog.v1.co_power_confirm` 开关,默认关闭避免疲劳)、攻击前后(由 `dialog.v1.attack_confirm` 开关);招募/占领响应尾部追加旁白。
- `NetworkClient.action_attack / action_co_power / action_claim` 三个 wrapper 新增 `callback: Callable = Callable()` 透传参数(`action_recruit` 早已支持),为「动作后旁白」提供 REST 回调通道。
- `InputState` 新增嵌套可重入 `lock() / unlock() / set_locked() / is_input_locked()` 与 `lock_changed` 信号;`DialogManager._start()` 自动 `InputState.lock()`,`_advance()` 队列空时自动 `unlock()`,业务侧不需手动管理。
- 顺手修 3 个真 bug:
  - Typewriter 重写为 `RichTextLabel.visible_ratio` + `tween_method`(原 tween 创建后立即 kill,callback 只改 `_dialog_visible_text` 不写 `dialog_text.text`,实际整段直接闪现)。
  - `choices[].value` 通过 `pressed.connect(_on_choice_selected.bind(value))` 上报,`play()` 返回值携带;原代码 handler 零参,100% 丢弃 `.value`。
  - 主线对话 404 时(`code < 200 or code >= 300`)显示状态提示而非空旁白框;`DialogManager.play` 自身拒绝 `null` / 空 `scenes`。
- `mainline_responses.gd` 删除死代码 `on_dialogue_response`(全项目无调用方),同时删除 18 行的 doc 引用。
- `tools/smoke_test.gd` 新增 3 条 DialogManager 断言(autoload 注册 / `play` 方法 / `is_playing` 方法),共 548 通过 / 0 失败。
- 验证:smoke_test **548 通过 / 0 失败**,对比基线 +3(新断言全过);action_latency_test 20 / 0;map_logic_movement_test、tileset_atlas_test 通过;view_position_reset_test 4 通过 / 2 失败(BoardCamera 既有问题,与本 PR 无关)。
- 已知限制(留 follow-up,本 PR 不阻塞):
  - 嵌套 `play()` 行为未定义,同一时刻只支持一个 awaiter;首批触发点无人嵌套。
  - `GameState.unit_killed` 信号触发时 victim 已从缓存移除,`GameState.get_unit(unit_id)` 大概率返回 `{}`,fallback 到 `unit_type`;精确名字需在 `_on_event_delta` 先抓快照再发信号。
  - `mainline_controller.gd:527` 那个死分支现在 CanvasLayer 隔离已修,但仍依赖后端 `chapters.py:180` schema 加 `dialogue` 字段。
  - chapter_06 整章对话 404(`game/stories/chapter_06/` 整个目录不存在),404 容错后显示状态提示,但章节本身没内容是设计层面问题。
  - 6/8 演讲者缺肖像(`红`/`太子`/`卡尔德` 等),fallback 显示 👤 emoji;需补 hero 模块。
- main.gd 净变化:本 PR 起点 3835 行(此前 PR 重构 mainline + lobby + theme + cn_labels 后),本轮再降 124 行 → 3711 行(累计从 6300 → 3711,共 -41%)。

## 2026-07-28

- 重构 `scripts/main.gd`：6300 行 → 3835 行（-39%），纯搬运，零行为改动。
- 新增 `scripts/ui/lobby_controller.gd`（2140 行）：整套联机大厅从 main.gd 抽离，挂在场景 `$Lobby` 节点上，沿用 saves / mainline / editor 已有的「子节点挂脚本 + `_main` 注入」模式。大厅的 43 个子控件引用、30 个私有状态变量、20 处信号接线全部自管；main.gd 侧只保留 `_on_lobby_pressed` 与 `_setup_lobby_commander_options` 两个转发薄壳。
- 新增 `scripts/ui/hud_theme.gd`（332 行）：`_apply_gba_theme` / `_apply_hud_theme` / `_apply_theme` 三个纯样式函数抽为 static，采用 `mainline_responses.gd` 既有的 host 派发约定；main.gd 保留同名薄壳，四处既有调用点未改动。
- 新增 `scripts/ui/cn_labels.gd`（201 行）：单位 / 技能 / 地形 / 指挥官 / 颜色 / 队伍 / 席位共 12 个中文查表函数抽为 static，main.gd 与 lobby_controller 均可直接取用，不再经 `_main` 绕行。
- 大厅控制器新增对外接口 `open()` / `show_choose()` / `enter_room_after_join()` / `reset_state()` / `selected_join_role()` / `selected_join_team()`，收敛 main.gd 原先散落的六处跨域调用。
- 编辑器保存地图后写入大厅预设的信号（`editor_view.map_saved`）改接到控制器；回主菜单时的大厅状态清理改由 `lobby_controller.reset_state()` 承接。
- 三个新模块一律用 `const X = preload(...)` 而非 `class_name`，避免 headless 跑测试时全局类缓存未建立导致的 Parse Error。
- 同步更新 `tools/smoke_test.gd`（15 处）与 `tools/view_position_reset_test.gd`（2 处）：大厅相关断言改指 `$Lobby` 控制器，断言强度不变。
- 验证：smoke_test 545 通过 / 0 失败、action_latency_test 20 通过 / 0 失败、map_logic_movement_test 与 tileset_atlas_test 通过、view_position_reset_test 4 通过 / 2 失败——全部与重构前基线逐项一致（该 2 项 BoardCamera 失败为既有问题，与本次重构无关）。

- Added a transparent, borderless selected-unit portrait slot that resolves hero portraits first and generic unit portraits from `assets/unit_portraits/`.
- Added generated generic unit portraits for all 15 registered unit types, with T2 portraits rendered more richly than T1 while keeping NPC eyes hidden.
- Fixed large-map camera refresh: state polling no longer reloads the same board every tick, so manual zoom and pan stay in place.
- Added middle-mouse panning support on the Godot board while keeping wheel zoom.
- Fixed rules-AI HQ targeting in team games: AI now excludes teammate HQs from enemy castle pull targets, so allied AI advances toward enemy HQs instead of the player's HQ.
- Added `red_full_roster_4p_20`, a 20x20 four-player free-mode map where red starts with one of every registered unit type and nearby village, barracks, and vault economy tiles.
- Expanded barracks recruitment across backend, Web, and Godot clients so every registered unit type is available from recruit UI paths.
- Fixed free-mode victory cleanup: the final kill now flushes dead units before rout evaluation, and match finish clears the player's suspend save so returning to menu cannot resume into the victory screen.

## 2026-07-27

- Changed the mainline entry to an FE8-style slot-first flow: players now choose one of the three formal save slots before the current chapter is resolved.
- Added `assets/tilesets/` as the preferred atlas-sheet home for map art.
- Wired the three new 48px-grid map sheets into `Config.TILESET_ATLAS_COORDS`.
- Updated `TileSetBuilder` so configured atlas sheets become shared runtime `TileSetAtlasSource` resources before legacy per-tile PNG fallback.
- Updated `MapLoader` to paint configured atlas coordinates directly.
- Routed transparent forest/mountain-style tiles through overlay layers so they render above biome-appropriate base ground.
- Added a focused `tileset_atlas_test` scene and smoke-test assertions for the new atlas mapping.
- Fixed Godot client movement previews so allied units are pass-through but not valid destinations; enemy units still fully block movement.
- Upgraded atlas rendering to parse sibling `.txt` label maps, grouping same-terrain variants by biome and selecting stable per-cell variants across each map.
