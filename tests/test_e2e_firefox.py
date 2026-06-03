"""Real end-to-end tests for the Firefox engine.

Firefox is supported by the architecture (the `firefox.py` plug-in + `Engine.FIREFOX`),
but these tests only run when Firefox is actually installed (geckodriver is fetched by
Selenium Manager). When Firefox is absent they are skipped — not faked — so the suite
stays green, and they exercise the REAL browser the moment Firefox is installed.

To run them: install Firefox, then `uv run pytest tests/test_e2e_firefox.py -m browser`.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from visus.web import Engine, expect, launch


def _firefox_available() -> bool:
    if shutil.which("firefox"):
        return True
    candidates = [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        "/usr/bin/firefox",
        "/usr/local/bin/firefox",
        "/Applications/Firefox.app/Contents/MacOS/firefox",
    ]
    return any(Path(c).exists() for c in candidates)


requires_firefox = pytest.mark.skipif(
    not _firefox_available(), reason="Firefox is not installed in this environment"
)


@pytest.mark.browser
@requires_firefox
def test_firefox_core_flow(base_url):
    """Locators + auto-wait + expect() drive a real Firefox."""
    with launch(Engine.FIREFOX, headless=True) as browser:
        page = browser.new_page()
        page.goto(f"{base_url}/locators.html")
        assert page.get_by_role("heading", name="Dashboard").count() == 1
        assert page.get_by_role("link").count() == 2
        page.get_by_role("button", name="Sign in").click()  # auto-wait works on Firefox
        expect(page.get_by_text("Welcome back")).to_be_visible()


@pytest.mark.browser
@requires_firefox
def test_firefox_fill_and_assert(base_url):
    with launch(Engine.FIREFOX, headless=True) as browser:
        page = browser.new_page()
        page.goto(f"{base_url}/forms.html")
        page.get_by_label("Username").fill("ada-firefox")
        expect(page.get_by_label("Username")).to_have_value("ada-firefox")


@pytest.mark.browser
@requires_firefox
def test_firefox_pdf_via_print_page(base_url):
    """pdf() uses the W3C print_page endpoint — native on Firefox (no CDP)."""
    with launch(Engine.FIREFOX, headless=True) as browser:
        page = browser.new_page()
        page.goto(f"{base_url}/forms.html")
        assert page.pdf()[:5] == b"%PDF-"


@pytest.mark.browser
@requires_firefox
def test_firefox_full_page_screenshot_native(base_url):
    """full_page screenshot falls back to Firefox-native get_full_page_screenshot_as_png."""
    with launch(Engine.FIREFOX, headless=True) as browser:
        page = browser.new_page()
        page.goto(f"{base_url}/forms.html")
        data = page.screenshot(full_page=True)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.browser
@requires_firefox
def test_firefox_download_via_prefs(base_url, tmp_path):
    """Downloads work on Firefox via the browser.download.* prefs (no CDP)."""
    with launch(Engine.FIREFOX, headless=True) as browser:
        page = browser.new_page()
        page.goto(f"{base_url}/downloads.html")
        with page.expect_download() as info:
            page.locator("#dl").click()
        download = info.value
        assert download.suggested_filename == "download.txt"
        assert os.path.exists(download.path)
        out = tmp_path / "saved.txt"
        download.save_as(str(out))
        assert out.read_text().strip() == "hello download"


@pytest.mark.browser
@requires_firefox
def test_firefox_frames(base_url):
    with launch(Engine.FIREFOX, headless=True) as browser:
        page = browser.new_page()
        page.goto(f"{base_url}/frames.html")
        page.frame_locator("#f1").locator("#btn").click()
        assert page.frame_locator("#f1").locator("#res").text_content() == "clicked"
