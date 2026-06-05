"""WebDriver-backed delegates. The ONLY place selenium types live behind the public API."""

from __future__ import annotations

import base64
import os
import time
from typing import TYPE_CHECKING, cast

from selenium.common.exceptions import (
    NoSuchWindowException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from visus.web import errors
from visus.web.backends.base import ContextDelegate, PageDelegate
from visus.web.backends.selenium.actionability import run_action
from visus.web.backends.selenium.expect_engine import run_expect
from visus.web.backends.selenium.js import BUNDLE_JS

if TYPE_CHECKING:
    from visus.web.api.fields import Field

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


def _parse_key(key: str) -> tuple[list[str], str]:
    """Split a Playwright-style key string into (modifiers, main_key).

    Examples::

        "Enter"           -> ([], Keys.ENTER)
        "Control+a"       -> ([Keys.CONTROL], "a")
        "Control+Shift+T" -> ([Keys.CONTROL, Keys.SHIFT], "t")
    """
    parts = key.split("+")
    mods = [_MODMAP[p] for p in parts[:-1] if p in _MODMAP]
    main = _KEYMAP.get(parts[-1], parts[-1])
    return mods, main


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

    def __init__(
        self,
        driver: WebDriver,
        handle: str,
        download_dir: str | None = None,
        context: SeleniumContextDelegate | None = None,
    ) -> None:
        self._driver = driver
        self._handle = handle
        self._closed = False
        self._download_dir = download_dir
        self._context = context
        self._mouse_x: int = 0
        self._mouse_y: int = 0

    def _activate(self) -> None:
        if self._closed:
            raise errors.TargetClosedError("page is closed")
        try:
            self._driver.switch_to.window(self._handle)
        except WebDriverException as exc:
            raise translate_exc(exc) from exc

    def handle(self) -> str:
        """Return this page's underlying browser window-handle string."""
        return self._handle

    def bring_to_front(self) -> None:
        """Focus this page's tab/window (Selenium ``switch_to.window``)."""
        self._activate()

    def context(self) -> ContextDelegate:
        """Return the context delegate that owns this page (``Page.context`` backing)."""
        if self._context is None:
            raise errors.VisusWebError("page is not attached to a context")
        return self._context

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
            mods, main = _parse_key(key)
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
        try:  # Chromium (Chrome/Edge)
            size = self._driver.execute_cdp_cmd("Page.getLayoutMetrics", {})["cssContentSize"]
            shot = self._driver.execute_cdp_cmd(
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
            )
            return base64.b64decode(cast(str, shot["data"]))
        except (AttributeError, WebDriverException, KeyError):
            pass
        get_full = getattr(self._driver, "get_full_page_screenshot_as_png", None)  # Firefox native
        if callable(get_full):
            try:
                return get_full()  # type: ignore[no-any-return]
            except WebDriverException:
                pass
        return self._driver.get_screenshot_as_png()

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
                if self._context is not None:
                    return self._context._make_page(handle)
                return SeleniumPageDelegate(self._driver, handle, self._download_dir)
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

    def list_fields(
        self, *, kinds: list[str] | None, include_hidden: bool, highlight: bool
    ) -> list[Field]:
        """Enumerate interactive fields via the bundle; optionally draw the overlay."""
        from visus.web.api.fields import Field

        self._activate()
        self._ensure_bundle()
        raw = cast(
            list[dict[str, object]],
            self._driver.execute_script(
                "return window.__visus.listFields(arguments[0]);",
                {"kinds": kinds, "includeHidden": include_hidden},
            ),
        )
        if highlight:
            try:
                self._driver.execute_script(
                    "window.__visus.highlightFields(arguments[0]);", raw
                )
            except WebDriverException:
                pass  # headless / drawing failures must never break enumeration
        def _pystr(s: str) -> str:
            return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

        def _code(d: dict[str, object]) -> str:
            # The ready-to-paste visus.web expression, frame-aware so an element
            # inside an iframe is reachable (a bare locator would not be).
            expr = "page"
            for sel in cast("list[str]", d.get("frame") or []):
                expr += f".frame_locator({_pystr(sel)})"
            if d.get("locator_kind") == "role":
                role = cast(str, d.get("role") or "")
                nm = cast(str, d.get("name") or "")
                expr += f".get_by_role({_pystr(role)}"
                if nm:
                    expr += f", name={_pystr(nm)}"
                expr += ")"
            else:
                loc = cast(str, d.get("locator") or "")
                expr += f".locator({_pystr(loc)}"
                if d.get("deep"):
                    expr += ", deep=True"
                expr += ")"
            return expr

        fields: list[Field] = []
        for d in raw:
            fields.append(
                Field(
                    index=cast(int, d["index"]),
                    kind=cast(str, d["kind"]),
                    tag=cast(str, d["tag"]),
                    type=cast("str | None", d["type"]),
                    role=cast("str | None", d["role"]),
                    name=cast(str, d["name"]),
                    label=cast("str | None", d["label"]),
                    placeholder=cast("str | None", d["placeholder"]),
                    value=cast("str | None", d["value"]),
                    checked=cast("bool | None", d["checked"]),
                    disabled=cast(bool, d["disabled"]),
                    visible=cast(bool, d["visible"]),
                    frame=cast("list[str]", d["frame"]),
                    shadow=cast(bool, d["shadow"]),
                    locator=cast(str, d["locator"]),
                    locator_kind=cast(str, d["locator_kind"]),
                    css=cast(str, d.get("css") or ""),
                    xpath=cast(str, d.get("xpath") or ""),
                    code=_code(d),
                    deep=bool(d.get("deep", False)),
                )
            )
        return fields

    def clear_highlights(self) -> None:
        """Remove the numbered field overlay and detach its listeners."""
        self._activate()
        self._ensure_bundle()
        try:
            self._driver.execute_script("window.__visus.clearHighlights();")
        except WebDriverException:
            pass

    def pdf(self) -> bytes:
        """Print the current page to PDF via W3C print_page (all browsers) with CDP fallback."""
        self._activate()
        from selenium.webdriver.common.print_page_options import PrintOptions

        try:
            raw = self._driver.print_page(PrintOptions())
            return base64.b64decode(raw)
        except WebDriverException:
            res = cast(
                dict[str, object],
                self._driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True}),
            )
            return base64.b64decode(cast(str, res["data"]))

    def snapshot_download_dir(self) -> list[str]:
        """Return the current list of files in the download directory."""
        if self._download_dir and os.path.isdir(self._download_dir):
            return os.listdir(self._download_dir)
        return []

    def wait_for_download(self, before: list[str], *, timeout_ms: int) -> tuple[str, str]:
        """Poll until a new completed file appears in the download directory."""
        if not self._download_dir:
            raise errors.VisusTimeoutError("no download directory configured")
        before_set = set(before)
        _PARTIAL_SUFFIXES = (".crdownload", ".tmp", ".part")
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if os.path.isdir(self._download_dir):
                for name in os.listdir(self._download_dir):
                    if name not in before_set and not any(
                        name.endswith(s) for s in _PARTIAL_SUFFIXES
                    ):
                        abspath = os.path.abspath(os.path.join(self._download_dir, name))
                        return (abspath, name)
            if time.monotonic() >= deadline:
                raise errors.VisusTimeoutError(f"no new download completed within {timeout_ms} ms")
            time.sleep(0.05)

    # ------------------------------------------------------------------
    # Low-level input device methods
    # ------------------------------------------------------------------

    def mouse_move(self, x: float, y: float) -> None:
        self._activate()
        self._mouse_x, self._mouse_y = int(x), int(y)
        ab = ActionBuilder(self._driver)
        ab.pointer_action.move_to_location(self._mouse_x, self._mouse_y)  # type: ignore[no-untyped-call]
        ab.perform()

    def mouse_down(self) -> None:
        self._activate()
        ab = ActionBuilder(self._driver)
        ab.pointer_action.pointer_down()  # type: ignore[no-untyped-call]
        ab.perform()

    def mouse_up(self) -> None:
        self._activate()
        ab = ActionBuilder(self._driver)
        ab.pointer_action.pointer_up()  # type: ignore[no-untyped-call]
        ab.perform()

    def mouse_click(self, x: float, y: float) -> None:
        self._activate()
        self._mouse_x, self._mouse_y = int(x), int(y)
        ab = ActionBuilder(self._driver)
        ab.pointer_action.move_to_location(  # type: ignore[no-untyped-call]
            self._mouse_x, self._mouse_y
        ).pointer_down().pointer_up()
        ab.perform()

    def mouse_dblclick(self, x: float, y: float) -> None:
        self._activate()
        self._mouse_x, self._mouse_y = int(x), int(y)
        ab = ActionBuilder(self._driver)
        (
            ab.pointer_action.move_to_location(  # type: ignore[no-untyped-call]
                self._mouse_x, self._mouse_y
            )
            .pointer_down()
            .pointer_up()
            .pointer_down()
            .pointer_up()
        )
        ab.perform()

    def mouse_wheel(self, delta_x: float, delta_y: float) -> None:
        self._activate()
        ab = ActionBuilder(self._driver)
        ab.wheel_action.scroll(  # type: ignore[no-untyped-call]
            x=self._mouse_x,
            y=self._mouse_y,
            delta_x=int(delta_x),
            delta_y=int(delta_y),
        )
        ab.perform()

    def keyboard_down(self, key: str) -> None:
        self._activate()
        # Modifiers like "Shift" live in _MODMAP; single chars and other keys in _KEYMAP.
        mapped = _MODMAP.get(key) or _KEYMAP.get(key, key)
        ActionChains(self._driver).key_down(mapped).perform()

    def keyboard_up(self, key: str) -> None:
        self._activate()
        mapped = _MODMAP.get(key) or _KEYMAP.get(key, key)
        ActionChains(self._driver).key_up(mapped).perform()

    def keyboard_press(self, key: str) -> None:
        self._activate()
        mods, main = _parse_key(key)
        ac = ActionChains(self._driver)
        if mods:
            for m in mods:
                ac.key_down(m)
            ac.send_keys(main)
            for m in reversed(mods):
                ac.key_up(m)
        else:
            ac.send_keys(main)
        ac.perform()

    def keyboard_type(self, text: str) -> None:
        self._activate()
        ActionChains(self._driver).send_keys(text).perform()

    def keyboard_insert_text(self, text: str) -> None:
        self._activate()
        ActionChains(self._driver).send_keys(text).perform()

    # ------------------------------------------------------------------
    # Network controls (Chromium CDP — documented as Chromium-only)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Observability helpers — used by the Recorder; never raise out
    # ------------------------------------------------------------------

    def _try_resolve(self, selector: str | None) -> object | None:
        if not selector:
            return None
        try:
            from visus.web.backends.selenium.resolver import resolve_elements

            els = resolve_elements(self._driver, self._ensure_bundle, selector)
            return els[0] if els else None
        except Exception:
            return None

    def capture_annotated_screenshot(self, selector: str | None) -> bytes:
        self._activate()
        self._ensure_bundle()
        el = self._try_resolve(selector)
        if el is not None:
            try:
                self._driver.execute_script("window.__visus.highlight(arguments[0]);", el)
            except WebDriverException:
                pass
        png: bytes = self._driver.get_screenshot_as_png()
        try:
            self._driver.execute_script("window.__visus.unhighlight();")
        except WebDriverException:
            pass
        return png

    def step_meta(self, selector: str | None) -> dict[str, object]:
        self._activate()
        meta: dict[str, object] = {
            "url": None,
            "title": None,
            "role": None,
            "name": None,
            "bbox": None,
        }
        try:
            meta["url"] = self._driver.current_url
            meta["title"] = self._driver.title
        except WebDriverException:
            pass
        el = self._try_resolve(selector)
        if el is not None:
            try:
                self._ensure_bundle()
                meta["role"] = self._driver.execute_script(
                    "return window.__visus.role(arguments[0]);", el
                )
                meta["name"] = self._driver.execute_script(
                    "return window.__visus.accessibleName(arguments[0]);", el
                )
                rect = self._driver.execute_script(
                    "var r=arguments[0].getBoundingClientRect();"
                    "return [Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)];",
                    el,
                )
                meta["bbox"] = rect
            except WebDriverException:
                pass
        return meta

    def _cdp(self, cmd: str, params: dict) -> object:  # type: ignore[type-arg]
        """Execute a CDP command; raise VisusWebError on non-Chromium or failures."""
        self._activate()
        try:
            return cast(object, self._driver.execute_cdp_cmd(cmd, params))
        except AttributeError as exc:
            raise errors.VisusWebError(f"{cmd} requires a Chromium engine (chrome/edge)") from exc
        except WebDriverException as exc:
            raise translate_exc(exc) from exc

    def block_urls(self, patterns: list[str]) -> None:
        """Block network requests matching *patterns* (Chromium only)."""
        self._cdp("Network.enable", {})
        self._cdp("Network.setBlockedURLs", {"urls": patterns})

    def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        """Attach extra HTTP request headers to every request (Chromium only)."""
        self._cdp("Network.enable", {})
        self._cdp("Network.setExtraHTTPHeaders", {"headers": headers})

    def set_offline(self, offline: bool) -> None:
        """Toggle offline mode via CDP network conditions (Chromium only)."""
        self._cdp("Network.enable", {})
        self._cdp(
            "Network.emulateNetworkConditions",
            {
                "offline": offline,
                "latency": 0,
                "downloadThroughput": -1,
                "uploadThroughput": -1,
            },
        )


class SeleniumContextDelegate:
    """Delegates one BrowserContext. If owns_driver=True it manages its own WebDriver process."""

    def __init__(
        self,
        driver: WebDriver,
        first_handle: str | None = None,
        download_dir: str | None = None,
        owns_driver: bool = False,
        profile_dir: str | None = None,
    ) -> None:
        self._driver = driver
        self._download_dir = download_dir
        self._owns_driver = owns_driver
        self._profile_dir = profile_dir
        self._pages: list[SeleniumPageDelegate] = []
        if first_handle is not None:
            self._make_page(first_handle)

    @property
    def owns_driver(self) -> bool:
        return self._owns_driver

    def _make_page(self, handle: str) -> SeleniumPageDelegate:
        """Return the tracked page for *handle*, creating + registering it if new.

        Deduplicates by handle so a popup adopted via ``expect_popup`` and a
        handle picked up by :meth:`_reconcile` resolve to the same delegate.
        """
        for p in self._pages:
            if p._handle == handle and not p._closed:
                return p
        page = SeleniumPageDelegate(self._driver, handle, self._download_dir, context=self)
        self._pages.append(page)
        return page

    def _live_handles(self) -> list[str] | None:
        """Current window handles, or ``None`` if the driver session is gone.

        A disposed driver fails to answer at all (``WebDriverException`` for an
        invalid session, or a raw connection error once the process has quit);
        any such failure means the session is unusable, so treat it as gone.
        """
        try:
            return list(self._driver.window_handles)
        except Exception:
            return None

    def _reconcile(self) -> list[SeleniumPageDelegate]:
        """Sync ``_pages`` against the driver's real window handles.

        Adopts handles opened outside visus (links, ``window.open``) and marks
        pages whose handle has vanished (closed externally) as closed. Returns
        the list of newly-adopted pages, in the browser's handle order.
        """
        live = self._live_handles()
        if live is None:  # session disposed — everything is gone
            for p in self._pages:
                p._closed = True
            return []
        live_set = set(live)
        tracked = {p._handle for p in self._pages if not p._closed}
        for p in self._pages:
            if not p._closed and p._handle not in live_set:
                p._closed = True
        return [self._make_page(h) for h in live if h not in tracked]

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
        return self._make_page(new_handles.pop())

    def pages(self) -> list[PageDelegate]:
        self._reconcile()
        return [p for p in self._pages if not p.is_closed()]

    def adopt_open_windows(self) -> list[PageDelegate]:
        """Adopt browser windows/tabs opened outside visus; return the new ones.

        ``pages()`` already reconciles on every read; this is the explicit
        trigger that returns *just* the pages discovered by this call (empty if
        everything was already tracked). Also drops externally-closed windows.
        """
        return list(self._reconcile())

    def close(self) -> None:
        for page in list(self._pages):
            page.close()
        if self._owns_driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            import shutil

            if self._profile_dir:
                shutil.rmtree(self._profile_dir, ignore_errors=True)
            if self._download_dir:
                shutil.rmtree(self._download_dir, ignore_errors=True)

    def cookies(self) -> list[dict]:  # type: ignore[type-arg]
        return self._driver.get_cookies()

    def add_cookies(self, cookies: list[dict]) -> None:  # type: ignore[type-arg]
        for c in cookies:
            self._driver.add_cookie(c)

    def clear_cookies(self) -> None:
        self._driver.delete_all_cookies()
