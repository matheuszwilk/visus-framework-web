from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable, Sequence
from time import monotonic, sleep
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from visus.web.api.locator import Locator, TextArg
    from visus.web.api.page import Page


def _text_arg(value: TextArg, exact: bool) -> dict[str, object]:
    """Encode a text matcher argument: {value, exact} for str, {regex, flags} for Pattern.

    Regex flags are passed as the Python int so the (Python-side) expect engine
    can re-compile the pattern faithfully.
    """
    if isinstance(value, re.Pattern):
        return {"regex": value.pattern, "flags": value.flags}
    return {"value": value, "exact": exact}


# --- soft-assertion collector (drained by expect.verify_soft / pytest plugin) ---

_soft_failures: list[AssertionError] = []


def verify_soft() -> None:
    """Raise one combined AssertionError for every collected soft failure, then reset."""
    global _soft_failures
    failures, _soft_failures = _soft_failures, []
    if failures:
        raise AssertionError(
            f"{len(failures)} soft assertion(s) failed:\n\n"
            + "\n\n".join(str(f) for f in failures)
        )


class LocatorAssertions:
    def __init__(
        self,
        locator: Locator,
        *,
        is_not: bool = False,
        message: str | None = None,
        soft: bool = False,
    ) -> None:
        self._locator = locator
        self._is_not = is_not
        self._message = message
        self._soft = soft

    @property
    def not_(self) -> LocatorAssertions:
        return LocatorAssertions(
            self._locator, is_not=not self._is_not, message=self._message, soft=self._soft
        )

    def _fail(self, err: AssertionError) -> None:
        if self._message:
            err = AssertionError(f"{self._message}\n{err}")
        if self._soft:
            _soft_failures.append(err)
            return
        raise err

    def _poll(self, matcher: str, arg: dict[str, object] | None, timeout: int | None) -> None:
        loc = self._locator
        try:
            loc._delegate.expect_poll(
                loc._encoded,
                matcher,
                arg,
                is_not=self._is_not,
                timeout_ms=timeout if timeout is not None else loc._defaults.expect_timeout_ms,
            )
        except AssertionError as exc:
            self._fail(exc)

    def to_be_visible(self, *, timeout: int | None = None) -> None:
        self._poll("visible", None, timeout)

    def to_be_hidden(self, *, timeout: int | None = None) -> None:
        self._poll("hidden", None, timeout)

    def to_be_enabled(self, *, timeout: int | None = None) -> None:
        self._poll("enabled", None, timeout)

    def to_be_checked(self, *, timeout: int | None = None) -> None:
        self._poll("checked", None, timeout)

    def to_have_text(
        self, expected: TextArg, *, exact: bool = True, timeout: int | None = None
    ) -> None:
        self._poll("text", _text_arg(expected, exact), timeout)

    def to_contain_text(self, expected: TextArg, *, timeout: int | None = None) -> None:
        self._poll("text", _text_arg(expected, False), timeout)

    def to_have_count(self, count: int, *, timeout: int | None = None) -> None:
        self._poll("count", {"count": count}, timeout)

    def to_have_value(self, value: TextArg, *, timeout: int | None = None) -> None:
        self._poll("value", _text_arg(value, True), timeout)

    def to_have_attribute(self, name: str, value: TextArg, *, timeout: int | None = None) -> None:
        self._poll("attribute", {"name": name, **_text_arg(value, True)}, timeout)

    def to_have_class(self, class_name: str, *, timeout: int | None = None) -> None:
        self._poll("class", {"value": class_name, "mode": "exact"}, timeout)

    def to_contain_class(self, class_name: str, *, timeout: int | None = None) -> None:
        self._poll("class", {"value": class_name, "mode": "contains"}, timeout)

    def to_have_role(self, role: str, *, timeout: int | None = None) -> None:
        self._poll("role", {"value": role}, timeout)

    def to_be_attached(self, *, timeout: int | None = None) -> None:
        self._poll("attached", None, timeout)

    def to_be_disabled(self, *, timeout: int | None = None) -> None:
        self._poll("disabled", None, timeout)

    def to_be_editable(self, *, timeout: int | None = None) -> None:
        self._poll("editable", None, timeout)

    def to_be_focused(self, *, timeout: int | None = None) -> None:
        self._poll("focused", None, timeout)

    def to_be_empty(self, *, timeout: int | None = None) -> None:
        self._poll("empty", None, timeout)

    def to_be_in_viewport(self, *, timeout: int | None = None) -> None:
        self._poll("in_viewport", None, timeout)

    def to_have_css(self, name: str, value: TextArg, *, timeout: int | None = None) -> None:
        self._poll("css", {"name": name, **_text_arg(value, True)}, timeout)

    def to_have_id(self, id: str, *, timeout: int | None = None) -> None:
        self._poll("id", {"value": id, "exact": True}, timeout)

    def to_have_values(self, values: Sequence[str], *, timeout: int | None = None) -> None:
        self._poll("values", {"values": list(values)}, timeout)


class PageAssertions:
    """Page-level web-first assertions: ``expect(page).to_have_url(...)`` etc."""

    def __init__(
        self,
        page: Page,
        *,
        is_not: bool = False,
        message: str | None = None,
        soft: bool = False,
    ) -> None:
        self._page = page
        self._is_not = is_not
        self._message = message
        self._soft = soft

    @property
    def not_(self) -> PageAssertions:
        return PageAssertions(
            self._page, is_not=not self._is_not, message=self._message, soft=self._soft
        )

    def _fail(self, err: AssertionError) -> None:
        if self._message:
            err = AssertionError(f"{self._message}\n{err}")
        if self._soft:
            _soft_failures.append(err)
            return
        raise err

    def _poll(
        self, check: Callable[[], tuple[bool, object]], what: str, timeout: int | None
    ) -> None:
        t = timeout if timeout is not None else self._page._defaults.expect_timeout_ms
        deadline = monotonic() + t / 1000
        received: object = None
        while True:
            ok, received = check()
            if ok != self._is_not:
                return
            if monotonic() >= deadline:
                break
            sleep(0.1)
        prefix = "not " if self._is_not else ""
        self._fail(
            AssertionError(
                f"expect(page): {prefix}{what} not satisfied within {t}ms;"
                f" last received: {received!r}"
            )
        )

    def to_have_url(self, url: str | re.Pattern[str], *, timeout: int | None = None) -> None:
        """Assert the page URL: glob string (``"*checkout*"``) or compiled regex."""

        def check() -> tuple[bool, object]:
            cur = self._page._delegate.current_url()
            if isinstance(url, re.Pattern):
                return (bool(url.search(cur)), cur)
            return (fnmatch.fnmatch(cur, url) or cur == url, cur)

        self._poll(check, f"to_have_url({url!r})", timeout)

    def to_have_title(self, title: str | re.Pattern[str], *, timeout: int | None = None) -> None:
        """Assert the page title: exact string or compiled regex (``re.search``)."""

        def check() -> tuple[bool, object]:
            cur = self._page._delegate.title()
            if isinstance(title, re.Pattern):
                return (bool(title.search(cur)), cur)
            return (cur == title, cur)

        self._poll(check, f"to_have_title({title!r})", timeout)


def expect(
    target: Locator | Page, message: str | None = None
) -> Union[LocatorAssertions, PageAssertions]:
    """Web-first assertion entry point.

    ``expect(locator).to_be_visible()``, ``expect(page).to_have_url(...)``.
    Pass *message* to prefix any failure with your own context. Use
    ``expect.soft(...)`` to collect failures instead of raising, then
    ``expect.verify_soft()`` to fail on everything collected at once.
    """
    from visus.web.api.page import Page

    if isinstance(target, Page):
        return PageAssertions(target, message=message)
    return LocatorAssertions(target, message=message)


def _soft_expect(
    target: Locator | Page, message: str | None = None
) -> Union[LocatorAssertions, PageAssertions]:
    """Soft variant of :func:`expect` — failures are collected, not raised."""
    from visus.web.api.page import Page

    if isinstance(target, Page):
        return PageAssertions(target, message=message, soft=True)
    return LocatorAssertions(target, message=message, soft=True)


expect.soft = _soft_expect  # type: ignore[attr-defined]
expect.verify_soft = verify_soft  # type: ignore[attr-defined]
