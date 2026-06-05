"""tests/test_e2e_mcp.py — Real-browser end-to-end tests for the visus-web MCP server.

These tests drive the actual tool functions (imported from visus.web.mcp.server)
against the local fixture HTTP server. They require a real headless Chrome browser.

Run subset:
    uv run pytest tests/test_e2e_mcp.py -v --no-cov -m browser
"""

from __future__ import annotations

import os

import pytest

# Force headless before the server module is imported (session reads env at page-open time)
os.environ["VISUS_WEB_HEADLESS"] = "1"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def srv(base_url: str):  # type: ignore[no-untyped-def]
    """Fresh session + (server_module, base_url) pair for each test."""
    from visus.web.mcp import server

    server._session.close()  # ensure clean slate
    yield server, base_url
    server._session.close()


# ---------------------------------------------------------------------------
# Navigation + inspect
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_navigate_title_url(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    result = server.browser_navigate(f"{base_url}/forms.html")
    assert "navigated" in result
    assert server.browser_title() == "forms fixture"
    assert "forms.html" in server.browser_url()


@pytest.mark.browser
def test_snapshot_contains_textbox(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    snap = server.browser_snapshot()
    assert isinstance(snap, list)
    assert len(snap) > 0
    # The forms fixture has an input labeled "Username"
    assert any(e["role"] == "textbox" and e["name"] == "Username" for e in snap), (
        f"Expected textbox/Username in snapshot, got: {snap}"
    )


@pytest.mark.browser
def test_fill_and_get_attribute(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    server.browser_fill("ada99", role="textbox", name="Username")
    # Use evaluate to read DOM property (get_attribute returns HTML attr, not DOM property)
    val = server.browser_evaluate("() => document.getElementById('user').value")
    assert val == "ada99"


@pytest.mark.browser
def test_get_text(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    # The span with data-testid="status" contains "online"
    txt = server.browser_get_text(selector="[data-testid='status']")
    assert txt == "online"


@pytest.mark.browser
def test_count(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    # Three <li> items in the list
    count = server.browser_count(selector="#items li")
    assert count == 3


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_click_button(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/actions.html")
    server.browser_click(selector="#counter")
    count_text = server.browser_get_text(selector="#count")
    assert count_text == "1"


@pytest.mark.browser
def test_dblclick(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/interactions.html")
    server.browser_dblclick(selector="#dbl")
    result = server.browser_get_text(selector="#dblres")
    assert result == "double"


@pytest.mark.browser
def test_press_enter(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/interactions.html")
    server.browser_press("Enter", selector="#txt")
    result = server.browser_get_text(selector="#pressres")
    assert result == "enter"


@pytest.mark.browser
def test_hover(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/interactions.html")
    server.browser_hover(selector="#hovertarget")
    result = server.browser_get_text(selector="#hoverres")
    assert result == "hovered"


@pytest.mark.browser
def test_check_uncheck(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/interactions.html")
    server.browser_check(selector="#cb")
    state = server.browser_get_text(selector="#cbstate")
    assert state == "on"
    server.browser_uncheck(selector="#cb")
    state2 = server.browser_get_text(selector="#cbstate")
    assert state2 == "off"


@pytest.mark.browser
def test_select_option(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/interactions.html")
    server.browser_select_option("y", selector="#sel")
    # Use evaluate to read DOM property (get_attribute returns HTML attr, not current value)
    result = server.browser_evaluate("() => document.getElementById('sel').value")
    assert result == "y"


@pytest.mark.browser
def test_focus_and_clear(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/interactions.html")
    server.browser_focus(selector="#txt")
    # The #txt input doesn't set focusres, but focus must not crash
    # Now clear the field and verify it's empty
    server.browser_clear(selector="#txt")
    val = server.browser_evaluate("() => document.getElementById('txt').value")
    assert val == ""


@pytest.mark.browser
def test_reload(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    result = server.browser_reload()
    assert "reloaded" in result


@pytest.mark.browser
def test_navigate_back_forward(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    server.browser_navigate(f"{base_url}/rpa.html")
    assert "rpa.html" in server.browser_url()
    server.browser_navigate_back()
    assert "forms.html" in server.browser_url()
    server.browser_navigate_forward()
    assert "rpa.html" in server.browser_url()


# ---------------------------------------------------------------------------
# Wait / expect
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_wait_for_visible(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/actions.html")
    # #counter is always visible
    result = server.browser_wait_for(state="visible", selector="#counter")
    assert result == "element is visible"


@pytest.mark.browser
def test_expect_text_pass(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/rpa.html")
    result = server.browser_expect_text("hello box", selector="#box")
    assert result == "PASSED"


@pytest.mark.browser
def test_expect_text_fail(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/rpa.html")
    result = server.browser_expect_text("NOT HERE", selector="#box")
    assert result.startswith("FAILED")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_tabs(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    # Initially 1 tab
    tabs = server.browser_tab_list()
    assert len(tabs) == 1
    assert tabs[0]["index"] == 0

    # Open new tab
    server.browser_tab_new(f"{base_url}/rpa.html")
    tabs2 = server.browser_tab_list()
    assert len(tabs2) == 2
    assert "rpa.html" in tabs2[1]["url"]

    # Switch back to tab 0
    server.browser_tab_select(0)
    assert "forms.html" in server.browser_url()

    # Close tab 1
    server.browser_tab_close(1)
    tabs3 = server.browser_tab_list()
    assert len(tabs3) == 1


@pytest.mark.browser
def test_tab_list_entries_expose_handle(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    tabs = server.browser_tab_list()
    assert tabs[0].get("handle")  # stable, non-empty handle string
    assert isinstance(tabs[0]["handle"], str)


@pytest.mark.browser
def test_tab_list_includes_external_window_open_tab(srv):  # type: ignore[no-untyped-def]
    """A tab opened by window.open (no expect_popup, no follow) appears in tab_list."""
    import time

    server, base_url = srv
    server.browser_navigate(f"{base_url}/popups.html")
    assert len(server.browser_tab_list()) == 1
    server.browser_click(selector="#pop")  # window.open('/forms.html','_blank')

    deadline = time.monotonic() + 5
    tabs = server.browser_tab_list()
    while len(tabs) < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
        tabs = server.browser_tab_list()
    assert len(tabs) == 2
    assert any("forms.html" in t["url"] for t in tabs)


@pytest.mark.browser
def test_tab_activate_by_handle(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")  # tab 0
    server.browser_tab_new(f"{base_url}/rpa.html")  # tab 1 (current)
    tabs = server.browser_tab_list()
    assert len(tabs) == 2
    handle0 = tabs[0]["handle"]

    server.browser_tab_activate(handle0)
    assert "forms.html" in server.browser_url()


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_handle_dialog_alert(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/popups.html")
    # Click button that triggers an alert after 50ms, then handle it
    server.browser_click(selector="#alertbtn")
    result = server.browser_handle_dialog(accept=True)
    assert "hi there" in result
    assert "accepted" in result


@pytest.mark.browser
def test_handle_dialog_confirm_dismiss(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/popups.html")
    server.browser_click(selector="#confirmbtn")
    result = server.browser_handle_dialog(accept=False)
    assert "dismissed" in result
    # The page sets #cres to "no" when dismissed
    import time

    time.sleep(0.1)
    cres = server.browser_get_text(selector="#cres")
    assert cres == "no"


# ---------------------------------------------------------------------------
# Cookies
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_cookies(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    # Clear first
    server.browser_clear_cookies()
    cookies_before = server.browser_get_cookies()
    assert cookies_before == []

    # Add a cookie
    server.browser_add_cookies([{"name": "test_cookie", "value": "hello", "url": base_url}])
    cookies_after = server.browser_get_cookies()
    assert any(c["name"] == "test_cookie" and c["value"] == "hello" for c in cookies_after)

    # Clear again
    server.browser_clear_cookies()
    assert server.browser_get_cookies() == []


# ---------------------------------------------------------------------------
# Screenshot + OCR vision
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_screenshot_returns_png(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    img = server.browser_screenshot()
    # FastMCP Image has .data bytes
    assert img.data[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.browser
def test_screenshot_full_page(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    img = server.browser_screenshot(full_page=True)
    assert img.data[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.browser
def test_screenshot_element(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    img = server.browser_screenshot(selector="#closebtn")
    assert img.data[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.browser
def test_ocr_read_text(srv):  # type: ignore[no-untyped-def]
    """OCR must recognize the large text rendered in the data: URL."""
    server, _ = srv
    server.browser_navigate("data:text/html,<h1 style='font-size:72px;color:black'>OCRMCP</h1>")
    raw = server.browser_read_text(selector="h1")
    txt = "".join(ch for ch in raw.upper() if ch.isalnum())
    assert "OCRMCP" in txt, f"OCR returned: {raw!r}"


# ---------------------------------------------------------------------------
# Evaluate
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_evaluate_arithmetic(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    result = server.browser_evaluate("() => 6 * 7")
    assert result == 42


@pytest.mark.browser
def test_evaluate_with_arg(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    result = server.browser_evaluate("(x) => x * 3", 14)
    assert result == 42


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_frame_locator(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/frames.html")
    # inner.html is loaded inside the iframe; it has a button "Inner Button"
    count = server.browser_count(selector="#btn", frame="#f1")
    assert count == 1


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_browser_close(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/forms.html")
    result = server.browser_close()
    assert result == "browser closed"
    # After close, session should reset and open fresh on next call
    # Navigate again to confirm it recovers
    server.browser_navigate(f"{base_url}/rpa.html")
    assert "rpa.html" in server.browser_url()
