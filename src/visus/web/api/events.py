"""Event holder types for expect_popup / expect_dialog / expect_download."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from visus.web import errors

if TYPE_CHECKING:
    from visus.web.backends.base import PageDelegate


class _ValueHolder:
    """Holds a single value set after a context-manager block completes."""

    def __init__(self) -> None:
        self._value: Any = _UNSET

    def _set(self, value: Any) -> None:  # noqa: ANN401
        self._value = value

    @property
    def value(self) -> Any:  # noqa: ANN401
        if self._value is _UNSET:
            raise errors.VisusWebError("value not available until the block completes")
        return self._value


_UNSET = object()


@dataclass(frozen=True)
class Dialog:
    """Immutable record of a browser dialog that was handled."""

    message: str
    type: str


@dataclass(frozen=True)
class Download:
    """Immutable record of a completed browser download."""

    path: str
    suggested_filename: str

    def save_as(self, target: str) -> None:
        """Copy the downloaded file to *target* (parent dirs are created automatically)."""
        import os

        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        shutil.copyfile(self.path, target)


@dataclass(frozen=True)
class ConsoleMessage:
    """A captured browser console message (Chromium).

    ``level`` is the WebDriver log level: ``"SEVERE"`` (console.error / uncaught
    exceptions), ``"WARNING"`` or ``"INFO"``. ``text`` includes the source
    location prefix as reported by the browser.
    """

    level: str
    text: str


class NetworkResponse:
    """A captured network response (Chromium). The body is fetched lazily."""

    def __init__(self, delegate: PageDelegate, rec: dict[str, object]) -> None:
        self._delegate = delegate
        self._request_id = cast(str, rec.get("request_id", ""))
        self.url = cast(str, rec.get("url", ""))
        self.status = cast(int, rec.get("status", 0))
        self.method = cast(str, rec.get("method", ""))
        self.resource_type = cast(str, rec.get("resource_type", ""))

    @property
    def ok(self) -> bool:
        """True for a 2xx status."""
        return 200 <= self.status < 300

    def body(self) -> str:
        """The response body (decoded as UTF-8), fetched via CDP."""
        return self._delegate.response_body(self._request_id)

    def __repr__(self) -> str:
        return f"<NetworkResponse {self.method or 'GET'} {self.url} {self.status}>"
