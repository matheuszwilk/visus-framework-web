from __future__ import annotations

from visus.web.api.page import Page
from visus.web.backends.base import ContextDelegate
from visus.web.config import Defaults


class Context:
    def __init__(self, delegate: ContextDelegate, defaults: Defaults) -> None:
        self._delegate = delegate
        self._defaults = defaults

    def new_page(self) -> Page:
        return Page(self._delegate.new_page(), self._defaults)

    @property
    def pages(self) -> list[Page]:
        return [Page(d, self._defaults) for d in self._delegate.pages()]

    def close(self) -> None:
        self._delegate.close()
