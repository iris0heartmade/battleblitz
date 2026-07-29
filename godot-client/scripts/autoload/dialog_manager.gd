extends CanvasLayer
## DialogManager — 全局对话 autoload,挂在 root,跨 view 可见。
##
## 从 main.gd 抽离,场景里原先的 DialogPanel 子树由本脚本在 _ready() 程序构建。
## 之前嵌在 $GameView/HUD 下会被 _hide_hud() 物理隔离,现在用 root-level
## CanvasLayer(layer=50) 跨菜单/大厅/游戏 view 都可见。
##
## 对外 API(主入口 play,支持 async/await + signal):
##   play(scenes, context)         可 await;返回 {"choice_value": String}
##   show_dialog(scene)              fire-and-forget 单场景
##   hide_dialog()                   中断当前 + 清队列
##   reset()                        硬重置(包括 heroes 缓存)
##   is_playing() -> bool
##   load_portrait(path) -> Tex    头像加载(委托给 PortraitLoader)
##   register_hero_speaker(name, path)  取代旧 _hero_speaker_map 直接写
##   record_turn_shown / record_death_shown / record_attack_shown  去重 helper
##
## 信号:scene_advanced / dialogue_finished / choice_made / dialogue_aborted
##
## ⚠ 已知限制:同一时刻只支持一个 awaiter,嵌套 play() 行为未定义。
##   (首批触发点无人嵌套,但 follow-up 必须留意)
##
## 注意:不写 class_name —— 跨文件 class_name 引用在 headless 跑测试时
## 全局类缓存未建立,会撞 Parse Error。统一用 const X = preload(...)。
## 本文件是 autoload,通过标识符 DialogManager 全局访问,无需在别处 preload。

const PortraitLoader = preload("res://scripts/core/portrait_loader.gd")
const MenuTheme = preload("res://scripts/ui/menu_theme.gd")

# --- 公共信号 ---
signal scene_advanced(scene_index: int)
signal dialogue_finished(choice_value: String, scene_index: int)
signal choice_made(choice_value: String, scene_index: int)
signal dialogue_aborted()
# 内部用:每次队列清空时 emit 一次,awaiter 据此醒来
signal _dialog_completed()

# --- 场景类型枚举(取代原 main.gd 的 _DIALOG_TYPE 等常量)---
enum {
	KIND_TYPE,        # 角色说话
	KIND_NARRATION,   # 旁白
	KIND_CHOICE,      # 选项
}

# --- 运行时状态 ---
var _queue: Array = []
var _active: bool = false
var _choice_value: String = ""
var _playing_depth: int = 0        # play() 嵌套深度;emit 信号只在最外层 drain 时
var _lock_depth: int = 0           # 跟踪 InputState.lock 调用
var _type_tween: Tween = null
var _portrait_tex: TextureRect = null
var _choice_container: VBoxContainer = null

# --- 头像映射(dialogue_name → {portrait_path, portrait_tex?})---
var _heroes: Dictionary = {}

# --- 触发点去重表(用 set 语义)---
var _seen_turn_keys: Dictionary = {}
var _seen_death_keys: Dictionary = {}
var _seen_attack_keys: Dictionary = {}

# --- UI 节点引用(在 _build_subtree() 末尾赋值)---
var _root: Panel = null
var _name_label: Label = null
var _text: RichTextLabel = null
var _continue_btn: Button = null
var _portrait_panel: Panel = null
var _portrait_label: Label = null


# ============================================================
# 生命周期
# ============================================================

func _ready() -> void:
	layer = 50  # 高于 HUD CanvasLayer(10) 与 tutorial bubble
	visible = true
	_build_subtree()
	if _continue_btn != null:
		_continue_btn.pressed.connect(_on_continue_pressed)


## 程序构建 UI 子树 — 镜像原 scenes/main.tscn 2098–2155 的 anchor/offset/text
func _build_subtree() -> void:
	_root = Panel.new()
	_root.name = "DialogPanel"
	_root.visible = false
	_root.anchor_left = 0.5
	_root.anchor_top = 1.0
	_root.anchor_right = 0.5
	_root.anchor_bottom = 1.0
	_root.offset_left = -600.0
	_root.offset_top = -315.0
	_root.offset_right = 600.0
	_root.offset_bottom = -30.0
	_root.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_root)

	_name_label = Label.new()
	_name_label.name = "CharacterName"
	_name_label.offset_left = 24.0
	_name_label.offset_top = 18.0
	_name_label.offset_right = -24.0
	_name_label.offset_bottom = 54.0
	_name_label.text = "👤 指挥官 艾莉卡"
	_name_label.add_theme_font_size_override("font_size", 27)
	_root.add_child(_name_label)

	var body := HBoxContainer.new()
	body.name = "DialogBody"
	body.anchor_right = 1.0
	body.anchor_bottom = 1.0
	body.offset_left = 24.0
	body.offset_top = 66.0
	body.offset_right = -24.0
	body.offset_bottom = -84.0
	body.add_theme_constant_override("separation", 24)
	_root.add_child(body)

	_portrait_panel = Panel.new()
	_portrait_panel.name = "Portrait"
	_portrait_panel.custom_minimum_size = Vector2(180, 165)
	body.add_child(_portrait_panel)

	_portrait_label = Label.new()
	_portrait_label.name = "PortraitLabel"
	_portrait_label.anchor_right = 1.0
	_portrait_label.anchor_bottom = 1.0
	_portrait_label.text = "👤"
	_portrait_label.horizontal_alignment = 1
	_portrait_label.vertical_alignment = 1
	_portrait_label.add_theme_font_size_override("font_size", 96)
	_portrait_panel.add_child(_portrait_label)

	# 运行时再贴 portrait texture(覆盖 emoji)
	_portrait_tex = TextureRect.new()
	_portrait_tex.name = "PortraitTex"
	_portrait_tex.anchor_right = 1.0
	_portrait_tex.anchor_bottom = 1.0
	_portrait_tex.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_portrait_tex.visible = false
	_portrait_panel.add_child(_portrait_tex)

	_text = RichTextLabel.new()
	_text.name = "DialogText"
	_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_text.bbcode_enabled = true
	_text.text = "「这片土地饱受战火蹂躏,我们必须夺回城堡!」"
	_text.scroll_active = false
	body.add_child(_text)

	_continue_btn = Button.new()
	_continue_btn.name = "ContinueBtn"
	_continue_btn.anchor_left = 1.0
	_continue_btn.anchor_top = 1.0
	_continue_btn.anchor_right = 1.0
	_continue_btn.anchor_bottom = 1.0
	_continue_btn.offset_left = -180.0
	_continue_btn.offset_top = -66.0
	_continue_btn.offset_right = -24.0
	_continue_btn.offset_bottom = -18.0
	_continue_btn.text = "继续 ▶"
	_continue_btn.custom_minimum_size = Vector2(150, 48)
	_root.add_child(_continue_btn)

	# 主题(GBA 火纹风 — 原 main._apply_hud_theme 给了 dialog_panel,
	# 现在 dialog_panel 不在 main 树里,主题自行应用)
	_apply_self_theme()

	# ChoiceContainer(运行时建)
	_choice_container = VBoxContainer.new()
	_choice_container.name = "ChoiceContainer"
	_choice_container.anchor_left = 0.0
	_choice_container.anchor_top = 0.0
	_choice_container.anchor_right = 1.0
	_choice_container.anchor_bottom = 1.0
	_choice_container.offset_left = 16.0
	_choice_container.offset_top = 130.0
	_choice_container.offset_right = -16.0
	_choice_container.offset_bottom = -50.0
	_choice_container.add_theme_constant_override("separation", 6)
	_choice_container.visible = false
	_root.add_child(_choice_container)


func _apply_self_theme() -> void:
	# 风格与原 main._apply_hud_theme 末尾对 DialogPanel 的处理一致
	var sb := StyleBoxFlat.new()
	sb.bg_color = MenuTheme.C_BG_PANEL
	sb.border_color = MenuTheme.C_GOLD
	sb.set_border_width_all(2)
	sb.set_corner_radius_all(3)
	sb.content_margin_left = MenuTheme.PAD
	sb.content_margin_right = MenuTheme.PAD
	sb.content_margin_top = MenuTheme.PAD
	sb.content_margin_bottom = MenuTheme.PAD
	_root.add_theme_stylebox_override("panel", sb)


# ============================================================
# 公共 API
# ============================================================

## 播放一串对话场景。可 await,返回 {"choice_value": String}。
## context 暂未消费,留作后续传 trigger 上下文。
func play(scenes: Variant, context: Dictionary = {}) -> Dictionary:
	if scenes == null:
		return {"choice_value": ""}
	var list: Array = scenes if scenes is Array else [scenes]
	if list.is_empty():
		return {"choice_value": ""}
	_choice_value = ""
	for sc in list:
		if sc is Dictionary:
			_enqueue_scene(sc)
	_start()
	await _dialog_completed
	dialogue_finished.emit(_choice_value, list.size() - 1)
	return {"choice_value": _choice_value}


## fire-and-forget 单场景
func show_dialog(scene: Dictionary) -> void:
	_enqueue_scene(scene)
	if not _active:
		_start()


## 中断当前并清队列
func hide_dialog() -> void:
	if _type_tween != null and _type_tween.is_running():
		_type_tween.kill()
	_queue.clear()
	_active = false
	_unlock_board()
	if _root != null:
		_root.visible = false
	# 唤醒可能挂着的 awaiter(用空 choice_value 兜底)
	_choice_value = ""
	if _playing_depth > 0:
		_playing_depth = 0
		_dialog_completed.emit()
	dialogue_aborted.emit()


## 硬重置(包含 heroes 缓存)
func reset() -> void:
	_heroes.clear()
	hide()


func is_playing() -> bool:
	return _active or not _queue.is_empty()


func load_portrait(p: String) -> Texture2D:
	return PortraitLoader.load(p)


## 替代旧 main.gd 直接读 _hero_speaker_map
func register_hero_speaker(dialogue_name: String, portrait_path: String) -> void:
	if dialogue_name == "":
		return
	_heroes[dialogue_name] = {"portrait_path": portrait_path}


## NetworkClient.list_heroes 回调 — 从 /heroes 响应填 _heroes
## 取代 mainline_controller 旧 _main._on_heroes_response
func _on_heroes_response(body: Variant, _code: int = 0) -> void:
	if not (body is Array):
		return
	for h in body:
		if not (h is Dictionary):
			continue
		var dialogue_name: String = str(h.get("dialogue_name", h.get("display_cn", "")))
		if dialogue_name == "":
			continue
		var portrait_url: String = str(h.get("portrait_url", ""))
		var portrait_path: String = ""
		if portrait_url != "":
			portrait_path = "res://assets/heroes/" + portrait_url.get_file()
		register_hero_speaker(dialogue_name, portrait_path)


# --- 触发点去重 helper ---
func record_turn_shown(game_id: int, turn_number: int, player_id: int) -> bool:
	var key := "%d:%d:%d" % [game_id, turn_number, player_id]
	if _seen_turn_keys.has(key):
		return false
	_seen_turn_keys[key] = true
	return true


func record_death_shown(game_id: int, unit_id: int, event_seq: int) -> bool:
	var key := "%d:%d:%d" % [game_id, unit_id, event_seq]
	if _seen_death_keys.has(key):
		return false
	_seen_death_keys[key] = true
	return true


func record_attack_shown(attacker_id: int, target_id: int, turn: int) -> bool:
	var key := "%d:%d:%d" % [attacker_id, target_id, turn]
	if _seen_attack_keys.has(key):
		return false
	_seen_attack_keys[key] = true
	return true


# ============================================================
# 内部:场景引擎
# ============================================================

func _enqueue_scene(scene: Dictionary) -> void:
	var stype: String = str(scene.get("type", "dialogue"))
	if stype == "battle_ref" or stype == "wait":
		return  # 当前不消费的两种类型
	if stype == "choice":
		var q: String = str(scene.get("question", "请选择:"))
		var choices_v: Variant = scene.get("choices", [])
		var choices: Array = choices_v if choices_v is Array else []
		_queue.append({
			"kind": KIND_CHOICE,
			"question": q,
			"choices": choices,
		})
		return
	var speaker: String = str(scene.get("speaker", scene.get("character", "")))
	var text: String = str(scene.get("text", ""))
	var col: String = str(scene.get("speaker_color", ""))
	_queue.append({
		"character": speaker,
		"text": text,
		"kind": KIND_TYPE if speaker != "" else KIND_NARRATION,
		"color": col,
	})


func _start() -> void:
	_playing_depth += 1
	if _playing_depth == 1:
		_lock_board()
	_advance()


func _advance() -> void:
	if _queue.is_empty():
		_active = false
		if _root != null:
			_root.visible = false
		_playing_depth = max(0, _playing_depth - 1)
		if _playing_depth == 0:
			_unlock_board()
			_dialog_completed.emit()
		return
	_active = true
	var entry: Dictionary = _queue.pop_front()
	var kind: int = int(entry.get("kind", KIND_TYPE))
	if kind == KIND_CHOICE:
		_render_choice(entry)
	else:
		_render_speaker_or_narration(entry)


func _render_speaker_or_narration(entry: Dictionary) -> void:
	var speaker: String = str(entry.get("character", ""))
	_name_label.text = speaker if speaker != "" else "（旁白）"
	var col_str: String = str(entry.get("color", ""))
	if col_str != "":
		_name_label.add_theme_color_override("font_color", Color(col_str))
	elif _name_label.has_theme_color_override("font_color"):
		_name_label.remove_theme_color_override("font_color")
	_set_portrait(speaker)
	_continue_btn.visible = true
	if _choice_container != null and is_instance_valid(_choice_container):
		_choice_container.visible = false
	_typewriter(str(entry.get("text", "")))


func _render_choice(entry: Dictionary) -> void:
	var q: String = str(entry.get("question", "请选择:"))
	_name_label.text = ""
	if _name_label.has_theme_color_override("font_color"):
		_name_label.remove_theme_color_override("font_color")
	_set_portrait("")
	_text.bbcode_enabled = true
	_text.text = q
	_text.visible_ratio = 1.0
	_continue_btn.visible = false
	if _choice_container == null or not is_instance_valid(_choice_container):
		return
	for child in _choice_container.get_children():
		child.queue_free()
	var choices_v: Variant = entry.get("choices", [])
	var choices: Array = choices_v if choices_v is Array else []
	for ch in choices:
		if not (ch is Dictionary):
			continue
		var value_str: String = str(ch.get("value", ""))
		var btn := Button.new()
		btn.text = str(ch.get("text", ""))
		btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		# BUG-FIX:bind value 进入回调,旧版 100% 丢弃
		btn.pressed.connect(_on_choice_selected.bind(value_str))
		_choice_container.add_child(btn)
	_choice_container.visible = true


func _on_choice_selected(value: String) -> void:
	_choice_value = value
	if _choice_container != null and is_instance_valid(_choice_container):
		_choice_container.visible = false
	if _continue_btn != null and is_instance_valid(_continue_btn):
		_continue_btn.visible = true
	choice_made.emit(value, -1)
	_advance()


func _on_continue_pressed() -> void:
	# BUG-FIX:typewriter 重写后,typing 中按继续 = 直接完成;
	# 不在 typing 中 = 推进到下一场景
	if _type_tween != null and _type_tween.is_running():
		_type_tween.kill()
		_text.visible_ratio = 1.0
		return
	_advance()


# BUG-FIX:typewriter 改用 RichTextLabel.visible_ratio(原生 + BBCode 友好)
func _typewriter(full_text: String) -> void:
	if _type_tween != null and _type_tween.is_running():
		_type_tween.kill()
	_text.bbcode_enabled = true
	_text.text = full_text
	_text.visible_ratio = 0.0
	var per_char: float = 0.03
	var duration: float = max(0.05, float(full_text.length()) * per_char)
	_type_tween = create_tween()
	_type_tween.tween_method(
		Callable(self, "_set_visible_ratio"),
		0.0, 1.0, duration
	)


func _set_visible_ratio(r: float) -> void:
	_text.visible_ratio = r


# --- 头像 ---
func _set_portrait(speaker: String) -> void:
	if _portrait_label == null or _portrait_tex == null:
		return
	if speaker == "" or not _heroes.has(speaker):
		_portrait_label.visible = true
		_portrait_tex.visible = false
		return
	var info_v: Variant = _heroes[speaker]
	if not (info_v is Dictionary):
		_portrait_label.visible = true
		_portrait_tex.visible = false
		return
	var info: Dictionary = info_v
	if info.has("portrait_tex") and info["portrait_tex"] is Texture2D:
		_portrait_tex.texture = info["portrait_tex"]
		_portrait_tex.visible = true
		_portrait_label.visible = false
		return
	var path: String = str(info.get("portrait_path", ""))
	if path == "":
		_portrait_label.visible = true
		_portrait_tex.visible = false
		return
	var tex := load_portrait(path)
	if tex != null:
		_portrait_tex.texture = tex
		_portrait_tex.visible = true
		_portrait_label.visible = false
		# 缓存
		info["portrait_tex"] = tex
	else:
		_portrait_label.visible = true
		_portrait_tex.visible = false


# --- 棋盘锁 ---
func _lock_board() -> void:
	if _lock_depth == 0:
		InputState.lock()
	_lock_depth += 1


func _unlock_board() -> void:
	if _lock_depth == 0:
		return
	_lock_depth -= 1
	if _lock_depth == 0:
		InputState.unlock()
