"""Pure-logic unit tests for the run_step backtrack helper.

No browser, no mocks — exercises the real retry logic with counting actions.
"""

from __future__ import annotations

import pytest

from visus.web import errors
from visus.web.api._steps import run_step


def test_run_step_records_last_step() -> None:
    """After a successful call, the delegate stores the action as _last_step."""
    d = object.__new__(type("D", (), {}))
    calls: list[str] = []
    run_step(d, lambda: calls.append("a"), backtrack=False)
    assert calls == ["a"] and d._last_step is not None  # type: ignore[attr-defined]


def test_run_step_backtracks_then_succeeds() -> None:
    """On first failure, re-runs the previous step then retries; second attempt succeeds."""
    d = object.__new__(type("D", (), {}))
    log: list[str] = []
    d._last_step = lambda: log.append("prev")
    state = {"n": 0}

    def action() -> None:
        state["n"] += 1
        if state["n"] < 2:
            raise errors.VisusTimeoutError("fail")
        log.append("ok")

    run_step(d, action, backtrack=True)
    assert log == ["prev", "ok"]


def test_run_step_raises_when_backtrack_exhausted() -> None:
    """If the action keeps failing after all budget cycles, the error propagates."""
    d = object.__new__(type("D", (), {}))
    d._last_step = lambda: None

    def action() -> None:
        raise errors.VisusTimeoutError("always")

    with pytest.raises(errors.VisusTimeoutError):
        run_step(d, action, backtrack=2)


def test_no_backtrack_raises_immediately() -> None:
    """With backtrack=False, a previous step must never run; error raises straight away."""
    d = object.__new__(type("D", (), {}))
    d._last_step = lambda: pytest.fail("must not run prev")

    with pytest.raises(errors.VisusWebError):
        run_step(
            d,
            (lambda: (_ for _ in ()).throw(errors.VisusWebError("x"))),  # type: ignore[attr-defined]
            backtrack=False,
        )


def test_run_step_backtrack_n_cycles() -> None:
    """With backtrack=N, the helper re-runs prev up to N times before giving up."""
    d = object.__new__(type("D", (), {}))
    log: list[str] = []
    d._last_step = lambda: log.append("prev")
    state = {"n": 0}

    def action() -> None:
        state["n"] += 1
        if state["n"] < 3:
            raise errors.VisusTimeoutError("not yet")
        log.append("ok")

    run_step(d, action, backtrack=3)
    assert log == ["prev", "prev", "ok"]


def test_run_step_no_prev_raises_immediately() -> None:
    """If backtrack is truthy but no previous step is recorded, the error propagates."""
    d = object.__new__(type("D", (), {}))
    # no _last_step set on d

    def action() -> None:
        raise errors.VisusTimeoutError("fail")

    with pytest.raises(errors.VisusTimeoutError):
        run_step(d, action, backtrack=True)


def test_run_step_updates_last_step_to_new_action() -> None:
    """After a successful action, _last_step points to the NEW action, not the old one."""
    d = object.__new__(type("D", (), {}))
    log: list[str] = []
    first = lambda: log.append("first")  # noqa: E731
    second = lambda: log.append("second")  # noqa: E731

    run_step(d, first, backtrack=False)
    assert d._last_step is first  # type: ignore[attr-defined]

    run_step(d, second, backtrack=False)
    assert d._last_step is second  # type: ignore[attr-defined]
