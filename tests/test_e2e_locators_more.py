import pytest


@pytest.fixture
def page(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/forms.html")
    return p


@pytest.mark.browser
def test_css_and_xpath_prefixes(page):
    # the css= / xpath= prefixes (and bare //) all resolve correctly
    assert page.locator("css=#user").count() == 1
    assert page.locator("css=#user").get_attribute("value") == "ada"
    assert page.locator("css=.field").count() == 1
    assert page.locator("xpath=//input[@id='user']").count() == 1
    assert page.locator("//input[@id='user']").count() == 1


@pytest.mark.browser
def test_malformed_selector_raises_visus_error(page):
    # a bad selector must surface as a VisusWebError, never a raw selenium exception
    from visus.web import errors

    with pytest.raises(errors.VisusWebError):
        page.locator("css=[[[bad").count()


@pytest.mark.browser
def test_get_by_label(page):
    assert page.get_by_label("Username").count() == 1
    assert page.get_by_label("Email address").count() == 1  # via aria-label
    assert page.get_by_label("Username").get_attribute("id") == "user"


@pytest.mark.browser
def test_get_by_placeholder(page):
    assert page.get_by_placeholder("Search the docs").count() == 1
    assert page.get_by_placeholder("search", exact=False).count() == 1


@pytest.mark.browser
def test_get_by_alt_text(page):
    assert page.get_by_alt_text("Company logo").count() == 1


@pytest.mark.browser
def test_get_by_title(page):
    assert page.get_by_title("Close dialog").count() == 1
    assert page.get_by_title("Close dialog").get_attribute("id") == "closebtn"


@pytest.mark.browser
def test_get_by_test_id(page):
    assert page.get_by_test_id("status").text_content() == "online"


@pytest.mark.browser
def test_reads_all_and_all_text_contents(page):
    items = page.locator("#items li")
    assert items.count() == 3
    assert items.all_text_contents() == ["alpha", "beta", "gamma"]
    assert len(items.all()) == 3
    assert items.all()[1].text_content() == "beta"


@pytest.mark.browser
def test_reads_get_attribute(page):
    assert page.locator("#user").get_attribute("value") == "ada"
    assert page.locator("#user").get_attribute("nope") is None


@pytest.mark.browser
def test_reads_state(page):
    assert page.locator("#user").is_enabled() is True
    assert page.locator("#dis").is_enabled() is False
    assert page.locator("#ro").is_editable() is False
    assert page.locator("#user").is_editable() is True
    assert page.locator("#search").is_hidden() is False
