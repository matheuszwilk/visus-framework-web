"""Edge IE-mode plug-in: drives Edge's Trident engine via the IE driver."""

from __future__ import annotations

import os
import threading

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.ie.options import Options
from selenium.webdriver.ie.service import Service

from visus.web.backends.browsers import _ie_preflight

_DEFAULT_EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
# webdriver.Ie hardcodes a 120 s client timeout with no override. A watchdog that kills the
# driver process lets us fail fast with a clear message instead of (apparently) hanging.
_LAUNCH_TIMEOUT = float(os.environ.get("VISUS_WEB_IE_TIMEOUT", "45"))
# IEDriverServer pin. The latest releases (4.8+, incl. the 4.14 that Selenium Manager picks
# by default) can no longer locate the IE-mode window in modern Edge and hang forever at
# "Finding window handle for IE Mode on Edge"; 4.0.0 still attaches. Verified on Edge 146.
_IE_DRIVER_VERSION = os.environ.get("VISUS_WEB_IE_DRIVER_VERSION", "4.0.0")


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
    # An explicit driver path always wins (e.g. air-gapped machines).
    path = os.environ.get("VISUS_WEB_IE_DRIVER") or _resolve_ie_driver(_IE_DRIVER_VERSION)
    return Service(executable_path=path) if path else Service()


def _resolve_ie_driver(version: str) -> str | None:
    """Resolve a pinned IEDriverServer version via Selenium Manager (downloads + caches it).

    Returns the driver path, or None to fall back to Selenium's default resolution (which
    picks the latest — broken on modern Edge; the launch watchdog then reports it cleanly).
    """
    try:
        from selenium.webdriver.common.selenium_manager import SeleniumManager

        result = SeleniumManager().binary_paths(
            ["--driver", "IEDriverServer", "--driver-version", version]
        )
        driver_path = result.get("driver_path")
        return str(driver_path) if driver_path else None
    except Exception:
        return None


def build_driver(*, options: Options, service: Service) -> webdriver.Ie:
    # Best-effort align Windows for IE mode (equalize the IE security zones; enable the Edge
    # policy if this process can write it). We do NOT pre-judge that IE mode is impossible —
    # without this the browser opens but never navigates, because session creation blocks
    # waiting for an IE-mode document that never appears.
    _ie_preflight.ensure()

    # webdriver.Ie hangs at NEW_SESSION when IE mode can't engage. A watchdog kills the
    # driver process after the timeout so we raise a clear, actionable error instead of
    # (apparently) hanging — never freezing on the caller's side.
    timed_out = threading.Event()

    def _kill() -> None:
        timed_out.set()
        try:
            service.stop()  # terminates IEDriverServer; unblocks a stuck NEW_SESSION
        except Exception:
            pass

    watchdog = threading.Timer(_LAUNCH_TIMEOUT, _kill)
    watchdog.daemon = True
    watchdog.start()
    try:
        return webdriver.Ie(options=options, service=service)
    except Exception as exc:
        if timed_out.is_set():
            message = f"Edge IE mode did not start within {_LAUNCH_TIMEOUT:.0f}s."
            if not _ie_preflight.ie_mode_enabled():
                message += " " + _ie_preflight.admin_hint()
            else:
                # Policy is ON: Edge opens in IE mode, but IEDriverServer couldn't attach
                # to the IE-mode window. Usually a leftover Edge instance — or, on recent
                # Edge, the abandoned IE driver can no longer locate the IE-mode window.
                message += (
                    " IE mode is enabled, but the IE driver couldn't attach to the IE-mode"
                    " window. Close ALL Edge windows and retry. If it persists, this Edge"
                    " version is too new for IEDriverServer (IE-mode automation is being"
                    " retired) — use a Chromium engine (edge/chrome) instead."
                )
            raise TimeoutException(message) from exc
        raise
    finally:
        watchdog.cancel()
