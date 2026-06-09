"""visus.web.async_api — async facade wrapping the sync API in asyncio.to_thread.

This facade mirrors the **entire** synchronous ``visus.web`` surface so an
asyncio program (FastAPI, bots, ``asyncio.gather`` over several browsers) never
has to drop into threads by hand. Every sync feature has an async counterpart,
with the **same method names and the same parameter names** — porting sync code
is a mechanical ``await`` insertion.

Two simple rules decide whether a member is ``async`` or plain:

* **Recipe builders** (``get_by_*`` / ``locator`` / ``first`` / ``last`` /
  ``nth`` / ``filter`` / ``frame_locator``) and **zero-I/O accessors** that only
  read state already held in-process (``handle`` / ``is_closed`` / ``context`` /
  ``contexts`` / ``mouse`` / ``keyboard`` / ``field`` / ``field_locator``) stay
  **synchronous** — they never touch the browser.
* **Everything that reaches the live browser** is an ``async`` coroutine that
  runs the blocking Selenium call in ``asyncio.to_thread`` so the event loop is
  never blocked.

Within a single browser session there is no real parallelism (the Selenium
session is single-threaded); the win is non-blocking integration with asyncio
and driving *several* browsers concurrently with ``asyncio.gather``.
"""

from __future__ import annotations

import asyncio
import sys
import webbrowser
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING

from visus.web import Engine, errors, tracing
from visus.web import expect as _sync_expect
from visus.web import launch as _sync_launch
from visus.web.api.browser import Browser
from visus.web.api.context import Context
from visus.web.api.events import Dialog, Download, _ValueHolder
from visus.web.api.fields import Field
from visus.web.api.frame_locator import FrameLocator
from visus.web.api.locator import Locator
from visus.web.api.page import Page
from visus.web.rpa import _print_summary, _slug

if TYPE_CHECKING:
    from visus.web.api.assertions import LocatorAssertions
    from visus.web.api.input import Keyboard, Mouse

__all__ = [
    "launch",
    "rpa",
    "expect",
    "Engine",
    "errors",
    "tracing",
    "Field",
    "Dialog",
    "Download",
    "AsyncBrowser",
    "AsyncContext",
    "AsyncPage",
    "AsyncLocator",
    "AsyncFrameLocator",
    "AsyncLocatorAssertions",
    "AsyncMouse",
    "AsyncKeyboard",
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
# rpa() — batteries-included async RPA session (launch + record + report)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def rpa(
    name: str = "run",
    *,
    engine: Engine | str = Engine.CHROME,
    headless: bool = False,
    outdir: str | None = None,
    report: bool = True,
    summary: bool = True,
    open_report: bool = False,
    reraise: bool = False,
) -> AsyncIterator[AsyncPage]:
    """Async twin of :func:`visus.web.rpa` — launch, recording, HTML report and a
    one-block summary are all handled for you. Yields a ready-to-drive
    :class:`AsyncPage`::

        from visus.web.async_api import rpa

        async with rpa("login", engine="firefox") as page:
            await page.goto("https://example.com/login")
            await page.get_by_label("User").fill("ada")
            await page.get_by_role("button", name="Sign in").click()

    On exit — whether the block finishes or a step fails — ``run.zip`` and
    ``report.html`` are written (to ``./visus-runs/<name>-<timestamp>/`` by
    default, or *outdir*), a summary is printed, and any error is surfaced just
    like the sync version (``reraise=True`` to re-raise the original error,
    otherwise the process exits with code 1 after the friendly summary).

    The recording itself spans the awaited browser calls (each runs in a worker
    thread that shares the global recorder); only the final zip/report write is
    done synchronously on the loop during teardown — identical to the sync flow.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = Path(outdir) if outdir else Path.cwd() / "visus-runs" / f"{_slug(name)}-{stamp}"
    base.mkdir(parents=True, exist_ok=True)
    zip_path = base / "run.zip"
    report_path = base / "report.html"

    box: dict[str, object] = {}
    rpa_error: BaseException | None = None
    try:
        with tracing.record(str(zip_path), report=str(report_path) if report else None) as rec:
            box["rec"] = rec
            browser = await launch(engine, headless=headless)
            try:
                yield await browser.new_page()
            finally:
                await browser.close()
    except (errors.VisusWebError, AssertionError) as exc:
        # an action failure (VisusWebError) OR an expect()/assert failure → present it
        # cleanly (friendly summary + exit 1) instead of dumping an internal traceback.
        rpa_error = exc
    finally:
        recorder = box.get("rec")
        active = rpa_error if rpa_error is not None else sys.exc_info()[1]
        if summary and recorder is not None:
            _print_summary(recorder, base, report_path if report else None, error=active)
        if open_report and report:
            try:
                webbrowser.open(report_path.resolve().as_uri())
            except Exception:
                pass

    if rpa_error is not None:
        if reraise:
            raise rpa_error
        raise SystemExit(1)


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

    @property
    def contexts(self) -> list[AsyncContext]:
        """The browser's open contexts (in-memory — no browser round-trip)."""
        return [AsyncContext(c) for c in self._b.contexts]

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

    async def pages(self) -> list[AsyncPage]:
        """The context's open pages/tabs (reconciles window handles — async)."""
        return [AsyncPage(p) for p in await asyncio.to_thread(lambda: self._c.pages)]

    async def adopt_open_windows(self) -> list[AsyncPage]:
        """Adopt windows/tabs opened outside visus; return the newly-adopted pages."""
        return [AsyncPage(p) for p in await asyncio.to_thread(self._c.adopt_open_windows)]

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

    Navigation, reads and actions are async; locator builders and zero-I/O
    accessors (``handle`` / ``is_closed`` / ``context`` / ``mouse`` /
    ``keyboard`` / ``field`` / ``field_locator``) are sync.
    """

    def __init__(self, p: Page) -> None:
        self._p = p

    # --- navigation / async reads ---

    async def goto(
        self,
        url: str,
        *,
        wait_until: str = "load",
        timeout: int | None = None,
        backtrack: bool | int = False,
    ) -> None:
        await asyncio.to_thread(
            lambda: self._p.goto(url, wait_until=wait_until, timeout=timeout, backtrack=backtrack)
        )

    async def title(self) -> str:
        return await asyncio.to_thread(self._p.title)

    async def content(self) -> str:
        return await asyncio.to_thread(self._p.content)

    async def url(self) -> str:
        return await asyncio.to_thread(lambda: self._p.url)

    async def screenshot(self, *, path: str | None = None, full_page: bool = False) -> bytes:
        return await asyncio.to_thread(lambda: self._p.screenshot(path=path, full_page=full_page))

    async def evaluate(self, expression: str, arg: object = None) -> object:
        return await asyncio.to_thread(lambda: self._p.evaluate(expression, arg))

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

    # --- zero-I/O accessors (sync, mirror the sync Page properties) ---

    @property
    def is_closed(self) -> bool:
        """Whether this page's tab/window has been closed (in-memory flag)."""
        return self._p.is_closed

    @property
    def handle(self) -> str:
        """The underlying browser window-handle string identifying this tab/window."""
        return self._p.handle

    @property
    def context(self) -> AsyncContext:
        """The :class:`AsyncContext` this page belongs to (Playwright-style)."""
        return AsyncContext(self._p.context)

    @property
    def mouse(self) -> AsyncMouse:
        """Low-level async mouse device for absolute-coordinate pointer actions."""
        return AsyncMouse(self._p.mouse)

    @property
    def keyboard(self) -> AsyncKeyboard:
        """Low-level async keyboard device for raw key events and text input."""
        return AsyncKeyboard(self._p.keyboard)

    # --- window focus (browser round-trip → async) ---

    async def bring_to_front(self) -> None:
        """Focus this page's tab/window (brings it to the front)."""
        await asyncio.to_thread(self._p.bring_to_front)

    async def activate(self) -> None:
        """Alias for :meth:`bring_to_front`."""
        await asyncio.to_thread(self._p.activate)

    # --- field enumerator ---

    async def list_fields(
        self,
        *,
        kinds: list[str] | None = None,
        include_hidden: bool = False,
        highlight: bool = True,
    ) -> list[Field]:
        """Enumerate RPA-relevant interactive fields on the current page (draws the
        numbered overlay unless ``highlight=False``)."""
        return await asyncio.to_thread(
            lambda: self._p.list_fields(
                kinds=kinds, include_hidden=include_hidden, highlight=highlight
            )
        )

    def field_locator(self, field: Field) -> AsyncLocator:
        """Build an :class:`AsyncLocator` for an enumerated :class:`Field`."""
        return AsyncLocator(self._p.field_locator(field))

    def field(self, index: int) -> AsyncLocator:
        """:class:`AsyncLocator` for field #*index* from the most recent
        :meth:`list_fields` call — act by number, like the CLI."""
        return AsyncLocator(self._p.field(index))

    async def clear_highlights(self) -> None:
        """Remove the numbered field overlay drawn by :meth:`list_fields`."""
        await asyncio.to_thread(self._p.clear_highlights)

    # --- vision ---

    async def solve_captcha(self, locator: AsyncLocator, *, preprocess: bool = True) -> str:
        """Solve a text/image CAPTCHA from *locator* (requires the ``[vision]`` extra)."""
        return await asyncio.to_thread(
            lambda: self._p.solve_captcha(locator._loc, preprocess=preprocess)
        )

    # --- event-capture context managers ---

    @asynccontextmanager
    async def expect_popup(self, *, timeout: int | None = None) -> AsyncIterator[_ValueHolder]:
        """Capture the new page opened as a popup. ``holder.value`` is an
        :class:`AsyncPage`::

            async with page.expect_popup() as popup:
                await page.get_by_role("link", name="Open").click()
            await popup.value.goto(...)
        """
        p = self._p
        before = await asyncio.to_thread(p._delegate.snapshot_handles)
        holder = _ValueHolder()
        yield holder
        t = timeout if timeout is not None else p._defaults.action_timeout_ms
        new_delegate = await asyncio.to_thread(
            p._delegate.adopt_new_handle, before, timeout_ms=t
        )
        holder._set(AsyncPage(Page(new_delegate, p._defaults)))

    @asynccontextmanager
    async def expect_dialog(
        self,
        *,
        accept: bool = True,
        prompt_text: str | None = None,
        timeout: int | None = None,
    ) -> AsyncIterator[_ValueHolder]:
        """Handle the next browser dialog; ``holder.value`` is a
        :class:`~visus.web.api.events.Dialog`."""
        p = self._p
        holder = _ValueHolder()
        yield holder
        t = timeout if timeout is not None else p._defaults.action_timeout_ms
        msg, typ = await asyncio.to_thread(
            p._delegate.handle_next_dialog,
            accept=accept,
            prompt_text=prompt_text,
            timeout_ms=t,
        )
        holder._set(Dialog(message=msg, type=typ))

    @asynccontextmanager
    async def expect_download(self, *, timeout: int | None = None) -> AsyncIterator[_ValueHolder]:
        """Wait for a file download to complete and capture it as a
        :class:`~visus.web.api.events.Download`."""
        p = self._p
        before = await asyncio.to_thread(p._delegate.snapshot_download_dir)
        holder = _ValueHolder()
        yield holder
        t = timeout if timeout is not None else p._defaults.action_timeout_ms
        path, name = await asyncio.to_thread(p._delegate.wait_for_download, before, timeout_ms=t)
        holder._set(Download(path=path, suggested_filename=name))

    # --- network controls (Chromium CDP) ---

    async def block_urls(self, patterns: list[str]) -> None:
        await asyncio.to_thread(lambda: self._p.block_urls(patterns))

    async def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        await asyncio.to_thread(lambda: self._p.set_extra_http_headers(headers))

    async def set_offline(self, offline: bool) -> None:
        await asyncio.to_thread(lambda: self._p.set_offline(offline))

    # --- sync locator builders (return AsyncLocator / AsyncFrameLocator) ---

    def locator(self, selector: str, *, deep: bool = False) -> AsyncLocator:
        return AsyncLocator(self._p.locator(selector, deep=deep))

    def get_by_role(
        self, role: str, *, name: str | None = None, exact: bool = False
    ) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_role(role, name=name, exact=exact))

    def get_by_text(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_text(text, exact=exact))

    def get_by_label(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_label(text, exact=exact))

    def get_by_placeholder(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_placeholder(text, exact=exact))

    def get_by_test_id(self, test_id: str) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_test_id(test_id))

    def get_by_alt_text(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_alt_text(text, exact=exact))

    def get_by_title(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._p.get_by_title(text, exact=exact))

    def frame_locator(self, selector: str) -> AsyncFrameLocator:
        return AsyncFrameLocator(self._p.frame_locator(selector))


# ---------------------------------------------------------------------------
# AsyncMouse / AsyncKeyboard
# ---------------------------------------------------------------------------


class AsyncMouse:
    """Async wrapper around the sync Mouse device facade."""

    def __init__(self, m: Mouse) -> None:
        self._m = m

    async def move(self, x: float, y: float) -> None:
        await asyncio.to_thread(self._m.move, x, y)

    async def down(self) -> None:
        await asyncio.to_thread(self._m.down)

    async def up(self) -> None:
        await asyncio.to_thread(self._m.up)

    async def click(self, x: float, y: float) -> None:
        await asyncio.to_thread(self._m.click, x, y)

    async def dblclick(self, x: float, y: float) -> None:
        await asyncio.to_thread(self._m.dblclick, x, y)

    async def wheel(self, delta_x: float, delta_y: float) -> None:
        await asyncio.to_thread(self._m.wheel, delta_x, delta_y)


class AsyncKeyboard:
    """Async wrapper around the sync Keyboard device facade."""

    def __init__(self, k: Keyboard) -> None:
        self._k = k

    async def down(self, key: str) -> None:
        await asyncio.to_thread(self._k.down, key)

    async def up(self, key: str) -> None:
        await asyncio.to_thread(self._k.up, key)

    async def press(self, key: str) -> None:
        await asyncio.to_thread(self._k.press, key)

    async def type(self, text: str) -> None:
        await asyncio.to_thread(self._k.type, text)

    async def insert_text(self, text: str) -> None:
        await asyncio.to_thread(self._k.insert_text, text)


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

    def locator(self, selector: str, *, deep: bool = False) -> AsyncLocator:
        return AsyncLocator(self._fl.locator(selector, deep=deep))

    def get_by_role(
        self, role: str, *, name: str | None = None, exact: bool = False
    ) -> AsyncLocator:
        return AsyncLocator(self._fl.get_by_role(role, name=name, exact=exact))

    def get_by_text(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._fl.get_by_text(text, exact=exact))

    def get_by_label(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._fl.get_by_label(text, exact=exact))

    def get_by_test_id(self, test_id: str) -> AsyncLocator:
        return AsyncLocator(self._fl.get_by_test_id(test_id))

    def frame_locator(self, selector: str) -> AsyncFrameLocator:
        return AsyncFrameLocator(self._fl.frame_locator(selector))


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

    def get_by_text(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_text(text, exact=exact))

    def get_by_label(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_label(text, exact=exact))

    def get_by_placeholder(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_placeholder(text, exact=exact))

    def get_by_alt_text(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_alt_text(text, exact=exact))

    def get_by_title(self, text: str, *, exact: bool = False) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_title(text, exact=exact))

    def get_by_test_id(self, test_id: str) -> AsyncLocator:
        return AsyncLocator(self._loc.get_by_test_id(test_id))

    def locator(self, selector: str, *, deep: bool = False) -> AsyncLocator:
        return AsyncLocator(self._loc.locator(selector, deep=deep))

    def filter(self, *, has_text: str | None = None) -> AsyncLocator:
        return AsyncLocator(self._loc.filter(has_text=has_text))

    def first(self) -> AsyncLocator:
        return AsyncLocator(self._loc.first())

    def last(self) -> AsyncLocator:
        return AsyncLocator(self._loc.last())

    def nth(self, index: int) -> AsyncLocator:
        return AsyncLocator(self._loc.nth(index))

    def frame_locator(self, selector: str) -> AsyncFrameLocator:
        return AsyncFrameLocator(self._loc.frame_locator(selector))

    # --- async reads ---

    async def count(self) -> int:
        return await asyncio.to_thread(self._loc.count)

    async def text_content(self) -> str | None:
        return await asyncio.to_thread(self._loc.text_content)

    async def input_value(self) -> str:
        return await asyncio.to_thread(self._loc.input_value)

    async def get_attribute(self, name: str) -> str | None:
        return await asyncio.to_thread(lambda: self._loc.get_attribute(name))

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

    async def click(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.click(timeout=timeout, force=force, backtrack=backtrack)
        )

    async def dblclick(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.dblclick(timeout=timeout, force=force, backtrack=backtrack)
        )

    async def fill(
        self,
        value: str,
        *,
        timeout: int | None = None,
        force: bool = False,
        backtrack: bool | int = False,
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.fill(value, timeout=timeout, force=force, backtrack=backtrack)
        )

    async def press(
        self, key: str, *, timeout: int | None = None, backtrack: bool | int = False
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.press(key, timeout=timeout, backtrack=backtrack)
        )

    async def hover(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.hover(timeout=timeout, force=force, backtrack=backtrack)
        )

    async def check(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.check(timeout=timeout, force=force, backtrack=backtrack)
        )

    async def uncheck(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.uncheck(timeout=timeout, force=force, backtrack=backtrack)
        )

    async def set_checked(
        self,
        checked: bool,
        *,
        timeout: int | None = None,
        force: bool = False,
        backtrack: bool | int = False,
    ) -> None:
        bt = backtrack
        await asyncio.to_thread(
            lambda: self._loc.set_checked(checked, timeout=timeout, force=force, backtrack=bt)
        )

    async def select_option(
        self,
        *,
        value: str | None = None,
        label: str | None = None,
        index: int | None = None,
        timeout: int | None = None,
        backtrack: bool | int = False,
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.select_option(
                value=value, label=label, index=index, timeout=timeout, backtrack=backtrack
            )
        )

    async def drag_to(
        self, target: AsyncLocator, *, timeout: int | None = None, backtrack: bool | int = False
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.drag_to(target._loc, timeout=timeout, backtrack=backtrack)
        )

    async def focus(
        self, *, timeout: int | None = None, backtrack: bool | int = False
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.focus(timeout=timeout, backtrack=backtrack)
        )

    async def blur(
        self, *, timeout: int | None = None, backtrack: bool | int = False
    ) -> None:
        await asyncio.to_thread(lambda: self._loc.blur(timeout=timeout, backtrack=backtrack))

    async def clear(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.clear(timeout=timeout, force=force, backtrack=backtrack)
        )

    async def set_input_files(
        self, files: str | list[str], *, backtrack: bool | int = False
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.set_input_files(files, backtrack=backtrack)
        )


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

    async def to_have_text(
        self, expected: str, *, exact: bool = True, timeout: int | None = None
    ) -> None:
        await asyncio.to_thread(
            lambda: self._a.to_have_text(expected, exact=exact, timeout=timeout)
        )

    async def to_contain_text(self, expected: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_contain_text(expected, timeout=timeout))

    async def to_have_value(self, value: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_value(value, timeout=timeout))

    async def to_have_attribute(self, name: str, value: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_attribute(name, value, timeout=timeout))

    async def to_have_class(self, class_name: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_class(class_name, timeout=timeout))

    async def to_contain_class(self, class_name: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_contain_class(class_name, timeout=timeout))

    async def to_have_role(self, role: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_role(role, timeout=timeout))

    async def to_have_count(self, count: int, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_count(count, timeout=timeout))
