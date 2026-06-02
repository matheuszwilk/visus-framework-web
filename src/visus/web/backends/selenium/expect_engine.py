"""Clean-room web-first assertion engine: poll-until-match with backoff."""

from __future__ import annotations

import re
from time import monotonic, sleep
from typing import cast

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from visus.web import errors

_BACKOFF: tuple[float, ...] = (0.0, 0.02, 0.05, 0.1, 0.1, 0.5)
_SINGLE_STATES = {"visible", "hidden", "enabled", "disabled", "editable", "checked"}


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip()


def _query(driver: WebDriver, selector: str) -> list[WebElement]:
    return cast(
        list[WebElement],
        driver.execute_script("return window.__visus.queryAll(arguments[0]);", selector),
    )


def _evaluate(
    driver: WebDriver, selector: str, matcher: str, arg: dict[str, object] | None
) -> tuple[bool, object]:
    els = _query(driver, selector)
    if matcher == "count":
        n = len(els)
        return (n == cast(dict[str, object], arg)["count"], n)
    if matcher in _SINGLE_STATES:
        if not els:
            # absent element: 'hidden' is satisfied, everything else is not
            return (matcher == "hidden", "not present")
        if len(els) > 1:
            raise errors.StrictModeViolation(
                f"assertion locator resolved to {len(els)} elements; use first()/last()/nth()"
            )
        res = cast(
            dict[str, object],
            driver.execute_script(
                "return window.__visus.elementState(arguments[0],arguments[1]);", els[0], matcher
            ),
        )
        return (bool(res["matches"]), res["received"])
    if matcher == "text":
        if not els:
            return (False, "not present")
        if len(els) > 1:
            raise errors.StrictModeViolation(
                f"assertion locator resolved to {len(els)} elements; use first()/last()/nth()"
            )
        actual = _norm_ws(
            cast(
                str,
                driver.execute_script("return window.__visus.normText(arguments[0]);", els[0]),
            )
        )
        spec = cast(dict[str, object], arg)
        want = _norm_ws(cast(str, spec["value"]))
        if spec["exact"]:
            return (actual == want, actual)
        return (want.lower() in actual.lower(), actual)
    if matcher == "value":
        if not els:
            return (False, "not present")
        if len(els) > 1:
            raise errors.StrictModeViolation("assertion locator matched multiple elements")
        actual = cast(str, driver.execute_script("return arguments[0].value;", els[0]) or "")
        spec = cast("dict[str, object]", arg)
        return (actual == spec["value"], actual)
    if matcher == "attribute":
        if not els:
            return (False, "not present")
        if len(els) > 1:
            raise errors.StrictModeViolation("assertion locator matched multiple elements")
        spec = cast("dict[str, object]", arg)
        actual = driver.execute_script(
            "return arguments[0].getAttribute(arguments[1]);", els[0], spec["name"]
        )
        return (actual == spec["value"], actual)
    if matcher == "class":
        if not els:
            return (False, "not present")
        if len(els) > 1:
            raise errors.StrictModeViolation("assertion locator matched multiple elements")
        spec = cast("dict[str, object]", arg)
        cls = cast(str, driver.execute_script("return arguments[0].getAttribute('class') || '';", els[0]))
        if spec["mode"] == "contains":
            return (cast(str, spec["value"]) in cls.split(), cls)
        return (_norm_ws(cls) == _norm_ws(cast(str, spec["value"])), cls)
    if matcher == "role":
        if not els:
            return (False, "not present")
        if len(els) > 1:
            raise errors.StrictModeViolation("assertion locator matched multiple elements")
        spec = cast("dict[str, object]", arg)
        actual = driver.execute_script("return window.__visus.role(arguments[0]);", els[0])
        return (actual == spec["value"], actual)
    raise ValueError(f"unknown matcher: {matcher}")


def run_expect(
    driver: WebDriver,
    selector: str,
    matcher: str,
    arg: dict[str, object] | None,
    *,
    is_not: bool,
    timeout_ms: int,
) -> None:
    deadline = monotonic() + timeout_ms / 1000
    retry = 0
    received: object = None
    while True:
        if retry:
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            sleep(min(_BACKOFF[min(retry, len(_BACKOFF) - 1)], remaining))
        matches, received = _evaluate(driver, selector, matcher, arg)
        if matches != is_not:  # satisfied (handles negation for free)
            return
        retry += 1
        if monotonic() > deadline:
            break
    prefix = "not " if is_not else ""
    detail = f" (expected {arg})" if arg else ""
    raise AssertionError(
        f"expect: {prefix}{matcher}{detail} not satisfied within {timeout_ms}ms;"
        f" last received: {received!r}"
    )
