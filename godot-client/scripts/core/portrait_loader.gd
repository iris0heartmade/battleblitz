extends RefCounted
## PortraitLoader — 对话头像与单位信息面板共用,从原 main.gd::_load_portrait 抽出。
##
## T:#18 备注:ResourceLoader 优先(res:// 路径 Godot 4 推荐走 ResourceLoader),
## 退回 Image.load + globalize_path。早期直接 img.load(res://...) 在
## 4.7 上偶发返回 null,导致 _set_unit_info_portrait 走"文件不存在"分支
## 把整个 panel.visible = false,玩家看到的就是"一块不透明面版没图"。
##
## 注意:不写 class_name —— 跨文件 class_name 引用在 headless 跑测试时
## 全局类缓存未建立,会撞 Parse Error。统一用 const X = preload(...)。

static func load(res_path: String) -> Texture2D:
	if res_path == "":
		return null
	if ResourceLoader.exists(res_path):
		var res := ResourceLoader.load(res_path)
		if res is Texture2D:
			return res
	var img := Image.new()
	var abs_path: String = res_path
	if res_path.begins_with("res://"):
		abs_path = ProjectSettings.globalize_path(res_path)
	if img.load(abs_path) != OK:
		return null
	return ImageTexture.create_from_image(img)
