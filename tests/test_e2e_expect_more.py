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
    expect(page.locator("#user")).to_have_class("field big")  # full class, exact
    expect(page.locator("#user")).to_contain_class("big")  # single token


@pytest.mark.browser
def test_to_have_role(page):
    expect(page.locator("#closebtn")).to_have_role("button")
    expect(page.locator("#user")).to_have_role("textbox")


@pytest.mark.browser
def test_to_be_disabled_and_editable(page):
    expect(page.locator("#dis")).to_be_disabled()
    expect(page.locator("#user")).to_be_editable()
    expect(page.locator("#ro")).not_.to_be_editable()


@pytest.mark.browser
def test_locator_wait_for_states(page):
    from visus.web import errors

    page.locator("#user").wait_for()  # default: visible
    page.locator("#user").wait_for(state="attached")
    page.locator("#missing").wait_for(state="detached")
    page.locator("#missing").wait_for(state="hidden")  # absent counts as hidden
    with pytest.raises(errors.VisusTimeoutError):
        page.locator("#missing").wait_for(state="visible", timeout=400)
    with pytest.raises(ValueError):
        page.locator("#user").wait_for(state="bogus")


@pytest.mark.browser
def test_expect_to_be_attached(page):
    expect(page.locator("#user")).to_be_attached()
    expect(page.locator("#missing")).not_.to_be_attached()


@pytest.mark.browser
def test_expect_page_url_and_title(page):
    import re

    expect(page).to_have_title("forms fixture")
    expect(page).to_have_title(re.compile("forms"))
    expect(page).to_have_url(re.compile(r"forms\.html$"))
    expect(page).to_have_url("*forms*")
    expect(page).not_.to_have_title("nope")
    with pytest.raises(AssertionError):
        expect(page).to_have_title("wrong", timeout=400)


@pytest.mark.browser
def test_new_locator_matchers(page):
    page.locator("#user").focus()
    expect(page.locator("#user")).to_be_focused()
    expect(page.locator("#search")).to_be_empty()
    expect(page.locator("#user")).not_.to_be_empty()
    expect(page.locator("#user")).to_be_in_viewport()
    expect(page.locator("#user")).to_have_id("user")
    expect(page.locator("#items")).to_have_css("display", "block")
    page.evaluate(
        "() => { const s = document.createElement('select'); s.multiple = true;"
        " s.id = 'multi'; ['a','b','c'].forEach(v => { const o = document.createElement('option');"
        " o.value = v; o.selected = v !== 'c'; s.appendChild(o); });"
        " document.body.appendChild(s); }"
    )
    expect(page.locator("#multi")).to_have_values(["a", "b"])
    expect(page.locator("#multi")).not_.to_have_values(["a", "b", "c"])
