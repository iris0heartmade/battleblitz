"""
回归测试：所有返回 204 No Content 的 DELETE 接口。

背景
----
FastAPI 从 0.115 起，只要路由函数的返回注解是 `-> None`，就会把
`NoneType` 当成「要返回响应体」的 response_model。而 204 按 HTTP 规范
不允许带响应体，于是 FastAPI 在**注册路由时**直接抛断言：

    AssertionError: Status code 204 must not have a response body

这个断言发生在 import 阶段 —— 不是某一个接口报错，而是整个
`app.main` 都加载不起来，后端完全无法启动。

修复方式是在路由装饰器上显式写 `response_model=None`，表示
「这个接口确实没有响应体」。接口行为没有任何变化（204 本来就不带
响应体），但 FastAPI 不再把它误判为需要响应体。

本文件的作用是：
1. 端到端跑通三个 204 删除接口，断言状态码是 204 且响应体为空；
2. 断言这些接口删除后资源确实没了（再查一次是 404）；
3. 扫描所有已注册的路由，只要状态码是 204，就必须显式声明
   `response_model=None`，防止以后新增接口时再踩同一个坑。
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


# 15x15 的合法布局，字符含义见 app/schemas.py 的地图编辑器契约：
# P=草地平原, F=森林, C=城堡地块, M=山丘(不可通行)
_VALID_LAYOUT = [
    "PPFFFFFFFFFFFFM",
    "PPFFFFFFFFFFFFM",
    "CCCCCCCCCCCCCCM",
    "CCCCCCCCCCCCCCM",
    "CCCCCCCCCCCCCCM",
    "CCCCCCCCCCCCCCM",
    "CCCCCCCCCCCCCCM",
    "CCCCCCCCCCCCCCM",
    "CCCCCCCCCCCCCCM",
    "CCCCCCCCCCCCCCM",
    "CCCCCCCCCCCCCCM",
    "CCCCCCCCCCCCCCM",
    "CCCCCCCCCCCCCCM",
    "MFFFFFFFFFFFFFP",
    "MFFFFFFFFFFFFFP",
]


@pytest.fixture
async def api_client():
    """ASGI 进程内客户端 —— 走完整路由栈，和真实 HTTP 请求同一条路径。"""
    from app.main import app
    from app.database import init_db

    await init_db()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.mark.integration
class TestDeleteGameReturns204:
    """DELETE /games/{game_id} —— 存档管理界面「删除存档」按钮。"""

    async def test_delete_game_returns_204_and_empty_body(self, api_client):
        created = await api_client.post("/games", json={"name": "Del204"})
        assert created.status_code in (200, 201), created.text
        game_id = created.json()["id"]

        resp = await api_client.delete(f"/games/{game_id}")

        assert resp.status_code == 204, resp.text
        # 204 不允许有响应体 —— 一旦 FastAPI 又把 `-> None` 误判成
        # 响应体模型，这里会拿到 `null` 之类的内容。
        assert resp.content == b"", f"204 不应带响应体，实际: {resp.content!r}"

    async def test_deleted_game_is_gone(self, api_client):
        created = await api_client.post("/games", json={"name": "DelGone"})
        game_id = created.json()["id"]
        await api_client.delete(f"/games/{game_id}")

        resp = await api_client.get(f"/games/{game_id}/lobby")

        assert resp.status_code == 404, resp.text


@pytest.mark.integration
class TestDeleteCustomMapReturns204:
    """DELETE /editor/maps/{map_id} —— 地图编辑器的「删除地图」按钮。"""

    async def test_delete_custom_map_returns_204_and_empty_body(self, api_client):
        body = {
            "name": "Del204Map",
            "size": {"width": 15, "height": 15},
            "biome": "grass",
            "layout": _VALID_LAYOUT,
            "initial_units": [],
        }
        created = await api_client.post("/editor/maps", json=body)
        assert created.status_code == 201, created.text
        map_id = created.json()["id"]

        resp = await api_client.delete(f"/editor/maps/{map_id}")

        assert resp.status_code == 204, resp.text
        assert resp.content == b"", f"204 不应带响应体，实际: {resp.content!r}"

    async def test_deleted_custom_map_is_gone(self, api_client):
        body = {
            "name": "Del204MapGone",
            "size": {"width": 15, "height": 15},
            "biome": "grass",
            "layout": _VALID_LAYOUT,
            "initial_units": [],
        }
        created = await api_client.post("/editor/maps", json=body)
        map_id = created.json()["id"]
        await api_client.delete(f"/editor/maps/{map_id}")

        resp = await api_client.get(f"/editor/maps/{map_id}")

        assert resp.status_code == 404, resp.text


@pytest.mark.integration
class TestDeleteProgressionUnitReturns204:
    """DELETE /progression/units/{unit_id} —— 养成系统弃用单位。"""

    async def test_delete_unit_returns_204_and_empty_body(self, api_client):
        profile = await api_client.post(
            "/progression/profiles", json={"user_name": "del204"}
        )
        assert profile.status_code in (200, 201), profile.text
        profile_id = profile.json()["id"]

        unit = await api_client.post(
            f"/progression/profiles/{profile_id}/units",
            json={"base_type": "archer", "nickname": "Bye204"},
        )
        assert unit.status_code in (200, 201), unit.text
        unit_id = unit.json()["id"]

        resp = await api_client.delete(f"/progression/units/{unit_id}")

        assert resp.status_code == 204, resp.text
        assert resp.content == b"", f"204 不应带响应体，实际: {resp.content!r}"


@pytest.mark.integration
class TestNoRouteCanBreakAppImport:
    """防止回归：任何 204 路由都必须显式声明 response_model=None。

    这是本文件最重要的一条 —— 它把「以后谁再写一个带 `-> None`
    的 204 接口就会整个后端起不来」这个坑，变成一条会失败的测试，
    而不是等到部署时才炸。
    """

    async def test_all_204_routes_declare_no_response_model(self):
        from app.main import app

        offenders = [
            f"{route.path} [{route.methods}]"
            for route in app.routes
            if getattr(route, "status_code", None) == 204
            and getattr(route, "response_model", None) is not None
        ]

        assert not offenders, (
            "以下 204 路由没有声明 response_model=None，"
            "FastAPI >=0.115 会在启动时断言失败：\n  " + "\n  ".join(offenders)
        )

    async def test_app_imports_successfully(self):
        """最直接的护栏：后端必须能 import 起来。"""
        from app.main import app

        assert len(app.routes) > 0
