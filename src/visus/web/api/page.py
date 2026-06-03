from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from visus.web.api.events import Dialog, Download, _ValueHolder
from visus.web.api.locator import Locator
from visus.web.backends.base import PageDelegate
from visus.web.config import Defaults

if TYPE_CHECKING:
    from visus.web.api.frame_locator import FrameLocator
    from visus.web.api.input import Keyboard, Mouse


class Page:
    def __init__(self, delegate: PageDelegate, defaults: Defaults) -> None:
        self._delegate = delegate
        self._defaults = defaults

    def goto(self, url: str, *, wait_until: str = "load", timeout: int | None = None) -> None:
        self._delegate.goto(
            url,
            wait_until=wait_until,
            timeout_ms=timeout if timeout is not None else self._defaults.navigation_timeout_ms,
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

    @property
    def is_closed(self) -> bool:
        return self._delegate.is_closed()

    def locator(self, selector: str) -> Locator:
        return Locator(self._delegate, (), self._defaults).locator(selector)

    def frame_locator(self, selector: str) -> FrameLocator:
        from visus.web.api.frame_locator import FrameLocator, _frame_step

        return FrameLocator(self._delegate, (_frame_step(selector),), self._defaults)

    def get_by_role(self, role: str, *, name: str | None = None, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_role(role, name=name, exact=exact)

    def get_by_text(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_text(text, exact=exact)

    def get_by_label(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_label(text, exact=exact)

    def get_by_placeholder(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_placeholder(text, exact=exact)

    def get_by_alt_text(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_alt_text(text, exact=exact)

    def get_by_title(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_title(text, exact=exact)

    def get_by_test_id(self, test_id: str) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_test_id(test_id)

    def snapshot(self) -> list[dict]:  # type: ignore[type-arg]
        """Return the page's interactive elements as a list of {role, name} dicts."""
        return self._delegate.snapshot()

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
