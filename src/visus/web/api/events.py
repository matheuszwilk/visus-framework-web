"""Event holder types for expect_popup / expect_dialog.  No selenium types here."""

from __future__ import annotations

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
