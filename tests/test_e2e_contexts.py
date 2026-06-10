"""Real BrowserContext isolation: each context gets its own driver process."""

from __future__ import annotations

import pytest


@pytest.mark.browser
def test_contexts_isolate_cookies(browser, base_url):
    """Cookies set in context A must NOT be visible in context B."""
    a = browser.new_context()
    pa = a.new_page()
    pa.goto(f"{base_url}/forms.html")

    b = browser.new_context()
    pb = b.new_page()
    pb.goto(f"{base_url}/forms.html")

    a.add_cookies([{"name": "ctx", "value": "A", "url": base_url}])

    assert any(c["name"] == "ctx" and c["value"] == "A" for c in a.cookies())
    assert all(c["name"] != "ctx" for c in b.cookies())  # B is isolated

    a.close()
    b.close()


@pytest.mark.browser
def test_context_cookies_cleared_independently(browser, base_url):
    """Clearing cookies in one context does not affect another."""
    a = browser.new_context()
    pa = a.new_page()
    pa.goto(f"{base_url}/forms.html")

    b = browser.new_context()
    pb = b.new_page()
    pb.goto(f"{base_url}/forms.html")

    a.add_cookies([{"name": "shared", "value": "yes", "url": base_url}])
    b.add_cookies([{"name": "shared", "value": "yes", "url": base_url}])

    a.clear_cookies()
    assert all(c["name"] != "shared" for c in a.cookies())
    # B's cookie must still be present.
    assert any(c["name"] == "shared" for c in b.cookies())

    a.close()
    b.close()


@pytest.mark.browser
def test_new_context_has_separate_driver(browser, base_url):
    """new_context() must spawn a fresh driver (owns_driver=True on the delegate)."""
    from visus.web.backends.selenium_backend import SeleniumBrowserDelegate

    delegate = browser._delegate  # type: ignore[attr-defined]
    assert isinstance(delegate, SeleniumBrowserDelegate)

    ctx = browser.new_context()
    ctx_delegate = ctx._delegate  # type: ignore[attr-defined]
    # The new context's delegate must own its driver.
    assert ctx_delegate.owns_driver is True
    ctx.close()


@pytest.mark.browser
def test_storage_state_roundtrip(browser, base_url, tmp_path):
    page = browser.new_page()
    page.goto(f"{base_url}/forms.html")
    page.evaluate(
        "() => { localStorage.setItem('tok', 'abc123'); sessionStorage.setItem('s', '1'); }"
    )
    ctx = page.context
    state = ctx.storage_state(path=str(tmp_path / "state.json"))
    assert isinstance(state["cookies"], list)
    origin = next(o for o in state["origins"] if o["origin"].startswith("http://127.0.0.1"))
    assert {"name": "tok", "value": "abc123"} in origin["localStorage"]
    assert {"name": "s", "value": "1"} in origin["sessionStorage"]
    assert (tmp_path / "state.json").exists()

    # restore into a FRESH context (separate driver): goto the origin, restore, read back
    ctx2 = browser.new_context()
    try:
        page2 = ctx2.new_page()
        page2.goto(f"{base_url}/forms.html")
        assert page2.evaluate("() => localStorage.getItem('tok')") is None
        ctx2.restore_storage_state(str(tmp_path / "state.json"))
        assert page2.evaluate("() => localStorage.getItem('tok')") == "abc123"
        assert page2.evaluate("() => sessionStorage.getItem('s')") == "1"
    finally:
        ctx2.close()
