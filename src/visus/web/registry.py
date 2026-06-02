from __future__ import annotations

from visus.web.backends.base import BrowserConfig
from visus.web.backends.browsers import chrome
from visus.web.engine import Engine
from visus.web.errors import UnsupportedEngineError

_CONFIGS: dict[Engine, BrowserConfig] = {
    Engine.CHROME: BrowserConfig(
        engine=Engine.CHROME,
        options_factory=chrome.build_options,
        service_factory=chrome.build_service,
        driver_factory=chrome.build_driver,
    ),
}


def get_browser_config(engine: Engine) -> BrowserConfig:
    try:
        return _CONFIGS[engine]
    except KeyError as exc:
        raise UnsupportedEngineError(
            f"Engine {engine.value!r} is not implemented yet (S0 supports: "
            f"{[e.value for e in _CONFIGS]})"
        ) from exc
