import pytest

from visus.web import expect


@pytest.fixture
def page(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/forms.html")
    return p


@pytest.mark.browser
def test_to_have_value(page):
    expect(page.locator("#user")).to_have_value("ada")
    with pytest.raises(AssertionError):
        expect(page.locator("#user")).to_have_value("bob", timeout=600)


@pytest.mark.browser
def test_to_have_attribute(page):
    expect(page.locator("#user")).to_have_attribute("type", "text")


@pytest.mark.browser
def test_to_have_class_and_contain_class(page):
    expect(page.locator("#user")).to_have_class("field big")     # full class, exact
    expect(page.locator("#user")).to_contain_class("big")        # single token


@pytest.mark.browser
def test_to_have_role(page):
    expect(page.locator("#closebtn")).to_have_role("button")
    expect(page.locator("#user")).to_have_role("textbox")


@pytest.mark.browser
def test_to_be_disabled_and_editable(page):
    expect(page.locator("#dis")).to_be_disabled()
    expect(page.locator("#user")).to_be_editable()
    expect(page.locator("#ro")).not_.to_be_editable()
