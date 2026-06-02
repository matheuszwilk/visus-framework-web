"""Real-browser codegen recorder tests."""

from __future__ import annotations

import pytest

from visus.web.cli.codegen import drain, generate_line, generate_script, inject_recorder


@pytest.mark.browser
def test_recorder_captures_click_and_fill(browser, base_url: str) -> None:  # type: ignore[no-untyped-def]
    page = browser.new_page()
    page.goto(f"{base_url}/forms.html")
    inject_recorder(page)
    # Fill the Username field; change event fires on blur (triggered by next click)
    page.get_by_role("textbox", name="Username").fill("ada")
    # Click another element to blur the textbox and fire the change event
    page.locator("#closebtn").click()
    events = drain(page)
    actions = [e["action"] for e in events]
    assert "fill" in actions and "click" in actions, (
        f"expected fill+click in {actions}"
    )
    # The username fill should generate a get_by_role or locator line
    fill_ev = next(e for e in events if e["action"] == "fill")
    line = generate_line(fill_ev)
    assert ".fill(" in line, f"expected .fill( in generated line: {line!r}"


@pytest.mark.browser
def test_generate_script_shape(browser, base_url: str) -> None:  # type: ignore[no-untyped-def]
    page = browser.new_page()
    page.goto(f"{base_url}/forms.html")
    inject_recorder(page)
    page.locator("#closebtn").click()
    code = generate_script(f"{base_url}/forms.html", drain(page))
    assert "from visus.web import launch" in code
    assert "page.goto(" in code
    assert ".click()" in code
