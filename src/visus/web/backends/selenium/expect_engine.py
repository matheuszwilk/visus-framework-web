"""Clean-room web-first assertion engine: poll-until-match with backoff."""

from __future__ import annotations

import re
from collections.abc import Callable
from time import monotonic, sleep
from typing import cast

from selenium.webdriver.remote.webdriver import WebDriver

from visus.web import errors

_BACKOFF: tuple[float, ...] = (0.0, 0.02, 0.05, 0.1, 0.1, 0.5)
_SINGLE_STATES = {"visible", "hidden", "enabled", "disabled", "editable", "checked"}


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def _text_matches(actual: str, spec: dict[str, object]) -> bool:
    """Compare *actual* against a text matcher spec: {value, exact} or {regex, flags}."""
    if "regex" in spec:
        pattern = re.compile(cast(str, spec["regex"]), cast(int, spec.get("flags", 0)))
        return pattern.search(actual) is not None
    want = _norm_ws(cast(str, spec["value"]))
    if spec.get("exact"):
        return actual == want
    return want.lower() in actual.lower()


def _evaluate(
    driver: WebDriver,
    ensure_bundle: Callable[[], None],
    selector: str,
    matcher: str,
    arg: dict[str, object] | None,
) -> tuple[bool, object]:
    from visus.web.backends.selenium.resolver import resolve_elements

    els = resolve_elements(driver, ensure_bundle, selector)
    if matcher == "count":
        n = len(els)
        return (n == cast(dict[str, object], arg)["count"], n)
    if matcher == "attached":
        return (len(els) > 0, f"{len(els)} element(s)")
    if matcher == "detached":
        return (len(els) == 0, f"{len(els)} element(s)")
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
        return (_text_matches(actual, spec), actual)
    if matcher == "value":
        if not els:
            return (False, "not present")
        if len(els) > 1:
            raise errors.StrictModeViolation("assertion locator matched multiple elements")
        actual = cast(str, driver.execute_script("return arguments[0].value;", els[0]) or "")
        spec = cast("dict[str, object]", arg)
        if "regex" in spec:
            return (_text_matches(actual, spec), actual)
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
        if "regex" in spec:
            return (actual is not None and _text_matches(cast(str, actual), spec), actual)
        return (actual == spec["value"], actual)
    if matcher == "class":
        if not els:
            return (False, "not present")
        if len(els) > 1:
            raise errors.StrictModeViolation("assertion locator matched multiple elements")
        spec = cast("dict[str, object]", arg)
        _cls_js = "return arguments[0].getAttribute('class') || '';"
        cls = cast(str, driver.execute_script(_cls_js, els[0]))
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
    if matcher in ("focused", "empty", "in_viewport", "css", "id", "values"):
        if not els:
            return (False, "not present")
        if len(els) > 1:
            raise errors.StrictModeViolation("assertion locator matched multiple elements")
        el = els[0]
        if matcher == "focused":
            focused = bool(
                driver.execute_script("return document.activeElement === arguments[0];", el)
            )
            return (focused, "focused" if focused else "not focused")
        if matcher == "empty":
            empty = bool(
                driver.execute_script(
                    "var el=arguments[0];"
                    "if(el.tagName==='INPUT'||el.tagName==='TEXTAREA') return el.value==='';"
                    "return el.childElementCount===0 && !(el.textContent||'').trim();",
                    el,
                )
            )
            return (empty, "empty" if empty else "not empty")
        if matcher == "in_viewport":
            inside = bool(
                driver.execute_script(
                    "var r=arguments[0].getBoundingClientRect();"
                    "var w=window.innerWidth||document.documentElement.clientWidth;"
                    "var h=window.innerHeight||document.documentElement.clientHeight;"
                    "return r.width>0&&r.height>0&&r.bottom>0&&r.right>0&&r.top<h&&r.left<w;",
                    el,
                )
            )
            return (inside, "in viewport" if inside else "outside viewport")
        if matcher == "css":
            spec = cast("dict[str, object]", arg)
            actual = cast(
                str,
                driver.execute_script(
                    "return getComputedStyle(arguments[0]).getPropertyValue(arguments[1]);",
                    el,
                    spec["name"],
                ),
            )
            if "regex" in spec:
                return (_text_matches(actual, spec), actual)
            return (actual == spec["value"], actual)
        if matcher == "id":
            spec = cast("dict[str, object]", arg)
            actual = cast(str, driver.execute_script("return arguments[0].id;", el))
            return (actual == spec["value"], actual)
        # values: the selected option values of a <select multiple>
        spec = cast("dict[str, object]", arg)
        got = cast(
            "list[str]",
            driver.execute_script(
                "return Array.prototype.map.call("
                "arguments[0].selectedOptions || [], function (o) { return o.value; });",
                el,
            ),
        )
        return (got == spec["values"], got)
    raise ValueError(f"unknown matcher: {matcher}")


def run_expect(
    driver: WebDriver,
    selector: str,
    matcher: str,
    arg: dict[str, object] | None,
    *,
    is_not: bool,
    timeout_ms: int,
    ensure_bundle: Callable[[], None],
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
        matches, received = _evaluate(driver, ensure_bundle, selector, matcher, arg)
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
