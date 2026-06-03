"""E2E tests for page.mouse and page.keyboard with a real headless browser."""

import pytest


@pytest.fixture
def page(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/input.html")
    return p


def _center(page, selector):
    box = page.evaluate(
        "() => { const r = document.querySelector('#pad').getBoundingClientRect();"
        " return {x: r.left + r.width/2, y: r.top + r.height/2}; }",
        None,
    )
    return box["x"], box["y"]  # type: ignore[index]


@pytest.mark.browser
def test_mouse_click_at_coords(page):
    x, y = _center(page, "#pad")
    page.mouse.click(x, y)
    assert page.locator("#c").text_content() == "clicked"


@pytest.mark.browser
def test_mouse_down_up(page):
    x, y = _center(page, "#pad")
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.up()
    assert page.locator("#m").text_content() == "down up"


@pytest.mark.browser
def test_mouse_wheel(page):
    x, y = _center(page, "#pad")
    page.mouse.move(x, y)
    page.mouse.wheel(0, 100)
    assert page.locator("#w").text_content() == "wheel"


@pytest.mark.browser
def test_keyboard_type_and_press(page):
    page.locator("#k").focus()
    page.keyboard.type("hello")
    assert page.locator("#k").input_value() == "hello"
    page.keyboard.press("Enter")
    assert page.locator("#k2").text_content() == "enter"
