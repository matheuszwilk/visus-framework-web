import pytest

from visus.web import errors


@pytest.mark.browser
def test_launch_goto_reads(browser, base_url):
    page = browser.new_page()
    page.goto(f"{base_url}/index.html")
    assert page.url.endswith("/index.html")
    assert page.title() == "visus-web test page"
    assert "Hello visus.web" in page.content()


@pytest.mark.browser
def test_navigation_back_forward(browser, base_url):
    page = browser.new_page()
    page.goto(f"{base_url}/index.html")
    page.goto(f"{base_url}/page2.html")
    assert page.title() == "page two"
    page.go_back()
    assert page.title() == "visus-web test page"
    page.go_forward()
    assert page.title() == "page two"


@pytest.mark.browser
def test_bad_url_raises_navigation_error(browser):
    page = browser.new_page()
    with pytest.raises(errors.VisusWebError):
        page.goto("http://127.0.0.1:1/nope", timeout=3000)


@pytest.mark.browser
def test_page_reload(browser, base_url):
    page = browser.new_page()
    page.goto(f"{base_url}/index.html")
    page.reload()
    assert page.title() == "visus-web test page"


@pytest.mark.browser
def test_page_close_and_is_closed(browser, base_url):
    page = browser.new_page()
    page.goto(f"{base_url}/index.html")
    assert page.is_closed is False
    page.close()
    assert page.is_closed is True


@pytest.mark.browser
def test_closed_page_raises_on_operation(browser, base_url):
    page = browser.new_page()
    page.goto(f"{base_url}/index.html")
    page.close()
    with pytest.raises(errors.TargetClosedError):
        page.title()


@pytest.mark.browser
def test_context_close(browser, base_url):
    from visus.web import launch

    with launch(headless=True) as b:
        ctx = b.new_context()
        page = ctx.new_page()
        page.goto(f"{base_url}/index.html")
        assert page.title() == "visus-web test page"
        ctx.close()


@pytest.mark.browser
def test_new_context_adds_to_delegate(browser):
    from visus.web import launch

    with launch(headless=True) as b:
        ctx = b.new_context()
        page = ctx.new_page()
        assert page.is_closed is False
