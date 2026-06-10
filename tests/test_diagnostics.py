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


def test_describe_composed_and_frame_and_smart_steps() -> None:
    inner = [{"kind": "css", "value": "input"}]
    assert describe_target(_sel({"kind": "filter_has", "steps": inner})) == 'has(css "input")'
    assert describe_target(_sel({"kind": "filter_has_not", "steps": inner})) == (
        'has not(css "input")'
    )
    assert describe_target(_sel({"kind": "or", "steps": inner})) == 'or(css "input")'
    assert describe_target(_sel({"kind": "and", "steps": inner})) == 'and(css "input")'
    assert describe_target(_sel({"kind": "filter_has_not_text", "value": "x"})) == (
        'filtered by NOT text "x"'
    )
    assert describe_target(_sel({"kind": "filter_has_text", "regex": "or.er"})) == (
        'filtered by text "or.er"'
    )
    assert describe_target(_sel({"kind": "frame", "frame": inner})) == "inside frame"
    smart = {"kind": "smart", "tag": "input", "candidates": [{"css": "#email"}]}
    assert "pasted element" in describe_target(_sel(smart))
    assert "#email" in describe_target(_sel(smart))


def test_build_action_error_did_you_mean_suggestion() -> None:
    from unittest.mock import MagicMock

    from visus.web.backends.selenium._diagnostics import build_action_error

    driver = MagicMock()
    driver.title = "T"
    driver.current_url = "u"
    driver.execute_script.return_value = [
        {"role": "button", "name": "Submit"},
        {"role": "button", "name": "Cancel"},
    ]
    msg = build_action_error(
        driver,
        _sel({"kind": "role", "role": "button", "name": "Submot", "exact": False}),
        "click",
        100,
        "not found",
    )
    assert "did you mean" in msg and "Submit" in msg


def test_build_action_error_lists_available_roles_without_close_match() -> None:
    from unittest.mock import MagicMock

    from visus.web.backends.selenium._diagnostics import build_action_error

    driver = MagicMock()
    driver.title = "T"
    driver.current_url = "u"
    driver.execute_script.return_value = [{"role": "button", "name": "Totally Different"}]
    msg = build_action_error(
        driver,
        _sel({"kind": "role", "role": "button", "name": "zzzz", "exact": False}),
        "click",
        100,
        "not found",
    )
    assert "buttons on this page" in msg


def test_build_action_error_text_step_suggestion_and_snapshot_failure() -> None:
    from unittest.mock import MagicMock

    from visus.web.backends.selenium._diagnostics import build_action_error

    driver = MagicMock()
    driver.title = "T"
    driver.current_url = "u"
    driver.execute_script.return_value = [{"role": "link", "name": "Sign in"}]
    msg = build_action_error(
        driver, _sel({"kind": "text", "value": "Sign im"}), "click", 100, "not found"
    )
    assert "did you mean" in msg

    broken = MagicMock()
    broken.title = "T"
    broken.current_url = "u"
    broken.execute_script.side_effect = RuntimeError("no page")
    msg2 = build_action_error(
        broken, _sel({"kind": "css", "value": "#a"}), "fill", 100, "not visible (hidden)"
    )
    assert "never became actionable" in msg2
