"""Edge IE-mode plug-in: drives Edge's Trident engine via the IE driver."""

from __future__ import annotations

import os

from selenium import webdriver
from selenium.webdriver.ie.options import Options
from selenium.webdriver.ie.service import Service

_DEFAULT_EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def build_options(*, headless: bool, download_dir: str, user_data_dir: str) -> Options:
    # IE-mode is always headed; headless/download_dir/user_data_dir do not apply.
    opts = Options()
    opts.attach_to_edge_chrome = True
    opts.edge_executable_path = os.environ.get("VISUS_WEB_EDGE_BINARY", _DEFAULT_EDGE)
    opts.ignore_zoom_level = True
    opts.ignore_protected_mode_settings = True
    opts.require_window_focus = False
    return opts


def build_service() -> Service:
    path = os.environ.get("VISUS_WEB_IE_DRIVER")
    return Service(executable_path=path) if path else Service()


def build_driver(*, options: Options, service: Service) -> webdriver.Ie:
    return webdriver.Ie(options=options, service=service)
