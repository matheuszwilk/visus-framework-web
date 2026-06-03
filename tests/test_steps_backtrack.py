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
    """Depth replay then EXACTLY one retry — never a retry loop.

    With a 3-step history and backtrack=3 on an always-failing action: the three
    previous steps each replay exactly once, the action runs exactly twice
    (one initial attempt + one retry), then the error propagates. This is the key
    difference from the old retry-loop ("cycles") behaviour, which would have run
    the action 4 times and replayed steps repeatedly.
    """
    d = _delegate()
    replays = {"s1": 0, "s2": 0, "s3": 0}
    d._step_history = [  # type: ignore[attr-defined]
        lambda: replays.__setitem__("s1", replays["s1"] + 1),
        lambda: replays.__setitem__("s2", replays["s2"] + 1),
        lambda: replays.__setitem__("s3", replays["s3"] + 1),
    ]
    action_calls = {"n": 0}

    def action() -> None:
        action_calls["n"] += 1
        raise errors.VisusTimeoutError("always fails")

    with pytest.raises(errors.VisusTimeoutError):
        run_step(d, action, backtrack=3)

    assert action_calls["n"] == 2  # one initial attempt + exactly one retry (no loop)
    assert replays == {"s1": 1, "s2": 1, "s3": 1}  # each prior step replayed exactly once


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


def test_failed_backtrack_still_records_steps_under_tracing(tmp_path) -> None:
    """A backtrack that fails is still recorded: the traced event shows how many
    steps it replayed, so 'it failed and retried' is visible in the report."""
    import json
    import zipfile

    from visus.web import tracing

    d = _delegate()
    d._step_history = [lambda: None, lambda: None, lambda: None]  # type: ignore[attr-defined]

    def action() -> None:
        raise errors.VisusTimeoutError("never works")

    zip_path = tmp_path / "run.zip"
    with pytest.raises(errors.VisusTimeoutError):
        with tracing.record(str(zip_path)):
            run_step(d, action, backtrack=3, action_name="click", selector="sel")

    z = zipfile.ZipFile(str(zip_path))
    events = [json.loads(x) for x in z.read("events.jsonl").decode().splitlines() if x.strip()]
    assert events, "expected a recorded event"
    failed = events[-1]
    assert failed["success"] is False
    assert failed["backtrack_steps"] == 3  # backtrack tried 3 steps even though it failed


def test_backtrack_records_depth_even_when_a_replay_fails() -> None:
    """If a replayed step itself fails (the page moved on), the attempted depth is still tagged."""
    d = _delegate()

    def bad_replay() -> None:
        raise errors.VisusTimeoutError("this step no longer exists on the page")

    d._step_history = [bad_replay, lambda: None, lambda: None]  # type: ignore[attr-defined]

    def action() -> None:
        raise errors.VisusTimeoutError("original failure")

    with pytest.raises(errors.VisusTimeoutError) as exc:
        run_step(d, action, backtrack=3)
    assert getattr(exc.value, "backtrack_steps", None) == 3  # depth-3 backtrack was attempted
