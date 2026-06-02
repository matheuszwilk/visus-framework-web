from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from visus.web.backends.base import PageDelegate
    from visus.web.config import Defaults


class Locator:
    """A lazy recipe: page delegate + immutable tuple of selector steps."""

    def __init__(
        self,
        delegate: PageDelegate,
        steps: tuple[dict[str, object], ...],
        defaults: Defaults,
    ) -> None:
        self._delegate = delegate
        self._steps = tuple(steps)
        self._defaults = defaults

    def _child(self, step: dict[str, object]) -> Locator:
        return Locator(self._delegate, self._steps + (step,), self._defaults)

    # --- builders (pure string/dict surgery; never touch the DOM) ---
    def get_by_role(self, role: str, *, name: str | None = None, exact: bool = False) -> Locator:
        return self._child({"kind": "role", "role": role, "name": name, "exact": exact})

    def get_by_text(self, text: str, *, exact: bool = False) -> Locator:
        return self._child({"kind": "text", "value": text, "exact": exact})

    def get_by_label(self, text: str, *, exact: bool = False) -> "Locator":
        return self._child({"kind": "label", "value": text, "exact": exact})

    def get_by_placeholder(self, text: str, *, exact: bool = False) -> "Locator":
        return self._child({"kind": "placeholder", "value": text, "exact": exact})

    def get_by_alt_text(self, text: str, *, exact: bool = False) -> "Locator":
        return self._child({"kind": "alt", "value": text, "exact": exact})

    def get_by_title(self, text: str, *, exact: bool = False) -> "Locator":
        return self._child({"kind": "title", "value": text, "exact": exact})

    def get_by_test_id(self, test_id: str) -> "Locator":
        return self._child({"kind": "testid", "value": test_id})

    def locator(self, selector: str) -> Locator:
        if selector.startswith("xpath="):
            return self._child({"kind": "xpath", "value": selector[len("xpath=") :]})
        if selector.startswith("//") or selector.startswith("("):
            return self._child({"kind": "xpath", "value": selector})
        return self._child({"kind": "css", "value": selector})

    def filter(self, *, has_text: str | None = None) -> Locator:
        if has_text is not None:
            return self._child({"kind": "filter_has_text", "value": has_text})
        return self

    def first(self) -> Locator:
        return self._child({"kind": "nth", "index": 0})

    def last(self) -> Locator:
        return self._child({"kind": "nth", "index": -1})

    def nth(self, index: int) -> Locator:
        return self._child({"kind": "nth", "index": index})

    @property
    def _encoded(self) -> str:
        return json.dumps(list(self._steps))

    # --- reads (resolve against the live page) ---
    def count(self) -> int:
        return self._delegate.locator_count(self._encoded)

    def is_visible(self) -> bool:
        return self._delegate.locator_is_visible(self._encoded)

    def text_content(self) -> str | None:
        return self._delegate.locator_text_content(self._encoded)

    # --- actions (auto-wait via actionability loop in the delegate) ---
    def click(self, *, timeout: int | None = None, force: bool = False) -> None:
        self._delegate.locator_click(
            self._encoded,
            timeout_ms=timeout if timeout is not None else self._defaults.action_timeout_ms,
            force=force,
        )

    def fill(self, value: str, *, timeout: int | None = None, force: bool = False) -> None:
        self._delegate.locator_fill(
            self._encoded,
            value,
            timeout_ms=timeout if timeout is not None else self._defaults.action_timeout_ms,
            force=force,
        )

    def input_value(self) -> str:
        return self._delegate.locator_input_value(self._encoded)

    def all(self) -> list["Locator"]:
        return [self.nth(i) for i in range(self.count())]

    def all_text_contents(self) -> list[str]:
        return self._delegate.locator_all_text(self._encoded)

    def get_attribute(self, name: str) -> str | None:
        return self._delegate.locator_get_attribute(self._encoded, name)

    def is_enabled(self) -> bool:
        return self._delegate.locator_state(self._encoded, "enabled")

    def is_checked(self) -> bool:
        return self._delegate.locator_state(self._encoded, "checked")

    def is_editable(self) -> bool:
        return self._delegate.locator_state(self._encoded, "editable")

    def is_hidden(self) -> bool:
        return self._delegate.locator_state(self._encoded, "hidden")
