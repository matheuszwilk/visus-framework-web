"""Backtrack helper for visus.web actions.

run_step() executes an action callable and, on VisusWebError, optionally
re-runs the last recorded successful step before retrying — up to int(backtrack)
cycles.  On success the action is recorded as the delegate's _last_step.

When tracing is active the step is timed and an event (+ screenshots) is emitted
via the active Recorder.  With tracing OFF the behaviour is byte-for-byte
identical to the pre-observability implementation.
"""

from __future__ import annotations

from collections.abc import Callable

from visus.web import errors


def run_step(
    delegate: object,
    action: Callable[[], None],
    backtrack: bool | int,
    *,
    action_name: str = "action",
    selector: str | None = None,
    target: str | None = None,
) -> None:
    """Run ``action()``.

    On :exc:`~visus.web.errors.VisusWebError`, if *backtrack* is truthy,
    re-run the previously recorded successful step (``delegate._last_step``) then retry
    ``action``, up to ``int(backtrack)`` cycles (``True`` → 1 cycle, ``N`` → up to N cycles).
    If still failing after all cycles, raise the error.

    On success, record ``action`` as the delegate's last successful step.

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
    """Fast path: unchanged backtrack semantics, zero tracing overhead."""
    budget = int(backtrack)  # False→0, True→1, N→N
    while True:
        try:
            action()
            break
        except errors.VisusWebError:
            prev: Callable[[], None] | None = getattr(delegate, "_last_step", None)
            if budget > 0 and prev is not None:
                budget -= 1
                prev()  # re-run the previous successful step (may raise → propagate)
                continue  # retry the action
            raise
    delegate._last_step = action  # type: ignore[attr-defined]


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

    start = time.monotonic()
    start_ts = time.time()
    budget = int(backtrack)
    cycles = 0
    error: str | None = None
    success = False
    try:
        while True:
            try:
                action()
                success = True
                break
            except errors.VisusWebError as exc:
                prev: Callable[[], None] | None = getattr(delegate, "_last_step", None)
                if budget > 0 and prev is not None:
                    budget -= 1
                    cycles += 1
                    prev()
                    continue
                error = str(exc)
                raise
        delegate._last_step = action  # type: ignore[attr-defined]
    finally:
        rec.record_action(
            delegate,
            action=action_name,
            selector=selector,
            target=target,
            start_ts=start_ts,
            end_ts=time.time(),
            duration_ms=int((time.monotonic() - start) * 1000),
            success=success,
            error=error,
            backtrack_cycles=cycles,
        )
