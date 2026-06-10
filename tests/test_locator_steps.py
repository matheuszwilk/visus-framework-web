import json
import re

import pytest

from visus.web.api.locator import Locator
from visus.web.config import Defaults

_DEFAULTS = Defaults()


class _RecordingDelegate:
    def __init__(self):
        self.last = None

    def locator_count(self, selector):
        self.last = selector
        return 0

    def locator_is_visible(self, selector):
        self.last = selector
        return False

    def locator_text_content(self, selector):
        self.last = selector
        return None

    def locator_click(self, selector, *, timeout_ms, force):
        self.last = selector

    def locator_fill(self, selector, value, *, timeout_ms, force):
        self.last = selector

    def locator_input_value(self, selector):
        self.last = selector
        return ""


def _steps(loc):
    return json.loads(loc._encoded)


def test_locator_css_and_xpath_prefixes():
    d = _RecordingDelegate()

    def mk(sel):
        return _steps(Locator(d, (), _DEFAULTS).locator(sel))

    assert mk("css=.item") == [{"kind": "css", "value": ".item"}]
    assert mk(".item") == [{"kind": "css", "value": ".item"}]
    assert mk("xpath=//a") == [{"kind": "xpath", "value": "//a"}]
    assert mk("//a") == [{"kind": "xpath", "value": "//a"}]


def test_get_by_role_appends_step_immutably():
    d = _RecordingDelegate()
    root = Locator(d, (), _DEFAULTS)
    btn = root.get_by_role("button", name="Sign in")
    assert _steps(root) == []  # original unchanged
    assert _steps(btn) == [{"kind": "role", "role": "button", "name": "Sign in", "exact": False}]


def test_chaining_and_nth_and_text():
    d = _RecordingDelegate()
    loc = Locator(d, (), _DEFAULTS).locator("ul.menu").get_by_text("Logout").first()
    assert _steps(loc) == [
        {"kind": "css", "value": "ul.menu"},
        {"kind": "text", "value": "Logout", "exact": False},
        {"kind": "nth", "index": 0},
    ]


def test_locator_detects_xpath():
    d = _RecordingDelegate()
    loc = Locator(d, (), _DEFAULTS).locator("//a[@id='x']")
    assert _steps(loc) == [{"kind": "xpath", "value": "//a[@id='x']"}]


def test_count_passes_encoded_steps_to_delegate():
    d = _RecordingDelegate()
    Locator(d, (), _DEFAULTS).get_by_text("Hi").count()
    assert json.loads(d.last) == [{"kind": "text", "value": "Hi", "exact": False}]


def test_locator_xpath_prefix():
    d = _RecordingDelegate()
    loc = Locator(d, (), _DEFAULTS).locator("xpath=//div")
    assert _steps(loc) == [{"kind": "xpath", "value": "//div"}]


def test_filter_with_no_args_returns_same_locator():
    d = _RecordingDelegate()
    loc = Locator(d, (), _DEFAULTS).get_by_text("foo")
    filtered = loc.filter()
    assert _steps(filtered) == _steps(loc)


def test_first_last_nth_steps():
    d = _RecordingDelegate()
    base = Locator(d, (), _DEFAULTS).get_by_text("item")
    text_step = {"kind": "text", "value": "item", "exact": False}
    assert _steps(base.first()) == [text_step, {"kind": "nth", "index": 0}]
    assert _steps(base.last()) == [text_step, {"kind": "nth", "index": -1}]
    assert _steps(base.nth(2)) == [text_step, {"kind": "nth", "index": 2}]


def test_get_by_text_regex_encodes_pattern():
    d = _RecordingDelegate()
    loc = Locator(d, (), _DEFAULTS).get_by_text(re.compile(r"Sub\w+", re.IGNORECASE))
    assert _steps(loc) == [{"kind": "text", "regex": r"Sub\w+", "flags": "i"}]


def test_get_by_label_regex_multiline_dotall_flags():
    d = _RecordingDelegate()
    loc = Locator(d, (), _DEFAULTS).get_by_label(re.compile("a.b", re.MULTILINE | re.DOTALL))
    assert _steps(loc) == [{"kind": "label", "regex": "a.b", "flags": "ms"}]


def test_get_by_role_name_regex():
    d = _RecordingDelegate()
    loc = Locator(d, (), _DEFAULTS).get_by_role("button", name=re.compile("ok"))
    assert _steps(loc) == [
        {"kind": "role", "role": "button", "nameRegex": "ok", "nameFlags": ""}
    ]


def test_filter_has_text_regex():
    d = _RecordingDelegate()
    loc = Locator(d, (), _DEFAULTS).locator("ul").filter(has_text=re.compile("item"))
    assert _steps(loc)[-1] == {"kind": "filter_has_text", "regex": "item", "flags": ""}


def test_or_and_and_embed_steps():
    d = _RecordingDelegate()
    a = Locator(d, (), _DEFAULTS).locator("#a")
    b = Locator(d, (), _DEFAULTS).locator("#b")
    assert _steps(a.or_(b)) == [
        {"kind": "css", "value": "#a"},
        {"kind": "or", "steps": [{"kind": "css", "value": "#b"}]},
    ]
    assert _steps(a.and_(b))[-1] == {"kind": "and", "steps": [{"kind": "css", "value": "#b"}]}


def test_filter_has_and_has_not_embed_steps():
    d = _RecordingDelegate()
    root = Locator(d, (), _DEFAULTS).locator("form")
    inner = Locator(d, (), _DEFAULTS).locator("input")
    assert _steps(root.filter(has=inner))[-1] == {
        "kind": "filter_has",
        "steps": [{"kind": "css", "value": "input"}],
    }
    assert _steps(root.filter(has_not=inner))[-1] == {
        "kind": "filter_has_not",
        "steps": [{"kind": "css", "value": "input"}],
    }
    assert _steps(root.filter(has_not_text="x"))[-1] == {
        "kind": "filter_has_not_text",
        "value": "x",
        "exact": False,
    }


def test_filter_combines_multiple_conditions():
    d = _RecordingDelegate()
    inner = Locator(d, (), _DEFAULTS).locator("input")
    loc = Locator(d, (), _DEFAULTS).locator("form").filter(has_text="a", has=inner)
    kinds = [s["kind"] for s in _steps(loc)]
    assert kinds == ["css", "filter_has_text", "filter_has"]


def test_compose_rejects_frame_locators():
    d = _RecordingDelegate()
    a = Locator(d, (), _DEFAULTS).locator("#a")
    framed = Locator(
        d, ({"kind": "frame", "frame": [{"kind": "css", "value": "iframe"}]},), _DEFAULTS
    ).locator("#x")
    with pytest.raises(ValueError):
        a.or_(framed)
    with pytest.raises(ValueError):
        a.and_(framed)
    with pytest.raises(ValueError):
        a.filter(has=framed)


def test_expect_passes_matcher_and_negation_to_delegate():
    from visus.web import expect
    from visus.web.config import Defaults

    class RecExpect:
        def __init__(self):
            self.calls = []

        def locator_count(self, s):
            return 0

        def locator_is_visible(self, s):
            return False

        def locator_text_content(self, s):
            return None

        def locator_click(self, s, *, timeout_ms, force): ...
        def locator_fill(self, s, v, *, timeout_ms, force): ...
        def locator_input_value(self, s):
            return ""

        def expect_poll(self, s, matcher, arg, *, is_not, timeout_ms):
            self.calls.append((matcher, arg, is_not, timeout_ms))

    d = RecExpect()
    loc = Locator(d, ({"kind": "css", "value": "#x"},), Defaults())
    expect(loc).to_be_visible()
    expect(loc).not_.to_be_visible()
    expect(loc).to_have_text("Hi")
    assert d.calls[0] == ("visible", None, False, 5000)
    assert d.calls[1] == ("visible", None, True, 5000)
    assert d.calls[2] == ("text", {"value": "Hi", "exact": True}, False, 5000)


class _FailingExpect:
    def expect_poll(self, s, matcher, arg, *, is_not, timeout_ms):
        raise AssertionError("inner detail")


def test_expect_message_prefixes_assertion_error():
    from visus.web import expect

    loc = Locator(_FailingExpect(), ({"kind": "css", "value": "#x"},), _DEFAULTS)
    with pytest.raises(AssertionError) as ei:
        expect(loc, "should show the cart").to_be_visible(timeout=1)
    assert "should show the cart" in str(ei.value)
    assert "inner detail" in str(ei.value)


def test_expect_soft_collects_and_verify_raises_once():
    from visus.web import expect

    loc = Locator(_FailingExpect(), ({"kind": "css", "value": "#x"},), _DEFAULTS)
    expect.soft(loc).to_be_visible(timeout=1)  # does NOT raise
    expect.soft(loc, "second check").to_have_text("x", timeout=1)
    with pytest.raises(AssertionError) as ei:
        expect.verify_soft()
    assert "2 soft assertion" in str(ei.value)
    assert "second check" in str(ei.value)
    expect.verify_soft()  # collector was reset — no failures left


def test_expect_text_and_value_accept_regex():
    from visus.web import expect
    from visus.web.config import Defaults

    class RecExpect:
        def __init__(self):
            self.calls = []

        def expect_poll(self, s, matcher, arg, *, is_not, timeout_ms):
            self.calls.append((matcher, arg, is_not))

    d = RecExpect()
    loc = Locator(d, ({"kind": "css", "value": "#x"},), Defaults())
    expect(loc).to_have_text(re.compile("Hi", re.IGNORECASE))
    expect(loc).to_contain_text(re.compile("part"))
    expect(loc).to_have_value(re.compile(r"\d+"))
    expect(loc).to_have_attribute("href", re.compile("example"))
    flags_i = re.compile("Hi", re.IGNORECASE).flags
    assert d.calls[0] == ("text", {"regex": "Hi", "flags": flags_i}, False)
    assert d.calls[1] == ("text", {"regex": "part", "flags": re.compile("part").flags}, False)
    assert d.calls[2] == ("value", {"regex": r"\d+", "flags": re.compile(r"\d+").flags}, False)
    assert d.calls[3] == (
        "attribute",
        {"name": "href", "regex": "example", "flags": re.compile("example").flags},
        False,
    )


def test_frame_locator_builders_and_xpath_frame_step():
    from visus.web.api.frame_locator import FrameLocator, _frame_step

    assert _frame_step("//ifr") == {
        "kind": "frame",
        "frame": [{"kind": "xpath", "value": "//ifr"}],
    }
    assert _frame_step("xpath=//f")["frame"] == [{"kind": "xpath", "value": "//f"}]
    assert _frame_step("css=#f")["frame"] == [{"kind": "css", "value": "#f"}]

    d = _RecordingDelegate()
    fl = FrameLocator(d, (_frame_step("#f"),), _DEFAULTS)
    assert _steps(fl.get_by_text("Hi"))[-1] == {"kind": "text", "value": "Hi", "exact": False}
    assert _steps(fl.get_by_label("Email"))[-1]["kind"] == "label"
    assert _steps(fl.get_by_test_id("row"))[-1] == {"kind": "testid", "value": "row"}
    assert _steps(fl.get_by_role("button", name="Go"))[-1]["kind"] == "role"
