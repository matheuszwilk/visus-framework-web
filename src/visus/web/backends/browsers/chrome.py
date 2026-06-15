"""Chrome plug-in: assembles Selenium options/service. Selenium Manager resolves the driver."""

from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def build_options(*, headless: bool, download_dir: str, user_data_dir: str) -> Options:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument(f"--user-data-dir={user_data_dir}")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-gpu")
    opts.add_experimental_option(
        "prefs",
        {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
        },
    )
    # Performance log feeds page.network_requests(); browser log feeds
    # page.console_messages(). Negligible overhead when never drained.
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL", "browser": "ALL"})
    # perfLoggingPrefs enables CDP Network.* events (requestWillBeSent/
    # responseReceived/loadingFinished) so NetworkCapture(use_cdp=True) captures
    # JSONP <script>, sendBeacon, images and document navigations beyond the
    # fetch/XHR JS hook. Must be set at session creation — cannot be turned on later.
    opts.add_experimental_option(
        "perfLoggingPrefs",
        {"enableNetwork": True, "enablePage": False},
    )
    return opts


def build_service() -> Service:
    # No executable_path: Selenium Manager (selenium>=4.6) downloads/resolves chromedriver.
    return Service()


def build_driver(*, options: Options, service: Service) -> webdriver.Chrome:
    return webdriver.Chrome(options=options, service=service)
