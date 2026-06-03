"""Low-level input-device facades — Mouse and Keyboard.

These are thin wrappers over the PageDelegate protocol methods so that
the public API (page.mouse / page.keyboard) stays selenium-free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from visus.web.backends.base import PageDelegate


class Mouse:
    """Absolute-coordinate pointer device facade."""

    def __init__(self, delegate: "PageDelegate") -> None:
        self._d = delegate

    def move(self, x: float, y: float) -> None:
        """Move the mouse pointer to absolute viewport coordinates (x, y)."""
        self._d.mouse_move(x, y)

    def down(self) -> None:
        """Press (hold) the primary mouse button at the current position."""
        self._d.mouse_down()

    def up(self) -> None:
        """Release the primary mouse button."""
        self._d.mouse_up()

    def click(self, x: float, y: float) -> None:
        """Move to (x, y) and perform a single left-click."""
        self._d.mouse_click(x, y)

    def dblclick(self, x: float, y: float) -> None:
        """Move to (x, y) and perform a double left-click."""
        self._d.mouse_dblclick(x, y)

    def wheel(self, delta_x: float, delta_y: float) -> None:
        """Scroll by (delta_x, delta_y) pixels at the current pointer position."""
        self._d.mouse_wheel(delta_x, delta_y)


class Keyboard:
    """Keyboard input facade."""

    def __init__(self, delegate: "PageDelegate") -> None:
        self._d = delegate

    def down(self, key: str) -> None:
        """Hold a key down (e.g. 'Shift', 'Control')."""
        self._d.keyboard_down(key)

    def up(self, key: str) -> None:
        """Release a held key."""
        self._d.keyboard_up(key)

    def press(self, key: str) -> None:
        """Press and release a key or key combo (e.g. 'Enter', 'Control+a')."""
        self._d.keyboard_press(key)

    def type(self, text: str) -> None:
        """Type a string of characters into the currently focused element."""
        self._d.keyboard_type(text)

    def insert_text(self, text: str) -> None:
        """Insert text at the cursor position without triggering key events."""
        self._d.keyboard_insert_text(text)
