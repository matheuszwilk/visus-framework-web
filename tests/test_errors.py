import pytest

from visus.web import errors


def test_all_errors_subclass_base():
    for name in (
        "UnsupportedEngineError",
        "VisusTimeoutError",
        "NavigationError",
        "TargetClosedError",
    ):
        cls = getattr(errors, name)
        assert issubclass(cls, errors.VisusWebError)


def test_base_is_exception():
    assert issubclass(errors.VisusWebError, Exception)


def test_raisable_with_message():
    with pytest.raises(errors.NavigationError, match="boom"):
        raise errors.NavigationError("boom")
