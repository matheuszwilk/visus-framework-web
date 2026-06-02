"""Real-browser E2E test for page.expect_download()."""

import os

import pytest


@pytest.mark.browser
def test_expect_download(browser, base_url, tmp_path):
    page = browser.new_page()
    page.goto(f"{base_url}/downloads.html")
    with page.expect_download() as info:
        page.locator("#dl").click()
    dl = info.value
    assert dl.suggested_filename == "download.txt"
    assert os.path.exists(dl.path)
    out = tmp_path / "saved.txt"
    dl.save_as(str(out))
    assert out.read_text().strip() == "hello download"
