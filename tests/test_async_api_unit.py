"""Unit tests for visus.web.async_api — mock the sync layer, no real browser.

These tests verify that every async wrapper calls the correct underlying sync
method with the correct arguments.  pytest-asyncio asyncio_mode=auto handles
the async test functions automatically.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from visus.web.async_api import (
    AsyncBrowser,
    AsyncContext,
    AsyncFrameLocator,
    AsyncLocator,
    AsyncLocatorAssertions,
    AsyncPage,
    expect,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loc() -> MagicMock:
    """Return a MagicMock that quacks like a sync Locator."""
    m = MagicMock()
    # builder methods return a MagicMock (used as Locator)
    for name in (
        "get_by_role",
        "get_by_text",
        "get_by_label",
        "get_by_placeholder",
        "get_by_alt_text",
        "get_by_title",
        "get_by_test_id",
        "locator",
        "filter",
        "first",
        "last",
        "nth",
        "frame_locator",
    ):
        getattr(m, name).return_value = MagicMock()
    m.all.return_value = []
    m.all_text_contents.return_value = []
    return m


def _make_page() -> MagicMock:
    m = MagicMock()
    for name in (
        "locator",
        "get_by_role",
        "get_by_text",
        "get_by_label",
        "get_by_placeholder",
        "get_by_alt_text",
        "get_by_title",
        "get_by_test_id",
        "frame_locator",
    ):
        getattr(m, name).return_value = MagicMock()
    m.url = "http://example.com/"
    return m


# ---------------------------------------------------------------------------
# AsyncBrowser
# ---------------------------------------------------------------------------


async def test_async_browser_new_page_calls_sync() -> None:
    sync_browser = MagicMock()
    sync_page = MagicMock()
    sync_browser.new_page.return_value = sync_page
    ab = AsyncBrowser(sync_browser)
    result = await ab.new_page()
    assert isinstance(result, AsyncPage)
    sync_browser.new_page.assert_called_once()


async def test_async_browser_new_context_calls_sync() -> None:
    sync_browser = MagicMock()
    sync_ctx = MagicMock()
    sync_browser.new_context.return_value = sync_ctx
    ab = AsyncBrowser(sync_browser)
    result = await ab.new_context()
    assert isinstance(result, AsyncContext)
    sync_browser.new_context.assert_called_once()


async def test_async_browser_close_calls_sync() -> None:
    sync_browser = MagicMock()
    ab = AsyncBrowser(sync_browser)
    await ab.close()
    sync_browser.close.assert_called_once()


async def test_async_browser_context_manager() -> None:
    sync_browser = MagicMock()
    ab = AsyncBrowser(sync_browser)
    async with ab as b:
        assert b is ab
    sync_browser.close.assert_called_once()


# ---------------------------------------------------------------------------
# AsyncContext
# ---------------------------------------------------------------------------


async def test_async_context_new_page() -> None:
    sync_ctx = MagicMock()
    sync_page = MagicMock()
    sync_ctx.new_page.return_value = sync_page
    ac = AsyncContext(sync_ctx)
    result = await ac.new_page()
    assert isinstance(result, AsyncPage)


async def test_async_context_cookies() -> None:
    sync_ctx = MagicMock()
    sync_ctx.cookies.return_value = [{"name": "a"}]
    ac = AsyncContext(sync_ctx)
    result = await ac.cookies()
    assert result == [{"name": "a"}]


async def test_async_context_add_cookies() -> None:
    sync_ctx = MagicMock()
    ac = AsyncContext(sync_ctx)
    cookies = [{"name": "x", "value": "y"}]
    await ac.add_cookies(cookies)
    sync_ctx.add_cookies.assert_called_once_with(cookies)


async def test_async_context_clear_cookies() -> None:
    sync_ctx = MagicMock()
    ac = AsyncContext(sync_ctx)
    await ac.clear_cookies()
    sync_ctx.clear_cookies.assert_called_once()


async def test_async_context_close() -> None:
    sync_ctx = MagicMock()
    ac = AsyncContext(sync_ctx)
    await ac.close()
    sync_ctx.close.assert_called_once()


async def test_async_context_context_manager() -> None:
    sync_ctx = MagicMock()
    ac = AsyncContext(sync_ctx)
    async with ac as c:
        assert c is ac
    sync_ctx.close.assert_called_once()


# ---------------------------------------------------------------------------
# AsyncPage — navigation / reads
# ---------------------------------------------------------------------------


async def test_async_page_goto() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    await ap.goto("http://x.com", wait_until="networkidle", timeout=5000)
    p.goto.assert_called_once_with(
        "http://x.com", wait_until="networkidle", timeout=5000, backtrack=False
    )


async def test_async_page_title() -> None:
    p = _make_page()
    p.title.return_value = "my title"
    ap = AsyncPage(p)
    assert await ap.title() == "my title"


async def test_async_page_content() -> None:
    p = _make_page()
    p.content.return_value = "<html/>"
    ap = AsyncPage(p)
    assert await ap.content() == "<html/>"


async def test_async_page_url() -> None:
    p = _make_page()
    p.url = "http://foo/"
    ap = AsyncPage(p)
    assert await ap.url() == "http://foo/"


async def test_async_page_screenshot() -> None:
    p = _make_page()
    p.screenshot.return_value = b"\x89PNG"
    ap = AsyncPage(p)
    data = await ap.screenshot(full_page=True)
    assert data == b"\x89PNG"
    p.screenshot.assert_called_once_with(path=None, full_page=True)


async def test_async_page_evaluate() -> None:
    p = _make_page()
    p.evaluate.return_value = 99
    ap = AsyncPage(p)
    result = await ap.evaluate("a => a", 99)
    assert result == 99
    p.evaluate.assert_called_once_with("a => a", 99)


async def test_async_page_reload() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    await ap.reload(timeout=3000)
    p.reload.assert_called_once_with(timeout=3000)


async def test_async_page_go_back() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    await ap.go_back(timeout=2000)
    p.go_back.assert_called_once_with(timeout=2000)


async def test_async_page_go_forward() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    await ap.go_forward(timeout=2000)
    p.go_forward.assert_called_once_with(timeout=2000)


async def test_async_page_close() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    await ap.close()
    p.close.assert_called_once()


async def test_async_page_snapshot() -> None:
    p = _make_page()
    p.snapshot.return_value = [{"role": "button", "name": "OK"}]
    ap = AsyncPage(p)
    result = await ap.snapshot()
    assert result == [{"role": "button", "name": "OK"}]


async def test_async_page_pdf() -> None:
    p = _make_page()
    p.pdf.return_value = b"%PDF"
    ap = AsyncPage(p)
    data = await ap.pdf(path=None)
    assert data == b"%PDF"
    p.pdf.assert_called_once_with(path=None)


async def test_async_page_block_urls() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    await ap.block_urls(["*.ads.*"])
    p.block_urls.assert_called_once_with(["*.ads.*"])


async def test_async_page_set_extra_http_headers() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    await ap.set_extra_http_headers({"X-Auth": "token"})
    p.set_extra_http_headers.assert_called_once_with({"X-Auth": "token"})


async def test_async_page_set_offline() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    await ap.set_offline(True)
    p.set_offline.assert_called_once_with(True)


# --- sync locator builders ---


def test_async_page_locator_returns_async_locator() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    result = ap.locator("div")
    assert isinstance(result, AsyncLocator)
    p.locator.assert_called_once_with("div")


def test_async_page_get_by_role() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    result = ap.get_by_role("button", name="OK")
    assert isinstance(result, AsyncLocator)
    p.get_by_role.assert_called_once_with("button", name="OK", exact=False)


def test_async_page_get_by_text() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    result = ap.get_by_text("hello")
    assert isinstance(result, AsyncLocator)


def test_async_page_get_by_label() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    assert isinstance(ap.get_by_label("Username"), AsyncLocator)


def test_async_page_get_by_placeholder() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    assert isinstance(ap.get_by_placeholder("Search"), AsyncLocator)


def test_async_page_get_by_alt_text() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    assert isinstance(ap.get_by_alt_text("logo"), AsyncLocator)


def test_async_page_get_by_title() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    assert isinstance(ap.get_by_title("Close dialog"), AsyncLocator)


def test_async_page_get_by_test_id() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    assert isinstance(ap.get_by_test_id("my-id"), AsyncLocator)


def test_async_page_frame_locator() -> None:
    p = _make_page()
    ap = AsyncPage(p)
    result = ap.frame_locator("#f1")
    assert isinstance(result, AsyncFrameLocator)


# ---------------------------------------------------------------------------
# AsyncFrameLocator
# ---------------------------------------------------------------------------


def _make_frame_loc() -> MagicMock:
    m = MagicMock()
    for name in (
        "locator",
        "get_by_role",
        "get_by_text",
        "get_by_label",
        "get_by_test_id",
        "frame_locator",
    ):
        getattr(m, name).return_value = MagicMock()
    return m


def test_async_frame_locator_locator() -> None:
    fl = _make_frame_loc()
    afl = AsyncFrameLocator(fl)
    result = afl.locator("button")
    assert isinstance(result, AsyncLocator)
    fl.locator.assert_called_once_with("button")


def test_async_frame_locator_get_by_role() -> None:
    fl = _make_frame_loc()
    afl = AsyncFrameLocator(fl)
    result = afl.get_by_role("button", name="OK")
    assert isinstance(result, AsyncLocator)


def test_async_frame_locator_get_by_text() -> None:
    fl = _make_frame_loc()
    afl = AsyncFrameLocator(fl)
    assert isinstance(afl.get_by_text("click me"), AsyncLocator)


def test_async_frame_locator_get_by_label() -> None:
    fl = _make_frame_loc()
    afl = AsyncFrameLocator(fl)
    assert isinstance(afl.get_by_label("Username"), AsyncLocator)


def test_async_frame_locator_get_by_test_id() -> None:
    fl = _make_frame_loc()
    afl = AsyncFrameLocator(fl)
    assert isinstance(afl.get_by_test_id("tid"), AsyncLocator)


def test_async_frame_locator_nested_frame_locator() -> None:
    fl = _make_frame_loc()
    afl = AsyncFrameLocator(fl)
    result = afl.frame_locator("#inner")
    assert isinstance(result, AsyncFrameLocator)
    fl.frame_locator.assert_called_once_with("#inner")


# ---------------------------------------------------------------------------
# AsyncLocator — builders
# ---------------------------------------------------------------------------


def test_async_locator_builders_sync() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)

    assert isinstance(al.get_by_role("button"), AsyncLocator)
    assert isinstance(al.get_by_text("x"), AsyncLocator)
    assert isinstance(al.get_by_label("y"), AsyncLocator)
    assert isinstance(al.get_by_placeholder("z"), AsyncLocator)
    assert isinstance(al.get_by_alt_text("img"), AsyncLocator)
    assert isinstance(al.get_by_title("ttl"), AsyncLocator)
    assert isinstance(al.get_by_test_id("tid"), AsyncLocator)
    assert isinstance(al.locator("div"), AsyncLocator)
    assert isinstance(al.filter(has_text="foo"), AsyncLocator)
    assert isinstance(al.first(), AsyncLocator)
    assert isinstance(al.last(), AsyncLocator)
    assert isinstance(al.nth(2), AsyncLocator)
    assert isinstance(al.frame_locator("#f"), AsyncFrameLocator)


# ---------------------------------------------------------------------------
# AsyncLocator — reads
# ---------------------------------------------------------------------------


async def test_async_locator_count() -> None:
    loc = _make_loc()
    loc.count.return_value = 3
    al = AsyncLocator(loc)
    assert await al.count() == 3
    loc.count.assert_called_once()


async def test_async_locator_text_content() -> None:
    loc = _make_loc()
    loc.text_content.return_value = "hello"
    al = AsyncLocator(loc)
    assert await al.text_content() == "hello"


async def test_async_locator_input_value() -> None:
    loc = _make_loc()
    loc.input_value.return_value = "ada"
    al = AsyncLocator(loc)
    assert await al.input_value() == "ada"


async def test_async_locator_get_attribute() -> None:
    loc = _make_loc()
    loc.get_attribute.return_value = "text"
    al = AsyncLocator(loc)
    result = await al.get_attribute("type")
    assert result == "text"
    loc.get_attribute.assert_called_once_with("type")


async def test_async_locator_all_text_contents() -> None:
    loc = _make_loc()
    loc.all_text_contents.return_value = ["a", "b"]
    al = AsyncLocator(loc)
    result = await al.all_text_contents()
    assert result == ["a", "b"]


async def test_async_locator_all() -> None:
    child = _make_loc()
    loc = _make_loc()
    loc.all.return_value = [child]
    al = AsyncLocator(loc)
    result = await al.all()
    assert len(result) == 1
    assert isinstance(result[0], AsyncLocator)


async def test_async_locator_is_visible() -> None:
    loc = _make_loc()
    loc.is_visible.return_value = True
    assert await AsyncLocator(loc).is_visible() is True


async def test_async_locator_is_enabled() -> None:
    loc = _make_loc()
    loc.is_enabled.return_value = False
    assert await AsyncLocator(loc).is_enabled() is False


async def test_async_locator_is_checked() -> None:
    loc = _make_loc()
    loc.is_checked.return_value = True
    assert await AsyncLocator(loc).is_checked() is True


async def test_async_locator_is_editable() -> None:
    loc = _make_loc()
    loc.is_editable.return_value = True
    assert await AsyncLocator(loc).is_editable() is True


async def test_async_locator_is_hidden() -> None:
    loc = _make_loc()
    loc.is_hidden.return_value = False
    assert await AsyncLocator(loc).is_hidden() is False


async def test_async_locator_evaluate() -> None:
    loc = _make_loc()
    loc.evaluate.return_value = "div"
    al = AsyncLocator(loc)
    result = await al.evaluate("el => el.tagName", None)
    assert result == "div"
    loc.evaluate.assert_called_once_with("el => el.tagName", None)


async def test_async_locator_screenshot() -> None:
    loc = _make_loc()
    loc.screenshot.return_value = b"\x89PNG"
    al = AsyncLocator(loc)
    data = await al.screenshot(path=None)
    assert data == b"\x89PNG"
    loc.screenshot.assert_called_once_with(path=None)


# ---------------------------------------------------------------------------
# AsyncLocator — actions
# ---------------------------------------------------------------------------


async def test_async_locator_click() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.click(timeout=3000, force=True)
    loc.click.assert_called_once_with(timeout=3000, force=True, backtrack=False)


async def test_async_locator_dblclick() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.dblclick(timeout=2000)
    loc.dblclick.assert_called_once_with(timeout=2000, force=False, backtrack=False)


async def test_async_locator_fill() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.fill("hello", timeout=5000)
    loc.fill.assert_called_once_with("hello", timeout=5000, force=False, backtrack=False)


async def test_async_locator_press() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.press("Enter")
    loc.press.assert_called_once_with("Enter", timeout=None, backtrack=False)


async def test_async_locator_hover() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.hover()
    loc.hover.assert_called_once_with(timeout=None, force=False, backtrack=False)


async def test_async_locator_check() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.check()
    loc.check.assert_called_once_with(timeout=None, force=False, backtrack=False)


async def test_async_locator_uncheck() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.uncheck()
    loc.uncheck.assert_called_once_with(timeout=None, force=False, backtrack=False)


async def test_async_locator_set_checked() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.set_checked(True)
    loc.set_checked.assert_called_once_with(True, timeout=None, force=False, backtrack=False)


async def test_async_locator_select_option() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.select_option(value="red", timeout=2000)
    loc.select_option.assert_called_once_with(
        value="red", label=None, index=None, timeout=2000, backtrack=False
    )


async def test_async_locator_drag_to() -> None:
    src_loc = _make_loc()
    tgt_loc = _make_loc()
    src = AsyncLocator(src_loc)
    tgt = AsyncLocator(tgt_loc)
    await src.drag_to(tgt, timeout=1000)
    src_loc.drag_to.assert_called_once_with(tgt_loc, timeout=1000, backtrack=False)


async def test_async_locator_focus() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.focus()
    loc.focus.assert_called_once_with(timeout=None, backtrack=False)


async def test_async_locator_blur() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.blur()
    loc.blur.assert_called_once_with(timeout=None, backtrack=False)


async def test_async_locator_clear() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.clear(timeout=500)
    loc.clear.assert_called_once_with(timeout=500, force=False, backtrack=False)


async def test_async_locator_set_input_files() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    await al.set_input_files("/tmp/file.txt")
    loc.set_input_files.assert_called_once_with("/tmp/file.txt", backtrack=False)


# ---------------------------------------------------------------------------
# AsyncLocatorAssertions
# ---------------------------------------------------------------------------


def _make_assertions() -> MagicMock:
    m = MagicMock()
    m.not_ = MagicMock()
    m.not_.not_ = m  # double-negation goes back to original
    return m


async def test_async_assertions_to_be_visible() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_be_visible(timeout=5000)
    a.to_be_visible.assert_called_once_with(timeout=5000)


async def test_async_assertions_to_be_hidden() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_be_hidden()
    a.to_be_hidden.assert_called_once_with(timeout=None)


async def test_async_assertions_to_be_enabled() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_be_enabled()
    a.to_be_enabled.assert_called_once_with(timeout=None)


async def test_async_assertions_to_be_disabled() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_be_disabled()
    a.to_be_disabled.assert_called_once_with(timeout=None)


async def test_async_assertions_to_be_editable() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_be_editable()
    a.to_be_editable.assert_called_once_with(timeout=None)


async def test_async_assertions_to_be_checked() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_be_checked()
    a.to_be_checked.assert_called_once_with(timeout=None)


async def test_async_assertions_to_have_text() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_have_text("hello", exact=False, timeout=2000)
    a.to_have_text.assert_called_once_with("hello", exact=False, timeout=2000)


async def test_async_assertions_to_contain_text() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_contain_text("world")
    a.to_contain_text.assert_called_once_with("world", timeout=None)


async def test_async_assertions_to_have_value() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_have_value("foo")
    a.to_have_value.assert_called_once_with("foo", timeout=None)


async def test_async_assertions_to_have_attribute() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_have_attribute("class", "active")
    a.to_have_attribute.assert_called_once_with("class", "active", timeout=None)


async def test_async_assertions_to_have_class() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_have_class("btn")
    a.to_have_class.assert_called_once_with("btn", timeout=None)


async def test_async_assertions_to_contain_class() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_contain_class("active")
    a.to_contain_class.assert_called_once_with("active", timeout=None)


async def test_async_assertions_to_have_role() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_have_role("button")
    a.to_have_role.assert_called_once_with("button", timeout=None)


async def test_async_assertions_to_have_count() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    await aa.to_have_count(3)
    a.to_have_count.assert_called_once_with(3, timeout=None)


async def test_async_assertions_not_returns_wrapper() -> None:
    a = _make_assertions()
    aa = AsyncLocatorAssertions(a)
    not_aa = aa.not_
    assert isinstance(not_aa, AsyncLocatorAssertions)
    assert not_aa._a is a.not_


# ---------------------------------------------------------------------------
# expect() top-level function
# ---------------------------------------------------------------------------


def test_expect_wraps_sync_expect() -> None:
    loc = _make_loc()
    al = AsyncLocator(loc)
    with patch("visus.web.async_api._sync_expect") as mock_expect:
        mock_assert = MagicMock()
        mock_expect.return_value = mock_assert
        result = expect(al)
    assert isinstance(result, AsyncLocatorAssertions)
    mock_expect.assert_called_once_with(loc)
