"""Pure-logic unit tests for the expect-engine matchers (no browser).

Covers the element-absent ("not present") and strict-mode branches of every
matcher by stubbing the frame-aware resolver.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from visus.web import errors
from visus.web.backends.selenium import resolver
from visus.web.backends.selenium.expect_engine import _evaluate, run_expect

_SEL = "[]"

_ARGS: dict[str, dict[str, object] | None] = {
    "text": {"value": "x", "exact": True},
    "value": {"value": "x", "exact": True},
    "attribute": {"name": "a", "value": "x", "exact": True},
    "class": {"value": "x", "mode": "exact"},
    "role": {"value": "button"},
    "focused": None,
    "empty": None,
    "in_viewport": None,
    "css": {"name": "display", "value": "block", "exact": True},
    "id": {"value": "x", "exact": True},
    "values": {"values": ["a"]},
}


def _patch_resolve(monkeypatch: pytest.MonkeyPatch, els: list[object]) -> None:
    monkeypatch.setattr(resolver, "resolve_elements", lambda d, e, s: els)


@pytest.mark.parametrize("matcher", sorted(_ARGS))
def test_single_element_matchers_absent_element(
    matcher: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolve(monkeypatch, [])
    ok, received = _evaluate(MagicMock(), lambda: None, _SEL, matcher, _ARGS[matcher])
    assert ok is False
    assert received == "not present"


@pytest.mark.parametrize("matcher", sorted(_ARGS))
def test_single_element_matchers_strict_violation(
    matcher: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_resolve(monkeypatch, [object(), object()])
    with pytest.raises(errors.StrictModeViolation):
        _evaluate(MagicMock(), lambda: None, _SEL, matcher, _ARGS[matcher])


def test_attached_detached_and_count(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, [])
    assert _evaluate(MagicMock(), lambda: None, _SEL, "attached", None)[0] is False
    assert _evaluate(MagicMock(), lambda: None, _SEL, "detached", None)[0] is True
    assert _evaluate(MagicMock(), lambda: None, _SEL, "count", {"count": 0})[0] is True
    _patch_resolve(monkeypatch, [object()])
    assert _evaluate(MagicMock(), lambda: None, _SEL, "attached", None)[0] is True
    assert _evaluate(MagicMock(), lambda: None, _SEL, "detached", None)[0] is False


def test_unknown_matcher_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_resolve(monkeypatch, [])
    with pytest.raises(ValueError):
        _evaluate(MagicMock(), lambda: None, _SEL, "bogus", None)


def test_run_expect_timeout_message_includes_received(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolve(monkeypatch, [])
    with pytest.raises(AssertionError) as ei:
        run_expect(
            MagicMock(),
            _SEL,
            "attached",
            None,
            is_not=False,
            timeout_ms=50,
            ensure_bundle=lambda: None,
        )
    assert "attached" in str(ei.value)
    assert "0 element(s)" in str(ei.value)
