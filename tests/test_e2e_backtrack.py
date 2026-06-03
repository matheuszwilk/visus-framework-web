"""Real-browser end-to-end tests for the backtrack feature.

Each test uses a fresh page so window.count resets.
The fixture HTML (backtrack.html) exposes buttons #t2 and #t3 only after
the Prepare button is clicked enough times (>=2 and >=3 respectively).
"""

from __future__ import annotations

import pytest

from visus.web import errors


@pytest.fixture
def page(browser, base_url):  # type: ignore[no-untyped-def]
    p = browser.new_page()
    p.goto(f"{base_url}/backtrack.html")
    return p


@pytest.mark.browser
def test_backtrack_reexecutes_previous_step(page) -> None:  # type: ignore[no-untyped-def]
    """backtrack=True re-runs Prepare (recorded as prev step), making #t2 appear, then succeeds."""
    page.get_by_role("button", name="Prepare").click()  # step A: count=1 (recorded)
    # #t2 needs count>=2; first attempt fails -> backtrack re-runs Prepare (count=2 -> #t2 appears)
    page.locator("#t2").click(backtrack=True, timeout=800)
    assert page.locator("#r2").text_content() == "clicked"


@pytest.mark.browser
def test_without_backtrack_fails(page) -> None:  # type: ignore[no-untyped-def]
    """Without backtrack, clicking #t2 (absent) raises VisusWebError immediately."""
    page.get_by_role("button", name="Prepare").click()  # count=1; #t2 absent
    with pytest.raises(errors.VisusWebError):
        page.locator("#t2").click(timeout=800)  # no backtrack -> raises


@pytest.mark.browser
def test_backtrack_true_insufficient_raises(page) -> None:  # type: ignore[no-untyped-def]
    """backtrack=True gives only 1 cycle; #t3 needs count>=3 so it still fails."""
    page.get_by_role("button", name="Prepare").click()  # count=1
    # #t3 needs count>=3; backtrack=True only reaches count=2 -> still fails -> raises
    with pytest.raises(errors.VisusWebError):
        page.locator("#t3").click(backtrack=True, timeout=800)


@pytest.mark.browser
def test_backtrack_n_cycles_succeeds(page) -> None:  # type: ignore[no-untyped-def]
    """backtrack=2 runs Prepare twice (count 2 then 3) so #t3 appears and the click succeeds."""
    page.get_by_role("button", name="Prepare").click()  # count=1
    # #t3 needs count>=3; backtrack=2 runs Prepare twice (count 2 then 3) -> #t3 appears -> succeeds
    page.locator("#t3").click(backtrack=2, timeout=800)
    assert page.locator("#r3").text_content() == "clicked"
