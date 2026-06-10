from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from visus.web.api.locator import Locator, TextArg


def _text_arg(value: TextArg, exact: bool) -> dict[str, object]:
    """Encode a text matcher argument: {value, exact} for str, {regex, flags} for Pattern.

    Regex flags are passed as the Python int so the (Python-side) expect engine
    can re-compile the pattern faithfully.
    """
    if isinstance(value, re.Pattern):
        return {"regex": value.pattern, "flags": value.flags}
    return {"value": value, "exact": exact}


class LocatorAssertions:
    def __init__(self, locator: Locator, *, is_not: bool = False) -> None:
        self._locator = locator
        self._is_not = is_not

    @property
    def not_(self) -> LocatorAssertions:
        return LocatorAssertions(self._locator, is_not=not self._is_not)

    def _poll(self, matcher: str, arg: dict[str, object] | None, timeout: int | None) -> None:
        loc = self._locator
        loc._delegate.expect_poll(
            loc._encoded,
            matcher,
            arg,
            is_not=self._is_not,
            timeout_ms=timeout if timeout is not None else loc._defaults.expect_timeout_ms,
        )

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


def expect(locator: Locator) -> LocatorAssertions:
    """Web-first assertion entry point: expect(locator).to_be_visible() etc."""
    return LocatorAssertions(locator)
