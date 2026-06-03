"""Unit tests for Mouse and Keyboard API wiring — no real browser needed.

These tests verify that:
1. Mouse and Keyboard delegate all calls to the PageDelegate correctly.
2. page.mouse and page.keyboard properties return the right objects.
3. The wiring is complete (all methods are present and forward correctly).
"""

from __future__ import annotations

import pytest

from visus.web.api.page import Page
from visus.web.config import Defaults


class _CapturingFakePage:
    """Records every delegate call so tests can assert what was called."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._url = "about:blank"
        self._closed = False

    # --- minimal PageDelegate stubs required by Protocol ---
    def goto(self, url, *, wait_until, timeout_ms):
        self._url = url

    def current_url(self):
        return self._url

    def title(self):
        return ""

    def content(self):
        return ""

    def reload(self, *, timeout_ms): ...
    def go_back(self, *, timeout_ms): ...
    def go_forward(self, *, timeout_ms): ...
    def close(self):
        self._closed = True

    def is_closed(self):
        return self._closed

    def locator_count(self, selector):
        return 0

    def locator_is_visible(self, selector):
        return False

    def locator_text_content(self, selector):
        return None

    def locator_click(self, selector, *, timeout_ms, force): ...
    def locator_fill(self, selector, value, *, timeout_ms, force): ...
    def locator_hover(self, selector, *, timeout_ms, force): ...
    def locator_dblclick(self, selector, *, timeout_ms, force): ...
    def locator_set_checked(self, selector, checked, *, timeout_ms, force): ...
    def locator_select_option(self, selector, *, value, label, index, timeout_ms): ...
    def locator_press(self, selector, key, *, timeout_ms): ...
    def locator_focus(self, selector, *, timeout_ms): ...
    def locator_blur(self, selector, *, timeout_ms): ...
    def locator_clear(self, selector, *, timeout_ms, force): ...
    def locator_drag_to(self, selector, target, *, timeout_ms): ...
    def locator_input_value(self, selector):
        return ""

    def locator_state(self, selector, state):
        return False

    def locator_all_text(self, selector):
        return []

    def locator_get_attribute(self, selector, name):
        return None

    def expect_poll(self, selector, matcher, arg, *, is_not, timeout_ms): ...
    def evaluate(self, expression, arg):
        return None

    def locator_evaluate(self, selector, expression, arg):
        return None

    def screenshot(self, *, full_page):
        return b""

    def locator_screenshot(self, selector):
        return b""

    def locator_set_input_files(self, selector, paths): ...
    def snapshot_handles(self):
        return []

    def adopt_new_handle(self, before, *, timeout_ms):
        return _CapturingFakePage()

    def handle_next_dialog(self, *, accept, prompt_text, timeout_ms):
        return ("", "dialog")

    def snapshot(self):
        return []

    def pdf(self):
        return b""

    def snapshot_download_dir(self):
        return []

    def wait_for_download(self, before, *, timeout_ms):
        return ("/tmp/f", "f")

    # --- new input device delegate methods ---
    def mouse_move(self, x, y):
        self.calls.append(("mouse_move", x, y))

    def mouse_down(self):
        self.calls.append(("mouse_down",))

    def mouse_up(self):
        self.calls.append(("mouse_up",))

    def mouse_click(self, x, y):
        self.calls.append(("mouse_click", x, y))

    def mouse_dblclick(self, x, y):
        self.calls.append(("mouse_dblclick", x, y))

    def mouse_wheel(self, delta_x, delta_y):
        self.calls.append(("mouse_wheel", delta_x, delta_y))

    def keyboard_down(self, key):
        self.calls.append(("keyboard_down", key))

    def keyboard_up(self, key):
        self.calls.append(("keyboard_up", key))

    def keyboard_press(self, key):
        self.calls.append(("keyboard_press", key))

    def keyboard_type(self, text):
        self.calls.append(("keyboard_type", text))

    def keyboard_insert_text(self, text):
        self.calls.append(("keyboard_insert_text", text))


@pytest.fixture
def fake_page():
    return _CapturingFakePage()


@pytest.fixture
def page(fake_page):
    return Page(fake_page, Defaults())


# ---------------------------------------------------------------------------
# page.mouse property
# ---------------------------------------------------------------------------


class TestMouseProperty:
    def test_mouse_property_returns_mouse_object(self, page):
        from visus.web.api.input import Mouse

        assert isinstance(page.mouse, Mouse)

    def test_mouse_move_delegates(self, page, fake_page):
        page.mouse.move(10.0, 20.0)
        assert ("mouse_move", 10.0, 20.0) in fake_page.calls

    def test_mouse_down_delegates(self, page, fake_page):
        page.mouse.down()
        assert ("mouse_down",) in fake_page.calls

    def test_mouse_up_delegates(self, page, fake_page):
        page.mouse.up()
        assert ("mouse_up",) in fake_page.calls

    def test_mouse_click_delegates(self, page, fake_page):
        page.mouse.click(100.0, 200.0)
        assert ("mouse_click", 100.0, 200.0) in fake_page.calls

    def test_mouse_dblclick_delegates(self, page, fake_page):
        page.mouse.dblclick(50.0, 75.0)
        assert ("mouse_dblclick", 50.0, 75.0) in fake_page.calls

    def test_mouse_wheel_delegates(self, page, fake_page):
        page.mouse.wheel(0.0, 120.0)
        assert ("mouse_wheel", 0.0, 120.0) in fake_page.calls


# ---------------------------------------------------------------------------
# page.keyboard property
# ---------------------------------------------------------------------------


class TestKeyboardProperty:
    def test_keyboard_property_returns_keyboard_object(self, page):
        from visus.web.api.input import Keyboard

        assert isinstance(page.keyboard, Keyboard)

    def test_keyboard_down_delegates(self, page, fake_page):
        page.keyboard.down("Shift")
        assert ("keyboard_down", "Shift") in fake_page.calls

    def test_keyboard_up_delegates(self, page, fake_page):
        page.keyboard.up("Shift")
        assert ("keyboard_up", "Shift") in fake_page.calls

    def test_keyboard_press_delegates(self, page, fake_page):
        page.keyboard.press("Enter")
        assert ("keyboard_press", "Enter") in fake_page.calls

    def test_keyboard_type_delegates(self, page, fake_page):
        page.keyboard.type("hello world")
        assert ("keyboard_type", "hello world") in fake_page.calls

    def test_keyboard_insert_text_delegates(self, page, fake_page):
        page.keyboard.insert_text("pasted text")
        assert ("keyboard_insert_text", "pasted text") in fake_page.calls
