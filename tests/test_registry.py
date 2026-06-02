import pytest
from visus.web.engine import Engine
from visus.web.errors import UnsupportedEngineError
from visus.web.registry import get_browser_config


def test_chrome_config_present():
    cfg = get_browser_config(Engine.CHROME)
    assert cfg.engine is Engine.CHROME
    assert callable(cfg.options_factory)
    assert callable(cfg.driver_factory)


def test_unimplemented_engine_raises():
    with pytest.raises(UnsupportedEngineError, match="firefox"):
        get_browser_config(Engine.FIREFOX)
