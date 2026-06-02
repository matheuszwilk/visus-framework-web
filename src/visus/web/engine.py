from __future__ import annotations

from enum import Enum

from visus.web.errors import UnsupportedEngineError


class Engine(str, Enum):
    CHROME = "chrome"
    EDGE = "edge"
    FIREFOX = "firefox"
    EDGE_IE = "edge_ie"

    @classmethod
    def from_str(cls, value: "Engine | str") -> "Engine":
        if isinstance(value, Engine):
            return value
        try:
            return cls(value.lower())
        except ValueError as exc:
            raise UnsupportedEngineError(
                f"Unknown engine {value!r}; supported: {[e.value for e in cls]}"
            ) from exc
