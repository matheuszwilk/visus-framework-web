from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

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

    def storage_state(self, *, path: str | None = None) -> dict:  # type: ignore[type-arg]
        """Snapshot cookies + web storage (for the open pages' origins).

        Pass ``path`` to also write the snapshot as JSON — reuse it in a later
        run with :meth:`restore_storage_state` to skip a login.
        """
        state = self._delegate.storage_state()
        if path is not None:
            Path(path).write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state

    def restore_storage_state(self, state: dict | str) -> None:  # type: ignore[type-arg]
        """Apply a snapshot from :meth:`storage_state` (a dict or a JSON file path).

        Navigate a page to the target origin first; cookies only apply to the
        currently-loaded domain and web storage is per-origin.
        """
        if isinstance(state, str):
            state = json.loads(Path(state).read_text(encoding="utf-8"))
        self._delegate.restore_storage_state(state)

    def cookies(self) -> list[dict]:  # type: ignore[type-arg]
        return self._delegate.cookies()

    def add_cookies(self, cookies: list[dict]) -> None:  # type: ignore[type-arg]
        self._delegate.add_cookies(cookies)

    def clear_cookies(self) -> None:
        self._delegate.clear_cookies()
