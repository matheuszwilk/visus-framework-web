"""Event holder types for expect_popup / expect_dialog / expect_download."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from visus.web import errors


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
