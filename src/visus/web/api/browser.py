from __future__ import annotations

from types import TracebackType

from visus.web.api.context import Context
from visus.web.api.page import Page
from visus.web.backends.base import BrowserDelegate
from visus.web.config import Defaults


class Browser:
    def __init__(self, delegate: BrowserDelegate, defaults: Defaults) -> None:
        self._delegate = delegate
        self._defaults = defaults
        self._default_context: Context | None = None

    def new_context(self) -> Context:
        return Context(self._delegate.new_context(), self._defaults)

    def new_page(self) -> Page:
        if self._default_context is None:
            # Adopt the browser's first (already-open) context.
            existing = self._delegate.contexts()
            delegate = existing[0] if existing else self._delegate.new_context()
            self._default_context = Context(delegate, self._defaults)
            pages = self._default_context.pages
            if pages:
                return pages[0]
        return self._default_context.new_page()

    @property
    def contexts(self) -> list[Context]:
        return [Context(d, self._defaults) for d in self._delegate.contexts()]

    def close(self) -> None:
        self._delegate.dispose()

    def __enter__(self) -> Browser:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
