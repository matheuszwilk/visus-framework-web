"""SeleniumBackend: owns the WebDriver process lifecycle."""

from __future__ import annotations

import atexit
import functools
import os
import shutil
import tempfile
import weakref
from collections.abc import Callable
from typing import cast

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

from visus.web.backends.base import BrowserConfig, ContextDelegate
from visus.web.backends.selenium.driver_delegate import (
    SeleniumContextDelegate,
    translate_exc,
)


def _cleanup(
    driver_ref: weakref.ref[WebDriver],
    profile_dir: str,
    download_dir: str,
    owns_profile: bool = True,
) -> None:
    """atexit safety net: quit a still-alive driver and remove its temp dirs.

    A user-supplied persistent profile (``owns_profile=False``) is never removed.
    """
    driver = driver_ref()
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass
    if owns_profile:
        shutil.rmtree(profile_dir, ignore_errors=True)
    shutil.rmtree(download_dir, ignore_errors=True)


def _spawn_driver(
    config: BrowserConfig,
    *,
    headless: bool,
    user_data_dir: str | None = None,
    remote_url: str | None = None,
) -> tuple[WebDriver, str, str, bool]:
    """Create a driver with a profile + download dir.

    The profile is a fresh temp dir unless *user_data_dir* names a persistent
    profile to reuse (created if missing, never deleted). With *remote_url*, the
    session is opened on a Selenium Grid / Remote WebDriver instead of spawning
    a local driver (download capture and profile paths are then remote-side).

    Returns (driver, profile_dir, download_dir, owns_profile).
    """
    owns_profile = user_data_dir is None
    if user_data_dir is not None:
        os.makedirs(user_data_dir, exist_ok=True)
        profile_dir = user_data_dir
    else:
        profile_dir = tempfile.mkdtemp(prefix="visus-web-")
    download_dir = tempfile.mkdtemp(prefix="visus-dl-")
    options = config.options_factory(
        headless=headless, download_dir=download_dir, user_data_dir=profile_dir
    )
    try:
        if remote_url is not None:
            driver = webdriver.Remote(command_executor=remote_url, options=options)  # type: ignore[arg-type]
        else:
            service = config.service_factory()
            driver = cast(WebDriver, config.driver_factory(options=options, service=service))
    except WebDriverException as exc:
        if owns_profile:
            shutil.rmtree(profile_dir, ignore_errors=True)
        shutil.rmtree(download_dir, ignore_errors=True)
        raise translate_exc(exc) from exc
    # Enable headless downloads for Chromium via CDP.
    try:
        driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": download_dir},
        )
    except Exception:
        pass  # Non-Chromium drivers don't support CDP; silently ignore.
    return driver, profile_dir, download_dir, owns_profile


class SeleniumBrowserDelegate:
    def __init__(
        self,
        driver: WebDriver,
        profile_dir: str,
        download_dir: str,
        *,
        config: BrowserConfig,
        headless: bool,
        owns_profile: bool = True,
        remote_url: str | None = None,
    ) -> None:
        self._driver = driver
        self._profile_dir = profile_dir
        self._download_dir = download_dir
        self._config = config
        self._headless = headless
        self._owns_profile = owns_profile
        self._remote_url = remote_url
        self._disposed = False
        self._contexts: list[SeleniumContextDelegate] = []
        # First context shares the launch driver (owns_driver=False).
        initial = driver.current_window_handle
        self._contexts.append(
            SeleniumContextDelegate(
                driver,
                first_handle=initial,
                download_dir=download_dir,
                owns_driver=False,
                profile_dir=None,
            )
        )
        # Register a per-instance atexit cleanup so it can be unregistered precisely
        # on dispose() (a bare _cleanup registration would be impossible to remove
        # selectively, leaking handlers across many launches).
        self._atexit_cleanup: Callable[[], None] = functools.partial(
            _cleanup, weakref.ref(driver), profile_dir, download_dir, owns_profile
        )
        atexit.register(self._atexit_cleanup)

    def new_context(self) -> ContextDelegate:
        # Extra contexts always use a fresh temp profile (a persistent
        # user_data_dir cannot be shared by two live browser processes) but do
        # follow the browser onto the same remote grid when one was used.
        driver, profile, dl, _owns = _spawn_driver(
            self._config, headless=self._headless, remote_url=self._remote_url
        )
        ctx = SeleniumContextDelegate(
            driver,
            first_handle=driver.current_window_handle,
            download_dir=dl,
            owns_driver=True,
            profile_dir=profile,
        )
        self._contexts.append(ctx)
        return ctx

    def contexts(self) -> list[ContextDelegate]:
        return cast(list[ContextDelegate], list(self._contexts))

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        atexit.unregister(self._atexit_cleanup)
        # Close all owning contexts (spawned drivers) first.
        for ctx in list(self._contexts):
            if ctx.owns_driver:
                ctx.close()
        # Then quit the root driver and clean root dirs.
        try:
            self._driver.quit()
        except Exception:
            pass
        if self._owns_profile:
            shutil.rmtree(self._profile_dir, ignore_errors=True)
        shutil.rmtree(self._download_dir, ignore_errors=True)


class SeleniumBackend:
    def launch(
        self,
        config: BrowserConfig,
        *,
        headless: bool,
        user_data_dir: str | None = None,
        remote_url: str | None = None,
    ) -> SeleniumBrowserDelegate:
        driver, profile_dir, download_dir, owns_profile = _spawn_driver(
            config, headless=headless, user_data_dir=user_data_dir, remote_url=remote_url
        )
        return SeleniumBrowserDelegate(
            driver,
            profile_dir,
            download_dir,
            config=config,
            headless=headless,
            owns_profile=owns_profile,
            remote_url=remote_url,
        )
