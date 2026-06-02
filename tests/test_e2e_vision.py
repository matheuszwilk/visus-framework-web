"""Real-browser OCR + image-match integration tests.

All tests are marked ``@pytest.mark.browser`` and require a live headed/headless
browser via the ``browser`` fixture defined in conftest.py.
"""

from __future__ import annotations

import numpy as np
import pytest


def _norm(s: str) -> str:
    return "".join(ch for ch in s.upper() if ch.isalnum())


@pytest.fixture
def page(browser, base_url):  # type: ignore[no-untyped-def]
    p = browser.new_page()
    p.goto(f"{base_url}/forms.html")
    return p


# ---------------------------------------------------------------------------
# OCR via Locator
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_locator_ocr_text(browser, base_url) -> None:  # type: ignore[no-untyped-def]
    """Render large clear text in a headless browser and read it back with OCR."""
    p = browser.new_page()
    p.goto("data:text/html,<h1 style='font-size:64px;font-family:monospace'>VISUSWEB</h1>")
    got = p.locator("h1").ocr_text()
    print(f"[E2E OCR] VISUSWEB -> raw={got!r} norm={_norm(got)!r}")
    assert "VISUSWEB" in _norm(got)


# ---------------------------------------------------------------------------
# Image matching via Locator
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_locator_find_image_self_match(page) -> None:  # type: ignore[no-untyped-def]
    """Take a screenshot of an element and find it inside itself — perfect match at (0,0)."""
    el = page.locator("#user")
    shot = el.screenshot()
    m = el.find_image(shot, confidence=0.95)
    print(f"[E2E MATCH] self-match -> {m}")
    assert m is not None and m.confidence > 0.99


@pytest.mark.browser
def test_locator_find_image_absent(page) -> None:  # type: ignore[no-untyped-def]
    """A patterned template clearly absent from the element returns None.

    A solid-colour needle must NOT be used here because TM_CCOEFF_NORMED treats
    zero-variance templates as matching everywhere (0/0 → 1.0).  This test uses
    a patterned needle (border + inner block) that is provably absent from the
    rendered input element.
    """
    # Patterned needle: black border + colored inner block — not in a grey input
    needle = np.zeros((15, 15, 3), np.uint8)
    needle[4:11, 4:11, 0] = 200  # inner 7×7 is dark-red
    assert page.locator("#user").find_image(needle, confidence=0.9) is None


# ---------------------------------------------------------------------------
# solve_captcha via Page
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_page_solve_captcha(browser) -> None:  # type: ignore[no-untyped-def]
    """Render simple captcha text and solve it via Page.solve_captcha."""
    p = browser.new_page()
    p.goto(
        "data:text/html,"
        "<div id='c' style='font-size:60px;letter-spacing:4px;font-family:monospace'>"
        "AB12CD"
        "</div>"
    )
    result = p.solve_captcha(p.locator("#c"))
    print(f"[E2E CAPTCHA] AB12CD -> raw={result!r} norm={_norm(result)!r}")
    assert _norm(result) == "AB12CD"
