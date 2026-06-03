"""Backtrack helper for visus.web actions.

run_step() executes an action and, on VisusWebError, optionally *backtracks*: it
re-runs the last N successful steps (oldest→newest), then retries the failed step
**once**.  ``backtrack`` is the depth — how many previous steps to replay before
retrying:

* ``False`` / ``0`` → disabled (the error propagates immediately)
* ``True``          → replay 1 previous step (the default depth)
* ``N``             → replay the last ``min(N, 3)`` steps

Example — steps 1, 2, 3, 4 where step 4 fails:
  ``backtrack=3`` re-runs 1, 2, 3 (in order) then retries 4;
  ``backtrack=1`` re-runs 3 then retries 4.

Backtrack is **not** a retry loop: the failed step is retried exactly once after
the replay.  Each delegate carries a rolling history of its last 3 successful
steps, so this behaves identically for the sync and async (to_thread) APIs.

When tracing is active the step is timed and an event (+ screenshots) is emitted
via the active Recorder.  With tracing OFF the behaviour is the same minus the
recording overhead.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from visus.web import errors

_log = logging.getLogger("visus.web")

MAX_BACKTRACK = 3  # how many previous steps the engine remembers and can replay


def _coerce_depth(backtrack: bool | int) -> int:
    """Backtrack depth: False/0 → 0 (off), True → 1, N → min(N, MAX_BACKTRACK)."""
    return max(0, min(int(backtrack), MAX_BACKTRACK))


def _record_step(delegate: object, action: Callable[[], None]) -> None:
    """Append a successful action to the delegate's rolling step history (last 3)."""
    history: list[Callable[[], None]] | None = getattr(delegate, "_step_history", None)
    if history is None:
        history = []
        delegate._step_history = history  # type: ignore[attr-defined]
    history.append(action)
    del history[:-MAX_BACKTRACK]  # keep only the most recent MAX_BACKTRACK steps


def _execute(delegate: object, action: Callable[[], None], depth: int) -> int:
    """Run ``action`` once; backtrack on failure.

    On :exc:`~visus.web.errors.VisusWebError`, if *depth* > 0, re-run the last
    *depth* successful steps (oldest→newest) then retry ``action`` exactly once.
    Returns the number of steps replayed (0 when the action succeeded on the first
    try).  Records the action as a successful step on success; re-raises if it
    still fails or if there is nothing to backtrack to.
    """
    try:
        action()
    except errors.VisusWebError:
        history: list[Callable[[], None]] = list(getattr(delegate, "_step_history", None) or [])
        replay = history[-depth:] if depth > 0 else []
        if not replay:
            raise  # backtrack disabled, or no previous step to return to
        attempted = len(replay)
        _log.info("backtrack: replaying %d previous step(s) before retry", attempted)
        in_replay = True
        try:
            for step in replay:
                step()  # re-run the previous step(s)
            in_replay = False
            action()  # then retry the failed step ONCE
        except errors.VisusWebError as exc:
            # A depth-N backtrack was attempted; tag it so the traced report records
            # the backtrack even when a replayed step (or the retry) ultimately fails.
            exc.backtrack_steps = attempted  # type: ignore[attr-defined]
            if in_replay:
                _log.warning("backtrack: a replayed step failed — the page may have moved on")
            raise
        _record_step(delegate, action)
        return attempted
    _record_step(delegate, action)
    return 0


def run_step(
    delegate: object,
    action: Callable[[], None],
    backtrack: bool | int,
    *,
    action_name: str = "action",
    selector: str | None = None,
    target: str | None = None,
) -> None:
    """Run ``action()`` with optional backtrack recovery.

    On :exc:`~visus.web.errors.VisusWebError`, if *backtrack* is truthy, re-run
    the last ``int(backtrack)`` (capped at 3) successful steps then retry
    ``action`` once.  ``True`` → depth 1.  On success, record ``action`` as the
    delegate's most recent successful step.

    *action_name*, *selector*, and *target* are forwarded to the :class:`Recorder`
    when tracing is active; they are ignored on the fast path.
    """
    from visus.web import tracing

    if not tracing.is_enabled() or tracing.current_recorder() is None:
        _run_plain(delegate, action, backtrack)
        return

    _run_traced(
        delegate,
        action,
        backtrack,
        action_name=action_name,
        selector=selector,
        target=target,
    )


def _run_plain(delegate: object, action: Callable[[], None], backtrack: bool | int) -> None:
    """Fast path: replay-then-retry backtrack with zero tracing overhead."""
    _execute(delegate, action, _coerce_depth(backtrack))


def _run_traced(
    delegate: object,
    action: Callable[[], None],
    backtrack: bool | int,
    *,
    action_name: str,
    selector: str | None,
    target: str | None,
) -> None:
    """Traced path: same semantics as _run_plain but times the step and records an event."""
    import time

    from visus.web import tracing

    rec = tracing.current_recorder()
    # rec should not be None here (caller checked), but guard defensively
    if rec is None:
        _run_plain(delegate, action, backtrack)
        return

    depth = _coerce_depth(backtrack)
    start = time.monotonic()
    start_ts = time.time()
    steps_replayed = 0
    error: str | None = None
    success = False
    label = target or selector or ""
    _log.info("%s → %s", action_name, label)
    try:
        steps_replayed = _execute(delegate, action, depth)
        success = True
    except errors.VisusWebError as exc:
        error = str(exc)
        steps_replayed = getattr(exc, "backtrack_steps", 0)  # backtrack tried but failed
        raise
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        if success:
            _log.info("%s ✓ (%dms, back %d step(s))", action_name, duration_ms, steps_replayed)
        else:
            _log.warning("%s ✗ %s", action_name, error or "")
        rec.record_action(
            delegate,
            action=action_name,
            selector=selector,
            target=target,
            start_ts=start_ts,
            end_ts=time.time(),
            duration_ms=duration_ms,
            success=success,
            error=error,
            backtrack_steps=steps_replayed,
        )
