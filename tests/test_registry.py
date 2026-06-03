import pytest

from visus.web.engine import Engine
from visus.web.errors import UnsupportedEngineError
from visus.web.registry import get_browser_config


def test_chrome_config_present():
    cfg = get_browser_config(Engine.CHROME)
    assert cfg.engine is Engine.CHROME
    assert callable(cfg.options_factory)
    assert callable(cfg.driver_factory)


def test_firefox_config_present():
    """Firefox is now a registered engine (plug-in added in cross-browser slice)."""
    cfg = get_browser_config(Engine.FIREFOX)
    assert cfg.engine is Engine.FIREFOX
    assert callable(cfg.options_factory)
    assert callable(cfg.driver_factory)


def test_unknown_engine_raises():
    """Passing a raw string that is not a valid Engine value should raise."""
    with pytest.raises((UnsupportedEngineError, ValueError)):
        Engine.from_str("netscape")
