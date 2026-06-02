from dataclasses import FrozenInstanceError

import pytest

from visus.web.backends.base import (
    Backend,
    BrowserConfig,
    BrowserDelegate,
    ContextDelegate,
    PageDelegate,
)
from visus.web.engine import Engine


class _FakePage:
    def goto(self, url, *, wait_until, timeout_ms): ...
    def current_url(self):
        return ""

    def title(self):
        return ""

    def content(self):
        return ""

    def reload(self, *, timeout_ms): ...
    def go_back(self, *, timeout_ms): ...
    def go_forward(self, *, timeout_ms): ...
    def close(self): ...
    def is_closed(self):
        return False

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
        return _FakePage()

    def handle_next_dialog(self, *, accept, prompt_text, timeout_ms):
        return ("", "dialog")


class _FakeContext:
    def new_page(self):
        return _FakePage()

    def pages(self):
        return []

    def close(self): ...
    def cookies(self):
        return []

    def add_cookies(self, cookies): ...
    def clear_cookies(self): ...


class _FakeBrowser:
    def new_context(self):
        return _FakeContext()

    def contexts(self):
        return []

    def dispose(self): ...


class _FakeBackend:
    def launch(self, config, *, headless):
        return _FakeBrowser()


class _NotAnything:
    pass


def test_page_delegate_conformance():
    assert isinstance(_FakePage(), PageDelegate)
    assert not isinstance(_NotAnything(), PageDelegate)


def test_context_delegate_conformance():
    assert isinstance(_FakeContext(), ContextDelegate)
    assert not isinstance(_NotAnything(), ContextDelegate)


def test_browser_delegate_conformance():
    assert isinstance(_FakeBrowser(), BrowserDelegate)
    assert not isinstance(_NotAnything(), BrowserDelegate)


def test_backend_conformance():
    assert isinstance(_FakeBackend(), Backend)
    assert not isinstance(_NotAnything(), Backend)


def test_browser_config_holds_fields():
    cfg = BrowserConfig(
        engine=Engine.CHROME,
        options_factory=lambda **k: None,
        service_factory=lambda **k: None,
        driver_factory=lambda **k: None,
    )
    assert cfg.engine is Engine.CHROME


def test_browser_config_is_frozen():
    cfg = BrowserConfig(
        engine=Engine.CHROME,
        options_factory=lambda **k: None,
        service_factory=lambda **k: None,
        driver_factory=lambda **k: None,
    )
    with pytest.raises(FrozenInstanceError):
        cfg.engine = Engine.FIREFOX  # type: ignore[misc]
