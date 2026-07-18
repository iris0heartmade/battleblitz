"""Real-browser regression coverage for the mainline entry flow.

These tests deliberately live outside normal pytest collection.  They boot a
separate Uvicorn process with a temporary SQLite database and only run when
``requirements-e2e.txt`` plus the Chromium browser have been installed.

Run from ``game/``:

    python -m pytest tests/e2e -m e2e -q
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import Page, sync_playwright
except ImportError:  # Keep two collected tests skipped, rather than exit 5.
    PlaywrightError = RuntimeError
    sync_playwright = None


GAME_DIR = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(base_url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("E2E Uvicorn process exited before it became ready")
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except urllib.error.URLError:
            time.sleep(0.2)
    raise RuntimeError("E2E Uvicorn process did not become ready within 30 seconds")


@pytest.fixture(scope="module")
def mainline_server(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Serve the UI against a per-module database, never battleblitz.db."""
    tmp_dir = tmp_path_factory.mktemp("mainline_e2e")
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite+aiosqlite:///{tmp_dir / 'mainline-e2e.db'}",
        "BB_LOG_DIR": str(tmp_dir / "logs"),
        "PYTHONPATH": str(GAME_DIR),
    })
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=GAME_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_server(base_url, process)
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.fixture(scope="module")
def browser():
    if sync_playwright is None:
        pytest.skip(
            "install game/requirements-e2e.txt and run `python -m playwright install chromium`",
        )
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            pytest.skip(
                "Chromium is unavailable; run `python -m playwright install chromium`: "
                f"{exc}",
            )
        try:
            yield chromium
        finally:
            chromium.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()


def _api_json(base_url: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read())


def _profile(base_url: str, user_name: str) -> dict:
    with urllib.request.urlopen(
        f"{base_url}/profile/{urllib.parse.quote(user_name)}", timeout=15
    ) as response:
        return json.loads(response.read())


def _open_mainline_list(page: Page, base_url: str, user_name: str) -> None:
    page.goto(f"{base_url}/ui/")
    page.evaluate(
        """(name) => {
            localStorage.setItem("battleblitz.settings.v1", JSON.stringify({
                playerName: name, preferredColor: "", theme: "classic",
                refreshSeconds: 3, soundOn: false,
            }));
            localStorage.removeItem("battleblitz.session.v1");
        }""",
        user_name,
    )
    page.reload()
    page.locator('[data-action="goto-mainline-list"]').click()
    page.locator("#view-mainline-list:not([hidden])").wait_for()
    page.locator('#mainline-list [data-mainline-id="chapter_test_01"]').wait_for()


def _chapter_start_button(page: Page, mainline_id: str):
    return page.locator(
        f'#mainline-list [data-mainline-id="{mainline_id}"] '
        '[data-action="mainline-card-click"]'
    )


@pytest.mark.e2e
def test_prepare_start_enters_battle_map(page: Page, mainline_server: str) -> None:
    """The preparation page's start button must hand off to the board."""
    _open_mainline_list(page, mainline_server, "e2e_prepare_start")

    _chapter_start_button(page, "chapter_test_01").click()
    page.locator("#view-mainline-prepare:not([hidden])").wait_for()
    expect_title = page.locator("#mainline-prepare-title")
    assert "测试章节 1" in expect_title.text_content()

    # The equipment API refreshes preparation data.  The hero assignment
    # count must be derived from that refreshed equipment state, not from a
    # stale client-only draft.
    page.locator('[data-action="mainline-prepare-tab"][data-tab="items"]').click()
    hero_row = page.locator('[data-action="mainline-prepare-focus-hero"]').first
    assert "已分配 2" in hero_row.text_content()
    page.locator('[data-action="mainline-prepare-equip"][data-slot="accessory"]:not([data-equipment-id])').click()
    assert "已分配 1" in hero_row.text_content()
    page.locator('[data-action="mainline-prepare-equip"][data-equipment-id="ruby_ring"]').click()
    assert "已分配 2" in hero_row.text_content()

    # Dialogue playback is independently tested.  Bypassing it here keeps
    # this regression focused on the preparation -> map hand-off.
    page.evaluate("() => { window.mainlineView._playDialogueSafely = async () => []; }")
    page.locator('[data-action="mainline-start-battle"]').click()
    page.locator("#view-game:not([hidden])").wait_for(timeout=15_000)
    page.locator(".cell").first.wait_for(timeout=15_000)


@pytest.mark.e2e
def test_selecting_other_chapter_requires_confirmation(page: Page, mainline_server: str) -> None:
    """Cancel keeps the active chapter; accept opens the clicked chapter's prep."""
    user_name = "e2e_selected_chapter"
    _api_json(
        mainline_server,
        "/mainlines/chapter_test_02/start",
        {"user_name": user_name, "skip_intro": True},
    )
    assert _profile(mainline_server, user_name)["active_mainline"] == "chapter_test_02"

    _open_mainline_list(page, mainline_server, user_name)
    start_first = _chapter_start_button(page, "chapter_test_01")

    page.once("dialog", lambda dialog: dialog.dismiss())
    start_first.click()
    page.locator("#view-mainline-list:not([hidden])").wait_for()
    assert _profile(mainline_server, user_name)["active_mainline"] == "chapter_test_02"

    page.once("dialog", lambda dialog: dialog.accept())
    start_first.click()
    page.locator("#view-mainline-prepare:not([hidden])").wait_for()
    assert "测试章节 1" in page.locator("#mainline-prepare-title").text_content()
    assert _profile(mainline_server, user_name)["active_mainline"] is None
