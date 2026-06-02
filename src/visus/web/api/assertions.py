from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from visus.web.api.locator import Locator


class LocatorAssertions:
    def __init__(self, locator: "Locator", *, is_not: bool = False) -> None:
        self._locator = locator
        self._is_not = is_not

    @property
    def not_(self) -> "LocatorAssertions":
        return LocatorAssertions(self._locator, is_not=not self._is_not)

    def _poll(self, matcher: str, arg: dict | None, timeout: int | None) -> None:
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

    def to_have_text(self, expected: str, *, exact: bool = True, timeout: int | None = None) -> None:
        self._poll("text", {"value": expected, "exact": exact}, timeout)

    def to_contain_text(self, expected: str, *, timeout: int | None = None) -> None:
        self._poll("text", {"value": expected, "exact": False}, timeout)

    def to_have_count(self, count: int, *, timeout: int | None = None) -> None:
        self._poll("count", {"count": count}, timeout)


def expect(locator: "Locator") -> LocatorAssertions:
    """Web-first assertion entry point: expect(locator).to_be_visible() etc."""
    return LocatorAssertions(locator)
