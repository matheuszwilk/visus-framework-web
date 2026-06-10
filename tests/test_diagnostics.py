"""Unit tests for the friendly action-error diagnostics (pure, no browser)."""

from __future__ import annotations

import json

from visus.web.backends.selenium._diagnostics import describe_target


def _sel(*steps: dict[str, object]) -> str:
    return json.dumps(list(steps))


def test_describe_role_with_name() -> None:
    s = _sel({"kind": "role", "role": "button", "name": "Submit", "exact": False})
    assert describe_target(s) == 'role "button" named "Submit"'


def test_describe_role_without_name() -> None:
    assert describe_target(_sel({"kind": "role", "role": "textbox"})) == 'role "textbox"'


def test_describe_css_and_xpath() -> None:
    assert describe_target(_sel({"kind": "css", "value": "#go"})) == 'css "#go"'
    assert describe_target(_sel({"kind": "xpath", "value": "//a"})) == 'xpath "//a"'


def test_describe_text_label_placeholder_testid() -> None:
    assert describe_target(_sel({"kind": "text", "value": "Hi"})) == 'text "Hi"'
    assert describe_target(_sel({"kind": "label", "value": "Email"})) == 'label "Email"'
    assert describe_target(_sel({"kind": "placeholder", "value": "Find"})) == 'placeholder "Find"'
    assert describe_target(_sel({"kind": "testid", "value": "row"})) == 'test-id "row"'


def test_describe_chain_with_nth() -> None:
    s = _sel(
        {"kind": "css", "value": "ul.menu"},
        {"kind": "text", "value": "Logout"},
        {"kind": "nth", "index": 0},
    )
    assert describe_target(s) == 'css "ul.menu" » text "Logout" » (first)'


def test_describe_falls_back_on_bad_json() -> None:
    assert describe_target("not-json") == "not-json"


def test_describe_smart_pasted_element() -> None:
    from visus.web.api._htmlsel import smart_step

    sel = json.dumps([smart_step('<input id="email" name="e" type="text">')])
    desc = describe_target(sel)
    assert "pasted element" in desc
    assert "input" in desc


def test_build_action_error_includes_wait_log() -> None:
    from unittest.mock import MagicMock

    from visus.web.backends.selenium._diagnostics import build_action_error

    driver = MagicMock()
    driver.title = "My Page"
    driver.current_url = "https://x.test"
    driver.execute_script.return_value = []
    msg = build_action_error(
        driver,
        _sel({"kind": "css", "value": "#go"}),
        "click",
        5000,
        "element intercepts pointer events (occluded)",
        wait_log=[
            (0.0, "not visible (hidden)"),
            (1.2, "not stable (still animating)"),
            (2.5, "element intercepts pointer events (occluded)"),
        ],
    )
    assert "log:" in msg
    assert "0.0s not visible (hidden)" in msg
    assert "1.2s not stable (still animating)" in msg
    assert "2.5s element intercepts pointer events (occluded)" in msg


def test_build_action_error_without_wait_log_unchanged() -> None:
    from unittest.mock import MagicMock

    from visus.web.backends.selenium._diagnostics import build_action_error

    driver = MagicMock()
    driver.title = "T"
    driver.current_url = "u"
    driver.execute_script.return_value = []
    msg = build_action_error(driver, _sel({"kind": "css", "value": "#a"}), "fill", 100, "not found")
    assert "log:" not in msg
