import pytest
from visus.web.engine import Engine
from visus.web.errors import UnsupportedEngineError


def test_members():
    assert Engine.CHROME.value == "chrome"
    assert {e.value for e in Engine} == {"chrome", "edge", "firefox", "edge_ie"}


def test_from_str_accepts_enum_and_string():
    assert Engine.from_str("chrome") is Engine.CHROME
    assert Engine.from_str(Engine.FIREFOX) is Engine.FIREFOX
    assert Engine.from_str("CHROME") is Engine.CHROME


def test_from_str_rejects_unknown():
    with pytest.raises(UnsupportedEngineError, match="webkit"):
        Engine.from_str("webkit")
