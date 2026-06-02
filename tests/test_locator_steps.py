import json

from visus.web.api.locator import Locator


class _RecordingDelegate:
    def __init__(self): self.last = None
    def locator_count(self, selector): self.last = selector; return 0
    def locator_is_visible(self, selector): self.last = selector; return False
    def locator_text_content(self, selector): self.last = selector; return None


def _steps(loc):
    return json.loads(loc._encoded)


def test_get_by_role_appends_step_immutably():
    d = _RecordingDelegate()
    root = Locator(d, (), None)
    btn = root.get_by_role("button", name="Sign in")
    assert _steps(root) == []  # original unchanged
    assert _steps(btn) == [{"kind": "role", "role": "button", "name": "Sign in", "exact": False}]


def test_chaining_and_nth_and_text():
    d = _RecordingDelegate()
    loc = Locator(d, (), None).locator("ul.menu").get_by_text("Logout").first()
    assert _steps(loc) == [
        {"kind": "css", "value": "ul.menu"},
        {"kind": "text", "value": "Logout", "exact": False},
        {"kind": "nth", "index": 0},
    ]


def test_locator_detects_xpath():
    d = _RecordingDelegate()
    loc = Locator(d, (), None).locator("//a[@id='x']")
    assert _steps(loc) == [{"kind": "xpath", "value": "//a[@id='x']"}]


def test_count_passes_encoded_steps_to_delegate():
    d = _RecordingDelegate()
    Locator(d, (), None).get_by_text("Hi").count()
    assert json.loads(d.last) == [{"kind": "text", "value": "Hi", "exact": False}]
