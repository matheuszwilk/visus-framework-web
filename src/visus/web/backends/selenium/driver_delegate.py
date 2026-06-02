"""WebDriver-backed delegates. The ONLY place selenium types live behind the public API."""

from __future__ import annotations

import base64
import os
import time
from typing import cast

from selenium.common.exceptions import (
    NoSuchWindowException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from visus.web import errors
from visus.web.backends.base import PageDelegate
from visus.web.backends.selenium.actionability import run_action
from visus.web.backends.selenium.expect_engine import run_expect
from visus.web.backends.selenium.js import BUNDLE_JS

_KEYMAP = {
    "Enter": Keys.ENTER,
    "Tab": Keys.TAB,
    "Escape": Keys.ESCAPE,
    "Backspace": Keys.BACK_SPACE,
    "Delete": Keys.DELETE,
    "ArrowUp": Keys.ARROW_UP,
    "ArrowDown": Keys.ARROW_DOWN,
    "ArrowLeft": Keys.ARROW_LEFT,
    "ArrowRight": Keys.ARROW_RIGHT,
    "Space": " ",
    "Home": Keys.HOME,
    "End": Keys.END,
}
_MODMAP = {"Control": Keys.CONTROL, "Shift": Keys.SHIFT, "Alt": Keys.ALT, "Meta": Keys.META}


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
        from visus.web.backends.selenium.resolver import resolve_elements

        return cast(list[object], resolve_elements(self._driver, self._ensure_bundle, selector))

    def _resolve_strict(self, selector: str) -> object | None:
        self._activate()
        from visus.web.backends.selenium.resolver import resolve_strict

        return resolve_strict(self._driver, self._ensure_bundle, selector)

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
            ensure_bundle=self._ensure_bundle,
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
            ensure_bundle=self._ensure_bundle,
        )

    def locator_hover(self, selector: str, *, timeout_ms: int, force: bool) -> None:
        self._activate()
        self._ensure_bundle()
        run_action(
            self._driver,
            selector,
            "hover",
            timeout_ms=timeout_ms,
            force=force,
            dispatch=lambda el: ActionChains(self._driver).move_to_element(el).perform(),
            ensure_bundle=self._ensure_bundle,
        )

    def locator_dblclick(self, selector: str, *, timeout_ms: int, force: bool) -> None:
        self._activate()
        self._ensure_bundle()
        run_action(
            self._driver,
            selector,
            "dblclick",
            timeout_ms=timeout_ms,
            force=force,
            dispatch=lambda el: (
                ActionChains(self._driver).move_to_element(el).double_click().perform()
            ),
            ensure_bundle=self._ensure_bundle,
        )

    def locator_set_checked(
        self, selector: str, checked: bool, *, timeout_ms: int, force: bool
    ) -> None:
        self._activate()
        self._ensure_bundle()

        def _do(el: WebElement) -> None:
            cur = bool(
                self._driver.execute_script(
                    "return window.__visus.elementState(arguments[0],'checked').matches;", el
                )
            )
            if cur != checked:
                ActionChains(self._driver).move_to_element(el).click().perform()

        run_action(
            self._driver,
            selector,
            "check",
            timeout_ms=timeout_ms,
            force=force,
            dispatch=_do,
            ensure_bundle=self._ensure_bundle,
        )

    def locator_select_option(
        self,
        selector: str,
        *,
        value: str | None,
        label: str | None,
        index: int | None,
        timeout_ms: int,
    ) -> None:
        self._activate()
        self._ensure_bundle()

        def _do(el: WebElement) -> None:
            sel = Select(el)
            if value is not None:
                sel.select_by_value(value)
            elif label is not None:
                sel.select_by_visible_text(label)
            elif index is not None:
                sel.select_by_index(index)

        run_action(
            self._driver,
            selector,
            "select_option",
            timeout_ms=timeout_ms,
            force=False,
            dispatch=_do,
            ensure_bundle=self._ensure_bundle,
        )

    def locator_press(self, selector: str, key: str, *, timeout_ms: int) -> None:
        self._activate()
        self._ensure_bundle()

        def _do(el: WebElement) -> None:
            parts = key.split("+")
            mods = [_MODMAP[p] for p in parts[:-1] if p in _MODMAP]
            main = _KEYMAP.get(parts[-1], parts[-1])
            if mods:
                self._driver.execute_script("arguments[0].focus();", el)
                ac = ActionChains(self._driver)
                for m in mods:
                    ac.key_down(m)
                ac.send_keys(main)
                for m in reversed(mods):
                    ac.key_up(m)
                ac.perform()
            else:
                el.send_keys(main)

        run_action(
            self._driver,
            selector,
            "press",
            timeout_ms=timeout_ms,
            force=False,
            dispatch=_do,
            ensure_bundle=self._ensure_bundle,
        )

    def locator_focus(self, selector: str, *, timeout_ms: int) -> None:
        self._activate()
        self._ensure_bundle()
        run_action(
            self._driver,
            selector,
            "focus",
            timeout_ms=timeout_ms,
            force=False,
            dispatch=lambda el: ActionChains(self._driver).move_to_element(el).click().perform(),
            ensure_bundle=self._ensure_bundle,
        )

    def locator_blur(self, selector: str, *, timeout_ms: int) -> None:
        self._activate()
        self._ensure_bundle()
        run_action(
            self._driver,
            selector,
            "blur",
            timeout_ms=timeout_ms,
            force=False,
            dispatch=lambda el: self._driver.execute_script("arguments[0].blur();", el),
            ensure_bundle=self._ensure_bundle,
        )

    def locator_clear(self, selector: str, *, timeout_ms: int, force: bool) -> None:
        self._activate()
        self._ensure_bundle()
        run_action(
            self._driver,
            selector,
            "clear",
            timeout_ms=timeout_ms,
            force=force,
            dispatch=lambda el: el.clear(),
            ensure_bundle=self._ensure_bundle,
        )

    def locator_drag_to(self, selector: str, target: str, *, timeout_ms: int) -> None:
        self._activate()
        self._ensure_bundle()
        tgt_raw = self._resolve_strict(target)
        if tgt_raw is None:
            raise errors.ElementNotFoundError(f"drag target not found: {target}")
        tgt = cast(WebElement, tgt_raw)

        def _do(src: WebElement) -> None:
            ActionChains(self._driver).click_and_hold(src).move_to_element(tgt).release().perform()

        run_action(
            self._driver,
            selector,
            "drag",
            timeout_ms=timeout_ms,
            force=False,
            dispatch=_do,
            ensure_bundle=self._ensure_bundle,
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
        run_expect(
            self._driver,
            selector,
            matcher,
            arg,
            is_not=is_not,
            timeout_ms=timeout_ms,
            ensure_bundle=self._ensure_bundle,
        )

    def evaluate(self, expression: str, arg: object) -> object:
        self._activate()
        script = f"return ({expression})(arguments[0]);"
        return cast(object, self._driver.execute_script(script, arg))

    def locator_evaluate(self, selector: str, expression: str, arg: object) -> object:
        self._activate()
        self._ensure_bundle()
        el = self._resolve_strict(selector)
        if el is None:
            raise errors.ElementNotFoundError(f"no element for evaluate: {selector}")
        return cast(
            object,
            self._driver.execute_script(
                f"return ({expression})(arguments[0], arguments[1]);", el, arg
            ),
        )

    def screenshot(self, *, full_page: bool) -> bytes:
        self._activate()
        if not full_page:
            return self._driver.get_screenshot_as_png()
        metrics = cast(
            dict[str, object],
            self._driver.execute_cdp_cmd("Page.getLayoutMetrics", {}),
        )
        size = cast(dict[str, object], metrics["cssContentSize"])
        shot = cast(
            dict[str, object],
            self._driver.execute_cdp_cmd(
                "Page.captureScreenshot",
                {
                    "captureBeyondViewport": True,
                    "fromSurface": True,
                    "clip": {
                        "x": 0,
                        "y": 0,
                        "width": size["width"],
                        "height": size["height"],
                        "scale": 1,
                    },
                },
            ),
        )
        return base64.b64decode(cast(str, shot["data"]))

    def locator_screenshot(self, selector: str) -> bytes:
        self._activate()
        self._ensure_bundle()
        el = self._resolve_strict(selector)
        if el is None:
            raise errors.ElementNotFoundError(f"no element for screenshot: {selector}")
        return cast(WebElement, el).screenshot_as_png

    def locator_set_input_files(self, selector: str, paths: list[str]) -> None:
        self._activate()
        self._ensure_bundle()
        el = self._resolve_strict(selector)
        if el is None:
            raise errors.ElementNotFoundError(f"no element for set_input_files: {selector}")
        cast(WebElement, el).send_keys("\n".join(os.path.abspath(p) for p in paths))

    # ------------------------------------------------------------------
    # Popup / dialog event helpers
    # ------------------------------------------------------------------

    def snapshot_handles(self) -> list[str]:
        """Return the current list of window handles."""
        return list(self._driver.window_handles)

    def adopt_new_handle(self, before: list[str], *, timeout_ms: int) -> PageDelegate:
        """Poll until a new window handle appears; return a delegate for it."""
        deadline = time.monotonic() + timeout_ms / 1000
        before_set = set(before)
        while True:
            new = set(self._driver.window_handles) - before_set
            if new:
                handle = new.pop()
                return SeleniumPageDelegate(self._driver, handle)
            if time.monotonic() >= deadline:
                raise errors.VisusTimeoutError(f"no new popup appeared within {timeout_ms} ms")
            time.sleep(0.05)

    def handle_next_dialog(
        self, *, accept: bool, prompt_text: str | None, timeout_ms: int
    ) -> tuple[str, str]:
        """Wait for an alert/confirm/prompt dialog, handle it, return (message, type)."""
        self._activate()
        try:
            WebDriverWait(self._driver, timeout_ms / 1000).until(EC.alert_is_present())
        except TimeoutException as exc:
            raise errors.VisusTimeoutError(f"no dialog appeared within {timeout_ms} ms") from exc
        alert = self._driver.switch_to.alert
        message = alert.text
        if prompt_text is not None:
            alert.send_keys(prompt_text)
        if accept:
            alert.accept()
        else:
            alert.dismiss()
        return (message, "dialog")

    def snapshot(self) -> list[dict]:  # type: ignore[type-arg]
        """Return interactive elements as {role, name} dicts using the __visus bundle."""
        self._activate()
        self._ensure_bundle()
        return cast(list[dict], self._driver.execute_script("return window.__visus.snapshot();"))  # type: ignore[type-arg]

    def pdf(self) -> bytes:
        """Print the current page to PDF via CDP printToPDF."""
        self._activate()
        res = cast(
            dict[str, object],
            self._driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True}),
        )
        return base64.b64decode(cast(str, res["data"]))


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

    def cookies(self) -> list[dict]:  # type: ignore[type-arg]
        return self._driver.get_cookies()

    def add_cookies(self, cookies: list[dict]) -> None:  # type: ignore[type-arg]
        for c in cookies:
            self._driver.add_cookie(c)

    def clear_cookies(self) -> None:
        self._driver.delete_all_cookies()
