"""Real-browser codegen recorder tests + pure-Python unit tests."""

from __future__ import annotations

import pytest

from visus.web.cli.codegen import (
    _target_expr,
    drain,
    generate_line,
    generate_script,
    inject_recorder,
)

# ---------------------------------------------------------------------------
# Pure-Python unit tests (no browser required)
# ---------------------------------------------------------------------------


def test_target_expr_role() -> None:
    t = {"kind": "role", "role": "button", "name": "Submit"}
    assert _target_expr(t) == "get_by_role('button', name='Submit')"


def test_target_expr_testid() -> None:
    t = {"kind": "testid", "value": "submit-btn"}
    assert _target_expr(t) == "get_by_test_id('submit-btn')"


def test_target_expr_css() -> None:
    t = {"kind": "css", "value": "#myid"}
    assert _target_expr(t) == "locator('#myid')"


def test_generate_line_click() -> None:
    ev = {"action": "click", "target": {"kind": "css", "value": "#btn"}}
    assert generate_line(ev) == "page.locator('#btn').click()"


def test_generate_line_fill() -> None:
    ev = {"action": "fill", "target": {"kind": "css", "value": "#inp"}, "value": "hello"}
    assert generate_line(ev) == "page.locator('#inp').fill('hello')"


def test_generate_line_select_option() -> None:
    ev = {"action": "select_option", "target": {"kind": "css", "value": "select"}, "value": "x"}
    line = generate_line(ev)
    assert ".select_option(value=" in line


def test_generate_line_unsupported() -> None:
    ev = {"action": "hover", "target": {"kind": "css", "value": "div"}}
    assert generate_line(ev).startswith("# unsupported:")


def test_generate_script_structure() -> None:
    events = [
        {"action": "click", "target": {"kind": "css", "value": "#btn"}},
    ]
    code = generate_script("https://example.com", events)
    assert "from visus.web import launch" in code
    assert "page.goto('https://example.com')" in code
    assert ".click()" in code


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
    assert "fill" in actions and "click" in actions, f"expected fill+click in {actions}"
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
