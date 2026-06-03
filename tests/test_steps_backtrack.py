"""Pure-logic unit tests for the run_step backtrack helper (depth semantics).

No browser, no mocks — exercises the real replay-then-retry logic with counting
actions.  ``backtrack`` is a DEPTH: re-run the last N successful steps (oldest→
newest), then retry the failed step ONCE.  It is NOT a retry loop.
"""

from __future__ import annotations

import pytest

from visus.web import errors
from visus.web.api._steps import MAX_BACKTRACK, _coerce_depth, run_step


def _delegate() -> object:
    """A bare object that can carry a ._step_history attribute."""
    return object.__new__(type("D", (), {}))


# --- depth coercion ---------------------------------------------------------


def test_coerce_depth_maps_values() -> None:
    assert _coerce_depth(False) == 0
    assert _coerce_depth(0) == 0
    assert _coerce_depth(True) == 1
    assert _coerce_depth(1) == 1
    assert _coerce_depth(2) == 2
    assert _coerce_depth(3) == 3
    assert _coerce_depth(4) == MAX_BACKTRACK  # capped at 3
    assert _coerce_depth(99) == MAX_BACKTRACK
    assert _coerce_depth(-5) == 0  # clamped to 0


# --- history bookkeeping ----------------------------------------------------


def test_records_step_history() -> None:
    d = _delegate()
    calls: list[str] = []
    run_step(d, lambda: calls.append("a"), backtrack=False)
    assert calls == ["a"]
    assert len(d._step_history) == 1  # type: ignore[attr-defined]


def test_history_capped_at_three() -> None:
    d = _delegate()
    for _ in range(5):
        run_step(d, lambda: None, backtrack=False)
    assert len(d._step_history) == MAX_BACKTRACK  # type: ignore[attr-defined]


def test_history_tracks_most_recent_step() -> None:
    d = _delegate()
    first = lambda: None  # noqa: E731
    second = lambda: None  # noqa: E731
    run_step(d, first, backtrack=False)
    assert d._step_history[-1] is first  # type: ignore[attr-defined]
    run_step(d, second, backtrack=False)
    assert d._step_history[-1] is second  # type: ignore[attr-defined]


# --- depth backtrack --------------------------------------------------------


def test_depth_one_replays_previous_step_then_retries() -> None:
    """backtrack=True (depth 1) re-runs the previous step, then the retry succeeds."""
    d = _delegate()
    log: list[str] = []
    d._step_history = [lambda: log.append("prev")]  # type: ignore[attr-defined]
    state = {"n": 0}

    def action() -> None:
        state["n"] += 1
        if state["n"] < 2:
            raise errors.VisusTimeoutError("not yet")
        log.append("ok")

    run_step(d, action, backtrack=True)
    assert log == ["prev", "ok"]


def test_depth_three_replays_three_previous_steps_in_order() -> None:
    """backtrack=3 replays the last 3 steps (oldest→newest) then retries once.

    Mirrors the user example: steps 1,2,3,4 where 4 fails → replay 1,2,3 then 4.
    """
    d = _delegate()
    log: list[str] = []
    d._step_history = [  # type: ignore[attr-defined]
        lambda: log.append("s1"),
        lambda: log.append("s2"),
        lambda: log.append("s3"),
    ]
    state = {"n": 0}

    def action() -> None:
        state["n"] += 1
        if state["n"] < 2:
            raise errors.VisusTimeoutError("not yet")
        log.append("ok")

    run_step(d, action, backtrack=3)
    assert log == ["s1", "s2", "s3", "ok"]


def test_depth_two_replays_only_last_two_steps() -> None:
    """backtrack=2 replays the *last two* steps (s2, s3) — never s1."""
    d = _delegate()
    log: list[str] = []
    d._step_history = [  # type: ignore[attr-defined]
        lambda: log.append("s1"),
        lambda: log.append("s2"),
        lambda: log.append("s3"),
    ]
    state = {"n": 0}

    def action() -> None:
        state["n"] += 1
        if state["n"] < 2:
            raise errors.VisusTimeoutError("not yet")
        log.append("ok")

    run_step(d, action, backtrack=2)
    assert log == ["s2", "s3", "ok"]


def test_backtrack_retries_only_once_no_loop() -> None:
    """The failed step is retried EXACTLY once: prev replays once, then the error raises.

    This is the key difference from a retry loop — backtrack is depth, not cycles.
    """
    d = _delegate()
    prev_calls = {"n": 0}

    def prev() -> None:
        prev_calls["n"] += 1

    d._step_history = [prev]  # type: ignore[attr-defined]

    def action() -> None:
        raise errors.VisusTimeoutError("always fails")

    with pytest.raises(errors.VisusTimeoutError):
        run_step(d, action, backtrack=3)  # depth 3, but only 1 step in history
    assert prev_calls["n"] == 1  # replayed once, NOT three times


def test_no_backtrack_raises_immediately() -> None:
    """backtrack=False must never replay a previous step."""
    d = _delegate()
    d._step_history = [lambda: pytest.fail("must not replay")]  # type: ignore[attr-defined]

    def action() -> None:
        raise errors.VisusWebError("x")

    with pytest.raises(errors.VisusWebError):
        run_step(d, action, backtrack=False)


def test_backtrack_with_no_history_raises() -> None:
    """backtrack truthy but no recorded steps → the error propagates."""
    d = _delegate()  # no _step_history recorded yet

    def action() -> None:
        raise errors.VisusTimeoutError("fail")

    with pytest.raises(errors.VisusTimeoutError):
        run_step(d, action, backtrack=True)
