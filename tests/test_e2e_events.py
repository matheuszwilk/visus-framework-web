"""Real-browser tests for popup and dialog event handling (S3b)."""

import pytest


@pytest.fixture
def page(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/popups.html")
    return p


@pytest.mark.browser
def test_expect_popup(page):
    with page.expect_popup() as info:
        page.locator("#pop").click()
    popup = info.value
    assert popup.title() == "forms fixture"
    popup.close()


@pytest.mark.browser
def test_expect_dialog_alert(page):
    with page.expect_dialog() as info:
        page.locator("#alertbtn").click()
    assert info.value.message == "hi there"


@pytest.mark.browser
def test_expect_dialog_confirm_accept(page):
    with page.expect_dialog(accept=True):
        page.locator("#confirmbtn").click()
    assert page.locator("#cres").text_content() == "yes"


@pytest.mark.browser
def test_expect_dialog_confirm_dismiss(page):
    with page.expect_dialog(accept=False):
        page.locator("#confirmbtn").click()
    assert page.locator("#cres").text_content() == "no"


@pytest.mark.browser
def test_expect_dialog_prompt(page):
    with page.expect_dialog(accept=True, prompt_text="Ada"):
        page.locator("#promptbtn").click()
    assert page.locator("#pres").text_content() == "Ada"
