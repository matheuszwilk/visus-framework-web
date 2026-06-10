"""Batteries-included RPA session — launch + record + report + summary, automatic.

The goal: the developer writes ONLY the automation; visus.web handles the rest.

    from visus.web import rpa

    with rpa("login", engine="firefox") as page:
        page.goto("https://example.com/login")
        page.get_by_label("User").fill("ada")
        page.get_by_role("button", name="Sign in").click()

On exit — whether the block finishes or a step fails — ``run.zip`` and
``report.html`` are written (to ``./visus-runs/<name>-<timestamp>/`` by default,
or *outdir*), a one-block summary is printed, and any error is re-raised so your
script/CI still sees the failure. No tempfile / zipfile / json / tracing plumbing
in your script.

For advanced cases (multiple pages, custom contexts) drop down to ``launch`` +
``tracing.record`` directly.
"""

from __future__ import annotations

import sys
import webbrowser
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import visus.web.tracing as tracing
from visus.web.engine import Engine

if TYPE_CHECKING:
    from visus.web.api.page import Page


def _slug(name: str) -> str:
    """Filesystem-safe label for the run folder."""
    kept = "".join(c if (c.isalnum() or c in "-_") else "-" for c in name).strip("-")
    return kept or "run"


@contextmanager
def rpa(
    name: str = "run",
    *,
    engine: Engine | str = Engine.CHROME,
    headless: bool = False,
    slow_mo: int = 0,
    user_data_dir: str | None = None,
    remote_url: str | None = None,
    outdir: str | None = None,
    report: bool = True,
    summary: bool = True,
    open_report: bool = False,
    reraise: bool = False,
) -> Iterator[Page]:
    """Run an RPA with launch, recording, the HTML report, and a summary handled for you.

    Yields a ready-to-drive :class:`~visus.web.api.page.Page`.

    Args:
        name: label for this run (used in the output folder name).
        engine: ``"chrome"`` | ``"edge"`` | ``"firefox"`` | ``"edge_ie"`` (or an :class:`Engine`).
        headless: run without a visible window.
        slow_mo: delay (ms) before each action/navigation — watch the run live.
        user_data_dir: persistent browser profile to reuse (cookies/logins survive
            across runs; the directory is never deleted by visus).
        remote_url: run on a Selenium Grid / Remote WebDriver instead of a local
            browser (e.g. ``"http://grid:4444/wd/hub"``).
        outdir: where to write run.zip/report.html (default ``./visus-runs/<name>-<ts>/``).
        report: render report.html on exit (it is written even when a step fails).
        summary: print a one-block run summary on exit.
        open_report: open report.html in the default browser on exit.
        reraise: on a failed step, re-raise the original :class:`~visus.web.errors.VisusWebError`
            (for programmatic handling). Default ``False``: the friendly summary already
            explains the failure, so the process just exits with code 1 — no internal
            traceback dumped to your console.
    """
    from visus.web import errors as _errors  # local import: avoid an import cycle
    from visus.web import launch

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = Path(outdir) if outdir else Path.cwd() / "visus-runs" / f"{_slug(name)}-{stamp}"
    base.mkdir(parents=True, exist_ok=True)
    zip_path = base / "run.zip"
    report_path = base / "report.html"

    box: dict[str, Any] = {}
    rpa_error: BaseException | None = None
    try:
        with tracing.record(str(zip_path), report=str(report_path) if report else None) as rec:
            box["rec"] = rec
            with launch(
                engine,
                headless=headless,
                slow_mo=slow_mo,
                user_data_dir=user_data_dir,
                remote_url=remote_url,
            ) as browser:
                yield browser.new_page()
    except (_errors.VisusWebError, AssertionError) as exc:
        # an action failure (VisusWebError) OR an expect()/assert failure → present it
        # cleanly (friendly summary + exit 1) instead of dumping an internal traceback.
        rpa_error = exc
    finally:
        recorder = box.get("rec")
        active = rpa_error if rpa_error is not None else sys.exc_info()[1]
        if summary and recorder is not None:
            _print_summary(recorder, base, report_path if report else None, error=active)
        if open_report and report:
            try:
                webbrowser.open(report_path.resolve().as_uri())
            except Exception:
                pass

    # Only reached when no *unexpected* exception is propagating. For a failed RPA
    # step: re-raise it if asked, otherwise exit cleanly with code 1 — the friendly
    # summary above already explained why, so there is no scary internal traceback.
    if rpa_error is not None:
        if reraise:
            raise rpa_error
        raise SystemExit(1)


def _print_summary(
    rec: Any, base: Path, report_path: Path | None, *, error: BaseException | None = None
) -> None:
    s = rec.summary()
    steps = ", ".join(f"{a}{'' if ok else '(FAILED)'}" for a, ok in s["steps"])
    status = "FAILED" if (error is not None or s["failures"]) else "OK"
    print(f"\n=== visus.web RPA [{status}] ===")
    print(f"actions   : {s['total']}")
    print(f"failures  : {s['failures']}")
    print(f"backtrack : {s['backtrack_steps']} step(s) replayed")
    if steps:
        print(f"steps     : {steps}")
    if error is not None:
        # surface the friendly action-error cleanly (indented), not buried in a traceback
        print("error     : " + "\n            ".join(str(error).splitlines()))
    print(f"folder    : {base}")
    if report_path is not None:
        print(f"report    : {report_path}")
