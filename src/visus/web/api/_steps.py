"""Backtrack helper for visus.web actions.

run_step() executes an action callable and, on VisusWebError, optionally
re-runs the last recorded successful step before retrying — up to int(backtrack)
cycles.  On success the action is recorded as the delegate's _last_step.
"""

from __future__ import annotations

from collections.abc import Callable

from visus.web import errors


def run_step(delegate: object, action: Callable[[], None], backtrack: bool | int) -> None:
    """Run ``action()``. On :exc:`~visus.web.errors.VisusWebError`, if *backtrack* is truthy,
    re-run the previously recorded successful step (``delegate._last_step``) then retry
    ``action``, up to ``int(backtrack)`` cycles (``True`` → 1 cycle, ``N`` → up to N cycles).
    If still failing after all cycles, raise the error.

    On success, record ``action`` as the delegate's last successful step.
    """
    budget = int(backtrack)  # False→0, True→1, N→N
    while True:
        try:
            action()
            break
        except errors.VisusWebError:
            prev: Callable[[], None] | None = getattr(delegate, "_last_step", None)
            if budget > 0 and prev is not None:
                budget -= 1
                prev()      # re-run the previous successful step (may raise → propagate)
                continue    # retry the action
            raise
    delegate._last_step = action  # type: ignore[attr-defined]
