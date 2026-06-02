import pytest

from visus.web import expect


@pytest.fixture
def page(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/expects.html")
    return p


@pytest.mark.browser
def test_to_have_text_retries_until_changed(page):
    expect(page.locator("#msg")).to_have_text("ready")  # text flips from 'loading' at 700ms


@pytest.mark.browser
def test_to_contain_text(page):
    expect(page.locator("#msg")).to_contain_text("read")


@pytest.mark.browser
def test_to_be_visible_retries_until_appears(page):
    expect(page.locator("#appear")).to_be_visible()


@pytest.mark.browser
def test_not_to_be_visible_retries_until_vanishes(page):
    expect(page.locator("#vanish")).not_.to_be_visible()


@pytest.mark.browser
def test_to_have_count_retries_until_list_grows(page):
    expect(page.locator("#list li")).to_have_count(3)


@pytest.mark.browser
def test_to_be_enabled_retries(page):
    expect(page.locator("#enableme")).to_be_enabled()


@pytest.mark.browser
def test_already_true_passes_fast(page):
    # one-shot path: msg is present immediately (text 'loading')
    expect(page.locator("#msg")).to_be_visible()


@pytest.mark.browser
def test_failing_assertion_raises_assertionerror(page):
    with pytest.raises(AssertionError):
        expect(page.locator("#appear")).to_have_text("never", timeout=800)


@pytest.mark.browser
def test_not_negation_failure_raises(page):
    # #msg IS visible, so not_.to_be_visible must fail within the timeout
    with pytest.raises(AssertionError):
        expect(page.locator("#msg")).not_.to_be_visible(timeout=800)
