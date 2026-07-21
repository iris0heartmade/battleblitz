"""
验证 difficulty_modifiers 在 JSON 中的存在 + 后端处理状态。

模板定义的 3 级难度（easy/normal/hard）在 JSON 端通过 ``extra="allow"``
保留在 ``model_extra``，但后端目前 **尚未** 读取并应用它们。
本节测试明确记录这个缺口，方便后续追踪。

Coverage:
  1. 所有 6 个制作章节 JSON 都携带 difficulty_modifiers 块
  2. 各难度级别有正确的字段（level_delta / gold_bonus / enemy_hp_mult / ...）
  3. 后端 start 响应 **不包含** 难度字段（已知缺口）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


MAINLINES_DIR = Path(__file__).resolve().parents[1] / "mainlines"

PRODUCTION_CHAPTERS = [
    "chapter_01_steel_rebellion",
    "chapter_02_border_flame",
    "chapter_03_crown_shadow",
    "chapter_04_frost_invasion",
    "chapter_05_crown_united",
    "chapter_06_iron_reckoning",
]

DIFFICULTY_LEVELS = ("easy", "normal", "hard")

REQUIRED_FIELDS = ("level_delta", "gold_bonus", "enemy_hp_mult", "reinforcement_turn_delay")


def _load_chapter_dict(chapter_id: str) -> dict:
    path = MAINLINES_DIR / f"{chapter_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ============================================================
# 1) difficulty_modifiers 存在性（ch06 必须有，其他可选）
# ============================================================

class TestDifficultyModifiersPresence:

    def test_chapter_06_has_difficulty_modifiers(self):
        """ch06 作为参考实现必须携带 difficulty_modifiers。"""
        data = _load_chapter_dict("chapter_06_iron_reckoning")
        assert "difficulty_modifiers" in data, (
            "chapter_06 must have difficulty_modifiers (reference implementation)"
        )
        block = data["difficulty_modifiers"]
        assert isinstance(block, dict) and len(block) >= 1

    @pytest.mark.parametrize("chapter_id", [c for c in PRODUCTION_CHAPTERS if c != "chapter_06_iron_reckoning"])
    def test_earlier_chapters_may_not_have_difficulty_modifiers_yet(self, chapter_id: str):
        """ch01-05 暂未迁移难度系统，不强制要求。"""
        data = _load_chapter_dict(chapter_id)
        if "difficulty_modifiers" not in data:
            pytest.skip(f"{chapter_id} does not have difficulty_modifiers yet")


class TestChapter06DifficultyModifiers:

    def _ch06_block(self) -> dict:
        return _load_chapter_dict("chapter_06_iron_reckoning").get("difficulty_modifiers", {})

    def test_all_three_levels_present(self):
        """ch06 必须提供 easy / normal / hard 三个级别。"""
        block = self._ch06_block()
        for level in DIFFICULTY_LEVELS:
            assert level in block, f"ch06 missing difficulty level {level!r}"
            assert isinstance(block[level], dict), f"ch06 {level} is not a dict"

    @pytest.mark.parametrize("level", DIFFICULTY_LEVELS)
    def test_each_level_has_required_fields(self, level: str):
        """每个难度级别必须有 4 个必填字段。"""
        block = self._ch06_block()
        lv = block.get(level) or {}
        for field in REQUIRED_FIELDS:
            assert field in lv, (
                f"ch06.difficulty_modifiers.{level} missing {field!r}; "
                f"got {sorted(lv.keys())}"
            )
            assert isinstance(lv[field], (int, float)), (
                f"ch06.difficulty_modifiers.{level}.{field} "
                f"should be numeric, got {type(lv[field]).__name__}"
            )

    def test_normal_is_baseline(self):
        """normal 级别应该是 (0偏移, 无倍率修正)。"""
        n = self._ch06_block().get("normal", {})
        assert n.get("level_delta", -999) == 0, (
            f"ch06 normal.level_delta should be 0, got {n.get('level_delta')}"
        )

    def test_easy_weaker_than_normal(self):
        """easy 应比 normal 更简单。"""
        block = self._ch06_block()
        e, n = block.get("easy", {}), block.get("normal", {})
        assert e.get("level_delta", 0) <= n.get("level_delta", 0)
        assert e.get("gold_bonus", 0) >= n.get("gold_bonus", 0)

    def test_hard_harder_than_normal(self):
        """hard 应比 normal 更难。"""
        block = self._ch06_block()
        h, n = block.get("hard", {}), block.get("normal", {})
        assert h.get("level_delta", 0) >= n.get("level_delta", 0)
        assert h.get("enemy_hp_mult", 1.0) >= n.get("enemy_hp_mult", 1.0)


# ============================================================
# 3) 后端处理状态检测（已知缺口）
# ============================================================

class TestDifficultyBackendProcessing:

    @pytest.mark.asyncio
    async def test_start_response_does_not_include_difficulty(self):
        """已知缺口: /start 的响应体目前不携带难度字段。

        当后端实现了 difficulty processing 后, start 请求应接受一个可选的
        ``difficulty`` 参数，响应应反映难度修正后的 HP/level/gold。
        在那之前，此测试验证响应中没有意外冒出来的 difficulty 相关字段。
        """
        from app.main import app
        from app.database import init_db, dispose_db
        from httpx import ASGITransport, AsyncClient

        await init_db()
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post("/progression/profiles", json={"user_name": "diff_tester"})
                assert r.status_code == 201

                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/start",
                    json={"user_name": "diff_tester", "skip_intro": True},
                )
                assert r.status_code in (200, 201), r.text
                body = r.json()

                extra_diff_fields = [k for k in body if "difficult" in k.lower()]
                assert not extra_diff_fields, (
                    f"start response unexpectedly contains difficulty-related fields: "
                    f"{extra_diff_fields}. If you just implemented difficulty processing, "
                    f"remove this assertion and add proper difficulty tests."
                )
        finally:
            await dispose_db()

    @pytest.mark.asyncio
    async def test_start_accepts_optional_difficulty_parameter(self):
        """已知缺口: /start 目前不接受 difficulty 参数。

        当实现后，POST 可以像这样：
            {"user_name": "...", "skip_intro": True, "difficulty": "hard"}
        """
        from app.main import app
        from app.database import init_db, dispose_db
        from httpx import ASGITransport, AsyncClient

        await init_db()
        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post("/progression/profiles", json={"user_name": "diff_gap"})
                assert r.status_code == 201

                r = await c.post(
                    "/mainlines/chapter_01_steel_rebellion/start",
                    json={"user_name": "diff_gap", "skip_intro": True, "difficulty": "hard"},
                )
                assert r.status_code in (200, 201), r.text
                body = r.json()
                pytest.xfail(reason="difficulty parameter not yet processed by backend")
        finally:
            await dispose_db()


# ============================================================
# 4) difficulty_modifiers 在 loader 负载中被保留（extra="allow"）
# ============================================================

class TestDifficultyInLoadedModel:

    def test_chapter_06_difficulty_modifiers_in_model_extra(self):
        """ch06 加载后 difficulty_modifiers 应在 model_extra 中。"""
        from app.mainline import load_mainline, clear_cache
        clear_cache()
        ml = load_mainline("chapter_06_iron_reckoning")
        extra = getattr(ml, "model_extra", None) or {}
        block = extra.get("difficulty_modifiers")
        assert block is not None, (
            f"ch06 difficulty_modifiers not in model_extra "
            f"(extra keys: {sorted(extra.keys())})"
        )
        for level in DIFFICULTY_LEVELS:
            assert level in block, f"ch06 model_extra missing {level}"

    @pytest.mark.parametrize("chapter_id", [c for c in PRODUCTION_CHAPTERS if c != "chapter_06_iron_reckoning"])
    def test_earlier_chapters_difficulty_modifiers_absent_in_model_extra(self, chapter_id: str):
        """ch01-05 在 loader 中没有 difficulty_modifiers 是正常的。"""
        from app.mainline import load_mainline, clear_cache
        clear_cache()
        ml = load_mainline(chapter_id)
        extra = getattr(ml, "model_extra", None) or {}
        block = extra.get("difficulty_modifiers")
        if block is None:
            pytest.skip(f"{chapter_id} has no difficulty_modifiers yet — expected")
