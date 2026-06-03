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
