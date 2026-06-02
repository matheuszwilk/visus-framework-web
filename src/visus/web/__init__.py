"""visus.web — Playwright-style web automation on a Selenium engine."""

from __future__ import annotations

from visus.web import errors
from visus.web.api.assertions import expect
from visus.web.api.browser import Browser
from visus.web.api.context import Context
from visus.web.api.page import Page
from visus.web.backends.selenium_backend import SeleniumBackend
from visus.web.config import Defaults
from visus.web.engine import Engine
from visus.web.registry import get_browser_config

__version__ = "0.0.1"

__all__ = [
    "launch",
    "expect",
    "Engine",
    "Browser",
    "Context",
    "Page",
    "errors",
]


def launch(engine: Engine | str = Engine.CHROME, *, headless: bool = False) -> Browser:
    """Launch a browser and return a Browser handle.

    Usage:
        with launch(headless=True) as browser:
            page = browser.new_page()
            page.goto("https://example.com")
    """
    resolved = Engine.from_str(engine)
    config = get_browser_config(resolved)
    backend = SeleniumBackend()
    delegate = backend.launch(config, headless=headless)
    return Browser(delegate, Defaults())
