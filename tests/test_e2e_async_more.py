"""Additional real-browser async tests for visus.web.async_api.

Covers the async wrappers not exercised by test_e2e_async.py:
  - Actions: hover, dblclick, check/uncheck, select_option, press, focus/blur,
    clear, drag_to, set_input_files
  - Reads: is_enabled, is_editable, is_checked, get_attribute, all(),
    all_text_contents
  - Media / page reads: screenshot (PNG bytes), page.content(), page.url(),
    page.evaluate()
  - Navigation: go_back, go_forward, reload
  - Expect matchers (auto-retry against 700ms DOM changes in expects.html)
  - Context: add_cookies round-trip
  - AsyncFrameLocator: click inside an iframe then assert via frame_locator
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from visus.web.async_api import expect, launch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# A: Actions — interactions.html
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_hover(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/interactions.html")

        await page.locator("#hovertarget").hover()
        result = await page.locator("#hoverres").text_content()
        assert result == "hovered"


@pytest.mark.browser
async def test_async_dblclick(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/interactions.html")

        await page.locator("#dbl").dblclick()
        result = await page.locator("#dblres").text_content()
        assert result == "double"


@pytest.mark.browser
async def test_async_check_uncheck(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/interactions.html")

        cb = page.locator("#cb")

        # Initially unchecked
        assert await cb.is_checked() is False

        await cb.check()
        assert await cb.is_checked() is True
        assert await page.locator("#cbstate").text_content() == "on"

        await cb.uncheck()
        assert await cb.is_checked() is False
        assert await page.locator("#cbstate").text_content() == "off"


@pytest.mark.browser
async def test_async_select_option(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/interactions.html")

        sel = page.locator("#sel")
        await sel.select_option(value="y")
        assert await sel.input_value() == "y"


@pytest.mark.browser
async def test_async_press(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/interactions.html")

        await page.locator("#txt").press("Enter")
        result = await page.locator("#pressres").text_content()
        assert result == "enter"


@pytest.mark.browser
async def test_async_focus_blur(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/interactions.html")

        focusable = page.locator("#focusable")
        await focusable.focus()
        assert await page.locator("#focusres").text_content() == "focused"

        await focusable.blur()
        assert await page.locator("#blurres").text_content() == "blurred"


@pytest.mark.browser
async def test_async_clear(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/interactions.html")

        txt = page.locator("#txt")
        # Pre-condition: value is "hello"
        assert await txt.input_value() == "hello"

        await txt.clear()
        assert await txt.input_value() == ""


@pytest.mark.browser
async def test_async_drag_to(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/interactions.html")

        src = page.locator("#src")
        dst = page.locator("#dst")
        await src.drag_to(dst)
        result = await page.locator("#dragres").text_content()
        assert result == "dropped"


@pytest.mark.browser
async def test_async_set_input_files(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/rpa.html")

        # Create a temporary file to upload
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello upload")
            tmp_path = f.name

        try:
            await page.locator("#up").set_input_files(tmp_path)
            filename = pathlib.Path(tmp_path).name
            upname = await page.locator("#upname").text_content()
            assert upname == filename
        finally:
            pathlib.Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# B: Reads — forms.html
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_is_enabled_editable(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        # Normal text input — enabled and editable
        user = page.locator("#user")
        assert await user.is_enabled() is True
        assert await user.is_editable() is True

        # Disabled button — not enabled
        dis = page.locator("#dis")
        assert await dis.is_enabled() is False

        # Readonly input — enabled but not editable
        ro = page.locator("#ro")
        assert await ro.is_enabled() is True
        assert await ro.is_editable() is False


@pytest.mark.browser
async def test_async_all_returns_list_of_async_locators(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        items = await page.locator("#items li").all()

        # Should return three AsyncLocator objects
        assert len(items) == 3

        # Each item must support awaitable text_content()
        texts = [await item.text_content() for item in items]
        assert texts == ["alpha", "beta", "gamma"]


@pytest.mark.browser
async def test_async_all_text_contents_forms(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        texts = await page.locator("#items li").all_text_contents()
        assert texts == ["alpha", "beta", "gamma"]


@pytest.mark.browser
async def test_async_get_attribute_forms(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        user = page.locator("#user")
        assert await user.get_attribute("type") == "text"
        assert await user.get_attribute("class") == "field big"
        # Non-existent attribute returns None
        assert await user.get_attribute("data-nope") is None


# ---------------------------------------------------------------------------
# C: Page reads & media
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_screenshot_png(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        data = await page.screenshot()
        assert isinstance(data, bytes)
        assert data[:8] == _PNG_MAGIC


@pytest.mark.browser
async def test_async_locator_screenshot_png(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        data = await page.locator("#user").screenshot()
        assert isinstance(data, bytes)
        assert data[:8] == _PNG_MAGIC


@pytest.mark.browser
async def test_async_page_content(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        html = await page.content()
        assert "forms fixture" in html
        assert "field big" in html


@pytest.mark.browser
async def test_async_page_url(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        url = await page.url()
        assert url.endswith("/forms.html")


@pytest.mark.browser
async def test_async_page_evaluate_expr(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        # Evaluate JS with an argument
        result = await page.evaluate("x => x * 3", 7)
        assert result == 21

        # Read a DOM value
        val = await page.evaluate("() => document.getElementById('user').value")
        assert val == "ada"


# ---------------------------------------------------------------------------
# D: Navigation — go_back / go_forward / reload
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_navigation_back_forward_reload(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()

        # Visit first page then second page
        await page.goto(f"{base_url}/index.html")
        assert await page.title() == "visus-web test page"

        await page.goto(f"{base_url}/page2.html")
        assert await page.title() == "page two"

        # Go back — title should return to the first page
        await page.go_back()
        assert await page.title() == "visus-web test page"

        # Go forward — back to page two
        await page.go_forward()
        assert await page.title() == "page two"

        # Reload stays on same page
        await page.reload()
        assert await page.title() == "page two"


# ---------------------------------------------------------------------------
# E: Expect matchers (auto-retry, 700ms DOM mutations) — expects.html
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_expect_to_have_text(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/expects.html")

        # #msg starts as "loading" then becomes "ready" at 700ms
        await expect(page.locator("#msg")).to_have_text("ready", exact=True)


@pytest.mark.browser
async def test_async_expect_to_contain_text(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/expects.html")

        await expect(page.locator("#msg")).to_contain_text("read")


@pytest.mark.browser
async def test_async_expect_to_be_hidden(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/expects.html")

        # #vanish is visible then hidden at 700ms
        await expect(page.locator("#vanish")).to_be_hidden()


@pytest.mark.browser
async def test_async_expect_to_be_visible(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/expects.html")

        # #appear is hidden then visible at 700ms
        await expect(page.locator("#appear")).to_be_visible()


@pytest.mark.browser
async def test_async_expect_to_have_count(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/expects.html")

        # #list starts with 1 li, grows to 3 at 700ms
        await expect(page.locator("#list li")).to_have_count(3)


@pytest.mark.browser
async def test_async_expect_to_be_enabled(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/expects.html")

        # #enableme starts disabled, becomes enabled at 700ms
        await expect(page.locator("#enableme")).to_be_enabled()


@pytest.mark.browser
async def test_async_expect_to_be_disabled(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        await expect(page.locator("#dis")).to_be_disabled()


@pytest.mark.browser
async def test_async_expect_to_be_editable_and_not(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        # #user is editable, #ro is not
        await expect(page.locator("#user")).to_be_editable()
        await expect(page.locator("#ro")).not_.to_be_editable()


@pytest.mark.browser
async def test_async_expect_to_have_attribute(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        await expect(page.locator("#user")).to_have_attribute("type", "text")


@pytest.mark.browser
async def test_async_expect_to_have_class_and_contain_class(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        user = page.locator("#user")
        await expect(user).to_have_class("field big")
        await expect(user).to_contain_class("big")


@pytest.mark.browser
async def test_async_expect_to_have_role(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        # #closebtn has role="button" implicitly (it's a <button>)
        await expect(page.locator("#closebtn")).to_have_role("button")


@pytest.mark.browser
async def test_async_expect_to_have_value(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        await expect(page.locator("#user")).to_have_value("ada")


# ---------------------------------------------------------------------------
# F: Context — add_cookies round-trip
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_context_add_cookies(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(f"{base_url}/index.html")

        # Add a cookie through the context API
        await ctx.add_cookies([{"name": "token", "value": "abc123", "url": f"{base_url}/"}])

        cookies = await ctx.cookies()
        names = {c["name"]: c["value"] for c in cookies}
        assert "token" in names
        assert names["token"] == "abc123"

        await ctx.clear_cookies()
        after = await ctx.cookies()
        assert not any(c["name"] == "token" for c in after)

        await ctx.close()


# ---------------------------------------------------------------------------
# H: Async backtrack — mirrors test_backtrack_reexecutes_previous_step
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_backtrack_reexecutes_previous_step(base_url: str) -> None:
    """Async version: backtrack=True re-runs the previous step, making #t2 appear."""
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/backtrack.html")

        # Step A: click Prepare (count=1, recorded as _last_step on delegate)
        await page.get_by_role("button", name="Prepare").click()

        # #t2 needs count>=2; first attempt fails -> backtrack re-runs Prepare
        # (count=2 -> #t2 appears) -> retry succeeds
        await page.locator("#t2").click(backtrack=True, timeout=800)

        assert await page.locator("#r2").text_content() == "clicked"


# ---------------------------------------------------------------------------
# G: AsyncFrameLocator — click inside iframe, assert via frame_locator
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_frame_locator_click_and_read(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/frames.html")

        fl = page.frame_locator("#f1")

        # Click the inner button
        inner_btn = fl.get_by_role("button", name="Inner Button")
        await inner_btn.click()

        # Read the result element inside the same frame
        res = fl.locator("#res")
        assert await res.text_content() == "clicked"
