import os
from pathlib import Path

import pytest

from visus.web import Engine, launch


@pytest.mark.browser
@pytest.mark.timeout(180)  # IE-mode cold start (zone setup + driver attach) can exceed 60s
def test_edge_ie_mode(base_url):
    # IE-mode automation only works with IEDriverServer 4.0.0 — 4.8+ (incl. the
    # 4.14 Selenium Manager picks by default) hang forever at "Finding window
    # handle for IE Mode on Edge" (see backends/browsers/edge_ie.py).
    #
    # IE-mode also opens a real HEADED Edge window and is focus/zone sensitive:
    # under a parallel (xdist) run it reliably hangs the worker mid-session, in
    # a way neither the launch watchdog nor pytest-timeout can interrupt — even
    # with the correct 4.0.0 driver. Run it standalone instead:
    #   pytest tests/test_e2e_edge_ie.py -n 0
    if os.environ.get("PYTEST_XDIST_WORKER"):
        pytest.skip("IE-mode e2e is excluded from parallel runs; run it standalone with -n 0")
    local = Path(__file__).resolve().parent.parent / "IEDriverServer.exe"
    if local.is_file():
        # a manually-provisioned repo-root binary wins (air-gapped machines)
        os.environ["VISUS_WEB_IE_DRIVER"] = str(local)
    else:
        # let edge_ie.py resolve the PINNED 4.0.0 via Selenium Manager — never
        # point at a non-existent file, and never let the latest (broken) win
        os.environ.pop("VISUS_WEB_IE_DRIVER", None)
    with launch(Engine.EDGE_IE, headless=False) as browser:  # IE-mode is always headed
        page = browser.new_page()
        page.goto(f"{base_url}/locators.html")
        assert page.get_by_role("heading", name="Dashboard").count() == 1
        assert page.locator(".greeting").text_content() == "Welcome back, Ada"
