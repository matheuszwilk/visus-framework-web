"""Real-browser end-to-end tests for the backtrack feature (depth semantics).

backtrack=N re-runs the last N successful steps (oldest→newest) then retries the
failed step once.  Two fixtures:
  * backtrack.html       — one Prepare button (depth-1 recovery)
  * backtrack_depth.html — three distinct step buttons (depth up to 3)
Each test uses a fresh page so the page counters reset.
"""

from __future__ import annotations

import pytest

from visus.web import errors


@pytest.fixture
def page(browser, base_url):  # type: ignore[no-untyped-def]
    p = browser.new_page()
    p.goto(f"{base_url}/backtrack.html")
    return p


@pytest.fixture
def depth_page(browser, base_url):  # type: ignore[no-untyped-def]
    p = browser.new_page()
    p.goto(f"{base_url}/backtrack_depth.html")
    return p


@pytest.mark.browser
def test_backtrack_reexecutes_previous_step(page) -> None:  # type: ignore[no-untyped-def]
    """backtrack=True re-runs Prepare (the previous step), making #t2 appear, then succeeds."""
    page.get_by_role("button", name="Prepare").click()  # step recorded: count=1
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
def test_backtrack_one_insufficient_raises(page) -> None:  # type: ignore[no-untyped-def]
    """Depth 1 only reaches count=2; #t3 needs count>=3, so the click still fails."""
    page.get_by_role("button", name="Prepare").click()  # count=1
    with pytest.raises(errors.VisusWebError):
        page.locator("#t3").click(backtrack=True, timeout=800)


@pytest.mark.browser
def test_backtrack_depth_three_replays_three_steps(depth_page) -> None:  # type: ignore[no-untyped-def]
    """The 4-step example: s1,s2,s3 succeed; #go (step 4) fails until backtrack=3
    replays s1,s2,s3 (count→6) and the single retry of #go then succeeds."""
    depth_page.locator("#s1").click()  # step 1: count=1 (recorded)
    depth_page.locator("#s2").click()  # step 2: count=2 (recorded)
    depth_page.locator("#s3").click()  # step 3: count=3 (recorded)
    depth_page.locator("#go").click(backtrack=3, timeout=800)  # step 4: needs count>=6
    assert depth_page.locator("#r").text_content() == "clicked"
    # the three previous steps were replayed in order before the single retry
    log = depth_page.locator("#log").text_content() or ""
    assert log.split() == ["s1", "s2", "s3", "s1", "s2", "s3"]


@pytest.mark.browser
def test_backtrack_depth_two_insufficient_raises(depth_page) -> None:  # type: ignore[no-untyped-def]
    """backtrack=2 replays only s2,s3 (count→5 < 6), so #go still fails — depth 3 is required."""
    depth_page.locator("#s1").click()
    depth_page.locator("#s2").click()
    depth_page.locator("#s3").click()
    with pytest.raises(errors.VisusWebError):
        depth_page.locator("#go").click(backtrack=2, timeout=800)
