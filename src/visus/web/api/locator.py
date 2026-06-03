from __future__ import annotations

import json
from typing import TYPE_CHECKING

from visus.web.api._steps import run_step

if TYPE_CHECKING:
    from visus.web.api.frame_locator import FrameLocator
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

    def get_by_label(self, text: str, *, exact: bool = False) -> Locator:
        return self._child({"kind": "label", "value": text, "exact": exact})

    def get_by_placeholder(self, text: str, *, exact: bool = False) -> Locator:
        return self._child({"kind": "placeholder", "value": text, "exact": exact})

    def get_by_alt_text(self, text: str, *, exact: bool = False) -> Locator:
        return self._child({"kind": "alt", "value": text, "exact": exact})

    def get_by_title(self, text: str, *, exact: bool = False) -> Locator:
        return self._child({"kind": "title", "value": text, "exact": exact})

    def get_by_test_id(self, test_id: str) -> Locator:
        return self._child({"kind": "testid", "value": test_id})

    def locator(self, selector: str) -> Locator:
        if selector.startswith("xpath="):
            return self._child({"kind": "xpath", "value": selector[len("xpath=") :]})
        if selector.startswith("//") or selector.startswith("("):
            return self._child({"kind": "xpath", "value": selector})
        return self._child({"kind": "css", "value": selector})

    def frame_locator(self, selector: str) -> FrameLocator:
        from visus.web.api.frame_locator import FrameLocator, _frame_step

        return FrameLocator(self._delegate, self._steps + (_frame_step(selector),), self._defaults)

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

    def _t(self, timeout: int | None) -> int:
        return timeout if timeout is not None else self._defaults.action_timeout_ms

    # --- actions (auto-wait via actionability loop in the delegate) ---
    def click(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_click(
                self._encoded, timeout_ms=self._t(timeout), force=force
            ),
            backtrack,
        )

    def fill(
        self,
        value: str,
        *,
        timeout: int | None = None,
        force: bool = False,
        backtrack: bool | int = False,
    ) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_fill(
                self._encoded, value, timeout_ms=self._t(timeout), force=force
            ),
            backtrack,
        )

    def hover(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_hover(
                self._encoded, timeout_ms=self._t(timeout), force=force
            ),
            backtrack,
        )

    def dblclick(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_dblclick(
                self._encoded, timeout_ms=self._t(timeout), force=force
            ),
            backtrack,
        )

    def check(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_set_checked(
                self._encoded, True, timeout_ms=self._t(timeout), force=force
            ),
            backtrack,
        )

    def uncheck(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_set_checked(
                self._encoded, False, timeout_ms=self._t(timeout), force=force
            ),
            backtrack,
        )

    def set_checked(
        self,
        checked: bool,
        *,
        timeout: int | None = None,
        force: bool = False,
        backtrack: bool | int = False,
    ) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_set_checked(
                self._encoded, checked, timeout_ms=self._t(timeout), force=force
            ),
            backtrack,
        )

    def select_option(
        self,
        *,
        value: str | None = None,
        label: str | None = None,
        index: int | None = None,
        timeout: int | None = None,
        backtrack: bool | int = False,
    ) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_select_option(
                self._encoded, value=value, label=label, index=index, timeout_ms=self._t(timeout)
            ),
            backtrack,
        )

    def press(self, key: str, *, timeout: int | None = None, backtrack: bool | int = False) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_press(self._encoded, key, timeout_ms=self._t(timeout)),
            backtrack,
        )

    def focus(self, *, timeout: int | None = None, backtrack: bool | int = False) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_focus(self._encoded, timeout_ms=self._t(timeout)),
            backtrack,
        )

    def blur(self, *, timeout: int | None = None, backtrack: bool | int = False) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_blur(self._encoded, timeout_ms=self._t(timeout)),
            backtrack,
        )

    def clear(
        self, *, timeout: int | None = None, force: bool = False, backtrack: bool | int = False
    ) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_clear(
                self._encoded, timeout_ms=self._t(timeout), force=force
            ),
            backtrack,
        )

    def drag_to(
        self, target: Locator, *, timeout: int | None = None, backtrack: bool | int = False
    ) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_drag_to(
                self._encoded, target._encoded, timeout_ms=self._t(timeout)
            ),
            backtrack,
        )

    def input_value(self) -> str:
        return self._delegate.locator_input_value(self._encoded)

    def all(self) -> list[Locator]:
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

    def evaluate(self, expression: str, arg: object = None) -> object:
        return self._delegate.locator_evaluate(self._encoded, expression, arg)

    def screenshot(self, *, path: str | None = None) -> bytes:
        from pathlib import Path

        data = self._delegate.locator_screenshot(self._encoded)
        if path is not None:
            Path(path).write_bytes(data)
        return data

    def set_input_files(
        self, files: str | list[str], *, backtrack: bool | int = False
    ) -> None:
        paths = [files] if isinstance(files, str) else list(files)
        run_step(
            self._delegate,
            lambda: self._delegate.locator_set_input_files(self._encoded, paths),
            backtrack,
        )

    # --- vision hooks (lazy-import; requires [vision] extra) ---
    def ocr_text(self) -> str:
        from visus.web.vision import read_text

        return read_text(self.screenshot())

    def find_image(self, template: object, *, confidence: float = 0.8) -> object:
        from visus.web.vision import find_image

        return find_image(self.screenshot(), template, confidence=confidence)  # type: ignore[arg-type]
