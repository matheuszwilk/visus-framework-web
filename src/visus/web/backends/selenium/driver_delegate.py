"""WebDriver-backed delegates. The ONLY place selenium types live behind the public API."""

from __future__ import annotations

from selenium.common.exceptions import (
    NoSuchWindowException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait

from visus.web import errors


def translate_exc(exc: Exception) -> errors.VisusWebError:
    """Map a selenium exception to the public visus.web hierarchy."""
    if isinstance(exc, TimeoutException):
        return errors.VisusTimeoutError(str(exc) or "operation timed out")
    if isinstance(exc, NoSuchWindowException):
        return errors.TargetClosedError(str(exc) or "target window is closed")
    if isinstance(exc, WebDriverException):
        return errors.VisusWebError(str(exc) or "webdriver error")
    return errors.VisusWebError(str(exc))


class SeleniumPageDelegate:
    """One browser window handle. Activates its window before each operation."""

    def __init__(self, driver: object, handle: str) -> None:
        self._driver = driver
        self._handle = handle
        self._closed = False

    def _activate(self) -> None:
        if self._closed:
            raise errors.TargetClosedError("page is closed")
        try:
            self._driver.switch_to.window(self._handle)
        except WebDriverException as exc:
            raise translate_exc(exc) from exc

    def goto(self, url: str, *, wait_until: str, timeout_ms: int) -> None:
        self._activate()
        self._driver.set_page_load_timeout(timeout_ms / 1000)
        try:
            self._driver.get(url)
        except TimeoutException as exc:
            raise errors.VisusTimeoutError(f"navigation to {url!r} timed out") from exc
        except WebDriverException as exc:
            raise errors.NavigationError(f"navigation to {url!r} failed: {exc}") from exc
        if wait_until in ("load", "domcontentloaded"):
            state = "complete" if wait_until == "load" else "interactive"
            WebDriverWait(self._driver, timeout_ms / 1000).until(
                lambda d: d.execute_script("return document.readyState")
                in ("complete",) + (("interactive",) if state == "interactive" else ())
            )

    def current_url(self) -> str:
        self._activate()
        return self._driver.current_url

    def title(self) -> str:
        self._activate()
        return self._driver.title

    def content(self) -> str:
        self._activate()
        return self._driver.page_source

    def reload(self, *, timeout_ms: int) -> None:
        self._activate()
        self._driver.set_page_load_timeout(timeout_ms / 1000)
        self._driver.refresh()

    def go_back(self, *, timeout_ms: int) -> None:
        self._activate()
        self._driver.back()

    def go_forward(self, *, timeout_ms: int) -> None:
        self._activate()
        self._driver.forward()

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._driver.switch_to.window(self._handle)
            self._driver.close()
        except WebDriverException:
            pass
        self._closed = True

    def is_closed(self) -> bool:
        return self._closed


class SeleniumContextDelegate:
    """S0: a non-isolated grouping over one driver. Real isolation arrives in S4 (BiDi)."""

    def __init__(self, driver: object, first_handle: str | None = None) -> None:
        self._driver = driver
        self._pages: list[SeleniumPageDelegate] = []
        if first_handle is not None:
            self._pages.append(SeleniumPageDelegate(driver, first_handle))

    def new_page(self) -> SeleniumPageDelegate:
        before = set(self._driver.window_handles)
        self._driver.switch_to.new_window("tab")
        new = (set(self._driver.window_handles) - before).pop()
        page = SeleniumPageDelegate(self._driver, new)
        self._pages.append(page)
        return page

    def pages(self) -> list[SeleniumPageDelegate]:
        return [p for p in self._pages if not p.is_closed()]

    def close(self) -> None:
        for page in list(self._pages):
            page.close()
