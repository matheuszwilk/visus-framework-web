"""Clean-room deadline+backoff actionability loop: auto-wait before click/fill."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic, sleep
from typing import cast

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from visus.web import errors

_ACTION_STATES: dict[str, tuple[str, ...]] = {
    "click": ("visible", "enabled", "stable"),
    "dblclick": ("visible", "enabled", "stable"),
    "check": ("visible", "enabled", "stable"),
    "hover": ("visible", "stable"),
    "drag": ("visible", "stable"),
    "fill": ("visible", "enabled", "editable"),
    "clear": ("visible", "enabled", "editable"),
    "select_option": ("visible", "enabled"),
    "press": ("visible",),
    "focus": (),
    "blur": (),
}
_POINTER_ACTIONS = frozenset({"click", "dblclick", "check", "hover", "drag"})
_BACKOFF: tuple[float, ...] = (0.0, 0.02, 0.1, 0.1, 0.5)


def _query_strict(
    driver: WebDriver, ensure_bundle: Callable[[], None], selector: str
) -> WebElement | None:
    from visus.web.backends.selenium.resolver import resolve_strict
    return resolve_strict(driver, ensure_bundle, selector)


def _blocking_reason(
    driver: WebDriver,
    el: WebElement,
    states: tuple[str, ...],
    name: str,
) -> str | None:
    for st in states:
        if st == "stable":
            stable = bool(
                driver.execute_async_script(
                    "var el=arguments[0],cb=arguments[arguments.length-1];"
                    "window.__visus.checkStable(el, cb);",
                    el,
                )
            )
            if not stable:
                return "not stable (still animating)"
            continue
        res = cast(
            dict[str, object],
            driver.execute_script(
                "return window.__visus.elementState(arguments[0],arguments[1]);", el, st
            ),
        )
        if not res["matches"]:
            return f"not {st} ({res['received']})"
    if name in _POINTER_ACTIONS:
        _SCROLL_JS = "arguments[0].scrollIntoView({block:'center',inline:'center'});"
        driver.execute_script(_SCROLL_JS, el)
        pt = cast(
            dict[str, float],
            driver.execute_script("return window.__visus.clickablePoint(arguments[0]);", el),
        )
        hit = bool(
            driver.execute_script(
                "return window.__visus.hitTarget(arguments[0],arguments[1],arguments[2]);",
                el,
                pt["x"],
                pt["y"],
            )
        )
        if not hit:
            return "element intercepts pointer events (occluded)"
    return None


def run_action(
    driver: WebDriver,
    selector: str,
    name: str,
    *,
    timeout_ms: int,
    force: bool,
    dispatch: Callable[[WebElement], None],
    ensure_bundle: Callable[[], None],
) -> None:
    states = _ACTION_STATES[name]
    deadline = monotonic() + timeout_ms / 1000
    retry = 0
    last_reason = "element not found"
    while True:
        if retry:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            sleep(min(_BACKOFF[min(retry, len(_BACKOFF) - 1)], remaining))
        el = _query_strict(driver, ensure_bundle, selector)
        if el is not None:
            reason = None if force else _blocking_reason(driver, el, states, name)
            if reason is None:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center',inline:'center'});", el
                )
                dispatch(el)
                return
            last_reason = reason
        retry += 1
        if monotonic() > deadline:
            break
    raise errors.VisusTimeoutError(f"{name!r} action timed out after {timeout_ms}ms: {last_reason}")
