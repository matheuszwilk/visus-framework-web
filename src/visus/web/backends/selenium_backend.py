"""SeleniumBackend: owns the WebDriver process lifecycle."""

from __future__ import annotations

import atexit
import shutil
import tempfile
import weakref

from selenium.common.exceptions import WebDriverException

from visus.web.backends.base import BrowserConfig
from visus.web.backends.selenium.driver_delegate import (
    SeleniumContextDelegate,
    translate_exc,
)


def _cleanup(driver_ref: "weakref.ref[object]", profile_dir: str) -> None:
    driver = driver_ref()
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass
    shutil.rmtree(profile_dir, ignore_errors=True)


class SeleniumBrowserDelegate:
    def __init__(self, driver: object, profile_dir: str) -> None:
        self._driver = driver
        self._profile_dir = profile_dir
        self._contexts: list[SeleniumContextDelegate] = []
        # First context adopts the driver's initial window handle.
        initial = driver.current_window_handle
        self._contexts.append(SeleniumContextDelegate(driver, first_handle=initial))
        atexit.register(_cleanup, weakref.ref(driver), profile_dir)

    def new_context(self) -> SeleniumContextDelegate:
        ctx = SeleniumContextDelegate(self._driver)
        # A context needs at least one window; open one immediately.
        ctx.new_page()
        self._contexts.append(ctx)
        return ctx

    def contexts(self) -> list[SeleniumContextDelegate]:
        return list(self._contexts)

    def dispose(self) -> None:
        try:
            self._driver.quit()
        except WebDriverException:
            pass
        shutil.rmtree(self._profile_dir, ignore_errors=True)


class SeleniumBackend:
    def launch(self, config: BrowserConfig, *, headless: bool) -> SeleniumBrowserDelegate:
        profile_dir = tempfile.mkdtemp(prefix="visus-web-")
        download_dir = tempfile.mkdtemp(prefix="visus-dl-")
        options = config.options_factory(
            headless=headless, download_dir=download_dir, user_data_dir=profile_dir
        )
        service = config.service_factory()
        try:
            driver = config.driver_factory(options=options, service=service)
        except WebDriverException as exc:
            shutil.rmtree(profile_dir, ignore_errors=True)
            raise translate_exc(exc) from exc
        return SeleniumBrowserDelegate(driver, profile_dir)
