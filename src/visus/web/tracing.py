"""Global tracing toggle + session manager for visus.web observability."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from visus.web.observability.recorder import Recorder


def _env_on() -> bool:
    return os.environ.get("VISUS_WEB_TRACING", "0").lower() not in ("0", "", "false", "no")


class _Tracing:
    def __init__(self) -> None:
        self.enabled: bool = _env_on()
        self.screenshot_each_action: bool = True  # per-action shots ON by default
        self.screenshot_on_failure: bool = True
        self.recorder: "Recorder | None" = None


_STATE = _Tracing()


def enable(**opts: Any) -> None:
    """Enable tracing, optionally setting options (screenshot_each_action, screenshot_on_failure)."""
    _STATE.enabled = True
    for k, v in opts.items():
        setattr(_STATE, k, v)


def disable() -> None:
    """Disable tracing globally."""
    _STATE.enabled = False


def is_enabled() -> bool:
    """Return True if tracing is currently enabled."""
    return _STATE.enabled


def current_recorder() -> "Recorder | None":
    """Return the active Recorder, or None if not inside a ``record()`` session."""
    return _STATE.recorder


def options() -> _Tracing:
    """Return the mutable options object."""
    return _STATE


@contextmanager
def record(zip_path: str, **opts: Any) -> "Iterator[Recorder]":
    """Context manager: enable tracing, collect events/screenshots, write zip on exit.

    Usage::

        with tracing.record("run.zip") as rec:
            page.goto(url)
            page.get_by_label("Name").fill("Ada")
    """
    from visus.web.observability.recorder import Recorder

    prev_enabled, prev_rec = _STATE.enabled, _STATE.recorder
    enable(**opts)
    rec = Recorder()
    _STATE.recorder = rec
    try:
        yield rec
    finally:
        _STATE.recorder = prev_rec
        _STATE.enabled = prev_enabled
        rec.write_zip(zip_path)


def render_report(zip_path: str, output: str = "report.html") -> str:
    """Render a self-contained HTML report from a tracing zip.

    Returns the path of the written HTML file.
    """
    from visus.web.observability.report import render_report as _render

    return _render(zip_path, output)
