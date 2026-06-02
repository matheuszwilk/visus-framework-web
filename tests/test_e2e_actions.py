import pytest

from visus.web import errors


@pytest.fixture
def page(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/actions.html")
    return p


@pytest.mark.browser
def test_click_performs_real_click(page):
    page.locator("#counter").click()
    assert page.locator("#count").text_content() == "1"
    page.locator("#counter").click()
    assert page.locator("#count").text_content() == "2"


@pytest.mark.browser
def test_click_auto_waits_for_visible(page):
    # #delayed is display:none for 700ms; click must wait, then click succeeds
    page.locator("#delayed").click()
    assert page.locator("#dres").text_content() == "clicked"


@pytest.mark.browser
def test_click_auto_waits_for_enabled(page):
    # #disabledbtn is disabled for 700ms; click must wait for enabled
    page.locator("#disabledbtn").click()
    assert page.locator("#ebres").text_content() == "clicked"


@pytest.mark.browser
def test_click_auto_waits_for_hit_target(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/overlay.html")
    # #under is covered by a full-screen overlay for 700ms; click must wait for it to clear
    p.locator("#under").click()
    assert p.locator("#ures").text_content() == "clicked"


@pytest.mark.browser
def test_fill_sets_value(page):
    page.locator("#name").fill("Ada Lovelace")
    assert page.locator("#name").input_value() == "Ada Lovelace"


@pytest.mark.browser
def test_fill_replaces_existing_value(page):
    page.locator("#name").fill("first")
    page.locator("#name").fill("second")
    assert page.locator("#name").input_value() == "second"


@pytest.mark.browser
def test_fill_auto_waits_for_editable(page):
    # #ro is readonly for 700ms; fill must wait for editable
    page.locator("#ro").fill("now editable")
    assert page.locator("#ro").input_value() == "now editable"


@pytest.mark.browser
def test_click_times_out_when_never_actionable(page):
    with pytest.raises(errors.VisusTimeoutError):
        page.locator("#does-not-exist").click(timeout=1000)


@pytest.mark.browser
def test_fill_times_out_when_missing(page):
    with pytest.raises(errors.VisusTimeoutError):
        page.locator("#nope").fill("x", timeout=1000)


@pytest.mark.browser
def test_force_click_bypasses_checks(page):
    # force=True clicks immediately without the actionability gate; #counter is already actionable
    page.locator("#counter").click(force=True)
    assert page.locator("#count").text_content() == "1"


@pytest.mark.browser
def test_strict_mode_blocks_ambiguous_click(page):
    # two buttons share role 'button'; clicking by role without name is ambiguous -> strict error
    with pytest.raises(errors.StrictModeViolation):
        page.get_by_role("button").click()
