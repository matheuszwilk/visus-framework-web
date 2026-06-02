from __future__ import annotations

from visus.web.backends.base import BrowserConfig
from visus.web.backends.browsers import chrome, edge, edge_ie
from visus.web.engine import Engine
from visus.web.errors import UnsupportedEngineError

_CONFIGS: dict[Engine, BrowserConfig] = {
    Engine.CHROME: BrowserConfig(
        engine=Engine.CHROME,
        options_factory=chrome.build_options,
        service_factory=chrome.build_service,
        driver_factory=chrome.build_driver,
    ),
    Engine.EDGE: BrowserConfig(
        engine=Engine.EDGE,
        options_factory=edge.build_options,
        service_factory=edge.build_service,
        driver_factory=edge.build_driver,
    ),
    Engine.EDGE_IE: BrowserConfig(
        engine=Engine.EDGE_IE,
        options_factory=edge_ie.build_options,
        service_factory=edge_ie.build_service,
        driver_factory=edge_ie.build_driver,
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
