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


@pytest.mark.browser
def test_regex_locators(page):
    import re

    # get_by_text / get_by_label / get_by_placeholder accept compiled patterns
    assert page.get_by_label(re.compile(r"^User\w+$")).count() == 1
    assert page.get_by_label(re.compile(r"^user\w+$", re.IGNORECASE)).count() == 1
    assert page.get_by_placeholder(re.compile("search the", re.IGNORECASE)).count() == 1
    # role + name regex
    assert page.get_by_role("textbox", name=re.compile("User")).count() == 1
    # a non-matching pattern matches nothing
    assert page.get_by_label(re.compile(r"^Nothing\d+$")).count() == 0


@pytest.mark.browser
def test_regex_assertions(page):
    import re

    from visus.web import expect

    expect(page.locator("#user")).to_have_value(re.compile(r"^ad."))
    expect(page.locator("#user")).to_have_attribute("type", re.compile("te.t"))
    expect(page.get_by_label("Username")).not_.to_have_value(re.compile(r"^\d+$"))


@pytest.mark.browser
def test_filter_has_and_has_not(page):
    # <ul id="items"> contains <li>s; only the list containing "beta" survives has=
    items = page.locator("ul").filter(has=page.get_by_text("beta", exact=True))
    assert items.count() == 1
    assert items.get_attribute("id") == "items"
    # has_not removes it
    assert page.locator("ul").filter(has_not=page.get_by_text("beta", exact=True)).count() == 0
    # has_not_text: li elements NOT containing "beta"
    others = page.locator("#items li").filter(has_not_text="beta")
    assert others.all_text_contents() == ["alpha", "gamma"]


@pytest.mark.browser
def test_or_and_and_composition(page):
    either = page.locator("#does-not-exist").or_(page.locator("#user"))
    assert either.count() == 1
    assert either.get_attribute("id") == "user"
    # or_ unions and keeps document order
    both = page.locator("#search").or_(page.locator("#user"))
    assert both.count() == 2
    assert both.first().get_attribute("id") == "user"
    # and_ intersects
    assert page.locator("input").and_(page.locator(".big")).get_attribute("id") == "user"
    assert page.locator("button").and_(page.locator(".big")).count() == 0


@pytest.mark.browser
def test_inner_text_html_bbox_all_inner_texts(page):
    li = page.locator("#items li").first()
    assert li.inner_text() == "alpha"
    assert "alpha" in page.locator("#items").inner_html()
    assert page.locator("#items li").all_inner_texts() == ["alpha", "beta", "gamma"]
    box = page.locator("#user").bounding_box()
    assert box is not None and box["width"] > 0 and box["height"] > 0
    assert page.locator("#missing").bounding_box() is None


@pytest.mark.browser
def test_dispatch_event_scroll_highlight(page):
    page.evaluate(
        "() => { window.__got = 0;"
        " document.querySelector('#user').addEventListener('custom-ping',"
        " () => { window.__got = 1; }); }"
    )
    page.locator("#user").dispatch_event("custom-ping")
    assert page.evaluate("() => window.__got") == 1
    page.locator("#items").scroll_into_view_if_needed()
    page.locator("#user").highlight()
    count_js = "() => document.querySelectorAll('[data-visus-highlight]').length"
    assert page.evaluate(count_js) > 0


@pytest.mark.browser
def test_press_sequentially(page):
    page.locator("#search").press_sequentially("abc")
    assert page.locator("#search").input_value() == "abc"
    page.locator("#search").clear()
    page.locator("#search").press_sequentially("xy", delay=10)
    assert page.locator("#search").input_value() == "xy"
