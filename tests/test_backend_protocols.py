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
    def current_url(self): return ""
    def title(self): return ""
    def content(self): return ""
    def reload(self, *, timeout_ms): ...
    def go_back(self, *, timeout_ms): ...
    def go_forward(self, *, timeout_ms): ...
    def close(self): ...
    def is_closed(self): return False


def test_structural_conformance():
    assert isinstance(_FakePage(), PageDelegate)


def test_non_conformer_is_rejected():
    class NotAPage:
        pass
    assert not isinstance(NotAPage(), PageDelegate)


def test_browser_config_is_frozen_dataclass():
    cfg = BrowserConfig(
        engine=Engine.CHROME,
        options_factory=lambda **k: None,
        service_factory=lambda **k: None,
        driver_factory=lambda **k: None,
    )
    assert cfg.engine is Engine.CHROME
