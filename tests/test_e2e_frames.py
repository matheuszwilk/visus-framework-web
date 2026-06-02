import pytest

from visus.web import expect


@pytest.fixture
def page(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/frames.html")
    return p


@pytest.mark.browser
def test_frame_locator_reads_inside_iframe(page):
    fl = page.frame_locator("#f1")
    assert fl.get_by_role("button", name="Inner Button").count() == 1
    assert fl.locator("#res").text_content() == "idle"


@pytest.mark.browser
def test_click_inside_iframe(page):
    page.frame_locator("#f1").locator("#btn").click()
    assert page.frame_locator("#f1").locator("#res").text_content() == "clicked"


@pytest.mark.browser
def test_fill_inside_iframe(page):
    page.frame_locator("#f1").locator("#inp").fill("framed text")
    assert page.frame_locator("#f1").locator("#inp").input_value() == "framed text"


@pytest.mark.browser
def test_expect_inside_iframe(page):
    page.frame_locator("#f1").locator("#btn").click()
    expect(page.frame_locator("#f1").locator("#res")).to_have_text("clicked")


@pytest.mark.browser
def test_nested_iframe(page):
    deep = page.frame_locator("#f1").frame_locator("#nested").locator("#deeptext")
    assert deep.text_content() == "deep value"


@pytest.mark.browser
def test_top_level_still_works_after_frame_ops(page):
    # prove the context resets: a frame op then a top-level read
    page.frame_locator("#f1").locator("#btn").click()
    assert page.locator("h1").text_content() == "Top Level"
    assert page.get_by_role("heading", name="Top Level").count() == 1
