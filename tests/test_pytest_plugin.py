"""The shipped pytest plugin: fixtures, screenshot-on-failure, soft-assert check.

Uses pytester to run an isolated inner pytest session (the plugin is loaded via
the installed ``pytest11`` entry point). The inner session overrides
``visus_browser`` with a stub so no real browser is needed — the plugin logic
under test (option wiring, report hook, on-failure screenshot, soft-assert
verification) is identical either way.
"""

from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]

_INNER_CONFTEST = """
import pytest


class StubPage:
    def goto(self, url):
        self.url = url

    def screenshot(self, *, path=None, full_page=False):
        if path is not None:
            with open(path, "wb") as f:
                f.write(b"PNG-STUB")
        return b"PNG-STUB"


class StubContext:
    def new_page(self):
        return StubPage()

    def close(self):
        pass


class StubBrowser:
    def new_context(self):
        return StubContext()

    def close(self):
        pass


@pytest.fixture(scope="session")
def visus_browser():
    b = StubBrowser()
    yield b
    b.close()
"""

_INNER_TESTS = """
def test_ok(visus_page):
    visus_page.goto("data:text/html,<h1>ok</h1>")
    assert visus_page.url.endswith("ok</h1>")


def test_fails(visus_page):
    visus_page.goto("data:text/html,<h1>bad</h1>")
    assert False, "intentional failure"


def test_soft_failure_is_verified(visus_page):
    from visus.web import expect
    from visus.web.api.locator import Locator
    from visus.web.config import Defaults

    class FailingDelegate:
        def expect_poll(self, s, matcher, arg, *, is_not, timeout_ms):
            raise AssertionError("soft inner failure")

    loc = Locator(FailingDelegate(), ({"kind": "css", "value": "#x"},), Defaults())
    expect.soft(loc).to_be_visible(timeout=1)
    # no direct raise here — the plugin's verify_soft() must fail the test
"""


def test_plugin_options_registered(pytester: pytest.Pytester) -> None:
    result = pytester.runpytest("--help")
    result.stdout.fnmatch_lines(["*--visus-engine*", "*--visus-headed*", "*--visus-output*"])


def test_fixtures_screenshot_on_failure_and_soft(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_INNER_CONFTEST)
    pytester.makepyfile(_INNER_TESTS)
    out = pytester.path / "artifacts"
    result = pytester.runpytest("--visus-output", str(out), "-p", "no:cacheprovider")
    result.assert_outcomes(passed=1, failed=2)
    names = {p.name for p in out.glob("*.png")}
    assert any("test_fails" in n for n in names), f"missing failure screenshot: {names}"
    # soft failure shows the collected message
    result.stdout.fnmatch_lines(["*1 soft assertion(s) failed*"])
