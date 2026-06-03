"""Frame-aware element resolution shared by reads, actions, and assertions."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from visus.web import errors

_QUERY = "return window.__visus.queryAll(arguments[0]);"


def _query(driver: WebDriver, steps: list[dict[str, object]]) -> list[WebElement]:
    try:
        return cast(list[WebElement], driver.execute_script(_QUERY, json.dumps(steps)))
    except WebDriverException as exc:
        # a malformed selector (or any resolution failure) must not leak a raw selenium type
        raise errors.VisusWebError(f"selector resolution failed: {exc.msg or exc}") from exc


def resolve_elements(
    driver: WebDriver, ensure_bundle: Callable[[], None], selector_json: str
) -> list[WebElement]:
    """Walk any frame steps (switching into iframes) and return the leaf matches.

    Idempotent: always restarts from the active window's top document. The caller
    must already have selected the correct window (via switch_to.window).
    """
    steps = cast("list[dict[str, object]]", json.loads(selector_json))
    if not any(s["kind"] == "frame" for s in steps):
        ensure_bundle()
        return _query(driver, steps)

    driver.switch_to.default_content()
    ensure_bundle()
    pending: list[dict[str, object]] = []
    for step in steps:
        if step["kind"] == "frame":
            frame_chain = pending + cast("list[dict[str, object]]", step["frame"])
            iframes = _query(driver, frame_chain)
            if len(iframes) > 1:
                raise errors.StrictModeViolation(
                    f"frame selector matched {len(iframes)} iframes; refine it"
                )
            if not iframes:
                raise errors.ElementNotFoundError("frame (iframe) not found")
            driver.switch_to.frame(iframes[0])
            ensure_bundle()
            pending = []
        else:
            pending.append(step)
    return _query(driver, pending)


def resolve_strict(
    driver: WebDriver, ensure_bundle: Callable[[], None], selector_json: str
) -> WebElement | None:
    els = resolve_elements(driver, ensure_bundle, selector_json)
    if len(els) > 1:
        raise errors.StrictModeViolation(
            f"locator resolved to {len(els)} elements; use first()/last()/nth()"
        )
    return els[0] if els else None
