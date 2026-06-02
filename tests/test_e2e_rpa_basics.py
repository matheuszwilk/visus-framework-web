import pytest


@pytest.fixture
def page(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/rpa.html")
    return p


@pytest.mark.browser
def test_page_evaluate(page):
    assert page.evaluate("() => document.title") == "rpa fixture"
    assert page.evaluate("a => a + 1", 41) == 42


@pytest.mark.browser
def test_locator_evaluate(page):
    assert page.locator("#box").evaluate("el => el.tagName") == "DIV"
    result = page.locator("#box").evaluate("(el, suffix) => el.textContent + suffix", "!")
    assert result == "hello box!"


@pytest.mark.browser
def test_page_screenshot_returns_png(page):
    data = page.screenshot()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.browser
def test_full_page_screenshot_returns_png(page):
    data = page.screenshot(full_page=True)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.browser
def test_screenshot_writes_file(page, tmp_path):
    out = tmp_path / "shot.png"
    page.screenshot(path=str(out))
    assert out.exists() and out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.browser
def test_locator_screenshot(page):
    data = page.locator("#box").screenshot()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.browser
def test_context_cookies(browser, base_url):
    ctx = browser.new_context()
    p = ctx.new_page()
    p.goto(f"{base_url}/rpa.html")
    ctx.add_cookies([{"name": "visus", "value": "42", "url": base_url}])
    names = {c["name"]: c["value"] for c in ctx.cookies()}
    assert names.get("visus") == "42"
    ctx.clear_cookies()
    assert all(c["name"] != "visus" for c in ctx.cookies())


@pytest.mark.browser
def test_set_input_files(page, tmp_path):
    f = tmp_path / "upload.txt"
    f.write_text("data")
    page.locator("#up").set_input_files(str(f))
    assert page.locator("#upname").text_content() == "upload.txt"
    assert page.locator("#up").input_value().endswith("upload.txt")
