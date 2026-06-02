import os
from pathlib import Path

import pytest

from visus.web import Engine, launch


@pytest.mark.browser
def test_edge_ie_mode(base_url):
    os.environ["VISUS_WEB_IE_DRIVER"] = str(
        Path(__file__).resolve().parent.parent / "IEDriverServer.exe"
    )
    with launch(Engine.EDGE_IE, headless=False) as browser:  # IE-mode is always headed
        page = browser.new_page()
        page.goto(f"{base_url}/locators.html")
        assert page.get_by_role("heading", name="Dashboard").count() == 1
        assert page.locator(".greeting").text_content() == "Welcome back, Ada"
