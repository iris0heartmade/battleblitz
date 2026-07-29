## Mainline response handlers — Phase 2 small-step extraction.
##
## Six key response handlers moved verbatim from ``main.gd`` to live
## alongside :class:`MainlineSession`.  Each handler is a ``static``
## function that takes the mainline session (via ``session: MainlineSession``)
## and the main.gd node (``host: Node``) so it can dispatch back into
## main.gd's UI helpers (``_update_status``, ``_show_view``, etc.) via
## ``host.call(...)`` without needing a class_name on main.gd.
##
## The originals are preserved as one-line shims in main.gd so any
## existing callback wiring (``Callable(self, "_on_mainline_start_response")``
## etc.) keeps working unchanged.
##
## Handlers covered here:
##   * :func:`on_prepare_response`        — GET /mainlines/{id}/prepare
##   * :func:`on_start_response`          — POST /mainlines/{id}/start
##   * :func:`on_auto_abandon_response`   — POST /mainlines/{id}/abandon (auto-retry path)
##   * :func:`on_advance_response`        — POST /mainlines/{id}/advance
##   * :func:`on_next_battle_response`    — POST /mainlines/{id}/next-battle (delegates to start)
##   * :func:`on_abandon_response`        — POST /mainlines/{id}/abandon (user path)
##   * :func:`on_complete_response`       — POST /mainlines/{id}/prepare/complete
class_name MainlineResponses

# Convention: handlers take (host, session, body, code[, extra]).
# `host` is the main.gd node; we use `host.call("name", ...)` to
# invoke its UI helpers because main.gd has no class_name.


# ============================================================
# GET /mainlines/{id}/prepare
# ============================================================


static func on_prepare_response(
	host: Node, session: MainlineSession, body: Variant, code: int, mainline_id: String
) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		host.call("_update_status", "整备页面加载失败 (HTTP %d)" % code)
		return
	session.prepare_payload = (body as Dictionary).duplicate(true)
	var title: String = str(body.get("title", mainline_id))
	var battle_index: int = int(body.get("battle_index", 0)) + 1
	var total: int = int(body.get("total_battles", 1))
	host.call(
		"_update_status",
		"准备: %s (战斗 %d/%d)" % [title, battle_index, total],
	)
	host.call("_set_mainline_page", "prepare")


# ============================================================
# POST /mainlines/{id}/start (with 409 auto-retry on mainline_already_active)
# ============================================================


static func on_start_response(
	host: Node, session: MainlineSession, body: Variant, code: int
) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		if (
			code == 409
			and _is_mainline_already_active_response(body)
			and not session.auto_retry_pending
		):
			session.auto_retry_pending = true
			var retry_id: String = session.selected_mainline_id
			if retry_id == "":
				retry_id = "chapter_01_steel_rebellion"
			host.call(
				"_update_status",
				"已有主线进度,正在放弃旧进度并重试...",
			)
			var user_name = host.get("_user_name")
			NetworkClient.abandon_mainline(
				retry_id,
				user_name,
				Callable(host, "_on_mainline_auto_abandon_response").bind(retry_id),
			)
			return
		session.auto_retry_pending = false
		var msg: String = "主线启动失败"
		if body is Dictionary:
			msg = "主线启动失败: %s" % str(body.get("detail", body.get("message", msg)))
		host.call("_update_status", msg)
		host.call("_show_view", "mainline")
		return
	session.auto_retry_pending = false
	var game_id: int = int(body.get("game_id", 0))
	var player_id: int = int(body.get("player_id", 0))
	if game_id <= 0 or player_id <= 0:
		host.call("_update_status", "主线启动失败: 响应缺少对局或玩家编号")
		host.call("_show_view", "mainline")
		return
	host.set("_game_id", game_id)
	host.set("_player_id", player_id)
	GameState.local_player_id = player_id
	UserSettings.set_value("session.v1.last_game_id", game_id)
	UserSettings.set_value("session.v1.last_player_id", player_id)
	session.active_mainline_id = str(body.get("mainline_id", ""))
	session.battle_game_id = game_id
	session.persist_active()
	UserSettings.set_value("session.v1.mainline_player_id", player_id)
	var battle_index: int = int(body.get("battle_index", 0)) + 1
	var total_battles: int = int(body.get("total_battles", 1))
	host.call(
		"_update_status",
		"主线战斗 %d/%d 已创建,进入棋盘..." % [battle_index, total_battles],
	)
	var dialogue_path: String = str(body.get("pre_battle_dialogue_url", ""))
	if dialogue_path != "":
		var user_name = host.get("_user_name")
		NetworkClient.fetch_mainline_dialogue(
			dialogue_path,
			Callable(host, "_on_mainline_dialogue_response"),
		)
	host.call("_show_view", "game")
	var next_btn = host.get("battle_mainline_next_btn")
	if next_btn != null and is_instance_valid(next_btn):
		next_btn.visible = false
	NetworkClient.connect_to_game(game_id, player_id)
	NetworkClient.get_game_state(game_id, Callable(host, "_on_state_poll_response"))


# ============================================================
# POST /mainlines/{id}/abandon (auto-retry intermediate)
# ============================================================


static func on_auto_abandon_response(
	host: Node, session: MainlineSession, body: Variant, code: int, mainline_id: String
) -> void:
	if code < 200 or code >= 300:
		session.auto_retry_pending = false
		var msg: String = "放弃旧主线失败"
		if body is Dictionary:
			msg = "放弃旧主线失败: %s" % str(body.get("detail", body.get("message", msg)))
		host.call("_update_status", msg)
		host.call("_show_view", "mainline")
		return
	host.call("_update_status", "旧主线已放弃,重新创建战斗...")
	var user_name = host.get("_user_name")
	NetworkClient.start_mainline(
		mainline_id,
		user_name,
		false,
		[],
		Callable(host, "_on_mainline_start_response"),
		true,
	)


# ============================================================
# POST /mainlines/{id}/advance
# ============================================================


static func on_advance_response(
	host: Node, session: MainlineSession, body: Variant, code: int
) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		var msg: String = "主线推进失败"
		if body is Dictionary:
			msg = "主线推进失败: %s" % str(body.get("detail", body.get("message", msg)))
		host.call("_update_status", msg)
		return
	var state: String = str(body.get("state", "battle"))
	var battle_index: int = int(body.get("battle_index", 0)) + 1
	var total_battles: int = int(body.get("total_battles", 1))
	var dialogue_path: String = str(body.get("post_battle_dialogue_url", ""))
	if dialogue_path != "":
		var user_name = host.get("_user_name")
		NetworkClient.fetch_mainline_dialogue(
			dialogue_path,
			Callable(host, "_on_mainline_dialogue_response"),
		)
	var next_btn = host.get("battle_mainline_next_btn")
	if state == "victory":
		var rewards_v: Variant = body.get("rewards", {})
		var rewards: Dictionary = (rewards_v if rewards_v is Dictionary else {}) as Dictionary
		var reward_bits: Array[String] = []
		if int(rewards.get("gold", 0)) > 0:
			reward_bits.append("+%d 金币" % int(rewards.get("gold", 0)))
		if str(rewards.get("unlock_class", "")) != "":
			reward_bits.append("解锁 %s" % str(rewards.get("unlock_class", "")))
		session.clear_active()
		if next_btn != null and is_instance_valid(next_btn):
			next_btn.visible = false
		host.call(
			"_update_status",
			"主线通关%s" % (": " + ", ".join(reward_bits) if reward_bits.size() > 0 else ""),
		)
	else:
		host.call(
			"_update_status",
			"主线推进到战斗 %d/%d" % [battle_index, total_battles],
		)
		if next_btn != null and is_instance_valid(next_btn):
			next_btn.visible = true
	# P0:服务端 /advance 写自动存档 → toast 提示(对齐 WebUI autoSaveToast)
	var auto_save_v: Variant = body.get("auto_save", {})
	if auto_save_v is Dictionary and auto_save_v.has("label"):
		host.call(
			"_show_auto_save_toast",
			"💾 自动存档完毕 ✓  %s" % str(auto_save_v.get("label", "")),
			1800.0,
		)


# ============================================================
# POST /mainlines/{id}/next-battle (alias to start)
# ============================================================


static func on_next_battle_response(
	host: Node, session: MainlineSession, body: Variant, code: int
) -> void:
	on_start_response(host, session, body, code)


# ============================================================
# POST /mainlines/{id}/abandon (user-initiated)
# ============================================================


static func on_abandon_response(
	host: Node, session: MainlineSession, body: Variant, code: int
) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		var msg: String = "放弃主线失败"
		if body is Dictionary:
			msg = "放弃主线失败: %s" % str(body.get("detail", body.get("message", msg)))
		host.call("_update_status", msg)
		return
	session.clear_active()
	session.auto_retry_pending = false
	host.call("_update_status", "主线已放弃")
	host.call("_show_view", "mainline")


# ============================================================
# POST /mainlines/{id}/prepare/complete
# ============================================================


static func on_complete_response(
	host: Node, session: MainlineSession, body: Variant, code: int
) -> void:
	if code < 200 or code >= 300 or not (body is Dictionary):
		host.call("_update_status", "完成整备失败 (HTTP %d)" % code)
		return
	var label: String = str(body.get("label", ""))
	host.call("_show_auto_save_toast", "💾 %s ✓" % label, 1800.0)
	host.call("_update_status", "整备完成: %s" % label)


# ============================================================
# Internal helpers
# ============================================================


static func _is_mainline_already_active_response(body: Variant) -> bool:
	if not (body is Dictionary):
		return false
	var detail_v: Variant = body.get("detail", {})
	if detail_v is Dictionary:
		return str(detail_v.get("error", "")) == "mainline_already_active"
	return str(detail_v).contains("mainline_already_active")
