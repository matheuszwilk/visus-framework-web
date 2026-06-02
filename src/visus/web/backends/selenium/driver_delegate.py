"""WebDriver-backed delegates. The ONLY place selenium types live behind the public API."""

from __future__ import annotations

from typing import cast

from selenium.common.exceptions import (
    NoSuchWindowException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from visus.web import errors
from visus.web.backends.base import PageDelegate
from visus.web.backends.selenium.actionability import run_action
from visus.web.backends.selenium.expect_engine import run_expect
from visus.web.backends.selenium.js import BUNDLE_JS


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

    def __init__(self, driver: WebDriver, handle: str) -> None:
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
        # Chrome renders some network errors (e.g. ERR_UNSAFE_PORT) as a
        # chrome-error:// page without raising a WebDriverException.  Detect
        # this by asking the page for its *actual* document URL, which is the
        # canonical chrome-error://chromewebdata/ for all such error pages.
        try:
            doc_url: str = cast(str, self._driver.execute_script("return document.URL"))
        except WebDriverException:
            doc_url = ""
        if doc_url.startswith("chrome-error://"):
            raise errors.NavigationError(f"navigation to {url!r} failed (browser error page)")
        if wait_until in ("load", "domcontentloaded"):
            state = "complete" if wait_until == "load" else "interactive"
            try:
                WebDriverWait(self._driver, timeout_ms / 1000).until(
                    lambda d: (
                        d.execute_script("return document.readyState")
                        in ("complete",) + (("interactive",) if state == "interactive" else ())
                    )
                )
            except TimeoutException as exc:
                raise errors.VisusTimeoutError(f"readyState wait for {url!r} timed out") from exc

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
        try:
            self._driver.refresh()
        except WebDriverException as exc:
            raise translate_exc(exc) from exc

    def go_back(self, *, timeout_ms: int) -> None:
        self._activate()
        try:
            self._driver.back()
        except WebDriverException as exc:
            raise translate_exc(exc) from exc

    def go_forward(self, *, timeout_ms: int) -> None:
        self._activate()
        try:
            self._driver.forward()
        except WebDriverException as exc:
            raise translate_exc(exc) from exc

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

    def _ensure_bundle(self) -> None:
        present = self._driver.execute_script("return !!window.__visus;")
        if not present:
            self._driver.execute_script(BUNDLE_JS)

    def _resolve_all(self, selector: str) -> list[object]:
        self._activate()
        self._ensure_bundle()
        return cast(
            list[object],
            self._driver.execute_script("return window.__visus.queryAll(arguments[0]);", selector),
        )

    def _resolve_strict(self, selector: str) -> object | None:
        els = self._resolve_all(selector)
        if len(els) > 1:
            raise errors.StrictModeViolation(
                f"locator resolved to {len(els)} elements; use first()/last()/nth() to pick one"
            )
        return els[0] if els else None

    def locator_count(self, selector: str) -> int:
        return len(self._resolve_all(selector))

    def locator_is_visible(self, selector: str) -> bool:
        el = self._resolve_strict(selector)
        if el is None:
            return False
        state = cast(
            dict[str, object],
            self._driver.execute_script(
                "return window.__visus.elementState(arguments[0], 'visible');", el
            ),
        )
        return cast(bool, state["matches"])

    def locator_text_content(self, selector: str) -> str | None:
        el = self._resolve_strict(selector)
        if el is None:
            return None
        return cast(
            "str | None",
            self._driver.execute_script("return window.__visus.normText(arguments[0]);", el),
        )

    def locator_click(self, selector: str, *, timeout_ms: int, force: bool) -> None:
        self._activate()
        self._ensure_bundle()
        run_action(
            self._driver,
            selector,
            "click",
            timeout_ms=timeout_ms,
            force=force,
            dispatch=lambda el: ActionChains(self._driver).move_to_element(el).click().perform(),
        )

    def locator_fill(self, selector: str, value: str, *, timeout_ms: int, force: bool) -> None:
        self._activate()
        self._ensure_bundle()

        def _do_fill(el: WebElement) -> None:
            el.clear()
            el.send_keys(value)

        run_action(
            self._driver,
            selector,
            "fill",
            timeout_ms=timeout_ms,
            force=force,
            dispatch=_do_fill,
        )

    def locator_input_value(self, selector: str) -> str:
        self._activate()
        self._ensure_bundle()
        el = self._resolve_strict(selector)
        if el is None:
            raise errors.ElementNotFoundError(f"no element for input_value: {selector}")
        return cast(str, self._driver.execute_script("return arguments[0].value;", el))

    def locator_state(self, selector: str, state: str) -> bool:
        el = self._resolve_strict(selector)
        if el is None:
            return state == "hidden"
        res = cast(
            "dict[str, object]",
            self._driver.execute_script(
                "return window.__visus.elementState(arguments[0],arguments[1]);", el, state
            ),
        )
        return bool(res["matches"])

    def locator_all_text(self, selector: str) -> list[str]:
        self._activate()
        self._ensure_bundle()
        els = self._resolve_all(selector)
        _js = "return window.__visus.normText(arguments[0]);"
        return [cast(str, self._driver.execute_script(_js, el)) for el in els]

    def locator_get_attribute(self, selector: str, name: str) -> str | None:
        el = self._resolve_strict(selector)
        if el is None:
            return None
        _js = "return arguments[0].getAttribute(arguments[1]);"
        return cast("str | None", self._driver.execute_script(_js, el, name))

    def expect_poll(
        self,
        selector: str,
        matcher: str,
        arg: dict[str, object] | None,
        *,
        is_not: bool,
        timeout_ms: int,
    ) -> None:
        self._activate()
        self._ensure_bundle()
        run_expect(self._driver, selector, matcher, arg, is_not=is_not, timeout_ms=timeout_ms)


class SeleniumContextDelegate:
    """S0: a non-isolated grouping over one driver. Real isolation arrives in S4 (BiDi)."""

    def __init__(self, driver: WebDriver, first_handle: str | None = None) -> None:
        self._driver = driver
        self._pages: list[SeleniumPageDelegate] = []
        if first_handle is not None:
            self._pages.append(SeleniumPageDelegate(driver, first_handle))

    def new_page(self) -> PageDelegate:
        before = set(self._driver.window_handles)
        try:
            self._driver.switch_to.new_window("tab")
        except WebDriverException as exc:
            raise translate_exc(exc) from exc
        new_handles = set(self._driver.window_handles) - before
        if len(new_handles) != 1:
            raise errors.VisusWebError(
                f"expected exactly one new window handle, found {len(new_handles)}"
            )
        page = SeleniumPageDelegate(self._driver, new_handles.pop())
        self._pages.append(page)
        return page

    def pages(self) -> list[PageDelegate]:
        return [p for p in self._pages if not p.is_closed()]

    def close(self) -> None:
        for page in list(self._pages):
            page.close()
