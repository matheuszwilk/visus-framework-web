from __future__ import annotations

import json

import pytest

from visus.web.network import NetworkCapture, scrub_headers


def test_scrub_headers_redacts_secrets():
    h = {"Authorization": "Bearer abc", "Cookie": "s=1", "Content-Type": "application/json"}
    out = scrub_headers(h)
    assert out["Authorization"] == "REDACTED"
    assert out["Cookie"] == "REDACTED"
    assert out["Content-Type"] == "application/json"


def test_scrub_headers_redacts_pattern_headers():
    h = {
        "X-Custom-Token": "t",
        "X-Service-Secret": "s",
        "X-Api-Key": "k",
        "X-Auth-Token": "a",
        "X-Session-Id": "sid",
        "Accept": "application/json",
    }
    out = scrub_headers(h)
    assert out["X-Custom-Token"] == "REDACTED"
    assert out["X-Service-Secret"] == "REDACTED"
    assert out["X-Api-Key"] == "REDACTED"
    assert out["X-Auth-Token"] == "REDACTED"
    assert out["X-Session-Id"] == "REDACTED"
    assert out["Accept"] == "application/json"


class FakePage:
    """Stub page: returns a canned JSON capture from .evaluate, no real browser."""

    url = "https://x/"

    def __init__(self):
        self._store = []

    def evaluate(self, expr, arg=None):
        if "window.__vcm_capture" in expr and "JSON.stringify" in expr:
            return (
                '[{"url":"https://x/api/items","method":"GET","status":200,'
                '"reqBody":null,"respBody":"[]","headers":{"Authorization":"Bearer z"}}]'
            )
        return None


def test_fallback_get_requests_scrubs():
    cap = NetworkCapture(FakePage(), use_cdp=False)
    cap.start()
    reqs = cap.get_requests(filter_type=["xhr", "fetch"])
    assert reqs[0]["url"].endswith("/api/items")
    assert reqs[0]["headers"]["Authorization"] == "REDACTED"


def test_export_enriched_writes_appendix_b_shape(tmp_path):
    cap = NetworkCapture(FakePage(), use_cdp=False)
    cap.start()
    out = tmp_path / "capture.json"
    cap.export_enriched(str(out))
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["target_url"] == "https://x/"
    assert doc["entries"][0]["url"].endswith("/api/items")
    assert doc["entries"][0]["headers"]["Authorization"] == "REDACTED"


def test_get_requests_empty_capture_returns_empty_list():
    class EmptyPage:
        url = "https://x/"

        def evaluate(self, expr, arg=None):
            if "window.__vcm_capture" in expr and "JSON.stringify" in expr:
                return "[]"
            return None

    cap = NetworkCapture(EmptyPage(), use_cdp=False)
    cap.start()
    assert cap.get_requests() == []


def test_cdp_path_falls_back_silently_when_no_driver():
    # use_cdp=True but FakePage has no _delegate/_driver — must not raise.
    cap = NetworkCapture(FakePage(), use_cdp=True)
    cap.start()
    assert cap._cdp_active is False
    reqs = cap.get_requests()
    assert reqs[0]["headers"]["Authorization"] == "REDACTED"
    cap.stop()


def test_cdp_path_enabled_when_driver_supports_it():
    class FakeDriver:
        def __init__(self):
            self.calls = []

        def execute_cdp_cmd(self, cmd, params):
            self.calls.append(cmd)
            return {}

    class FakeDelegate:
        def __init__(self, driver):
            self._driver = driver

    class CdpPage:
        url = "https://x/"

        def __init__(self, driver):
            self._delegate = FakeDelegate(driver)

        def evaluate(self, expr, arg=None):
            if "window.__vcm_capture" in expr and "JSON.stringify" in expr:
                return "[]"
            return None

    driver = FakeDriver()
    cap = NetworkCapture(CdpPage(driver), use_cdp=True)
    cap.start()
    assert cap._cdp_active is True
    assert "Network.enable" in driver.calls
    cap.stop()
    assert "Network.disable" in driver.calls


@pytest.mark.browser
def test_network_capture_real_browser_fetch(tmp_path):
    """Integration: launch headless Chrome, fire a fetch, assert capture + scrub."""
    from visus.web import launch

    html = (
        "data:text/html,"
        "<html><body><button id='go' onclick=\"fetch('https://httpbin.org/get')\">go</button>"
        "</body></html>"
    )
    with launch(headless=True) as browser:
        page = browser.new_page()
        page.goto(html)
        cap = NetworkCapture(page)
        cap.start()  # install BEFORE interaction
        page.locator("#go").click()
        # let the fetch resolve
        page.evaluate("() => new Promise(r => setTimeout(r, 1500))")
        reqs = cap.get_requests(filter_type=["xhr", "fetch"])
        assert any("httpbin.org/get" in r["url"] for r in reqs)
        for r in reqs:
            auth = r["headers"].get("Authorization")
            assert auth is None or auth == "REDACTED"
        cap.stop()
