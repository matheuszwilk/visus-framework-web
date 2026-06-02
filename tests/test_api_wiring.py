from visus.web.api.browser import Browser
from visus.web.config import Defaults


class FakePage:
    def __init__(self): self._url = "about:blank"; self._closed = False
    def goto(self, url, *, wait_until, timeout_ms): self._url = url
    def current_url(self): return self._url
    def title(self): return "FAKE"
    def content(self): return "<html>fake</html>"
    def reload(self, *, timeout_ms): ...
    def go_back(self, *, timeout_ms): ...
    def go_forward(self, *, timeout_ms): ...
    def close(self): self._closed = True
    def is_closed(self): return self._closed


class FakeContext:
    def __init__(self): self._pages = []
    def new_page(self): p = FakePage(); self._pages.append(p); return p
    def pages(self): return self._pages
    def close(self): [p.close() for p in self._pages]


class FakeBrowserDelegate:
    def __init__(self): self._ctxs = []; self.disposed = False
    def new_context(self): c = FakeContext(); self._ctxs.append(c); return c
    def contexts(self): return self._ctxs
    def dispose(self): self.disposed = True


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
