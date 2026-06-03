"""End-to-end tests for the async facade (visus.web.async_api).

pytest-asyncio is configured with asyncio_mode = "auto" so all async def
test_* functions are collected and run automatically without extra markers.
"""

from __future__ import annotations

import pytest

from visus.web.async_api import expect, launch

# ---------------------------------------------------------------------------
# Test: core page flow (goto / title / locator reads / fill / assertions)
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_end_to_end(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")
        assert await page.title() == "forms fixture"

        user = page.get_by_role("textbox", name="Username")
        assert await user.count() == 1
        await user.fill("ada99")
        assert await user.input_value() == "ada99"
        await expect(user).to_have_value("ada99")
        await expect(page.get_by_title("Close dialog")).to_be_visible()


# ---------------------------------------------------------------------------
# Test: frame_locator and count inside an iframe
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_click_and_frames(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/frames.html")
        inner_btn = page.frame_locator("#f1").get_by_role("button", name="Inner Button")
        assert await inner_btn.count() == 1


# ---------------------------------------------------------------------------
# Test: click effect visible in the DOM
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_click_updates_dom(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/actions.html")
        counter = page.locator("#counter")
        count_display = page.locator("#count")
        await counter.click()
        assert await count_display.text_content() == "1"
        await counter.click()
        assert await count_display.text_content() == "2"


# ---------------------------------------------------------------------------
# Test: page.evaluate() returns a value from the browser context
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_evaluate(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/index.html")
        result = await page.evaluate("a => a + 1", 41)
        assert result == 42

        title_result = await page.evaluate("() => document.title")
        assert title_result == "visus-web test page"


# ---------------------------------------------------------------------------
# Test: .not_ negation on assertions
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_not_negation(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        # The disabled button is present but disabled — not enabled
        disabled_btn = page.get_by_role("button", name="disabled")
        await expect(disabled_btn).to_be_visible()
        await expect(disabled_btn).to_be_disabled()
        await expect(disabled_btn).not_.to_be_enabled()

        # The username input is visible and enabled — not hidden
        user = page.get_by_label("Username")
        await expect(user).to_be_visible()
        await expect(user).not_.to_be_hidden()


# ---------------------------------------------------------------------------
# Test: context isolation — cookies round-trip through AsyncContext
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_context_cookies(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(f"{base_url}/index.html")

        # Set a cookie via JS, then read it back through the context API.
        await page.evaluate("() => { document.cookie = 'color=blue; path=/'; }")
        cookies = await ctx.cookies()
        names = {c["name"] for c in cookies}
        assert "color" in names

        await ctx.clear_cookies()
        after = await ctx.cookies()
        assert not any(c["name"] == "color" for c in after)
        await ctx.close()


# ---------------------------------------------------------------------------
# Test: is_visible / is_hidden / is_enabled async reads
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_state_reads(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        user = page.get_by_role("textbox", name="Username")
        assert await user.is_visible() is True
        assert await user.is_hidden() is False
        assert await user.is_enabled() is True

        disabled_btn = page.get_by_role("button", name="disabled")
        assert await disabled_btn.is_enabled() is False


# ---------------------------------------------------------------------------
# Test: all_text_contents across a list of items
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_all_text_contents(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        items = page.locator("#items li")
        texts = await items.all_text_contents()
        assert texts == ["alpha", "beta", "gamma"]


# ---------------------------------------------------------------------------
# Test: get_attribute
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_get_attribute(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")

        # The username input has id="user"
        user_input = page.locator("#user")
        assert await user_input.get_attribute("type") == "text"
        assert await user_input.get_attribute("id") == "user"
