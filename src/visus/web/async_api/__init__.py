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
from visus.web.api.assertions import PageAssertions, verify_soft
from visus.web.api.assertions import _soft_expect as _sync_soft_expect
from visus.web.api.browser import Browser
from visus.web.api.context import Context
from visus.web.api.events import ConsoleMessage, Dialog, Download, NetworkResponse, _ValueHolder
from visus.web.api.fields import Field
from visus.web.api.frame_locator import FrameLocator
from visus.web.api.locator import Locator, TextArg
from visus.web.api.page import Page
from visus.web.rpa import _print_summary, _slug

if TYPE_CHECKING:
    import re
    from collections.abc import Callable, Sequence

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
    "ConsoleMessage",
    "AsyncBrowser",
    "AsyncContext",
    "AsyncPage",
    "AsyncLocator",
    "AsyncFrameLocator",
    "AsyncLocatorAssertions",
    "AsyncPageAssertions",
    "AsyncNetworkResponse",
    "AsyncMouse",
    "AsyncKeyboard",
]


# ---------------------------------------------------------------------------
# Top-level factory
# ---------------------------------------------------------------------------


async def launch(
    engine: Engine | str = Engine.CHROME,
    *,
    headless: bool = False,
    slow_mo: int = 0,
    user_data_dir: str | None = None,
    remote_url: str | None = None,
) -> AsyncBrowser:
    """Launch a browser and return an AsyncBrowser handle.

    Same options as the sync :func:`visus.web.launch` — *slow_mo* (ms delay per
    operation), *user_data_dir* (persistent profile) and *remote_url* (Selenium
    Grid / Remote WebDriver).

    Usage::

        async with await launch(headless=True) as browser:
            page = await browser.new_page()
            await page.goto("https://example.com")
    """
    return AsyncBrowser(
        await asyncio.to_thread(
            lambda: _sync_launch(
                engine,
                headless=headless,
                slow_mo=slow_mo,
                user_data_dir=user_data_dir,
                remote_url=remote_url,
            )
        )
    )


# ---------------------------------------------------------------------------
# rpa() — batteries-included async RPA session (launch + record + report)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def rpa(
    name: str = "run",
    *,
    engine: Engine | str = Engine.CHROME,
    headless: bool = False,
    slow_mo: int = 0,
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
            browser = await launch(engine, headless=headless, slow_mo=slow_mo)
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


def expect(
    target: AsyncLocator | AsyncPage, message: str | None = None
) -> AsyncLocatorAssertions | AsyncPageAssertions:
    """Web-first assertion entry point (async).

    ``await expect(locator).to_be_visible()``,
    ``await expect(page).to_have_url(...)``. Pass *message* to prefix failures;
    use ``expect.soft(...)`` + ``expect.verify_soft()`` for soft assertions.
    """
    if isinstance(target, AsyncPage):
        return AsyncPageAssertions(PageAssertions(target._p, message=message))
    return AsyncLocatorAssertions(_sync_expect(target._loc, message))


def _soft_expect(
    target: AsyncLocator | AsyncPage, message: str | None = None
) -> AsyncLocatorAssertions | AsyncPageAssertions:
    """Soft variant of :func:`expect` — failures are collected, not raised."""
    if isinstance(target, AsyncPage):
        return AsyncPageAssertions(PageAssertions(target._p, message=message, soft=True))
    return AsyncLocatorAssertions(_sync_soft_expect(target._loc, message))  # type: ignore[arg-type]


expect.soft = _soft_expect  # type: ignore[attr-defined]
expect.verify_soft = verify_soft  # type: ignore[attr-defined]


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

    def set_default_timeout(self, timeout: int) -> None:
        """Default timeout (ms) for pages created after this call (in-memory)."""
        self._c.set_default_timeout(timeout)

    def set_default_navigation_timeout(self, timeout: int) -> None:
        """Default navigation timeout (ms) for pages created after this call."""
        self._c.set_default_navigation_timeout(timeout)

    async def storage_state(self, *, path: str | None = None) -> dict:  # type: ignore[type-arg]
        """Snapshot cookies + web storage; optionally write it to *path* as JSON."""
        return await asyncio.to_thread(lambda: self._c.storage_state(path=path))

    async def restore_storage_state(self, state: dict | str) -> None:  # type: ignore[type-arg]
        """Apply a snapshot from :meth:`storage_state` (dict or JSON file path)."""
        await asyncio.to_thread(lambda: self._c.restore_storage_state(state))

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

    # --- default timeouts (in-memory → sync) ---

    def set_default_timeout(self, timeout: int) -> None:
        """Default timeout (ms) for actions AND navigations on this page."""
        self._p.set_default_timeout(timeout)

    def set_default_navigation_timeout(self, timeout: int) -> None:
        """Default timeout (ms) for navigations only."""
        self._p.set_default_navigation_timeout(timeout)

    # --- web-first synchronization ---

    async def wait_for_url(
        self,
        url: str | re.Pattern[str] | Callable[[str], bool],
        *,
        timeout: int | None = None,
    ) -> None:
        """Wait until the page URL matches *url* (glob, regex or predicate)."""
        await asyncio.to_thread(lambda: self._p.wait_for_url(url, timeout=timeout))

    async def wait_for_load_state(self, state: str = "load", *, timeout: int | None = None) -> None:
        """Wait for document.readyState: 'load' or 'domcontentloaded'."""
        await asyncio.to_thread(lambda: self._p.wait_for_load_state(state, timeout=timeout))

    async def wait_for_function(
        self, expression: str, arg: object = None, *, timeout: int | None = None
    ) -> object:
        """Poll a JS function until truthy; return its value."""
        return await asyncio.to_thread(
            lambda: self._p.wait_for_function(expression, arg, timeout=timeout)
        )

    async def wait_for_timeout(self, timeout: float) -> None:
        """Async sleep for *timeout* milliseconds (does not block the loop)."""
        await asyncio.sleep(timeout / 1000)

    # --- network/console capture (Chromium) ---

    async def network_requests(self) -> list[AsyncNetworkResponse]:
        """Every network response captured so far (Chromium only)."""
        recs = await asyncio.to_thread(self._p.network_requests)
        return [AsyncNetworkResponse(r) for r in recs]

    async def console_messages(self) -> list[ConsoleMessage]:
        """Every console message captured so far (Chromium only)."""
        return await asyncio.to_thread(self._p.console_messages)

    async def wait_for_response(
        self, url_pattern: str, *, timeout: int | None = None
    ) -> AsyncNetworkResponse:
        """Wait for the next response whose URL matches *url_pattern* (Chromium only)."""
        rec = await asyncio.to_thread(
            lambda: self._p.wait_for_response(url_pattern, timeout=timeout)
        )
        return AsyncNetworkResponse(rec)

    @asynccontextmanager
    async def expect_response(
        self, url_pattern: str, *, timeout: int | None = None
    ) -> AsyncIterator[_ValueHolder]:
        """Run an action and capture the response it triggers (Chromium only)::

            async with page.expect_response("*api/login*") as info:
                await page.get_by_role("button", name="Sign in").click()
            assert info.value.ok
        """
        p = self._p
        marker = await asyncio.to_thread(p._delegate.network_marker)
        holder = _ValueHolder()
        yield holder
        t = timeout if timeout is not None else p._defaults.action_timeout_ms
        rec = await asyncio.to_thread(
            lambda: p._delegate.wait_for_response(url_pattern, timeout_ms=t, from_index=marker)
        )
        holder._set(AsyncNetworkResponse(NetworkResponse(p._delegate, rec)))

    # --- init scripts + emulation ---

    async def add_init_script(self, script: str) -> None:
        """Inject *script* before every document loaded from now on (Chromium only)."""
        await asyncio.to_thread(lambda: self._p.add_init_script(script))

    async def set_geolocation(
        self, latitude: float, longitude: float, *, accuracy: float = 100
    ) -> None:
        """Override the device geolocation (Chromium only)."""
        await asyncio.to_thread(
            lambda: self._p.set_geolocation(latitude, longitude, accuracy=accuracy)
        )

    async def grant_permissions(
        self, permissions: list[str], *, origin: str | None = None
    ) -> None:
        """Grant browser permissions, optionally per-origin (Chromium only)."""
        await asyncio.to_thread(lambda: self._p.grant_permissions(permissions, origin=origin))

    async def set_device_metrics(
        self,
        width: int,
        height: int,
        *,
        device_scale_factor: float = 1.0,
        mobile: bool = False,
    ) -> None:
        """Emulate a device viewport: size, pixel ratio, mobile flag (Chromium only)."""
        await asyncio.to_thread(
            lambda: self._p.set_device_metrics(
                width, height, device_scale_factor=device_scale_factor, mobile=mobile
            )
        )

    async def set_viewport_size(self, width: int, height: int) -> None:
        """Resize the window so the page viewport is exactly width×height."""
        await asyncio.to_thread(lambda: self._p.set_viewport_size(width, height))

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
# AsyncNetworkResponse
# ---------------------------------------------------------------------------


class AsyncNetworkResponse:
    """Async wrapper around a captured :class:`~visus.web.api.events.NetworkResponse`."""

    def __init__(self, r: NetworkResponse) -> None:
        self._r = r
        self.url = r.url
        self.status = r.status
        self.method = r.method
        self.resource_type = r.resource_type

    @property
    def ok(self) -> bool:
        """True for a 2xx status."""
        return self._r.ok

    async def body(self) -> str:
        """The response body (decoded as UTF-8), fetched via CDP."""
        return await asyncio.to_thread(self._r.body)

    def __repr__(self) -> str:
        return repr(self._r).replace("NetworkResponse", "AsyncNetworkResponse")


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

    def filter(
        self,
        *,
        has_text: TextArg | None = None,
        has_not_text: TextArg | None = None,
        has: AsyncLocator | None = None,
        has_not: AsyncLocator | None = None,
    ) -> AsyncLocator:
        return AsyncLocator(
            self._loc.filter(
                has_text=has_text,
                has_not_text=has_not_text,
                has=has._loc if has is not None else None,
                has_not=has_not._loc if has_not is not None else None,
            )
        )

    def or_(self, other: AsyncLocator) -> AsyncLocator:
        """Elements matching this locator OR *other* (union, document order)."""
        return AsyncLocator(self._loc.or_(other._loc))

    def and_(self, other: AsyncLocator) -> AsyncLocator:
        """Elements matching this locator AND *other* (intersection)."""
        return AsyncLocator(self._loc.and_(other._loc))

    def first(self) -> AsyncLocator:
        return AsyncLocator(self._loc.first())

    def last(self) -> AsyncLocator:
        return AsyncLocator(self._loc.last())

    def nth(self, index: int) -> AsyncLocator:
        return AsyncLocator(self._loc.nth(index))

    def frame_locator(self, selector: str) -> AsyncFrameLocator:
        return AsyncFrameLocator(self._loc.frame_locator(selector))

    # --- async reads ---

    async def wait_for(self, *, state: str = "visible", timeout: int | None = None) -> None:
        """Wait until the locator reaches *state*: visible|hidden|attached|detached."""
        await asyncio.to_thread(lambda: self._loc.wait_for(state=state, timeout=timeout))

    async def inner_text(self) -> str:
        return await asyncio.to_thread(self._loc.inner_text)

    async def inner_html(self) -> str:
        return await asyncio.to_thread(self._loc.inner_html)

    async def all_inner_texts(self) -> list[str]:
        return await asyncio.to_thread(self._loc.all_inner_texts)

    async def bounding_box(self) -> dict[str, float] | None:
        return await asyncio.to_thread(self._loc.bounding_box)

    async def dispatch_event(
        self, type: str, event_init: dict[str, object] | None = None
    ) -> None:
        await asyncio.to_thread(lambda: self._loc.dispatch_event(type, event_init))

    async def scroll_into_view_if_needed(self) -> None:
        await asyncio.to_thread(self._loc.scroll_into_view_if_needed)

    async def highlight(self) -> None:
        await asyncio.to_thread(self._loc.highlight)

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

    async def press_sequentially(
        self,
        text: str,
        *,
        delay: int = 0,
        timeout: int | None = None,
        backtrack: bool | int = False,
    ) -> None:
        await asyncio.to_thread(
            lambda: self._loc.press_sequentially(
                text, delay=delay, timeout=timeout, backtrack=backtrack
            )
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

    async def to_be_attached(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_be_attached(timeout=timeout))

    async def to_be_focused(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_be_focused(timeout=timeout))

    async def to_be_empty(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_be_empty(timeout=timeout))

    async def to_be_in_viewport(self, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_be_in_viewport(timeout=timeout))

    async def to_have_css(self, name: str, value: TextArg, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_css(name, value, timeout=timeout))

    async def to_have_id(self, id: str, *, timeout: int | None = None) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_id(id, timeout=timeout))

    async def to_have_values(
        self, values: Sequence[str], *, timeout: int | None = None
    ) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_values(values, timeout=timeout))


# ---------------------------------------------------------------------------
# AsyncPageAssertions
# ---------------------------------------------------------------------------


class AsyncPageAssertions:
    """Async wrapper around the sync PageAssertions."""

    def __init__(self, sync_assertions: PageAssertions) -> None:
        self._a = sync_assertions

    @property
    def not_(self) -> AsyncPageAssertions:
        return AsyncPageAssertions(self._a.not_)

    async def to_have_url(
        self, url: str | re.Pattern[str], *, timeout: int | None = None
    ) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_url(url, timeout=timeout))

    async def to_have_title(
        self, title: str | re.Pattern[str], *, timeout: int | None = None
    ) -> None:
        await asyncio.to_thread(lambda: self._a.to_have_title(title, timeout=timeout))
