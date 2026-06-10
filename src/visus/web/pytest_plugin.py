"""pytest plugin for visus.web — browser fixtures with batteries included.

Installed automatically with the package (``pytest11`` entry point). Provides:

* ``visus_browser`` — session-scoped browser (engine/headed via CLI options)
* ``visus_context`` — function-scoped isolated context
* ``visus_page``    — function-scoped page; on test failure a screenshot is
  saved to ``--visus-output`` (default ``visus-results/``)
* soft assertions (``expect.soft``) are verified automatically at test end

Options::

    pytest --visus-engine=firefox --visus-headed --visus-output=artifacts
"""

from __future__ import annotations

import re
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from visus.web.api.browser import Browser
    from visus.web.api.context import Context
    from visus.web.api.page import Page


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("visus-web")
    group.addoption(
        "--visus-engine",
        default="chrome",
        help="browser engine for the visus fixtures (chrome|edge|firefox|edge_ie)",
    )
    group.addoption(
        "--visus-headed",
        action="store_true",
        default=False,
        help="run the visus browser headed (visible window)",
    )
    group.addoption(
        "--visus-output",
        default="visus-results",
        help="directory for on-failure screenshots (default: visus-results)",
    )


@pytest.fixture(scope="session")
def visus_browser(request: pytest.FixtureRequest) -> Iterator[Browser]:
    """A browser shared by the whole test session."""
    from visus.web import launch

    browser = launch(
        request.config.getoption("--visus-engine"),
        headless=not request.config.getoption("--visus-headed"),
    )
    yield browser
    browser.close()


@pytest.fixture()
def visus_context(visus_browser: Browser) -> Iterator[Context]:
    """A fresh, isolated context per test (own cookies/storage)."""
    ctx = visus_browser.new_context()
    yield ctx
    ctx.close()


@pytest.fixture()
def visus_page(
    visus_context: Context, request: pytest.FixtureRequest
) -> Iterator[Page]:
    """A fresh page per test. Saves a screenshot to --visus-output on failure."""
    page = visus_context.new_page()
    yield page
    rep = getattr(request.node, "_visus_rep_call", None)
    if rep is not None and rep.failed:
        outdir = Path(str(request.config.getoption("--visus-output")))
        outdir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.-]+", "-", request.node.nodeid)
        try:
            page.screenshot(path=str(outdir / f"{safe}.png"))
        except Exception:
            pass  # a dead page must not mask the original test failure


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, Any, None]:
    outcome = yield
    rep = outcome.get_result()  # type: ignore[attr-defined]
    if rep.when == "call":
        item._visus_rep_call = rep  # type: ignore[attr-defined]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None, Any, None]:
    """Verify soft assertions at the end of the test call phase.

    Raising here marks the TEST as failed (a teardown raise would only be an
    error). If the test already failed on its own, collected soft failures are
    drained silently so they cannot leak into the next test.
    """
    outcome = yield
    from visus.web.api.assertions import verify_soft

    try:
        verify_soft()
    except AssertionError:
        if outcome.excinfo is None:  # type: ignore[attr-defined]
            raise
