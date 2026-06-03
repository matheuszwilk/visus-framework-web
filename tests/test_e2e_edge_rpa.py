"""Real-browser E2E tests proving pdf/screenshot/download work on Microsoft Edge."""

from __future__ import annotations

import os

import pytest

from visus.web import Engine, launch


@pytest.mark.browser
def test_edge_pdf_and_fullpage_screenshot(base_url):
    with launch(Engine.EDGE, headless=True) as browser:
        page = browser.new_page()
        page.goto(f"{base_url}/forms.html")
        assert page.pdf()[:5] == b"%PDF-"
        assert page.screenshot(full_page=True)[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.browser
def test_edge_download(base_url, tmp_path):
    with launch(Engine.EDGE, headless=True) as browser:
        page = browser.new_page()
        page.goto(f"{base_url}/downloads.html")
        with page.expect_download() as info:
            page.locator("#dl").click()
        assert info.value.suggested_filename == "download.txt"
        assert os.path.exists(info.value.path)
