from __future__ import annotations

from visus.web.api.locator import Locator
from visus.web.backends.base import PageDelegate
from visus.web.config import Defaults


class Page:
    def __init__(self, delegate: PageDelegate, defaults: Defaults) -> None:
        self._delegate = delegate
        self._defaults = defaults

    def goto(self, url: str, *, wait_until: str = "load", timeout: int | None = None) -> None:
        self._delegate.goto(
            url,
            wait_until=wait_until,
            timeout_ms=timeout if timeout is not None else self._defaults.navigation_timeout_ms,
        )

    @property
    def url(self) -> str:
        return self._delegate.current_url()

    def title(self) -> str:
        return self._delegate.title()

    def content(self) -> str:
        return self._delegate.content()

    def reload(self, *, timeout: int | None = None) -> None:
        self._delegate.reload(
            timeout_ms=timeout if timeout is not None else self._defaults.navigation_timeout_ms
        )

    def go_back(self, *, timeout: int | None = None) -> None:
        self._delegate.go_back(
            timeout_ms=timeout if timeout is not None else self._defaults.navigation_timeout_ms
        )

    def go_forward(self, *, timeout: int | None = None) -> None:
        self._delegate.go_forward(
            timeout_ms=timeout if timeout is not None else self._defaults.navigation_timeout_ms
        )

    def close(self) -> None:
        self._delegate.close()

    @property
    def is_closed(self) -> bool:
        return self._delegate.is_closed()

    def locator(self, selector: str) -> Locator:
        return Locator(self._delegate, (), self._defaults).locator(selector)

    def get_by_role(self, role: str, *, name: str | None = None, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_role(role, name=name, exact=exact)

    def get_by_text(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_text(text, exact=exact)

    def get_by_label(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_label(text, exact=exact)

    def get_by_placeholder(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_placeholder(text, exact=exact)

    def get_by_alt_text(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_alt_text(text, exact=exact)

    def get_by_title(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_title(text, exact=exact)

    def get_by_test_id(self, test_id: str) -> Locator:
        return Locator(self._delegate, (), self._defaults).get_by_test_id(test_id)
