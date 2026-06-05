"""Real-browser tests for multi-window / tab tracking.

Covers: auto-reconciliation of ``context.pages`` against the live browser
window handles, the explicit ``context.adopt_open_windows()`` sync, on-demand
``page.bring_to_front()`` / ``page.activate()`` focus, and the stable
``page.handle`` identity.
"""

import time

import pytest

OPEN_FORMS_JS = "() => { window.open('/forms.html', '_blank'); }"


def _wait_pages(ctx, n, timeout=5.0):
    """Poll ``context.pages`` until it has at least *n* live pages."""
    deadline = time.monotonic() + timeout
    pages = ctx.pages
    while len(pages) < n and time.monotonic() < deadline:
        time.sleep(0.05)
        pages = ctx.pages
    return pages


def _wait_adopt(ctx, n, timeout=5.0):
    """Poll ``adopt_open_windows()`` until *n* new pages have been adopted."""
    deadline = time.monotonic() + timeout
    collected = []
    while len(collected) < n and time.monotonic() < deadline:
        collected += ctx.adopt_open_windows()
        if len(collected) >= n:
            break
        time.sleep(0.05)
    return collected


@pytest.mark.browser
def test_context_pages_includes_window_open_tab(browser, base_url):
    """A tab opened by window.open WITHOUT expect_popup shows up in context.pages."""
    page = browser.new_page()
    page.goto(f"{base_url}/popups.html")
    ctx = browser.contexts[0]
    assert len(ctx.pages) == 1

    page.locator("#pop").click()  # window.open('/forms.html','_blank'); no expect_popup

    pages = _wait_pages(ctx, 2)
    assert len(pages) == 2
    urls = {p.url for p in pages}
    assert any(u.endswith("/forms.html") for u in urls)


@pytest.mark.browser
def test_adopt_open_windows_returns_only_new_tabs(browser, base_url):
    """Explicit adopt_open_windows() returns just-discovered tabs; idempotent after."""
    page = browser.new_page()
    page.goto(f"{base_url}/popups.html")
    ctx = browser.contexts[0]

    page.evaluate(OPEN_FORMS_JS)

    new = _wait_adopt(ctx, 1)
    assert len(new) == 1
    assert new[0].url.endswith("/forms.html")
    # Already tracked now → nothing new to adopt.
    assert ctx.adopt_open_windows() == []
    assert len(ctx.pages) == 2


@pytest.mark.browser
def test_context_pages_drops_externally_closed_tab(browser, base_url):
    """A window closed outside visus (not via page.close) is dropped from context.pages."""
    page = browser.new_page()
    page.goto(f"{base_url}/popups.html")
    ctx = browser.contexts[0]

    page.evaluate(OPEN_FORMS_JS)
    pages = _wait_pages(ctx, 2)
    forms = next(p for p in pages if p.url.endswith("/forms.html"))

    # Externally close that window via the raw driver (page._closed stays False).
    driver = ctx._delegate._driver
    driver.switch_to.window(forms.handle)
    driver.close()

    remaining = ctx.pages
    assert len(remaining) == 1
    assert remaining[0].url.endswith("/popups.html")  # no TargetClosedError leak


@pytest.mark.browser
def test_expect_popup_is_registered_in_context(browser, base_url):
    """A popup captured via expect_popup is tracked in context.pages (same handle, once)."""
    page = browser.new_page()
    page.goto(f"{base_url}/popups.html")
    ctx = browser.contexts[0]

    with page.expect_popup() as info:
        page.locator("#pop").click()
    popup = info.value

    pages = ctx.pages
    assert len(pages) == 2  # not double-counted
    assert popup.handle in {p.handle for p in pages}

    popup.close()
    assert len(ctx.pages) == 1


@pytest.mark.browser
def test_bring_to_front_and_activate_focus_the_tab(browser, base_url):
    """bring_to_front()/activate() switch the driver's active window to that page."""
    page = browser.new_page()
    page.goto(f"{base_url}/forms.html")
    ctx = browser.contexts[0]
    page2 = ctx.new_page()
    page2.goto(f"{base_url}/popups.html")
    driver = ctx._delegate._driver

    page.bring_to_front()
    assert driver.current_window_handle == page.handle

    page2.activate()
    assert driver.current_window_handle == page2.handle


@pytest.mark.browser
def test_context_pages_is_empty_after_browser_close(base_url):
    """A disposed session yields an empty context.pages, not a TargetClosedError."""
    from visus.web import launch

    b = launch(headless=True)
    page = b.new_page()
    page.goto(f"{base_url}/forms.html")
    ctx = b.contexts[0]
    assert len(ctx.pages) == 1

    b.close()  # quits the driver — handles are gone

    assert ctx.pages == []
    assert ctx.adopt_open_windows() == []


@pytest.mark.browser
def test_page_handle_is_stable_and_distinct(browser):
    """page.handle is a stable, non-empty string, distinct per tab."""
    page = browser.new_page()
    ctx = browser.contexts[0]
    page2 = ctx.new_page()

    assert isinstance(page.handle, str) and page.handle
    assert page.handle == page.handle
    assert page.handle != page2.handle
