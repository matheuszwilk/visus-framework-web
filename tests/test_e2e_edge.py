import pytest

from visus.web import Engine, expect, launch


@pytest.mark.browser
def test_edge_end_to_end(base_url):
    with launch(Engine.EDGE, headless=True) as browser:
        page = browser.new_page()
        page.goto(f"{base_url}/locators.html")
        assert page.get_by_role("heading", name="Dashboard").count() == 1
        assert page.get_by_role("button", name="Sign in").count() == 1
        page.get_by_role("button", name="Sign in").click()  # auto-wait works on Edge
        expect(page.get_by_text("Welcome back")).to_be_visible()
