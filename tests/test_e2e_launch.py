import pytest


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
    from visus.web import errors

    page = browser.new_page()
    with pytest.raises(errors.VisusWebError):
        page.goto("http://127.0.0.1:1/nope", timeout=3000)
