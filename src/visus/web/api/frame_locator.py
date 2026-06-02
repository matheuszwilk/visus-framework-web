from __future__ import annotations

from typing import TYPE_CHECKING

from visus.web.api.locator import Locator

if TYPE_CHECKING:
    from visus.web.backends.base import PageDelegate
    from visus.web.config import Defaults


def _frame_step(selector: str) -> dict[str, object]:
    if selector.startswith("xpath=") or selector.startswith("//") or selector.startswith("("):
        inner = selector[len("xpath=") :] if selector.startswith("xpath=") else selector
        return {"kind": "frame", "frame": [{"kind": "xpath", "value": inner}]}
    return {"kind": "frame", "frame": [{"kind": "css", "value": selector}]}


class FrameLocator:
    def __init__(
        self,
        delegate: PageDelegate,
        steps: tuple[dict[str, object], ...],
        defaults: Defaults,
    ) -> None:
        self._delegate = delegate
        self._steps = tuple(steps)
        self._defaults = defaults

    def frame_locator(self, selector: str) -> FrameLocator:
        return FrameLocator(self._delegate, self._steps + (_frame_step(selector),), self._defaults)

    def locator(self, selector: str) -> Locator:
        return Locator(self._delegate, self._steps, self._defaults).locator(selector)

    def get_by_role(self, role: str, *, name: str | None = None, exact: bool = False) -> Locator:
        return Locator(self._delegate, self._steps, self._defaults).get_by_role(
            role, name=name, exact=exact
        )

    def get_by_text(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, self._steps, self._defaults).get_by_text(text, exact=exact)

    def get_by_label(self, text: str, *, exact: bool = False) -> Locator:
        return Locator(self._delegate, self._steps, self._defaults).get_by_label(text, exact=exact)

    def get_by_test_id(self, test_id: str) -> Locator:
        return Locator(self._delegate, self._steps, self._defaults).get_by_test_id(test_id)
