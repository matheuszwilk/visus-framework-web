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


@pytest.mark.browser
def test_network_requests_capture(browser, base_url):
    page = browser.new_page()
    page.goto(f"{base_url}/network.html")
    page.wait_for_function("() => document.getElementById('r').textContent !== 'pending'")
    reqs = page.network_requests()
    urls = [r.url for r in reqs]
    assert any(u.endswith("/network.html") for u in urls)
    assert any(u.endswith("/forms.html") for u in urls)  # the in-page fetch
    doc = next(r for r in reqs if r.url.endswith("/network.html"))
    assert doc.status == 200 and doc.ok


@pytest.mark.browser
def test_wait_for_response_and_body(browser, base_url):
    from visus.web import errors

    page = browser.new_page()
    page.goto(f"{base_url}/network.html")
    resp = page.wait_for_response("*forms.html")
    assert resp.status == 200
    assert "Username" in resp.body()
    with pytest.raises(errors.VisusTimeoutError):
        page.wait_for_response("*never-fetched*", timeout=600)


@pytest.mark.browser
def test_expect_response_around_action(browser, base_url):
    page = browser.new_page()
    page.goto(f"{base_url}/forms.html")
    with page.expect_response("*page2*") as info:
        page.evaluate("() => fetch('/page2.html')")
    assert info.value.status == 200


@pytest.mark.browser
def test_console_messages_capture(browser, base_url):
    page = browser.new_page()
    page.goto(f"{base_url}/forms.html")
    page.evaluate("() => console.error('boom-from-test')")
    msgs = page.console_messages()
    assert any("boom-from-test" in m.text for m in msgs)
    assert any(m.level == "SEVERE" for m in msgs)


@pytest.mark.browser
def test_add_init_script(browser, base_url):
    page = browser.new_page()
    page.add_init_script("window.__seeded = 42;")
    page.goto(f"{base_url}/forms.html")
    assert page.evaluate("() => window.__seeded") == 42


@pytest.mark.browser
def test_viewport_and_device_metrics_and_geolocation(browser, base_url):
    page = browser.new_page()
    page.goto(f"{base_url}/forms.html")
    page.set_viewport_size(800, 600)
    assert page.evaluate("() => window.innerWidth") == 800
    # mobile=False: a page without a <meta viewport> would lay out at 980px on mobile
    page.set_device_metrics(390, 844, device_scale_factor=3.0, mobile=False)
    assert page.evaluate("() => window.innerWidth") == 390
    assert page.evaluate("() => window.devicePixelRatio") == 3
    page.grant_permissions(["geolocation"], origin=base_url)
    page.set_geolocation(-23.55, -46.63)
    coords = page.evaluate(
        "() => new Promise(res => navigator.geolocation.getCurrentPosition("
        "p => res([p.coords.latitude, p.coords.longitude]), e => res(['err', e.code])))"
    )
    assert coords == [-23.55, -46.63]

