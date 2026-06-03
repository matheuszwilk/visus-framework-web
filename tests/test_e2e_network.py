"""Real-browser E2E tests for Chromium CDP network controls."""

from __future__ import annotations

import json

import pytest


@pytest.mark.browser
def test_block_urls(browser, base_url):
    """block_urls causes a blocked fetch to put 'blocked' in the result div."""
    from visus.web import expect

    page = browser.new_page()
    page.block_urls(["*forms.html*"])
    page.goto(f"{base_url}/network.html")
    # The fetch to /forms.html should be blocked; JS sets #r to 'blocked'.
    expect(page.locator("#r")).to_have_text("blocked")


@pytest.mark.browser
def test_extra_http_headers(browser, base_url):
    """set_extra_http_headers injects a custom header visible on the server."""
    page = browser.new_page()
    page.set_extra_http_headers({"X-Visus": "hello"})
    page.goto(f"{base_url}/echo-headers")
    body = page.evaluate("() => document.body.innerText")
    headers = json.loads(str(body))
    # Header names may be lowercased by the browser or server.
    assert headers.get("X-Visus") == "hello" or headers.get("x-visus") == "hello"


@pytest.mark.browser
def test_set_offline(browser, base_url):
    """set_offline(True) makes navigator.onLine return False."""
    page = browser.new_page()
    page.goto(f"{base_url}/forms.html")
    page.set_offline(True)
    online = page.evaluate("() => navigator.onLine")
    assert online is False
    # Restore connectivity so subsequent test cleanup doesn't hang.
    page.set_offline(False)
