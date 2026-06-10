from __future__ import annotations

from dataclasses import replace

from visus.web.api.page import Page
from visus.web.backends.base import ContextDelegate
from visus.web.config import Defaults


class Context:
    def __init__(self, delegate: ContextDelegate, defaults: Defaults) -> None:
        self._delegate = delegate
        self._defaults = defaults

    def new_page(self) -> Page:
        return Page(self._delegate.new_page(), self._defaults)

    def set_default_timeout(self, timeout: int) -> None:
        """Default timeout (ms) for actions and navigations on pages created
        by this context *after* this call."""
        self._defaults = replace(
            self._defaults, action_timeout_ms=timeout, navigation_timeout_ms=timeout
        )

    def set_default_navigation_timeout(self, timeout: int) -> None:
        """Default navigation timeout (ms) for pages created after this call."""
        self._defaults = replace(self._defaults, navigation_timeout_ms=timeout)

    @property
    def pages(self) -> list[Page]:
        return [Page(d, self._defaults) for d in self._delegate.pages()]

    def adopt_open_windows(self) -> list[Page]:
        """Adopt browser windows/tabs opened outside visus (links, ``window.open``).

        ``context.pages`` already reflects these automatically; call this when you
        want the list of *just-discovered* pages. Also drops windows that were
        closed externally. Returns the newly-adopted pages.
        """
        return [Page(d, self._defaults) for d in self._delegate.adopt_open_windows()]

    def close(self) -> None:
        self._delegate.close()

    def cookies(self) -> list[dict]:  # type: ignore[type-arg]
        return self._delegate.cookies()

    def add_cookies(self, cookies: list[dict]) -> None:  # type: ignore[type-arg]
        self._delegate.add_cookies(cookies)

    def clear_cookies(self) -> None:
        self._delegate.clear_cookies()
