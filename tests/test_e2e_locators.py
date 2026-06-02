import pytest

from visus.web import errors


@pytest.fixture
def page(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/locators.html")
    return p


@pytest.mark.browser
def test_get_by_role_button_by_name(page):
    assert page.get_by_role("button", name="Sign in").count() == 1
    assert page.get_by_role("button", name="Sign in").is_visible() is True


@pytest.mark.browser
def test_get_by_role_uses_aria_label_for_name(page):
    # the second button's accessible name comes from aria-label, not text content
    assert page.get_by_role("button", name="Sign out of account").count() == 1
    assert page.get_by_role("button", name="x").count() == 0


@pytest.mark.browser
def test_get_by_role_link_and_heading(page):
    assert page.get_by_role("link").count() == 2
    assert page.get_by_role("link", name="Settings").count() == 1
    assert page.get_by_role("heading", name="Dashboard").count() == 1


@pytest.mark.browser
def test_get_by_role_textbox_via_label(page):
    # accessible name from associated <label for>
    assert page.get_by_role("textbox", name="Email address").count() == 1


@pytest.mark.browser
def test_get_by_text_substring_and_exact(page):
    assert page.get_by_text("Welcome back").count() == 1  # substring, ci
    assert page.get_by_text("welcome back, ada").count() == 1  # case-insensitive
    assert page.get_by_text("Welcome", exact=True).count() == 0  # exact requires full text
    assert page.get_by_text("Welcome back, Ada", exact=True).count() == 1


@pytest.mark.browser
def test_get_by_text_innermost(page):
    # "Logout" is in an <li>; get_by_text returns the li, not <ul>/<body>
    loc = page.get_by_text("Logout")
    assert loc.count() == 1
    assert loc.text_content() == "Logout"


@pytest.mark.browser
def test_strict_mode_violation_on_multiple(page):
    dup = page.get_by_text("repeat")
    assert dup.count() == 2
    with pytest.raises(errors.StrictModeViolation):
        dup.is_visible()  # strict single-element read on 2 matches
    with pytest.raises(errors.StrictModeViolation):
        dup.text_content()


@pytest.mark.browser
def test_first_last_nth(page):
    dup = page.get_by_text("repeat")
    assert dup.first().count() == 1
    assert dup.last().count() == 1
    assert dup.nth(0).is_visible() is True


@pytest.mark.browser
def test_chaining_scopes_to_descendants(page):
    # text "Profile"/"Logout" only inside ul.menu
    menu = page.locator("ul.menu")
    assert menu.get_by_text("Logout").count() == 1
    assert menu.get_by_text("Dashboard").count() == 0  # heading is outside the menu


@pytest.mark.browser
def test_css_and_xpath(page):
    assert page.locator(".greeting").text_content() == "Welcome back, Ada"
    assert page.locator("//button[@id='signin']").count() == 1


@pytest.mark.browser
def test_hidden_element_not_visible_but_present(page):
    secret = page.locator("#hidden")
    assert secret.count() == 1
    assert secret.is_visible() is False


@pytest.mark.browser
def test_missing_locator_reads(page):
    nope = page.locator(".does-not-exist")
    assert nope.count() == 0
    assert nope.is_visible() is False
    assert nope.text_content() is None


@pytest.mark.browser
def test_shadow_dom_role(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/shadow.html")
    # NOTE: S1a engine does not pierce shadow roots yet; documents the limitation.
    # The host has no light-DOM button, so a top-level role query finds 0.
    assert p.get_by_role("button", name="Shadow Button").count() == 0
