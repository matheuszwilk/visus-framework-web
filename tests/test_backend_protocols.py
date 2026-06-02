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
    def locator_input_value(self, selector):
        return ""


class _FakeContext:
    def new_page(self):
        return _FakePage()

    def pages(self):
        return []

    def close(self): ...


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
