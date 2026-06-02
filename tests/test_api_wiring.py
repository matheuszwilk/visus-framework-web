from visus.web.api.browser import Browser
from visus.web.config import Defaults


class FakePage:
    def __init__(self):
        self._url = "about:blank"
        self._closed = False
        self.reloaded = False
        self.backed = False
        self.forwarded = False

    def goto(self, url, *, wait_until, timeout_ms):
        self._url = url

    def current_url(self):
        return self._url

    def title(self):
        return "FAKE"

    def content(self):
        return "<html>fake</html>"

    def reload(self, *, timeout_ms):
        self.reloaded = True

    def go_back(self, *, timeout_ms):
        self.backed = True

    def go_forward(self, *, timeout_ms):
        self.forwarded = True

    def close(self):
        self._closed = True

    def is_closed(self):
        return self._closed

    def locator_count(self, selector):
        return 0

    def locator_is_visible(self, selector):
        return False

    def locator_text_content(self, selector):
        return None

    def locator_click(self, selector, *, timeout_ms, force):
        pass

    def locator_fill(self, selector, value, *, timeout_ms, force):
        pass

    def locator_input_value(self, selector):
        return ""


class FakeContext:
    def __init__(self):
        self._pages = []
        self._closed = False

    def new_page(self):
        p = FakePage()
        self._pages.append(p)
        return p

    def pages(self):
        return self._pages

    def close(self):
        self._closed = True
        for p in self._pages:
            p.close()


class FakeBrowserDelegate:
    def __init__(self):
        self._ctxs = []
        self.disposed = False

    def new_context(self):
        c = FakeContext()
        self._ctxs.append(c)
        return c

    def contexts(self):
        return self._ctxs

    def dispose(self):
        self.disposed = True


def test_browser_new_page_goto_and_reads():
    bd = FakeBrowserDelegate()
    with Browser(bd, Defaults()) as browser:
        page = browser.new_page()
        page.goto("https://example.com")
        assert page.url == "https://example.com"
        assert page.title() == "FAKE"
        assert "fake" in page.content()
    assert bd.disposed is True


def test_close_passes_timeout_default_through():
    bd = FakeBrowserDelegate()
    browser = Browser(bd, Defaults())
    page = browser.new_page()
    page.goto("https://a.test", timeout=1234)
    assert page.url == "https://a.test"
    browser.close()
    assert bd.disposed is True


def test_page_reload_go_back_forward_close_is_closed():
    bd = FakeBrowserDelegate()
    browser = Browser(bd, Defaults())
    page = browser.new_page()
    page.reload()
    assert page._delegate.reloaded is True  # type: ignore[attr-defined]
    page.go_back()
    assert page._delegate.backed is True  # type: ignore[attr-defined]
    page.go_forward()
    assert page._delegate.forwarded is True  # type: ignore[attr-defined]
    assert page.is_closed is False
    page.close()
    assert page.is_closed is True


def test_browser_new_context_and_contexts_property():
    bd = FakeBrowserDelegate()
    browser = Browser(bd, Defaults())
    ctx = browser.new_context()
    assert len(browser.contexts) == 1
    p = ctx.new_page()
    p.goto("https://ctx.test")
    assert p.url == "https://ctx.test"
    ctx.close()
    assert bd._ctxs[0]._closed is True  # type: ignore[attr-defined]


def test_page_locator_entry_points_wiring():
    bd = FakeBrowserDelegate()
    browser = Browser(bd, Defaults())
    page = browser.new_page()
    # Verify that Page.locator / get_by_role / get_by_text return Locators that wire correctly
    loc = page.locator(".foo")
    assert loc.count() == 0
    loc2 = page.get_by_role("button", name="OK")
    assert loc2.count() == 0
    loc3 = page.get_by_text("hello")
    assert loc3.count() == 0
