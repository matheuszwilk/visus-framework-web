"""visus.web.async_api — async facade wrapping the sync API in asyncio.to_thread.

Lazy builders (get_by_role / locator / first / last / nth / filter) are SYNC
because they only build a recipe; anything that touches the browser is ASYNC.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import TYPE_CHECKING

from visus.web import Engine
from visus.web import expect as _sync_expect
from visus.web import launch as _sync_launch
from visus.web.api.browser import Browser
from visus.web.api.context import Context
from visus.web.api.frame_locator import FrameLocator
from visus.web.api.locator import Locator
from visus.web.api.page import Page

if TYPE_CHECKING:
    from visus.web.api.assertions import LocatorAssertions

__all__ = [
    "launch",
    "expect",
    "AsyncBrowser",
    "AsyncContext",
    "AsyncPage",
    "AsyncLocator",
    "AsyncFrameLocator",
    "AsyncLocatorAssertions",
]


# ---------------------------------------------------------------------------
# Top-level factory
# ---------------------------------------------------------------------------


async def launch(engine: Engine | str = Engine.CHROME, *, headless: bool = False) -> AsyncBrowser:
    """Launch a browser and return an AsyncBrowser handle.

    Usage::

        async with await launch(headless=True) as browser:
            page = await browser.new_page()
            await page.goto("https://example.com")
    """
    return AsyncBrowser(await asyncio.to_thread(lambda: _sync_launch(engine, headless=headless)))


# ---------------------------------------------------------------------------
# expect() — wraps the sync LocatorAssertions
# ---------------------------------------------------------------------------


def expect(async_locator: AsyncLocator) -> AsyncLocatorAssertions:
    """Return an AsyncLocatorAssertions object for the given AsyncLocator.

    Usage::

        await expect(page.get_by_role("button")).to_be_visible()
    """
    return AsyncLocatorAssertions(_sync_expect(async_locator._loc))


# ---------------------------------------------------------------------------
# AsyncBrowser
# ---------------------------------------------------------------------------


class AsyncBrowser:
    """Async wrapper around the sync Browser."""

    def __init__(self, b: Browser) -> None:
        self._b = b

    async def new_page(self) -> AsyncPage:
        return AsyncPage(await asyncio.to_thread(self._b.new_page))

    async def new_context(self) -> AsyncContext:
        return AsyncContext(await asyncio.to_thread(self._b.new_context))

    async def close(self) -> None:
        await asyncio.to_thread(self._b.close)

    async def __aenter__(self) -> AsyncBrowser:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# AsyncContext
# ---------------------------------------------------------------------------


class AsyncContext:
    """Async wrapper around the sync Context."""

    def __init__(self, c: Context) -> None:
        self._c = c

    async def new_page(self) -> AsyncPage:
        return AsyncPage(await asyncio.to_thread(self._c.new_page))

    async def cookies(self) -> list[dict]:  # type: ignore[type-arg]
        return await asyncio.to_thread(self._c.cookies)

    async def add_cookies(self, cookies: list[dict]) -> None:  # type: ignore[type-arg]
        await asyncio.to_thread(lambda: self._c.add_cookies(cookies))

    async def clear_cookies(self) -> None:
        await asyncio.to_thread(self._c.clear_cookies)

    async def close(self) -> None:
        await asyncio.to_thread(self._c.close)

    async def __aenter__(self) -> AsyncContext:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()


# ---------------------------------------------------------------------------
# AsyncPage
# ---------------------------------------------------------------------------


class AsyncPage:
    """Async wrapper around the sync Page.

    Navigation and reads are async; locator builders are sync (they only
    construct a recipe and never touch the DOM).
    """

    def __init__(self, p: Page) -> None:
        self._p = p

    # --- navigation / async reads ---

    async def goto(self, url: str, *, wait_until: str = "load", timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._p.goto(url, wait_until=wait_until, timeout=timeout))

    async def title(self) -> str:
        return await asyncio.to_thread(self._p.title)

    async def content(self) -> str:
        return await asyncio.to_thread(self._p.content)

    async def url(self) -> str:
        return await asyncio.to_thread(lambda: self._p.url)

    async def screenshot(self, *, path: str | None = None, full_page: bool = False) -> bytes:
        return await asyncio.to_thread(lambda: self._p.screenshot(path=path, full_page=full_page))

    async def evaluate(self, expr: str, arg: object = None) -> object:
        return await asyncio.to_thread(lambda: self._p.evaluate(expr, arg))

    async def reload(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._p.reload(timeout=timeout))

    async def go_back(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._p.go_back(timeout=timeout))

    async def go_forward(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._p.go_forward(timeout=timeout))

    async def close(self) -> None:
        await asyncio.to_thread(self._p.close)

    async def snapshot(self) -> list[dict]:  # type: ignore[type-arg]
        return await asyncio.to_thread(self._p.snapshot)

    async def pdf(self, *, path: str | None = None) -> bytes:
        return await asyncio.to_thread(lambda: self._p.pdf(path=path))

    # --- network controls (Chromium CDP) ---

    async def block_urls(self, patterns: list[str]) -> None:
        await asyncio.to_thread(lambda: self._p.block_urls(patterns))

    async def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        await asyncio.to_thread(lambda: self._p.set_extra_http_headers(headers))

    async def set_offline(self, offline: bool) -> None:
        await asyncio.to_thread(lambda: self._p.set_offline(offline))

    # --- sync locator builders (return AsyncLocator / AsyncFrameLocator) ---

    def locator(self, sel: str) -> AsyncLocator:
        return AsyncLocator(self._p.locator(sel))

    def get_by_role(
        self, role: str, *, name: str | None = None, exact: bool = False
    ) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_role(role, name=name, exact=exact))

    def get_by_text(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_text(t, exact=exact))

    def get_by_label(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_label(t, exact=exact))

    def get_by_placeholder(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_placeholder(t, exact=exact))

    def get_by_test_id(self, tid: str) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_test_id(tid))

    def get_by_alt_text(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_alt_text(t, exact=exact))

    def get_by_title(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_title(t, exact=exact))

    def frame_locator(self, sel: str) -> AsyncFrameLocator:
        return AsyncFrameLocator(self._p.frame_locator(sel))


# ---------------------------------------------------------------------------
# AsyncFrameLocator
# ---------------------------------------------------------------------------


class AsyncFrameLocator:
    """Async wrapper around the sync FrameLocator.

    All builders are sync (recipe only); actual resolution happens later
    via an AsyncLocator action.
    """

    def __init__(self, fl: FrameLocator) -> None:
        self._fl = fl

    def locator(self, sel: str) -> AsyncLocator:
        return AsyncLocator(self._fl.locator(sel))

    def get_by_role(
        self, role: str, *, name: str | None = None, exact: bool = False
    ) -> AsyncLocator:
        return AsyncLocator(self._fl.get_by_role(role, name=name, exact=exact))

    def get_by_text(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._fl.get_by_text(t, exact=exact))

    def get_by_label(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._fl.get_by_label(t, exact=exact))

    def get_by_test_id(self, tid: str) -> AsyncLocator:
        return AsyncLocator(self._fl.get_by_test_id(tid))

    def frame_locator(self, sel: str) -> AsyncFrameLocator:
        return AsyncFrameLocator(self._fl.frame_locator(sel))


# ---------------------------------------------------------------------------
# AsyncLocator
# ---------------------------------------------------------------------------


class AsyncLocator:
    """Async wrapper around the sync Locator.

    Builder methods (get_by_*, locator, first, last, nth, filter) are SYNC —
    they only append a step to the recipe tuple without touching the DOM.

    All reads and actions are ASYNC, delegating to asyncio.to_thread so the
    event loop is never blocked by Selenium I/O.
    """

    def __init__(self, loc: Locator) -> None:
        self._loc = loc

    # --- sync builders ---

    def get_by_role(
        self, role: str, *, name: str | None = None, exact: bool = False
    ) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_role(role, name=name, exact=exact))

    def get_by_text(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_text(t, exact=exact))

    def get_by_label(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_label(t, exact=exact))

    def get_by_placeholder(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_placeholder(t, exact=exact))

    def get_by_alt_text(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_alt_text(t, exact=exact))

    def get_by_title(self, t: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_title(t, exact=exact))

    def get_by_test_id(self, tid: str) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_test_id(tid))

    def locator(self, sel: str) -> AsyncLocator:
        return AsyncLocator(self._loc.locator(sel))

    def filter(self, *, has_text: str | None = None) -> AsyncLocator:
        return AsyncLocator(self._loc.filter(has_text=has_text))

    def first(self) -> AsyncLocator:
        return AsyncLocator(self._loc.first())

    def last(self) -> AsyncLocator:
        return AsyncLocator(self._loc.last())

    def nth(self, i: int) -> AsyncLocator:
        return AsyncLocator(self._loc.nth(i))

    def frame_locator(self, sel: str) -> AsyncFrameLocator:
        return AsyncFrameLocator(self._loc.frame_locator(sel))

    # --- async reads ---

    async def count(self) -> int:
        return await asyncio.to_thread(self._loc.count)

    async def text_content(self) -> str | None:
        return await asyncio.to_thread(self._loc.text_content)

    async def input_value(self) -> str:
        return await asyncio.to_thread(self._loc.input_value)

    async def get_attribute(self, n: str) -> str | None:
        return await asyncio.to_thread(lambda: self._loc.get_attribute(n))

    async def all_text_contents(self) -> list[str]:
        return await asyncio.to_thread(self._loc.all_text_contents)

    async def all(self) -> list[AsyncLocator]:
        return [AsyncLocator(x) for x in await asyncio.to_thread(self._loc.all)]

    async def is_visible(self) -> bool:
        return await asyncio.to_thread(self._loc.is_visible)

    async def is_enabled(self) -> bool:
        return await asyncio.to_thread(self._loc.is_enabled)

    async def is_checked(self) -> bool:
        return await asyncio.to_thread(self._loc.is_checked)

    async def is_editable(self) -> bool:
        return await asyncio.to_thread(self._loc.is_editable)

    async def is_hidden(self) -> bool:
        return await asyncio.to_thread(self._loc.is_hidden)

    async def evaluate(self, expression: str, arg: object = None) -> object:
        return await asyncio.to_thread(lambda: self._loc.evaluate(expression, arg))

    async def screenshot(self, *, path: str | None = None) -> bytes:
        return await asyncio.to_thread(lambda: self._loc.screenshot(path=path))

    async def ocr_text(self) -> str:
        return await asyncio.to_thread(self._loc.ocr_text)

    async def find_image(self, template: object, *, confidence: float = 0.8) -> object:
        conf = confidence
        return await asyncio.to_thread(lambda: self._loc.find_image(template, confidence=conf))

    # --- async actions ---

    async def click(self, *, timeout: int | None = None, force: bool = False) -> None:
        await asyncio.to_thread(lambda: self._loc.click(timeout=timeout, force=force))

    async def dblclick(self, *, timeout: int | None = None, force: bool = False) -> None:
        await asyncio.to_thread(lambda: self._loc.dblclick(timeout=timeout, force=force))

    async def fill(self, v: str, *, timeout: int | None = None, force: bool = False) -> None:
        await asyncio.to_thread(lambda: self._loc.fill(v, timeout=timeout, force=force))

    async def press(self, key: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._loc.press(key, timeout=timeout))

    async def hover(self, *, timeout: int | None = None, force: bool = False) -> None:
        await asyncio.to_thread(lambda: self._loc.hover(timeout=timeout, force=force))

    async def check(self, *, timeout: int | None = None, force: bool = False) -> None:
        await asyncio.to_thread(lambda: self._loc.check(timeout=timeout, force=force))

    async def uncheck(self, *, timeout: int | None = None, force: bool = False) -> None:
        await asyncio.to_thread(lambda: self._loc.uncheck(timeout=timeout, force=force))

    async def set_checked(
        self, checked: bool, *, timeout: int | None = None, force: bool = False
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.set_checked(checked, timeout=timeout, force=force)
        )

    async def select_option(
        self,
        *,
        value: str | None = None,
        label: str | None = None,
        index: int | None = None,
        timeout: int | None = None,
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.select_option(value=value, label=label, index=index, timeout=timeout)
        )

    async def drag_to(self, target: AsyncLocator, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._loc.drag_to(target._loc, timeout=timeout))

    async def focus(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._loc.focus(timeout=timeout))

    async def blur(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._loc.blur(timeout=timeout))

    async def clear(self, *, timeout: int | None = None, force: bool = False) -> None:
        await asyncio.to_thread(lambda: self._loc.clear(timeout=timeout, force=force))

    async def set_input_files(self, files: str | list[str]) -> None:
        await asyncio.to_thread(lambda: self._loc.set_input_files(files))


# ---------------------------------------------------------------------------
# AsyncLocatorAssertions
# ---------------------------------------------------------------------------


class AsyncLocatorAssertions:
    """Async wrapper around the sync LocatorAssertions.

    All matchers block the thread via asyncio.to_thread, so polling never
    blocks the event loop.
    """

    def __init__(self, sync_assertions: LocatorAssertions) -> None:
        self._a = sync_assertions

    @property
    def not_(self) -> AsyncLocatorAssertions:
        return AsyncLocatorAssertions(self._a.not_)

    async def to_be_visible(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_be_visible(timeout=timeout))

    async def to_be_hidden(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_be_hidden(timeout=timeout))

    async def to_be_enabled(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_be_enabled(timeout=timeout))

    async def to_be_disabled(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_be_disabled(timeout=timeout))

    async def to_be_editable(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_be_editable(timeout=timeout))

    async def to_be_checked(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_be_checked(timeout=timeout))

    async def to_have_text(self, t: str, *, exact: bool = True, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_text(t, exact=exact, timeout=timeout))

    async def to_contain_text(self, t: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_contain_text(t, timeout=timeout))

    async def to_have_value(self, v: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_value(v, timeout=timeout))

    async def to_have_attribute(self, name: str, value: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_attribute(name, value, timeout=timeout))

    async def to_have_class(self, class_name: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_class(class_name, timeout=timeout))

    async def to_contain_class(self, class_name: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_contain_class(class_name, timeout=timeout))

    async def to_have_role(self, role: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_role(role, timeout=timeout))

    async def to_have_count(self, n: int, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_count(n, timeout=timeout))
