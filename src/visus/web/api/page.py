from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any, cast

from visus.web import errors

from visus.web.api._steps import run_step
from visus.web.api.events import Dialog, Download, _ValueHolder
from visus.web.api.locator import Locator, TextArg
from visus.web.backends.base import PageDelegate
from visus.web.config import Defaults

if TYPE_CHECKING:
    from visus.web.api.context import Context
    from visus.web.api.fields import Field
    from visus.web.api.frame_locator import FrameLocator
    from visus.web.api.input import Keyboard, Mouse


class Page:
    def __init__(self, delegate: PageDelegate, defaults: Defaults) -> None:
        self._delegate = delegate
        self._defaults = defaults
        self._last_fields: list[Field] = []

    def goto(
        self,
        url: str,
        *,
        wait_until: str = "load",
        timeout: int | None = None,
        backtrack: bool | int = False,
    ) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.goto(
                url,
                wait_until=wait_until,
                timeout_ms=timeout if timeout is not None else self._defaults.navigation_timeout_ms,
            ),
            backtrack,
            action_name="goto",
            target=url,
        )

    @property
    def url(self) -> str:
        return self._delegate.current_url()

    def title(self) -> str:
        return self._delegate.title()

    def content(self) -> str:
        return self._delegate.content()

    def reload(self, *, timeout: int | None = None) -> None:
        self._delegate.reload(
            timeout_ms=timeout if timeout is not None else self._defaults.navigation_timeout_ms
        )

    def go_back(self, *, timeout: int | None = None) -> None:
        self._delegate.go_back(
            timeout_ms=timeout if timeout is not None else self._defaults.navigation_timeout_ms
        )

    def go_forward(self, *, timeout: int | None = None) -> None:
        self._delegate.go_forward(
            timeout_ms=timeout if timeout is not None else self._defaults.navigation_timeout_ms
        )

    def close(self) -> None:
        self._delegate.close()

    # --- default timeouts (page-level overrides) ---

    def set_default_timeout(self, timeout: int) -> None:
        """Default timeout (ms) for actions AND navigations on this page.

        Locators created *after* this call pick up the new default; per-call
        ``timeout=`` still wins. Call it right after creating the page.
        """
        self._defaults = replace(
            self._defaults, action_timeout_ms=timeout, navigation_timeout_ms=timeout
        )

    def set_default_navigation_timeout(self, timeout: int) -> None:
        """Default timeout (ms) for navigations only (``goto``/``reload``/history)."""
        self._defaults = replace(self._defaults, navigation_timeout_ms=timeout)

    # --- web-first synchronization ---

    def _poll_until(self, check: Callable[[], bool], timeout_ms: int, what: str) -> None:
        deadline = monotonic() + timeout_ms / 1000
        while True:
            if check():
                return
            if monotonic() >= deadline:
                raise errors.VisusTimeoutError(f"{what} not satisfied within {timeout_ms}ms")
            sleep(0.1)

    def wait_for_url(
        self,
        url: str | re.Pattern[str] | Callable[[str], bool],
        *,
        timeout: int | None = None,
    ) -> None:
        """Wait until :attr:`url` matches *url* — a glob string (``"*checkout*"``),
        a compiled regex (``re.search``), or a predicate over the current URL."""
        t = timeout if timeout is not None else self._defaults.navigation_timeout_ms
        if isinstance(url, re.Pattern):
            check: Callable[[], bool] = lambda: bool(url.search(self._delegate.current_url()))
        elif callable(url):
            check = lambda: bool(url(self._delegate.current_url()))
        else:
            check = lambda: (
                fnmatch.fnmatch(self._delegate.current_url(), url)
                or self._delegate.current_url() == url
            )
        self._poll_until(check, t, f"wait_for_url({url!r})")

    def wait_for_load_state(self, state: str = "load", *, timeout: int | None = None) -> None:
        """Wait for ``document.readyState``: ``"load"`` (complete) or
        ``"domcontentloaded"`` (interactive or complete)."""
        if state not in ("load", "domcontentloaded"):
            raise ValueError("state must be 'load' or 'domcontentloaded'")
        want = ("complete",) if state == "load" else ("interactive", "complete")
        t = timeout if timeout is not None else self._defaults.navigation_timeout_ms
        self._poll_until(
            lambda: self._delegate.evaluate("() => document.readyState", None) in want,
            t,
            f"wait_for_load_state({state!r})",
        )

    def wait_for_function(
        self, expression: str, arg: object = None, *, timeout: int | None = None
    ) -> object:
        """Poll *expression* (a JS function) until it returns a truthy value;
        return that value."""
        t = timeout if timeout is not None else self._defaults.action_timeout_ms
        result: list[object] = [None]

        def check() -> bool:
            result[0] = self._delegate.evaluate(expression, arg)
            return bool(result[0])

        self._poll_until(check, t, f"wait_for_function({expression!r})")
        return result[0]

    def wait_for_timeout(self, timeout: float) -> None:
        """Sleep for *timeout* milliseconds. Discouraged — prefer web-first waits
        (:meth:`wait_for_url`, ``locator.wait_for``, ``expect``)."""
        sleep(timeout / 1000)

    @property
    def is_closed(self) -> bool:
        return self._delegate.is_closed()

    @property
    def handle(self) -> str:
        """The underlying browser window-handle string identifying this tab/window.

        Stable for the lifetime of the browser session — use it to key a page to
        a row in a window list across refreshes.
        """
        return self._delegate.handle()

    @property
    def context(self) -> Context:
        """The :class:`~visus.web.api.context.Context` this page belongs to.

        Playwright-style ``page.context`` — lets you reach ``page.context.pages``
        (e.g. from the page handed to you by ``rpa()``) to enumerate or focus
        other tabs without dropping down to ``launch``.
        """
        from visus.web.api.context import Context

        return Context(self._delegate.context(), self._defaults)

    def bring_to_front(self) -> None:
        """Focus this page's tab/window (brings it to the front)."""
        self._delegate.bring_to_front()

    def activate(self) -> None:
        """Alias for :meth:`bring_to_front`."""
        self._delegate.bring_to_front()

    def locator(self, selector: str, *, deep: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).locator(selector, deep=deep)

    def frame_locator(self, selector: str) -> FrameLocator:
        from visus.web.api.frame_locator import FrameLocator, _frame_step

        return FrameLocator(self._delegate, (_frame_step(selector),), self._defaults)

    def get_by_role(
        self, role: str, *, name: TextArg | None = None, exact: bool = False
    ) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_role(role, name=name, exact=exact)

    def get_by_text(self, text: TextArg, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_text(text, exact=exact)

    def get_by_label(self, text: TextArg, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_label(text, exact=exact)

    def get_by_placeholder(self, text: TextArg, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_placeholder(text, exact=exact)

    def get_by_alt_text(self, text: TextArg, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_alt_text(text, exact=exact)

    def get_by_title(self, text: TextArg, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_title(text, exact=exact)

    def get_by_test_id(self, test_id: str) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_test_id(test_id)

    def snapshot(self) -> list[dict]:  # type: ignore[type-arg]
        """Return the page's interactive elements as a list of {role, name} dicts."""
        return self._delegate.snapshot()

    def list_fields(
        self,
        *,
        kinds: list[str] | None = None,
        include_hidden: bool = False,
        highlight: bool = True,
    ) -> list[Field]:
        """Enumerate RPA-relevant interactive fields on the current page.

        Walks the main document, open Shadow DOM, and same-origin iframes, returning
        a stable, document-order list of :class:`Field` descriptors. By default only
        visible, enabled fields are returned and a numbered overlay is drawn (a no-op
        in headless); pass ``highlight=False`` to skip drawing, ``include_hidden=True``
        to also return hidden/disabled fields, or ``kinds=[...]`` to filter by kind.
        """
        fields = self._delegate.list_fields(
            kinds=kinds, include_hidden=include_hidden, highlight=highlight
        )
        self._last_fields = list(fields)  # cached for field(index)
        return fields

    def field_locator(self, field: Field) -> Locator:
        """Build a :class:`Locator` for an enumerated :class:`Field` (from
        :meth:`list_fields`), resolving its iframe chain and shadow-DOM (``deep``)
        automatically — the script equivalent of the CLI's ``visus click/fill <n>``::

            for f in page.list_fields():
                if f.name == "Username":
                    page.field_locator(f).fill("student")
        """
        root: Any = self
        for sel in field.frame:
            root = root.frame_locator(sel)
        return cast(Locator, root.locator(field.locator, deep=field.deep))

    def field(self, index: int) -> Locator:
        """:class:`Locator` for field #*index* from the most recent
        :meth:`list_fields` call — act by number like the CLI::

            page.list_fields()              # discover (also draws the overlay)
            page.field(9).fill("student")   # == `visus fill 9 student`

        Note: indices are positional and shift if the page changes — great for
        quick/interactive scripts; for durable automation prefer a stable selector
        (e.g. the ``code``/``css`` from a field, like ``page.locator("#username")``).
        """
        if not self._last_fields:
            raise RuntimeError("no fields cached — call page.list_fields() first")
        if not 0 <= index < len(self._last_fields):
            raise IndexError(
                f"field index {index} out of range (have {len(self._last_fields)})"
            )
        return self.field_locator(self._last_fields[index])

    def clear_highlights(self) -> None:
        """Remove the numbered field overlay drawn by :meth:`list_fields`."""
        self._delegate.clear_highlights()

    def evaluate(self, expression: str, arg: object = None) -> object:
        return self._delegate.evaluate(expression, arg)

    def screenshot(self, *, path: str | None = None, full_page: bool = False) -> bytes:
        data = self._delegate.screenshot(full_page=full_page)
        if path is not None:
            Path(path).write_bytes(data)
        return data

    @property
    def mouse(self) -> Mouse:
        """Low-level mouse device for absolute-coordinate pointer actions."""
        from visus.web.api.input import Mouse

        return Mouse(self._delegate)

    @property
    def keyboard(self) -> Keyboard:
        """Low-level keyboard device for raw key events and text input."""
        from visus.web.api.input import Keyboard

        return Keyboard(self._delegate)

    def pdf(self, *, path: str | None = None) -> bytes:
        """Print the current page to PDF (Chromium only, via CDP printToPDF)."""
        data = self._delegate.pdf()
        if path is not None:
            Path(path).write_bytes(data)
        return data

    # --- vision hooks (lazy-import; requires [vision] extra) ---
    def solve_captcha(self, locator: Locator, *, preprocess: bool = True) -> str:
        from visus.web.vision import solve_captcha

        return solve_captcha(locator.screenshot(), preprocess=preprocess)

    @contextmanager
    def expect_popup(self, *, timeout: int | None = None) -> Generator[_ValueHolder, None, None]:
        """Context manager that captures the new Page opened as a popup."""
        before = self._delegate.snapshot_handles()
        holder: _ValueHolder = _ValueHolder()
        yield holder
        new_delegate = self._delegate.adopt_new_handle(
            before,
            timeout_ms=timeout if timeout is not None else self._defaults.action_timeout_ms,
        )
        holder._set(Page(new_delegate, self._defaults))

    @contextmanager
    def expect_dialog(
        self,
        *,
        accept: bool = True,
        prompt_text: str | None = None,
        timeout: int | None = None,
    ) -> Generator[_ValueHolder, None, None]:
        """Context manager that handles the next browser dialog and captures its details."""
        holder: _ValueHolder = _ValueHolder()
        yield holder
        msg, typ = self._delegate.handle_next_dialog(
            accept=accept,
            prompt_text=prompt_text,
            timeout_ms=timeout if timeout is not None else self._defaults.action_timeout_ms,
        )
        holder._set(Dialog(message=msg, type=typ))

    # --- network controls (Chromium CDP) ---

    def block_urls(self, patterns: list[str]) -> None:
        """Block network requests matching *patterns* (Chromium only, via CDP)."""
        self._delegate.block_urls(patterns)

    def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        """Attach extra HTTP request headers to every request (Chromium only, via CDP)."""
        self._delegate.set_extra_http_headers(headers)

    def set_offline(self, offline: bool) -> None:
        """Toggle offline mode (Chromium only, via CDP). Restores with ``set_offline(False)``."""
        self._delegate.set_offline(offline)

    @contextmanager
    def expect_download(self, *, timeout: int | None = None) -> Generator[_ValueHolder, None, None]:
        """Context manager that waits for a file download to complete and captures it."""
        before = self._delegate.snapshot_download_dir()
        holder: _ValueHolder = _ValueHolder()
        yield holder
        path, name = self._delegate.wait_for_download(
            before,
            timeout_ms=timeout if timeout is not None else self._defaults.action_timeout_ms,
        )
        holder._set(Download(path=path, suggested_filename=name))
