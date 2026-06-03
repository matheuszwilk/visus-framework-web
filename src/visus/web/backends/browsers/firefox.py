"""Firefox plug-in: assembles Selenium options/service. Selenium Manager resolves geckodriver."""

from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

_MIMES = "application/octet-stream,text/plain,application/pdf,application/zip,image/png,text/csv"


def build_options(*, headless: bool, download_dir: str, user_data_dir: str) -> Options:
    opts = Options()
    if headless:
        opts.add_argument("-headless")
    opts.set_preference("browser.download.folderList", 2)
    opts.set_preference("browser.download.dir", download_dir)
    opts.set_preference("browser.download.useDownloadDir", True)
    opts.set_preference("browser.helperApps.neverAskSaveToDisk", _MIMES)
    opts.set_preference("pdfjs.disabled", True)
    return opts


def build_service() -> Service:
    # No executable_path: Selenium Manager (selenium>=4.6) downloads/resolves geckodriver.
    return Service()


def build_driver(*, options: Options, service: Service) -> webdriver.Firefox:
    return webdriver.Firefox(options=options, service=service)
