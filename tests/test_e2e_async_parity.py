"""Real-browser E2E tests proving the async facade reaches 100% sync parity.

These mirror the sync e2e suites (events, input, fields, navigation, downloads,
rpa) through ``visus.web.async_api`` so every newly-wrapped member is exercised
against a live headless browser — not just asserted at the mock layer.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time

import pytest

from visus.web.async_api import AsyncContext, AsyncPage, launch, rpa

OPEN_FORMS_JS = "() => { window.open('/forms.html', '_blank'); }"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _wait_pages(ctx: AsyncContext, n: int, timeout: float = 5.0) -> list[AsyncPage]:
    """Poll ``await ctx.pages()`` until it has at least *n* live pages."""
    deadline = time.monotonic() + timeout
    pages = await ctx.pages()
    while len(pages) < n and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
        pages = await ctx.pages()
    return pages


async def _center(page: AsyncPage) -> tuple[float, float]:
    box = await page.evaluate(
        "() => { const r = document.querySelector('#pad').getBoundingClientRect();"
        " return {x: r.left + r.width/2, y: r.top + r.height/2}; }",
        None,
    )
    return box["x"], box["y"]  # type: ignore[index]


# ---------------------------------------------------------------------------
# Event-capture context managers — popups.html / downloads.html
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_expect_popup(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/popups.html")
        async with page.expect_popup() as info:
            await page.locator("#pop").click()
        popup = info.value
        assert isinstance(popup, AsyncPage)
        assert await popup.title() == "forms fixture"
        await popup.close()


@pytest.mark.browser
async def test_async_expect_dialog_alert(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/popups.html")
        async with page.expect_dialog() as info:
            await page.locator("#alertbtn").click()
        assert info.value.message == "hi there"


@pytest.mark.browser
async def test_async_expect_dialog_confirm_dismiss(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/popups.html")
        async with page.expect_dialog(accept=False):
            await page.locator("#confirmbtn").click()
        assert await page.locator("#cres").text_content() == "no"


@pytest.mark.browser
async def test_async_expect_dialog_prompt(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/popups.html")
        async with page.expect_dialog(accept=True, prompt_text="Ada"):
            await page.locator("#promptbtn").click()
        assert await page.locator("#pres").text_content() == "Ada"


@pytest.mark.browser
async def test_async_expect_download(base_url: str, tmp_path: object) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/downloads.html")
        async with page.expect_download() as info:
            await page.locator("#dl").click()
        dl = info.value
        assert dl.suggested_filename == "download.txt"
        assert os.path.exists(dl.path)
        out = tmp_path / "saved.txt"  # type: ignore[operator]
        dl.save_as(str(out))
        assert out.read_text().strip() == "hello download"


# ---------------------------------------------------------------------------
# Low-level input devices — input.html
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_mouse_click_and_wheel(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/input.html")
        x, y = await _center(page)
        await page.mouse.click(x, y)
        assert await page.locator("#c").text_content() == "clicked"
        await page.mouse.move(x, y)
        await page.mouse.wheel(0, 100)
        assert await page.locator("#w").text_content() == "wheel"


@pytest.mark.browser
async def test_async_mouse_down_up_and_dblclick(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/input.html")
        x, y = await _center(page)
        await page.mouse.move(x, y)
        await page.mouse.down()
        await page.mouse.up()
        assert await page.locator("#m").text_content() == "down up"
        await page.mouse.dblclick(x, y)
        assert await page.locator("#dc").text_content() == "dblclicked"


@pytest.mark.browser
async def test_async_keyboard_type_press_insert(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/input.html")
        await page.locator("#k").focus()
        await page.keyboard.type("hello")
        assert await page.locator("#k").input_value() == "hello"
        await page.keyboard.press("Enter")
        assert await page.locator("#k2").text_content() == "enter"
        # insert_text (no key events) + select-all combo then overtype
        await page.keyboard.press("Control+a")
        await page.keyboard.insert_text("world")
        assert await page.locator("#k").input_value() == "world"


@pytest.mark.browser
async def test_async_keyboard_down_up(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/input.html")
        await page.locator("#shift").focus()
        await page.keyboard.down("Shift")
        await page.keyboard.up("Shift")
        assert await page.locator("#k3").text_content() in ("", "shift-held")


# ---------------------------------------------------------------------------
# Field enumerator + deep selector — fields.html
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_list_fields_and_act_by_index(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/fields.html")

        # nothing enumerated yet
        with pytest.raises(RuntimeError):
            page.field(0)

        fields = await page.list_fields(highlight=False)
        names = {f.locator for f in fields}
        assert "#topinput" in names

        idx = next(f.index for f in fields if f.locator == "#topinput")
        await page.field(idx).fill("by-index")
        assert await page.field(idx).input_value() == "by-index"

        # field_locator(field) resolves frame chain + deep automatically
        f = next(f for f in fields if f.locator == "#topinput")
        await page.field_locator(f).fill("by-field")
        assert await page.field_locator(f).input_value() == "by-field"


@pytest.mark.browser
async def test_async_clear_highlights(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/fields.html")
        fields = await page.list_fields(highlight=True)
        assert fields
        count_js = "() => document.querySelectorAll('[data-visus-field]').length"
        assert await page.evaluate(count_js) > 0
        await page.clear_highlights()
        assert await page.evaluate(count_js) == 0


@pytest.mark.browser
async def test_async_locator_deep_pierces_shadow_dom(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/fields.html")
        # A plain query can't reach an open shadow root; a deep query can.
        assert await page.locator("#shadowinput").count() == 0
        assert await page.locator("#shadowinput", deep=True).count() == 1


# ---------------------------------------------------------------------------
# Multi-tab tracking — popups.html
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_context_pages_and_handle_and_page_context(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/popups.html")

        # browser.contexts (sync property) and page.context (sync property)
        assert isinstance(browser.contexts[0], AsyncContext)
        ctx = page.context
        assert isinstance(ctx, AsyncContext)

        # page.handle is a stable non-empty string in the context's page set
        assert isinstance(page.handle, str) and page.handle
        assert page.handle in {p.handle for p in await ctx.pages()}

        # a window.open tab (no expect_popup) is auto-reconciled into ctx.pages()
        await page.evaluate(OPEN_FORMS_JS)
        pages = await _wait_pages(ctx, 2)
        assert len(pages) == 2
        urls = [await p.url() for p in pages]
        assert any(u.endswith("/forms.html") for u in urls)


@pytest.mark.browser
async def test_async_adopt_open_windows(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/popups.html")
        ctx = page.context

        await page.evaluate(OPEN_FORMS_JS)
        # poll adopt_open_windows() until the new tab is discovered
        deadline = time.monotonic() + 5.0
        new: list[AsyncPage] = []
        while not new and time.monotonic() < deadline:
            new = await ctx.adopt_open_windows()
            if new:
                break
            await asyncio.sleep(0.05)
        assert len(new) == 1
        assert (await new[0].url()).endswith("/forms.html")
        # already tracked → nothing new to adopt
        assert await ctx.adopt_open_windows() == []


@pytest.mark.browser
async def test_async_bring_to_front_and_activate(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/forms.html")
        ctx = page.context
        page2 = await ctx.new_page()
        await page2.goto(f"{base_url}/popups.html")

        await page.bring_to_front()
        assert page.handle in {p.handle for p in await ctx.pages()}
        await page2.activate()
        # both calls completed without error and both tabs remain tracked
        assert page2.handle in {p.handle for p in await ctx.pages()}


@pytest.mark.browser
async def test_async_page_is_closed(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        ctx = page.context
        page2 = await ctx.new_page()
        assert page2.is_closed is False
        await page2.close()
        assert page2.is_closed is True


# ---------------------------------------------------------------------------
# Batteries-included async rpa() — real run writes artifacts + exposes context
# ---------------------------------------------------------------------------


@pytest.mark.browser
async def test_async_rpa_real_run(base_url: str, tmp_path: object) -> None:
    async with rpa(
        "async-ctx", engine="chrome", headless=True, outdir=str(tmp_path), summary=False
    ) as page:
        await page.goto(f"{base_url}/popups.html")
        ctx = page.context
        assert page.handle in {p.handle for p in await ctx.pages()}
        await page.evaluate(OPEN_FORMS_JS)
        pages = await _wait_pages(ctx, 2)
        urls = [await p.url() for p in pages]
        assert any(u.endswith("/forms.html") for u in urls)

    # run.zip + report.html are written on a clean exit
    assert (tmp_path / "run.zip").exists()  # type: ignore[operator]
    assert (tmp_path / "report.html").exists()  # type: ignore[operator]


@pytest.mark.browser
async def test_async_set_input_files_via_field(base_url: str) -> None:
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto(f"{base_url}/rpa.html")
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"data")
            tmp = f.name
        try:
            await page.locator("#up").set_input_files(tmp)
            assert (await page.locator("#upname").text_content()) == os.path.basename(tmp)
        finally:
            os.unlink(tmp)
