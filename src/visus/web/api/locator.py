from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Union

from visus.web.api._steps import run_step

if TYPE_CHECKING:
    from visus.web.api.frame_locator import FrameLocator
    from visus.web.backends.base import PageDelegate
    from visus.web.config import Defaults

TextArg = Union[str, "re.Pattern[str]"]
"""A text matcher: plain string (substring, or exact with ``exact=True``) or a
compiled :class:`re.Pattern` (matched with JS ``RegExp.test`` semantics)."""


def _js_flags(flags: int) -> str:
    """Translate Python re flags into the JS RegExp flags we support (i, m, s)."""
    out = ""
    if flags & re.IGNORECASE:
        out += "i"
    if flags & re.MULTILINE:
        out += "m"
    if flags & re.DOTALL:
        out += "s"
    return out


def _text_step(kind: str, text: TextArg, exact: bool) -> dict[str, object]:
    """Encode a text-ish matcher step: {value, exact} for str, {regex, flags} for re.Pattern."""
    if isinstance(text, re.Pattern):
        return {"kind": kind, "regex": text.pattern, "flags": _js_flags(text.flags)}
    return {"kind": kind, "value": text, "exact": exact}


def _embed(other: Locator) -> list[dict[str, object]]:
    """Steps of *other* for embedding into a composed step (filter_has / or / and).

    Composition is evaluated inside a single document, so a locator that crosses
    into an iframe cannot be embedded.
    """
    if any(s.get("kind") == "frame" for s in other._steps):
        raise ValueError("cannot compose locators that cross into an iframe")
    return list(other._steps)


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
    def get_by_role(
        self, role: str, *, name: TextArg | None = None, exact: bool = False
    ) -> Locator:
        if isinstance(name, re.Pattern):
            return self._child(
                {
                    "kind": "role",
                    "role": role,
                    "nameRegex": name.pattern,
                    "nameFlags": _js_flags(name.flags),
                }
            )
        return self._child({"kind": "role", "role": role, "name": name, "exact": exact})

    def get_by_text(self, text: TextArg, *, exact: bool = False) -> Locator:
        return self._child(_text_step("text", text, exact))

    def get_by_label(self, text: TextArg, *, exact: bool = False) -> Locator:
        return self._child(_text_step("label", text, exact))

    def get_by_placeholder(self, text: TextArg, *, exact: bool = False) -> Locator:
        return self._child(_text_step("placeholder", text, exact))

    def get_by_alt_text(self, text: TextArg, *, exact: bool = False) -> Locator:
        return self._child(_text_step("alt", text, exact))

    def get_by_title(self, text: TextArg, *, exact: bool = False) -> Locator:
        return self._child(_text_step("title", text, exact))

    def get_by_test_id(self, test_id: str) -> Locator:
        return self._child({"kind": "testid", "value": test_id})

    def locator(self, selector: str, *, deep: bool = False) -> Locator:
        if selector.lstrip().startswith("<"):
            # a pasted DevTools element (Copy element) → resilient, multi-candidate locator
            from visus.web.api import _htmlsel

            step = _htmlsel.smart_step(selector)
            if deep:
                step = {**step, "deep": True}
            return self._child(step)
        if selector.startswith("xpath="):
            return self._child({"kind": "xpath", "value": selector[len("xpath=") :]})
        if selector.startswith("css="):
            return self._child(self._css_step(selector[len("css=") :], deep))
        if selector.startswith("//") or selector.startswith("("):
            return self._child({"kind": "xpath", "value": selector})
        return self._child(self._css_step(selector, deep))

    @staticmethod
    def _css_step(value: str, deep: bool) -> dict[str, object]:
        # `deep` makes queryAll pierce open shadow roots (shadow-DOM Field.locator
        # re-resolution). Omitted when false to keep plain CSS steps unchanged.
        step: dict[str, object] = {"kind": "css", "value": value}
        if deep:
            step["deep"] = True
        return step

    def frame_locator(self, selector: str) -> FrameLocator:
        from visus.web.api.frame_locator import FrameLocator, _frame_step

        return FrameLocator(self._delegate, self._steps + (_frame_step(selector),), self._defaults)

    def filter(
        self,
        *,
        has_text: TextArg | None = None,
        has_not_text: TextArg | None = None,
        has: Locator | None = None,
        has_not: Locator | None = None,
    ) -> Locator:
        """Narrow the matched set: by contained text (``has_text``/``has_not_text``)
        and/or by a relative inner locator (``has``/``has_not``)."""
        loc = self
        if has_text is not None:
            loc = loc._child(_text_step("filter_has_text", has_text, False))
        if has_not_text is not None:
            loc = loc._child(_text_step("filter_has_not_text", has_not_text, False))
        if has is not None:
            loc = loc._child({"kind": "filter_has", "steps": _embed(has)})
        if has_not is not None:
            loc = loc._child({"kind": "filter_has_not", "steps": _embed(has_not)})
        return loc

    def or_(self, other: Locator) -> Locator:
        """Elements matching this locator OR *other* (union, document order)."""
        return self._child({"kind": "or", "steps": _embed(other)})

    def and_(self, other: Locator) -> Locator:
        """Elements matching this locator AND *other* (intersection)."""
        return self._child({"kind": "and", "steps": _embed(other)})

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
            action_name="click",
            selector=self._encoded,
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
            action_name="fill",
            selector=self._encoded,
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
            action_name="hover",
            selector=self._encoded,
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
            action_name="dblclick",
            selector=self._encoded,
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
            action_name="check",
            selector=self._encoded,
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
            action_name="uncheck",
            selector=self._encoded,
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
            action_name="set_checked",
            selector=self._encoded,
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
            action_name="select_option",
            selector=self._encoded,
        )

    def press(self, key: str, *, timeout: int | None = None, backtrack: bool | int = False) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_press(self._encoded, key, timeout_ms=self._t(timeout)),
            backtrack,
            action_name="press",
            selector=self._encoded,
        )

    def focus(self, *, timeout: int | None = None, backtrack: bool | int = False) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_focus(self._encoded, timeout_ms=self._t(timeout)),
            backtrack,
            action_name="focus",
            selector=self._encoded,
        )

    def blur(self, *, timeout: int | None = None, backtrack: bool | int = False) -> None:
        run_step(
            self._delegate,
            lambda: self._delegate.locator_blur(self._encoded, timeout_ms=self._t(timeout)),
            backtrack,
            action_name="blur",
            selector=self._encoded,
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
            action_name="clear",
            selector=self._encoded,
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
            action_name="drag_to",
            selector=self._encoded,
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

    def set_input_files(self, files: str | list[str], *, backtrack: bool | int = False) -> None:
        paths = [files] if isinstance(files, str) else list(files)
        run_step(
            self._delegate,
            lambda: self._delegate.locator_set_input_files(self._encoded, paths),
            backtrack,
            action_name="set_input_files",
            selector=self._encoded,
        )

    # --- vision hooks (lazy-import; requires [vision] extra) ---
    def ocr_text(self) -> str:
        from visus.web.vision import read_text

        return read_text(self.screenshot())

    def find_image(self, template: object, *, confidence: float = 0.8) -> object:
        from visus.web.vision import find_image

        return find_image(self.screenshot(), template, confidence=confidence)  # type: ignore[arg-type]
