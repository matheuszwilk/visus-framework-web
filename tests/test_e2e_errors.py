"""Real-browser tests for the friendly, debuggable action-error messages."""

from __future__ import annotations

import pytest

from visus.web import errors


@pytest.fixture
def page(browser, base_url):  # type: ignore[no-untyped-def]
    p = browser.new_page()
    p.goto(f"{base_url}/forms.html")
    return p


@pytest.mark.browser
def test_error_message_describes_target_page_and_next_steps(page) -> None:  # type: ignore[no-untyped-def]
    """A not-found click yields a structured message: target, page, status, and hints."""
    with pytest.raises(errors.VisusWebError) as exc:
        page.locator("#totally-missing").click(timeout=300)
    msg = str(exc.value)
    assert 'css "#totally-missing"' in msg  # human-readable target, not raw JSON
    assert "could not find" in msg
    assert "forms.html" in msg  # page context (URL)
    assert "status:" in msg and "try:" in msg  # structured + actionable for humans and AI


@pytest.mark.browser
def test_error_suggests_did_you_mean_for_misspelt_name(browser, base_url) -> None:  # type: ignore[no-untyped-def]
    """A misspelt role-name target gets a fuzzy 'did you mean' from the live page."""
    p = browser.new_page()
    p.goto(f"{base_url}/backtrack.html")  # has a button whose accessible name is "Prepare"
    # "Prepair" is a typo that is NOT a substring of "Prepare" (so it genuinely misses)
    # but is fuzzy-close, so the diagnostics should suggest the real name.
    with pytest.raises(errors.VisusWebError) as exc:
        p.get_by_role("button", name="Prepair").click(timeout=300)
    msg = str(exc.value)
    assert "did you mean" in msg.lower()
    assert "Prepare" in msg  # the real button name is suggested
