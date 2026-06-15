"""CDP-path tests for NetworkCapture.

These pin the contract that ``use_cdp=True`` actually *consumes* CDP Network
events (drained from Chrome's performance log) and merges them with the JS
fetch/XHR hook — so JSONP ``<script>``, ``sendBeacon``, images and document
navigations (all invisible to the fetch/XHR patch) are captured.
"""

from __future__ import annotations

import json

import pytest
from selenium.common.exceptions import WebDriverException

from visus.web.network import NetworkCapture


def _perf(method: str, params: dict) -> dict:
    """Build one Chrome performance-log entry wrapping a CDP message."""
    return {"message": json.dumps({"message": {"method": method, "params": params}})}


class _PerfDriver:
    """Fake Selenium driver: CDP enable + performance-log draining + getResponseBody.

    ``log_batches`` is a list of batches; each ``get_log('performance')`` call
    pops the next batch (mirroring Selenium, where get_log drains the buffer).
    """

    def __init__(
        self,
        log_batches: list[list[dict]],
        bodies: dict[str, str] | None = None,
        b64_bodies: dict[str, str] | None = None,
    ) -> None:
        self._batches = [list(b) for b in log_batches]
        self._bodies = bodies or {}
        self._b64 = b64_bodies or {}
        self.calls: list[str] = []
        self.body_requests: list[str] = []

    def execute_cdp_cmd(self, cmd: str, params: dict) -> dict:
        self.calls.append(cmd)
        if cmd == "Network.getResponseBody":
            rid = params["requestId"]
            self.body_requests.append(rid)
            if rid in self._bodies:
                return {"body": self._bodies[rid], "base64Encoded": False}
            if rid in self._b64:
                return {"body": self._b64[rid], "base64Encoded": True}
            raise WebDriverException("No data found for resource with given identifier")
        return {}

    def get_log(self, kind: str) -> list[dict]:
        assert kind == "performance"
        return self._batches.pop(0) if self._batches else []


class _CdpPage:
    """Stub page exposing ``_delegate._driver`` and a canned JS hook buffer."""

    url = "https://site/"

    def __init__(self, driver: object, js_capture: str = "[]") -> None:
        self._delegate = type("D", (), {"_driver": driver})()
        self._js_capture = js_capture

    def evaluate(self, expr: str, arg: object = None) -> object:
        if "window.__vcm_capture" in expr and "JSON.stringify" in expr:
            return self._js_capture
        return None


def _req(
    rid: str, url: str, *, rtype: str, method: str = "GET", headers: dict | None = None
) -> dict:
    request = {"url": url, "method": method, "headers": headers or {}}
    return _perf(
        "Network.requestWillBeSent",
        {"requestId": rid, "type": rtype, "request": request},
    )


def _resp(rid: str, *, status: int, rtype: str, mime: str, headers: dict | None = None) -> dict:
    response = {"status": status, "mimeType": mime, "headers": headers or {}}
    return _perf(
        "Network.responseReceived",
        {"requestId": rid, "type": rtype, "response": response},
    )


def _done(rid: str) -> dict:
    return _perf("Network.loadingFinished", {"requestId": rid})


def _hook_json(url: str, *, resp_body: str | None = None) -> str:
    """A canned JS-hook ``window.__vcm_capture`` buffer with one GET entry."""
    entry = {
        "url": url, "method": "GET", "status": 200,
        "reqBody": None, "respBody": resp_body, "headers": {},
    }
    return json.dumps([entry])


# --------------------------------------------------------------------------- #
# CDP draining + correlation
# --------------------------------------------------------------------------- #


def test_cdp_captures_jsonp_script_request_invisible_to_fetch_hook():
    url = "https://solr.example/opensearch/suggest/?q=test"
    batch = [
        _req("R1", url, rtype="Script", headers={"Cookie": "sess=secret"}),
        _resp("R1", status=200, rtype="Script", mime="application/javascript"),
        _done("R1"),
    ]
    driver = _PerfDriver([batch], bodies={"R1": "suggest_cb(['a','b'])"})
    cap = NetworkCapture(_CdpPage(driver, js_capture="[]"), use_cdp=True)
    cap.start()
    reqs = cap.get_requests()

    assert len(reqs) == 1
    e = reqs[0]
    assert e["url"] == url
    assert e["method"] == "GET"
    assert e["status"] == 200
    assert e["resourceType"].lower() == "script"
    assert e["source"] == "cdp"
    assert e["headers"]["Cookie"] == "REDACTED"  # request headers scrubbed
    assert "suggest_cb" in (e["respBody"] or "")


def test_cdp_entry_merges_and_dedupes_with_js_hook_entry():
    url = "https://site/api/items"
    js = _hook_json(url, resp_body="[1,2]")
    batch = [
        _req("R1", url, rtype="XHR", headers={"Authorization": "Bearer tok"}),
        _resp("R1", status=200, rtype="XHR", mime="application/json"),
        _done("R1"),
    ]
    driver = _PerfDriver([batch], bodies={"R1": "[1,2]"})
    cap = NetworkCapture(_CdpPage(driver, js_capture=js), use_cdp=True)
    cap.start()
    reqs = cap.get_requests()

    assert len(reqs) == 1  # deduped on (method, url)
    e = reqs[0]
    assert e["respBody"] == "[1,2]"  # JS hook body retained
    assert e["resourceType"].lower() == "xhr"  # type filled from CDP
    assert e["headers"]["Authorization"] == "REDACTED"  # request auth surfaced + scrubbed


def test_filter_type_filters_by_cdp_resource_type():
    doc = "https://site/page"
    scr = "https://cdn/jsonp.js?q=x"
    batch = [
        _req("D", doc, rtype="Document"),
        _resp("D", status=200, rtype="Document", mime="text/html"),
        _done("D"),
        _req("S", scr, rtype="Script"),
        _resp("S", status=200, rtype="Script", mime="application/javascript"),
        _done("S"),
    ]
    driver = _PerfDriver([batch], bodies={})
    cap = NetworkCapture(_CdpPage(driver, js_capture="[]"), use_cdp=True)
    cap.start()

    only_script = cap.get_requests(filter_type=["script"])
    assert [e["url"] for e in only_script] == [scr]

    both = cap.get_requests()
    assert {e["url"] for e in both} == {doc, scr}


def test_cdp_drain_accumulates_across_multiple_get_requests_calls():
    u1, u2 = "https://site/a", "https://site/b"
    b1 = [
        _req("R1", u1, rtype="XHR"),
        _resp("R1", status=200, rtype="XHR", mime="text/json"),
        _done("R1"),
    ]
    b2 = [
        _req("R2", u2, rtype="XHR"),
        _resp("R2", status=200, rtype="XHR", mime="text/json"),
        _done("R2"),
    ]
    driver = _PerfDriver([b1, b2], bodies={})
    cap = NetworkCapture(_CdpPage(driver, js_capture="[]"), use_cdp=True)
    cap.start()

    first = cap.get_requests()
    assert {e["url"] for e in first} == {u1}

    second = cap.get_requests()  # second drain returns b2; b1 must be retained
    assert {e["url"] for e in second} == {u1, u2}


def test_get_response_body_failure_does_not_break_capture():
    url = "https://site/api/x"
    batch = [
        _req("R1", url, rtype="XHR"),
        _resp("R1", status=200, rtype="XHR", mime="application/json"),
        _done("R1"),
    ]
    driver = _PerfDriver([batch], bodies={})  # no body -> getResponseBody raises
    cap = NetworkCapture(_CdpPage(driver, js_capture="[]"), use_cdp=True)
    cap.start()
    reqs = cap.get_requests()

    assert len(reqs) == 1
    assert reqs[0]["url"] == url
    assert reqs[0]["respBody"] is None


def test_binary_response_body_is_not_fetched():
    url = "https://site/logo.png"
    batch = [
        _req("R1", url, rtype="Image"),
        _resp("R1", status=200, rtype="Image", mime="image/png"),
        _done("R1"),
    ]
    driver = _PerfDriver([batch], bodies={"R1": "PNGDATA"})
    cap = NetworkCapture(_CdpPage(driver, js_capture="[]"), use_cdp=True)
    cap.start()
    reqs = cap.get_requests()

    assert reqs[0]["url"] == url
    assert reqs[0]["respBody"] is None
    assert driver.body_requests == []  # binary mime -> no getResponseBody call


def test_get_log_failure_is_silent_and_returns_js_entries():
    class _BrokenLogDriver:
        def execute_cdp_cmd(self, cmd: str, params: dict) -> dict:
            return {}

        def get_log(self, kind: str) -> list[dict]:
            raise WebDriverException("performance log not enabled")

    js = _hook_json("https://site/api/z", resp_body="{}")
    cap = NetworkCapture(_CdpPage(_BrokenLogDriver(), js_capture=js), use_cdp=True)
    cap.start()
    reqs = cap.get_requests()

    assert len(reqs) == 1
    assert reqs[0]["url"].endswith("/api/z")


def test_malformed_perf_log_entries_are_skipped():
    good = "https://site/api/ok"
    batch = [
        {"message": "not-json"},  # undecodable
        {"message": json.dumps({"no_message_key": True})},  # wrong shape
        _perf("Page.frameNavigated", {"frame": {}}),  # non-Network event ignored
        _req("R1", good, rtype="Fetch"),
        _resp("R1", status=200, rtype="Fetch", mime="application/json"),
        _done("R1"),
    ]
    driver = _PerfDriver([batch], bodies={})
    cap = NetworkCapture(_CdpPage(driver, js_capture="[]"), use_cdp=True)
    cap.start()
    reqs = cap.get_requests()

    assert [e["url"] for e in reqs] == [good]


# --------------------------------------------------------------------------- #
# Redirect chains, distinct-request preservation, incremental state, base64
# --------------------------------------------------------------------------- #


def test_cdp_redirect_chain_produces_an_entry_per_hop():
    a, b = "https://site/old", "https://site/new"
    redirect_hop = _perf(
        "Network.requestWillBeSent",
        {
            "requestId": "R",
            "type": "Document",
            "request": {"url": b, "method": "GET", "headers": {}},
            "redirectResponse": {
                "url": a, "status": 302, "headers": {"Location": b}, "mimeType": "text/html"
            },
        },
    )
    batch = [
        _req("R", a, rtype="Document"),  # original hop (no redirectResponse yet)
        redirect_hop,  # 302 A->B carried on the next requestWillBeSent for the same id
        _resp("R", status=200, rtype="Document", mime="text/html"),
        _done("R"),
    ]
    cap = NetworkCapture(_CdpPage(_PerfDriver([batch]), js_capture="[]"), use_cdp=True)
    cap.start()
    by_url = {e["url"]: e for e in cap.get_requests()}

    assert set(by_url) == {a, b}  # both hops survive
    assert by_url[a]["status"] == 302  # the redirect hop is not lost
    assert by_url[a]["headers"]["Location"] == b
    assert by_url[b]["status"] == 200  # the final hop


def test_distinct_same_url_post_requests_are_not_collapsed():
    url = "https://site/graphql"

    def post(rid: str, body: str) -> list[dict]:
        return [
            _perf(
                "Network.requestWillBeSent",
                {
                    "requestId": rid, "type": "Fetch",
                    "request": {"url": url, "method": "POST", "headers": {}, "postData": body},
                },
            ),
            _resp(rid, status=200, rtype="Fetch", mime="application/json"),
            _done(rid),
        ]

    batch = post("R1", '{"q":"a"}') + post("R2", '{"q":"b"}')
    driver = _PerfDriver([batch], bodies={"R1": '{"a":1}', "R2": '{"b":2}'})
    cap = NetworkCapture(_CdpPage(driver, js_capture="[]"), use_cdp=True)
    cap.start()
    reqs = cap.get_requests()

    assert len(reqs) == 2  # distinct payloads to the same endpoint both survive
    assert {e["reqBody"] for e in reqs} == {'{"q":"a"}', '{"q":"b"}'}
    assert {e["respBody"] for e in reqs} == {'{"a":1}', '{"b":2}'}


def test_drain_holds_correlated_records_not_raw_messages():
    u1, u2 = "https://site/a", "https://site/b"
    b1 = [
        _req("R1", u1, rtype="XHR"),
        _resp("R1", status=200, rtype="XHR", mime="text/json"),
        _done("R1"),
    ]
    b2 = [
        _req("R2", u2, rtype="XHR"),
        _resp("R2", status=200, rtype="XHR", mime="text/json"),
        _done("R2"),
    ]
    cap = NetworkCapture(_CdpPage(_PerfDriver([b1, b2]), js_capture="[]"), use_cdp=True)
    cap.start()
    cap.get_requests()
    cap.get_requests()

    # State is bounded to one correlated record per hop, not an ever-growing raw log.
    assert len(cap._cdp_records) == 2
    assert getattr(cap, "_cdp_messages", []) == []


def test_base64_binary_body_is_discarded_not_mojibaked():
    import base64

    url = "https://site/blob"
    batch = [
        _req("R1", url, rtype="Fetch"),
        _resp("R1", status=200, rtype="Fetch", mime="application/json"),
        _done("R1"),
    ]
    invalid_utf8 = base64.b64encode(bytes([0xFF, 0xFE, 0x00])).decode()
    driver = _PerfDriver([batch], b64_bodies={"R1": invalid_utf8})
    cap = NetworkCapture(_CdpPage(driver, js_capture="[]"), use_cdp=True)
    cap.start()
    reqs = cap.get_requests()

    assert reqs[0]["respBody"] is None  # garbage is discarded, not replacement-charred


# --------------------------------------------------------------------------- #
# Broadened JS hook (string-level guard — full behavior covered by browser test)
# --------------------------------------------------------------------------- #


def test_hook_js_intercepts_beacon_and_jsonp_and_image():
    from visus.web.network import _HOOK_JS

    assert "sendBeacon" in _HOOK_JS
    assert "createElement" in _HOOK_JS  # JSONP <script>/<img> interception
    assert "__vcm_capture" in _HOOK_JS


# --------------------------------------------------------------------------- #
# Launch enables Chrome/Edge performance logging (prerequisite for CDP drain)
# --------------------------------------------------------------------------- #


def test_chrome_options_enable_performance_logging():
    from visus.web.backends.browsers import chrome

    opts = chrome.build_options(headless=True, download_dir="/tmp/dl", user_data_dir="/tmp/ud")
    caps = opts.to_capabilities()
    assert caps.get("goog:loggingPrefs", {}).get("performance") == "ALL"
    assert opts.experimental_options.get("perfLoggingPrefs", {}).get("enableNetwork") is True


def test_edge_options_enable_performance_logging():
    from visus.web.backends.browsers import edge

    opts = edge.build_options(headless=True, download_dir="/tmp/dl", user_data_dir="/tmp/ud")
    caps = opts.to_capabilities()
    logging_prefs = caps.get("ms:loggingPrefs") or caps.get("goog:loggingPrefs") or {}
    assert logging_prefs.get("performance") == "ALL"
    assert opts.experimental_options.get("perfLoggingPrefs", {}).get("enableNetwork") is True


@pytest.mark.browser
def test_cdp_captures_jsonp_and_beacon_in_real_browser():
    """End-to-end: JSONP <script> + sendBeacon are captured (invisible to fetch/XHR)."""
    from visus.web import launch

    html = (
        "data:text/html,<html><body>"
        "<button id='go' onclick=\""
        "navigator.sendBeacon('https://httpbin.org/post','ping');"
        "var s=document.createElement('script');"
        "s.src='https://httpbin.org/get?jsonp=1';document.body.appendChild(s);"
        "\">go</button></body></html>"
    )
    with launch(headless=True) as browser:
        page = browser.new_page()
        page.goto(html)
        cap = NetworkCapture(page)  # use_cdp=True default
        cap.start()
        page.locator("#go").click()
        page.evaluate("() => new Promise(r => setTimeout(r, 2500))")
        reqs = cap.get_requests()
        urls = " ".join(r["url"] for r in reqs)
        assert cap._cdp_records, "CDP perf-log delivered no Network events (CDP path is dead)"
        assert "httpbin.org/get" in urls  # JSONP <script> captured
        assert "httpbin.org/post" in urls  # sendBeacon captured
        cap.stop()
