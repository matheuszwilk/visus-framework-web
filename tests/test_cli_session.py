"""Fast unit tests for the persistent-session CLI.

Covers:
  * SessionHandler.handle pure paths with a fake page (+ a real headless page for
    actions, marked browser),
  * console.dispatch with a fake send,
  * session-file discovery + stale cleanup (isolated via tmp_path),
  * Typer CliRunner arg parsing with session_client monkeypatched.

NEVER writes .visus into the repo root — all session files live under tmp_path.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from visus.web.cli import console, session_client, session_server
from visus.web.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeLocator:
    def __init__(self, log: list[str], label: str = "loc") -> None:
        self._log = log
        self._label = label

    def first(self) -> _FakeLocator:
        return self

    def frame_locator(self, sel: str) -> _FakeLocator:
        return _FakeLocator(self._log, f"{self._label}>frame({sel})")

    def locator(self, selector: str, *, deep: bool = False) -> _FakeLocator:
        return _FakeLocator(self._log, f"{self._label}>loc({selector},deep={deep})")

    def get_by_role(
        self, role: str, *, name: str | None = None, exact: bool = False
    ) -> _FakeLocator:
        return _FakeLocator(self._log, f"role({role},{name})")

    def get_by_text(self, text: str, *, exact: bool = False) -> _FakeLocator:
        return _FakeLocator(self._log, f"text({text})")

    def click(self) -> None:
        self._log.append(f"click:{self._label}")

    def fill(self, text: str) -> None:
        self._log.append(f"fill:{self._label}:{text}")

    def check(self) -> None:
        self._log.append(f"check:{self._label}")

    def uncheck(self) -> None:
        self._log.append(f"uncheck:{self._label}")

    def select_option(self, *, value: str | None = None) -> None:
        self._log.append(f"select:{self._label}:{value}")

    def press(self, key: str) -> None:
        self._log.append(f"press:{self._label}:{key}")

    def hover(self) -> None:
        self._log.append(f"hover:{self._label}")

    def dblclick(self) -> None:
        self._log.append(f"dblclick:{self._label}")

    def focus(self) -> None:
        self._log.append(f"focus:{self._label}")

    def clear(self) -> None:
        self._log.append(f"clear:{self._label}")

    def drag_to(self, target: _FakeLocator) -> None:
        self._log.append(f"drag:{self._label}->{target._label}")

    def set_input_files(self, paths: list[str]) -> None:
        self._log.append(f"upload:{self._label}:{','.join(paths)}")

    def count(self) -> int:
        self._log.append(f"count:{self._label}")
        return 3

    def nth(self, i: int) -> _FakeLocator:
        return _FakeLocator(self._log, f"{self._label}[{i}]")

    def is_visible(self) -> bool:
        return True

    def get_attribute(self, name: str) -> str:
        return f"attr:{self._label}:{name}"

    def ocr_text(self) -> str:
        return f"ocr:{self._label}"

    def text_content(self) -> str:
        return f"text-of:{self._label}"

    def screenshot(self, *, path: str | None = None) -> bytes:
        self._log.append(f"screenshot:{self._label}")
        if path:
            Path(path).write_bytes(b"PNG")
        return b"PNG"


class _FakeField:
    def __init__(self, index: int, locator: str, frame: list[str], deep: bool) -> None:
        self.index = index
        self.locator = locator
        self.frame = frame
        self.deep = deep
        self.kind = "input"
        self.name = f"f{index}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "name": self.name,
            "locator": self.locator,
            "frame": self.frame,
            "deep": self.deep,
        }


class _FakePage:
    def __init__(self) -> None:
        self.log: list[str] = []
        self.url = "about:blank"
        self._fields = [
            _FakeField(0, "#a", [], False),
            _FakeField(1, "#b", ["#f1"], True),
        ]

    def list_fields(
        self, *, kinds: Any = None, include_hidden: bool = False, highlight: bool = True
    ):
        self.log.append(f"list_fields:kinds={kinds}:hidden={include_hidden}:hl={highlight}")
        return self._fields

    def frame_locator(self, sel: str) -> _FakeLocator:
        return _FakeLocator(self.log, f"frame({sel})")

    def locator(self, selector: str, *, deep: bool = False) -> _FakeLocator:
        return _FakeLocator(self.log, f"loc({selector},deep={deep})")

    def get_by_role(
        self, role: str, *, name: str | None = None, exact: bool = False
    ) -> _FakeLocator:
        return _FakeLocator(self.log, f"role({role},{name})")

    def get_by_text(self, text: str, *, exact: bool = False) -> _FakeLocator:
        return _FakeLocator(self.log, f"text({text})")

    def goto(self, url: str) -> None:
        self.log.append(f"goto:{url}")
        self.url = url

    def title(self) -> str:
        return "FakeTitle"

    def go_back(self) -> None:
        self.log.append("go_back")
        self.url = "about:back"

    def go_forward(self) -> None:
        self.log.append("go_forward")
        self.url = "about:forward"

    def reload(self) -> None:
        self.log.append("reload")

    def snapshot(self) -> list[dict[str, Any]]:
        return [{"role": "button", "name": "Go"}, {"role": "textbox", "name": "Email"}]

    def evaluate(self, expression: str, arg: object = None) -> object:
        self.log.append(f"eval:{expression}:{arg}")
        return {"expr": expression, "arg": arg}

    def solve_captcha(self, loc: _FakeLocator) -> str:
        return f"captcha:{loc._label}"

    def clear_highlights(self) -> None:
        self.log.append("clear_highlights")

    def screenshot(self, *, path: str | None = None, full_page: bool = False) -> bytes:
        self.log.append(f"screenshot:full_page={full_page}")
        if path:
            Path(path).write_bytes(b"PNG")
        return b"PNG"


class _FakeContext:
    def __init__(self) -> None:
        self._cookies: list[dict[str, Any]] = [
            {"name": "sid", "value": "abc", "domain": "x.test"}
        ]

    def cookies(self) -> list[dict[str, Any]]:
        return list(self._cookies)

    def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        self._cookies.extend(cookies)

    def clear_cookies(self) -> None:
        self._cookies = []


class _FakeBrowser:
    def __init__(self) -> None:
        self.closed = False
        self._context = _FakeContext()

    @property
    def contexts(self) -> list[_FakeContext]:
        return [self._context]

    def close(self) -> None:
        self.closed = True


def _handler_with_fake_page(page: _FakePage) -> session_server.SessionHandler:
    h = session_server.SessionHandler(engine="chrome", headless=True)
    h._browser = _FakeBrowser()  # mark as "running" so _ensure() is a no-op
    h._page = page  # type: ignore[assignment]
    return h


# ---------------------------------------------------------------------------
# SessionHandler.handle — pure paths (fake page, no sockets, no browser)
# ---------------------------------------------------------------------------


def test_handle_unknown_op_returns_error() -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True)
    resp = h.handle("nope", {})
    assert resp["ok"] is False
    assert "unknown op" in resp["error"]


def test_handle_list_fields_caches_and_returns_dicts() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    resp = h.handle("list_fields", {"kinds": ["input"], "include_hidden": True, "highlight": False})
    assert resp["ok"] is True
    fields = resp["result"]["fields"]
    assert [f["index"] for f in fields] == [0, 1]
    assert h._fields  # cached for index targeting
    assert "list_fields:kinds=['input']:hidden=True:hl=False" in page.log


def test_handle_click_by_index_reresolves_via_frame_and_deep() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    h.handle("list_fields", {})
    resp = h.handle("click", {"index": 1})  # field 1 has frame=['#f1'], deep=True
    assert resp["ok"] is True and resp["result"] == "clicked"
    # The cached field was re-resolved through frame_locator(#f1).locator(#b, deep=True).
    assert any("click:frame(#f1)>loc(#b,deep=True)" == e for e in page.log)


def test_handle_click_index_out_of_range_is_clean_error() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    h.handle("list_fields", {})
    resp = h.handle("click", {"index": 99})
    assert resp["ok"] is False
    assert "out of range" in resp["error"]


def test_handle_actions_by_selector_use_make_locator() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    assert h.handle("fill", {"selector": "#x", "text": "hi"})["result"] == "filled with 'hi'"
    assert h.handle("check", {"selector": "#c"})["result"] == "checked"
    assert h.handle("uncheck", {"selector": "#c"})["result"] == "unchecked"
    assert h.handle("select", {"selector": "#s", "value": "v"})["result"] == "selected 'v'"
    assert h.handle("press", {"selector": "#i", "key": "Enter"})["result"] == "pressed 'Enter'"
    assert "fill:loc(#x,deep=False):hi" in page.log


def test_handle_get_text_by_role() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    resp = h.handle("get_text", {"role": "button", "name": "OK"})
    assert resp["ok"] is True
    assert resp["result"] == "text-of:role(button,OK)"


def test_handle_get_text_by_index_reresolves_via_frame_and_deep() -> None:
    """Index read re-resolves the cached field (frame chain + deep) before .text_content()."""
    page = _FakePage()
    h = _handler_with_fake_page(page)
    h.handle("list_fields", {})
    resp = h.handle("get_text", {"index": 1})  # field 1: frame=['#f1'], deep=True
    assert resp["ok"] is True
    assert resp["result"] == "text-of:frame(#f1)>loc(#b,deep=True)"


def test_handle_target_text_resolves_via_get_by_text_not_fill_value() -> None:
    """target_text maps to get_by_text; the load-bearing text/target_text split."""
    page = _FakePage()
    h = _handler_with_fake_page(page)
    resp = h.handle("click", {"target_text": "Save", "exact": True})
    assert resp["ok"] is True and resp["result"] == "clicked"
    # Re-resolved via get_by_text('Save', ...) -> _FakeLocator label "text(Save)".
    assert any(e == "click:text(Save)" for e in page.log)


def test_handle_target_without_target_errors() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    resp = h.handle("click", {})  # no index, no selector/role/text
    assert resp["ok"] is False
    assert "provide one of" in resp["error"]


# ---------------------------------------------------------------------------
# New ops — parity with the MCP browser_* tools (fake page/locator/context)
# ---------------------------------------------------------------------------


def test_handle_navigation_back_forward_reload() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    assert h.handle("back", {})["result"] == "about:back"
    assert h.handle("forward", {})["result"] == "about:forward"
    assert h.handle("reload", {})["result"] == page.url  # reload doesn't change url
    assert "go_back" in page.log and "go_forward" in page.log and "reload" in page.log


def test_handle_title_url_snapshot() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    assert h.handle("title", {})["result"] == "FakeTitle"
    assert h.handle("url", {})["result"] == page.url
    snap = h.handle("snapshot", {})["result"]
    assert snap["elements"][0] == {"role": "button", "name": "Go"}


def test_handle_get_attribute_and_count() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    resp = h.handle("get_attribute", {"selector": "#a", "attr_name": "href"})
    assert resp["result"] == "attr:loc(#a,deep=False):href"
    assert h.handle("count", {"selector": "#a"})["result"] == 3


def test_handle_hover_dblclick_focus_clear_input_by_selector() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    assert h.handle("hover", {"selector": "#h"})["result"] == "hovered"
    assert h.handle("dblclick", {"selector": "#d"})["result"] == "double-clicked"
    assert h.handle("focus", {"selector": "#f"})["result"] == "focused"
    assert h.handle("clear_input", {"selector": "#ci"})["result"] == "cleared"
    assert "hover:loc(#h,deep=False)" in page.log
    assert "dblclick:loc(#d,deep=False)" in page.log
    assert "focus:loc(#f,deep=False)" in page.log
    assert "clear:loc(#ci,deep=False)" in page.log


def test_handle_drag_by_selector_target() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    resp = h.handle("drag", {"selector": "#src", "target_selector": "#dst"})
    assert resp["ok"] is True and resp["result"] == "dragged to '#dst'"
    assert "drag:loc(#src,deep=False)->loc(#dst,deep=False)" in page.log


def test_handle_drag_by_index_targets() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    h.handle("list_fields", {})
    resp = h.handle("drag", {"index": 0, "target_index": 1})
    assert resp["ok"] is True and "dragged to field 1" == resp["result"]


def test_handle_drag_without_target_errors() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    resp = h.handle("drag", {"selector": "#src"})
    assert resp["ok"] is False and "drag target" in resp["error"]


def test_handle_upload_sets_files() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    resp = h.handle("upload", {"selector": "#file", "paths": ["/a.png", "/b.png"]})
    assert resp["result"] == "set 2 file(s)"
    assert "upload:loc(#file,deep=False):/a.png,/b.png" in page.log


def test_handle_wait_visible_passes_immediately() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    resp = h.handle("wait", {"selector": "#x", "state": "visible", "timeout": 1000})
    assert resp["ok"] is True and resp["result"] == "element is visible"


def test_handle_wait_hidden_times_out_cleanly() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    # The fake locator is always visible, so waiting for 'hidden' must time out.
    resp = h.handle("wait", {"selector": "#x", "state": "hidden", "timeout": 50})
    assert resp["ok"] is False and "hidden" in resp["error"]


def test_handle_expect_text_passes() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)

    class _Expectable(_FakeLocator):
        def to_have_text(self, expected: str, *, timeout: int | None = None) -> None:
            if expected not in self.text_content():
                raise AssertionError("mismatch")

    # Monkeypatch expect() to wrap our fake first() locator.
    import visus.web.cli.session_server as ss

    page._fields = []
    h._fields = []
    loc = _Expectable([])
    orig_target = h._target
    h._target = lambda args: loc  # type: ignore[assignment, method-assign]
    real_expect = ss.expect
    ss.expect = lambda location: location  # type: ignore[assignment]
    try:
        resp = h.handle("expect_text", {"selector": "#x", "expected_text": "text-of:loc"})
        assert resp["result"] == "PASSED"
        resp2 = h.handle("expect_text", {"selector": "#x", "expected_text": "nope"})
        assert resp2["result"].startswith("FAILED")
    finally:
        ss.expect = real_expect  # type: ignore[assignment]
        h._target = orig_target  # type: ignore[method-assign]


def test_handle_cookies_roundtrip() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    got = h.handle("cookies", {})["result"]
    assert got["cookies"][0]["name"] == "sid"
    assert h.handle("add_cookies", {"cookies": [{"name": "x", "value": "1"}]})["result"] == (
        "added 1 cookie(s)"
    )
    assert any(c["name"] == "x" for c in h.handle("cookies", {})["result"]["cookies"])
    assert h.handle("clear_cookies", {})["result"] == "cookies cleared"
    assert h.handle("cookies", {})["result"]["cookies"] == []


def test_handle_eval_returns_result() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    resp = h.handle("eval", {"expression": "() => 1", "arg": 7})
    assert resp["ok"] is True
    assert resp["result"]["result"] == {"expr": "() => 1", "arg": 7}


def test_handle_read_text_and_solve_captcha() -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    assert h.handle("read_text", {"selector": "#c"})["result"] == "ocr:loc(#c,deep=False)"
    assert h.handle("solve_captcha", {"selector": "#c"})["result"] == "captcha:loc(#c,deep=False)"


def test_handle_goto_screenshot_clear_status(tmp_path: Path) -> None:
    page = _FakePage()
    h = _handler_with_fake_page(page)
    assert h.handle("goto", {"url": "http://x"})["result"] == "http://x"
    out = tmp_path / "shot.png"
    assert h.handle("screenshot", {"path": str(out)})["ok"] is True
    assert out.read_bytes() == b"PNG"
    assert h.handle("clear_highlights", {})["result"] == "cleared"
    status = h.handle("status", {})["result"]
    assert status["running"] is True and status["url"] == "http://x"


def test_handle_status_not_running() -> None:
    h = session_server.SessionHandler(engine="firefox", headless=True)
    status = h.handle("status", {})["result"]
    assert status["running"] is False and status["engine"] == "firefox"


def test_handle_shutdown_closes_browser() -> None:
    closed = {"v": False}

    class _B:
        def close(self) -> None:
            closed["v"] = True

    h = session_server.SessionHandler(engine="chrome", headless=True)
    h._browser = _B()  # type: ignore[assignment]
    h._page = _FakePage()  # type: ignore[assignment]
    assert h.handle("shutdown", {})["result"] == "shutdown"
    assert closed["v"] is True and h._browser is None


def test_handler_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISUS_WEB_ENGINE", "edge")
    monkeypatch.setenv("VISUS_WEB_HEADLESS", "1")
    h = session_server.SessionHandler()
    assert h._engine == "edge" and h._headless is True


def test_make_locator_requires_a_target() -> None:
    page = _FakePage()
    with pytest.raises(ValueError, match="provide one of"):
        session_server.make_locator(page)  # type: ignore[arg-type]


def test_ensure_partial_launch_failure_is_atomic_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If context/page/goto setup raises, the partial browser is torn down so the
    next op retries cleanly (no wedge, no leaked driver)."""
    launched: list[_FakeBrowser] = []

    class _PageBoomBrowser(_FakeBrowser):
        def new_page(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("page boom")

    class _GoodBrowser(_FakeBrowser):
        def new_page(self):  # type: ignore[no-untyped-def]
            return _FakePage()

    browsers = [_PageBoomBrowser(), _GoodBrowser()]

    def fake_launch(engine, *, headless):  # type: ignore[no-untyped-def]
        b = browsers.pop(0)
        launched.append(b)
        return b

    monkeypatch.setattr(session_server, "launch", fake_launch)
    h = session_server.SessionHandler(engine="chrome", headless=True)

    # First op: setup raises -> clean error AND the partial browser is closed.
    resp = h.handle("status", {})  # status triggers page() via no-op? -> use list_fields
    # status() does NOT call page() when not running, so drive an op that needs the page.
    resp = h.handle("list_fields", {})
    assert resp["ok"] is False
    assert "page boom" in resp["error"]
    assert "AssertionError" not in resp["error"]  # not the empty-assert wedge
    assert launched[0].closed is True  # partial browser was torn down
    assert h._browser is None  # reset so the next op retries

    # Second op: a fresh launch succeeds (proves it retried, did not wedge).
    resp2 = h.handle("list_fields", {})
    assert resp2["ok"] is True
    assert len(launched) == 2  # launched again on retry


# ---------------------------------------------------------------------------
# console.dispatch — pure (fake send)
# ---------------------------------------------------------------------------


def _recording_send() -> tuple[list[tuple[str, dict[str, Any]]], Any]:
    calls: list[tuple[str, dict[str, Any]]] = []

    def send(op: str, args: dict[str, Any]) -> Any:
        calls.append((op, args))
        if op == "list_fields":
            return {
                "fields": [
                    {
                        "index": 0,
                        "kind": "button",
                        "name": "Go",
                        "locator": "#go",
                        "code": 'page.locator("#go")',
                        "css": "#go",
                        "xpath": '//*[@id="go"]',
                        "frame": [],
                    }
                ]
            }
        if op == "goto":
            return "http://dest"
        if op == "get_text":
            return "hello"
        if op == "screenshot":
            return "/tmp/shot.png"
        return "ok"

    return calls, send


def test_dispatch_blank_and_help_and_quit() -> None:
    _, send = _recording_send()
    assert console.dispatch("", send) == ""
    assert "commands:" in console.dispatch("help", send)
    assert console.dispatch("quit", send) == "__QUIT__"


def test_dispatch_list_renders_table() -> None:
    calls, send = _recording_send()
    out = console.dispatch("list", send)
    assert calls[0][0] == "list_fields"
    # short, wrap-safe tokens (the table may wrap long cells at default width)
    assert "button" in out and "#go" in out


def test_dispatch_actions_map_to_ops() -> None:
    calls, send = _recording_send()
    console.dispatch("click 3", send)
    console.dispatch("fill 2 hello world", send)
    console.dispatch("check 1", send)
    console.dispatch("uncheck 1", send)
    console.dispatch("select 4 us", send)
    console.dispatch("press 5 Enter", send)
    console.dispatch("clear", send)
    ops = [c[0] for c in calls]
    assert ops == ["click", "fill", "check", "uncheck", "select", "press", "clear_highlights"]
    assert calls[0][1] == {"index": 3}
    assert calls[1][1] == {"index": 2, "text": "hello world"}
    assert calls[4][1] == {"index": 4, "value": "us"}
    assert calls[5][1] == {"index": 5, "key": "Enter"}


def test_dispatch_goto_text_screenshot() -> None:
    _, send = _recording_send()
    assert "navigated to http://dest" in console.dispatch("goto http://dest", send)
    assert console.dispatch("text 0", send) == "hello"
    assert "saved /tmp/shot.png" in console.dispatch("screenshot", send)


def test_dispatch_unknown_and_missing_arg() -> None:
    _, send = _recording_send()
    assert "unknown command" in console.dispatch("frobnicate", send)
    assert "missing argument" in console.dispatch("click", send)


def test_dispatch_surfaces_session_error() -> None:
    def send(op: str, args: dict[str, Any]) -> Any:
        raise session_client.SessionError("daemon gone")

    out = console.dispatch("click 1", send)
    assert "error: daemon gone" in out


def test_format_fields_empty() -> None:
    assert console.format_fields([]) == "(no fields found)"


def test_format_fields_table_shows_visus_css_xpath() -> None:
    # width=200 so long cells do not wrap and full strings are assertable.
    out = console.format_fields(
        [
            {
                "index": 0,
                "kind": "button",
                "name": "Submit",
                "frame": ["#f1"],
                "code": 'page.frame_locator("#f1").locator("#submit")',
                "css": "#submit",
                "xpath": '//*[@id="submit"]',
            }
        ],
        width=200,
    )
    assert "VISUS" in out and "CSS" in out and "XPATH" in out  # column headers
    assert "button" in out and "Submit" in out
    # frame-aware visus call + the css value are present (rich folds/crops long
    # cells at narrow widths, so assert short, wrap-safe tokens; the exact code /
    # xpath values are asserted at the source in test_e2e_fields.py).
    assert "frame" in out and "#f1" in out  # the frame_locator(...) wrapping
    assert "#submit" in out  # css value


# ---------------------------------------------------------------------------
# console.run_console — session attach + input loop (injected fns)
# ---------------------------------------------------------------------------


def test_run_console_starts_session_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}
    monkeypatch.setattr(console.session_client, "find_session", lambda d=None: None)
    monkeypatch.setattr(
        console.session_client,
        "start_daemon",
        lambda engine, headless, url, **kw: calls.update(
            engine=engine, headless=headless, url=url
        ),
    )
    outputs: list[str] = []
    console.run_console(
        "http://x",
        engine="firefox",
        headless=True,
        input_fn=lambda _p: "quit",
        output_fn=outputs.append,
    )
    assert calls == {"engine": "firefox", "headless": True, "url": "http://x"}


def test_run_console_gotos_when_session_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        console.session_client, "find_session", lambda d=None: {"pid": 1, "port": 2}
    )
    monkeypatch.setattr(
        console.session_client,
        "send",
        lambda op, args=None, **kw: sent.append((op, args)) or None,
    )
    console.run_console(
        "http://dest",
        input_fn=lambda _p: "quit",
        output_fn=lambda _s: None,
    )
    assert ("goto", {"url": "http://dest"}) in sent


def test_run_console_loop_dispatches_then_quits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        console.session_client, "find_session", lambda d=None: {"pid": 1, "port": 2}
    )
    monkeypatch.setattr(console.session_client, "send", lambda op, args=None, **kw: "ok")
    lines = iter(["help", "quit"])
    outputs: list[str] = []
    console.run_console(
        None,
        input_fn=lambda _p: next(lines),
        output_fn=outputs.append,
    )
    assert any("commands:" in o for o in outputs)  # help ran before quit broke the loop


@pytest.mark.parametrize("exc", [EOFError, KeyboardInterrupt])
def test_run_console_clean_break_on_eof_or_interrupt(
    monkeypatch: pytest.MonkeyPatch, exc: type[BaseException]
) -> None:
    monkeypatch.setattr(
        console.session_client, "find_session", lambda d=None: {"pid": 1, "port": 2}
    )

    def _raise(_prompt: str) -> str:
        raise exc

    # Must return cleanly (no exception propagates).
    console.run_console(None, input_fn=_raise, output_fn=lambda _s: None)


def test_cli_console_command_invokes_run_console(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run_console(url=None, *, engine="chrome", headless=False, **kw):  # type: ignore[no-untyped-def]
        captured.update(url=url, engine=engine, headless=headless)

    monkeypatch.setattr("visus.web.cli.console.run_console", fake_run_console)
    r = runner.invoke(app, ["console", "http://x", "--engine", "edge", "--headless"])
    assert r.exit_code == 0
    assert captured == {"url": "http://x", "engine": "edge", "headless": True}


# ---------------------------------------------------------------------------
# session-file discovery + stale cleanup (isolated under tmp_path)
# ---------------------------------------------------------------------------


def _write_session(dir_: Path, info: dict[str, Any]) -> Path:
    visus = dir_ / ".visus"
    visus.mkdir(parents=True, exist_ok=True)
    sf = visus / "session.json"
    sf.write_text(json.dumps(info), encoding="utf-8")
    return sf


def test_find_session_none_when_absent(tmp_path: Path) -> None:
    assert session_client.find_session(tmp_path) is None


def test_find_session_searches_upward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Live socket so the liveness check passes.
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        _write_session(tmp_path, {"pid": 1, "port": port, "token": "t"})
        monkeypatch.setattr(session_client, "_pid_alive", lambda pid: True)
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        info = session_client.find_session(deep)
        assert info is not None and info["port"] == port and info["token"] == "t"
    finally:
        srv.close()


def test_find_session_cleans_stale_dead_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sf = _write_session(tmp_path, {"pid": 999999, "port": 1, "token": "t"})
    monkeypatch.setattr(session_client, "_pid_alive", lambda pid: False)
    assert session_client.find_session(tmp_path) is None
    assert not sf.exists()  # stale file removed


def test_find_session_cleans_stale_socket_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # pid "alive" but nothing listening on the recorded port → stale.
    sf = _write_session(tmp_path, {"pid": 1, "port": 1, "token": "t"})
    monkeypatch.setattr(session_client, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(session_client, "_socket_open", lambda port, **kw: False)
    assert session_client.find_session(tmp_path) is None
    assert not sf.exists()


def test_find_session_cleans_corrupt_file(tmp_path: Path) -> None:
    visus = tmp_path / ".visus"
    visus.mkdir(parents=True)
    sf = visus / "session.json"
    sf.write_text("{not json", encoding="utf-8")
    assert session_client.find_session(tmp_path) is None
    assert not sf.exists()


def test_send_without_session_raises(tmp_path: Path) -> None:
    with pytest.raises(session_client.SessionError, match="no live session"):
        session_client.send("status", start_dir=tmp_path)


def test_status_none_without_session(tmp_path: Path) -> None:
    assert session_client.status(start_dir=tmp_path) is None


def test_stop_without_session(tmp_path: Path) -> None:
    assert session_client.stop(start_dir=tmp_path) == "no session running"


def test_send_real_raises_on_daemon_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive the REAL send(): a daemon {ok:False,error} must surface as SessionError."""
    handler = _handler_with_fake_page(_FakePage())
    token = "tok"
    t, port = _serve_in_thread(handler, token, tmp_path)
    monkeypatch.setattr(session_client, "_pid_alive", lambda pid: True)
    try:
        with pytest.raises(session_client.SessionError, match="out of range"):
            # No list_fields run -> index 999 is out of range -> ok:False from daemon.
            session_client.send("click", {"index": 999}, start_dir=tmp_path)
    finally:
        _shutdown_thread(t, port, token)


def test_send_raw_raises_on_empty_response(tmp_path: Path) -> None:
    """_send_raw: an empty/closed response line -> 'daemon closed the connection'."""
    import threading

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _accept_and_eof() -> None:
        conn, _ = srv.accept()
        try:
            # Read the client's request line, then send a clean EOF (no response
            # line) so the client's readline() returns b"" -> the empty-line path.
            conn.recv(4096)
            conn.shutdown(socket.SHUT_WR)
            conn.recv(4096)  # wait for the client to finish before closing
        finally:
            conn.close()

    th = threading.Thread(target=_accept_and_eof, daemon=True)
    th.start()
    try:
        with pytest.raises(session_client.SessionError, match="closed the connection"):
            session_client._send_raw(port, {"token": "t", "op": "status"}, timeout=5)
    finally:
        th.join(timeout=5)
        srv.close()


def test_start_daemon_refuses_when_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session_client, "find_session", lambda d=None: {"pid": 7, "port": 8, "token": "t"}
    )
    with pytest.raises(session_client.SessionError, match="already running"):
        session_client.start_daemon("chrome", True, None, cwd=tmp_path)


def test_start_daemon_retries_through_partial_session_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Popen no-op; session.json first corrupt then valid with a live socket.

    Exercises start_daemon's not-yet-ready polling: JSONDecodeError retry, then a
    valid file whose socket accepts -> returns the info dict.
    """
    monkeypatch.setattr(session_client, "find_session", lambda d=None: None)

    # A real listening socket so _socket_open() succeeds once the file is valid.
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    visus = tmp_path / ".visus"
    visus.mkdir(parents=True, exist_ok=True)
    sf = visus / "session.json"

    state = {"calls": 0}

    class _FakePopen:
        def __init__(self, *a: Any, **kw: Any) -> None:
            # First write a corrupt/partial file (simulates a mid-write read).
            sf.write_text("{partial", encoding="utf-8")

    monkeypatch.setattr(session_client.subprocess, "Popen", _FakePopen)

    # On the second poll, replace the corrupt file with a valid one.
    real_is_file = Path.is_file

    def patched_is_file(self: Path) -> bool:
        if self == sf:
            state["calls"] += 1
            if state["calls"] >= 2 and sf.read_text(encoding="utf-8").startswith("{partial"):
                sf.write_text(
                    json.dumps({"pid": 1, "port": port, "token": "t"}), encoding="utf-8"
                )
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", patched_is_file)
    try:
        info = session_client.start_daemon("chrome", True, None, cwd=tmp_path, timeout=5.0)
        assert info["port"] == port and info["token"] == "t"
    finally:
        srv.close()


def test_stop_swallows_send_failure_on_dead_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop() against a session whose port refuses must swallow the error and clean up."""
    sf = _write_session(tmp_path, {"pid": 1, "port": 9, "token": "t"})
    info = {"pid": 1, "port": 9, "token": "t", "_file": str(sf)}
    monkeypatch.setattr(session_client, "find_session", lambda start_dir=None: info)
    # _send_raw blows up (nothing listening); stop() must still finish cleanly.
    monkeypatch.setattr(
        session_client,
        "_send_raw",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("connection refused")),
    )
    assert session_client.stop(start_dir=tmp_path) == "session stopped"
    assert not sf.exists()  # cleaned up


def test_pid_alive_negative() -> None:
    assert session_client._pid_alive(-1) is False


def test_pid_alive_windows_tasklist_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the win32 tasklist parse: pid present -> True, absent/raising -> False."""
    monkeypatch.setattr(session_client.sys, "platform", "win32")

    class _Completed:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    # pid present in tasklist output -> alive.
    monkeypatch.setattr(
        session_client.subprocess,
        "run",
        lambda *a, **kw: _Completed("python.exe   12345 Console   1   50,000 K"),
    )
    assert session_client._pid_alive(12345) is True

    # pid absent -> not alive.
    monkeypatch.setattr(
        session_client.subprocess,
        "run",
        lambda *a, **kw: _Completed("INFO: No tasks are running which match the criteria."),
    )
    assert session_client._pid_alive(12345) is False

    # subprocess raises -> treated as not alive (exception fallback).
    def _boom(*a: Any, **kw: Any) -> Any:
        raise OSError("tasklist missing")

    monkeypatch.setattr(session_client.subprocess, "run", _boom)
    assert session_client._pid_alive(12345) is False


def test_socket_open_false_on_closed_port() -> None:
    # Bind then immediately close → that port should refuse.
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    assert session_client._socket_open(port, timeout=0.5) is False


# ---------------------------------------------------------------------------
# JSON-lines protocol — drive serve() in a thread (no real browser)
# ---------------------------------------------------------------------------


def test_serve_protocol_with_fake_handler(tmp_path: Path) -> None:
    """Exercise the socket server end-to-end against a fake page handler."""
    import threading

    page = _FakePage()
    handler = _handler_with_fake_page(page)
    token = "secret-token"

    t = threading.Thread(
        target=session_server.serve, kwargs={"handler": handler, "token": token, "cwd": tmp_path}
    )
    t.start()
    try:
        sf = session_server.session_file(tmp_path)
        # Wait for the session file to appear.
        for _ in range(100):
            if sf.is_file():
                break
            import time

            time.sleep(0.05)
        info = json.loads(sf.read_text(encoding="utf-8"))
        port = info["port"]
        assert info["token"] == token

        def rpc(payload: dict[str, Any]) -> dict[str, Any]:
            with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                f = sock.makefile("rwb")
                f.write((json.dumps(payload) + "\n").encode("utf-8"))
                f.flush()
                return json.loads(f.readline().decode("utf-8"))

        # bad token rejected
        assert rpc({"token": "wrong", "op": "status"})["error"].startswith("unauthorized")
        # list_fields works
        r = rpc({"token": token, "op": "list_fields", "args": {}})
        assert r["ok"] and len(r["result"]["fields"]) == 2
        # index click re-resolves through the cache
        assert rpc({"token": token, "op": "click", "args": {"index": 0}})["result"] == "clicked"
        # bad json line gets an error response
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            fb = sock.makefile("rwb")
            fb.write(b"{garbage\n")
            fb.flush()
            assert json.loads(fb.readline().decode("utf-8"))["ok"] is False
        # shutdown stops the server
        assert rpc({"token": token, "op": "shutdown"})["result"] == "shutdown"
    finally:
        t.join(timeout=10)
    assert not t.is_alive()
    assert not session_server.session_file(tmp_path).is_file()  # cleaned on shutdown


def _serve_in_thread(handler: session_server.SessionHandler, token: str, tmp_path: Path):
    """Start serve() in a thread; return (thread, port). Wait for the session file."""
    import threading
    import time as _time

    t = threading.Thread(
        target=session_server.serve,
        kwargs={"handler": handler, "token": token, "cwd": tmp_path},
        daemon=True,
    )
    t.start()
    sf = session_server.session_file(tmp_path)
    for _ in range(200):
        if sf.is_file():
            break
        _time.sleep(0.02)
    info = json.loads(sf.read_text(encoding="utf-8"))
    return t, int(info["port"])


def _shutdown_thread(t, port: int, token: str) -> None:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        f = sock.makefile("rwb")
        f.write((json.dumps({"token": token, "op": "shutdown"}) + "\n").encode("utf-8"))
        f.flush()
        f.readline()
    t.join(timeout=10)


@pytest.mark.parametrize("bad", ["123", '"hi"', "[1, 2, 3]", "null"])
def test_serve_non_dict_request_returns_error_not_crash(bad: str, tmp_path: Path) -> None:
    """A valid-JSON-but-non-dict line must get {ok:False,error} and keep the thread alive."""
    handler = _handler_with_fake_page(_FakePage())
    token = "tok"
    t, port = _serve_in_thread(handler, token, tmp_path)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
            f = sock.makefile("rwb")
            f.write((bad + "\n").encode("utf-8"))
            f.flush()
            resp = json.loads(f.readline().decode("utf-8"))
            assert resp["ok"] is False
            assert "expected a JSON object" in resp["error"]
            # The same connection's handler thread is still alive: a follow-up
            # well-formed request on it gets a normal response.
            f.write(
                (json.dumps({"token": token, "op": "status"}) + "\n").encode("utf-8")
            )
            f.flush()
            ok = json.loads(f.readline().decode("utf-8"))
            assert ok["ok"] is True
    finally:
        _shutdown_thread(t, port, token)
    assert not t.is_alive()


def test_serve_writes_session_file_atomically(tmp_path: Path) -> None:
    """No leftover *.tmp file remains after the atomic os.replace startup write."""
    handler = _handler_with_fake_page(_FakePage())
    token = "tok"
    t, port = _serve_in_thread(handler, token, tmp_path)
    try:
        visus = tmp_path / ".visus"
        leftovers = list(visus.glob("session.json.*.tmp"))
        assert leftovers == []
        assert (visus / "session.json").is_file()
    finally:
        _shutdown_thread(t, port, token)


def test_serve_second_daemon_aborts_via_lock(tmp_path: Path) -> None:
    """A duplicate serve() on the same dir must hit the O_EXCL lock and abort."""
    handler = _handler_with_fake_page(_FakePage())
    token = "tok"
    t, port = _serve_in_thread(handler, token, tmp_path)
    try:
        with pytest.raises(session_server.SessionLockedError):
            session_server.serve(
                handler=_handler_with_fake_page(_FakePage()), token="other", cwd=tmp_path
            )
    finally:
        _shutdown_thread(t, port, token)
    # Lock is released on shutdown so a fresh daemon can claim it again.
    assert not (tmp_path / ".visus" / "session.json.lock").exists()


# ---------------------------------------------------------------------------
# Typer CliRunner arg parsing (session_client monkeypatched — no real daemon)
# ---------------------------------------------------------------------------


def test_cli_list_fields_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_send(op: str, args: dict[str, Any]) -> Any:
        captured["op"] = op
        captured["args"] = args
        return {"fields": [{"index": 0, "kind": "input", "name": "n", "locator": "#n"}]}

    monkeypatch.setattr(session_client, "send", lambda op, args=None: fake_send(op, args or {}))
    r = runner.invoke(app, ["list-fields", "--kind", "input,button", "--all", "--json"])
    assert r.exit_code == 0
    assert captured["op"] == "list_fields"
    assert captured["args"]["kinds"] == ["input", "button"]
    assert captured["args"]["include_hidden"] is True
    data = json.loads(r.output)
    assert data[0]["locator"] == "#n"


def test_cli_list_fields_blocks_and_no_highlight(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_send(op: str, args: dict[str, Any] | None = None) -> Any:
        captured["args"] = args
        return {
            "fields": [
                {
                    "index": 0,
                    "kind": "input",
                    "name": "n",
                    "locator": "#n",
                    "code": 'page.locator("#n")',
                    "css": "#n",
                    "xpath": '//*[@id="n"]',
                    "frame": [],
                }
            ]
        }

    monkeypatch.setattr(session_client, "send", fake_send)
    r = runner.invoke(app, ["list-fields", "--no-highlight"])
    assert r.exit_code == 0
    assert captured["args"]["highlight"] is False
    assert "input" in r.output and "#n" in r.output


def test_cli_click_by_index(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_send(op: str, args: dict[str, Any] | None = None) -> Any:
        captured["op"], captured["args"] = op, args
        return "clicked"

    monkeypatch.setattr(session_client, "send", fake_send)
    r = runner.invoke(app, ["click", "2"])
    assert r.exit_code == 0 and "clicked" in r.output
    assert captured["op"] == "click" and captured["args"] == {"index": 2}


def test_cli_click_by_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        session_client, "send", lambda op, args=None: captured.update(op=op, args=args) or "clicked"
    )
    r = runner.invoke(app, ["click", "--selector", "#go"])
    assert r.exit_code == 0
    assert captured["args"]["selector"] == "#go"


def test_cli_click_requires_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_client, "send", lambda op, args=None: "x")
    r = runner.invoke(app, ["click"])
    assert r.exit_code == 1
    assert "provide an index" in r.output


def test_cli_click_by_role_and_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """--role/--name wire through to the target dict (role re-resolution path)."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        session_client, "send", lambda op, args=None: captured.update(op=op, args=args) or "ok"
    )
    r = runner.invoke(app, ["get-text", "--role", "button", "--name", "OK"])
    assert r.exit_code == 0
    assert captured["args"] == {
        "selector": None,
        "role": "button",
        "name": "OK",
        "target_text": None,
    }


def test_cli_click_by_text_maps_to_target_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """--text becomes a target_text TARGET (never a colliding 'text' key)."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        session_client, "send", lambda op, args=None: captured.update(op=op, args=args) or "ok"
    )
    r = runner.invoke(app, ["click", "--text", "Save"])
    assert r.exit_code == 0
    assert captured["args"]["target_text"] == "Save"
    assert "text" not in captured["args"]  # no collision with fill's text VALUE


def test_cli_fill_keeps_text_value_and_target_text_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fill's positional VALUE lands in 'text'; a --selector target stays separate."""
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        session_client, "send", lambda op, args=None: captured.update(op=op, args=args) or "ok"
    )
    r = runner.invoke(app, ["fill", "--selector", "#email", "--value", "hi"])
    assert r.exit_code == 0
    assert captured["args"]["text"] == "hi"  # the fill VALUE
    assert captured["args"]["selector"] == "#email"  # the TARGET
    assert "target_text" in captured["args"] and captured["args"]["target_text"] is None


def test_cli_fill_select_press(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        session_client, "send", lambda op, args=None: calls.append((op, args)) or "ok"
    )
    # index-first, value-second (intuitive: `visus fill 7 hello`, like `click N`)
    assert runner.invoke(app, ["fill", "1", "hello"]).exit_code == 0
    assert runner.invoke(app, ["select", "2", "us"]).exit_code == 0
    assert runner.invoke(app, ["press", "3", "Enter"]).exit_code == 0
    assert calls[0] == ("fill", {"index": 1, "text": "hello"})
    assert calls[1] == ("select", {"index": 2, "value": "us"})
    assert calls[2] == ("press", {"index": 3, "key": "Enter"})


def test_cli_goto_and_get_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_send(op: str, args: dict[str, Any] | None = None) -> Any:
        return "http://x" if op == "goto" else "the text"

    monkeypatch.setattr(session_client, "send", fake_send)
    assert "navigated to http://x" in runner.invoke(app, ["goto", "http://x"]).output
    assert "the text" in runner.invoke(app, ["get-text", "0"]).output


def test_cli_check_uncheck_clear_screenshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(session_client, "send", lambda op, args=None: f"did-{op}")
    assert "did-check" in runner.invoke(app, ["check", "0"]).output
    assert "did-uncheck" in runner.invoke(app, ["uncheck", "0"]).output
    assert "did-clear_highlights" in runner.invoke(app, ["clear"]).output
    out = tmp_path / "x.png"
    assert "did-screenshot" in runner.invoke(app, ["session-screenshot", "-o", str(out)]).output


def test_cli_session_screenshot_full_page_and_element(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--full-page and element targeting reach the daemon (MCP browser_screenshot parity)."""
    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        session_client, "send", lambda op, args=None: calls.append((op, args or {})) or "/p.png"
    )
    out = tmp_path / "x.png"

    # No target → page screenshot; full_page defaults to False and is forwarded.
    assert runner.invoke(app, ["session-screenshot", "-o", str(out)]).exit_code == 0
    assert calls[-1][0] == "screenshot"
    assert calls[-1][1]["full_page"] is False
    assert "index" not in calls[-1][1] and "selector" not in calls[-1][1]

    # --full-page forwards full_page=True.
    assert runner.invoke(app, ["session-screenshot", "-o", str(out), "--full-page"]).exit_code == 0
    assert calls[-1][1]["full_page"] is True

    # Element by index.
    assert runner.invoke(app, ["session-screenshot", "-o", str(out), "2"]).exit_code == 0
    assert calls[-1][1]["index"] == 2

    # Element by selector.
    assert (
        runner.invoke(app, ["session-screenshot", "-o", str(out), "-s", "#hero"]).exit_code == 0
    )
    assert calls[-1][1]["selector"] == "#hero"


def test_handle_screenshot_full_page_and_element(tmp_path: Path) -> None:
    """The daemon op honours full_page and element targets (mirrors browser_screenshot)."""
    page = _FakePage()
    h = _handler_with_fake_page(page)

    out = tmp_path / "full.png"
    assert h.handle("screenshot", {"path": str(out), "full_page": True})["ok"] is True
    assert out.read_bytes() == b"PNG"
    assert "screenshot:full_page=True" in page.log

    elem = tmp_path / "elem.png"
    res = h.handle("screenshot", {"path": str(elem), "selector": "#hero"})
    assert res["ok"] is True
    assert elem.read_bytes() == b"PNG"
    # The element path screenshots the locator, not the page.
    assert any(entry.startswith("screenshot:loc(#hero") for entry in page.log)


def test_cli_send_error_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(op: str, args: dict[str, Any] | None = None) -> Any:
        raise session_client.SessionError("no live session")

    monkeypatch.setattr(session_client, "send", boom)
    r = runner.invoke(app, ["click", "0"])
    assert r.exit_code == 1 and "no live session" in r.output


# ---------------------------------------------------------------------------
# New CLI commands — arg parsing (session_client.send monkeypatched)
# ---------------------------------------------------------------------------


def _record(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Monkeypatch session_client.send to record (op, args) and return a generic result."""
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_send(op: str, args: dict[str, Any] | None = None) -> Any:
        calls.append((op, args or {}))
        if op in ("back", "forward", "reload", "url", "title"):
            return "http://dest"
        if op == "snapshot":
            return {"elements": [{"role": "button", "name": "Go"}]}
        if op == "count":
            return 3
        if op == "cookies":
            return {"cookies": [{"name": "sid", "value": "v", "domain": "d"}]}
        if op == "eval":
            return {"result": "evald"}
        if op == "tab_new":
            return {"index": 1, "title": "T"}
        if op == "tab_close":
            return {"closed": 1, "remaining": 1, "active": 0}
        if op == "find_image":
            return {"found": True, "x": 10, "y": 20, "confidence": 0.95}
        return f"did-{op}"

    monkeypatch.setattr(session_client, "send", fake_send)
    return calls


def test_cli_back_forward_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    assert "went back to http://dest" in runner.invoke(app, ["back"]).output
    assert "went forward to http://dest" in runner.invoke(app, ["forward"]).output
    assert "reloaded http://dest" in runner.invoke(app, ["reload"]).output
    assert [c[0] for c in calls] == ["back", "forward", "reload"]


def test_cli_title_url_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    _record(monkeypatch)
    assert "http://dest" in runner.invoke(app, ["title"]).output
    assert "http://dest" in runner.invoke(app, ["url"]).output
    out = runner.invoke(app, ["snapshot"])
    assert out.exit_code == 0 and "button" in out.output and "Go" in out.output
    outj = runner.invoke(app, ["snapshot", "--json"])
    assert json.loads(outj.output)[0]["role"] == "button"


def test_cli_get_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    r = runner.invoke(app, ["get-attribute", "href", "2"])
    assert r.exit_code == 0
    assert calls[-1] == ("get_attribute", {"index": 2, "attr_name": "href"})
    r2 = runner.invoke(app, ["get-attribute", "href", "--selector", "#a"])
    assert r2.exit_code == 0
    assert calls[-1][1]["selector"] == "#a" and calls[-1][1]["attr_name"] == "href"


def test_cli_count(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    r = runner.invoke(app, ["count", "--selector", ".item"])
    assert r.exit_code == 0 and "3" in r.output
    assert calls[-1] == ("count", {"selector": ".item", "role": None, "name": None,
                                    "target_text": None})


def test_cli_hover_dblclick_focus_clear_input(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    assert runner.invoke(app, ["hover", "1"]).exit_code == 0
    assert runner.invoke(app, ["dblclick", "2"]).exit_code == 0
    assert runner.invoke(app, ["focus", "3"]).exit_code == 0
    assert runner.invoke(app, ["clear-input", "4"]).exit_code == 0
    assert [c[0] for c in calls] == ["hover", "dblclick", "focus", "clear_input"]
    assert calls[0][1] == {"index": 1}
    assert calls[3][1] == {"index": 4}


def test_cli_drag_by_index_and_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    assert runner.invoke(app, ["drag", "0", "1"]).exit_code == 0
    assert calls[-1] == ("drag", {"index": 0, "target_index": 1})
    assert runner.invoke(app, ["drag", "--selector", "#s", "--to-selector", "#t"]).exit_code == 0
    assert calls[-1][1]["selector"] == "#s" and calls[-1][1]["target_selector"] == "#t"
    assert runner.invoke(app, ["drag", "--selector", "#s", "--to-index", "4"]).exit_code == 0
    assert calls[-1][1]["target_index"] == 4


def test_cli_drag_requires_target(monkeypatch: pytest.MonkeyPatch) -> None:
    _record(monkeypatch)
    r = runner.invoke(app, ["drag", "--selector", "#s"])
    assert r.exit_code == 1 and "drag target" in r.output


def test_cli_upload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _record(monkeypatch)
    f1 = tmp_path / "a.txt"
    f1.write_text("x")
    r = runner.invoke(app, ["upload", "2", str(f1)])
    assert r.exit_code == 0
    assert calls[-1][0] == "upload" and calls[-1][1]["index"] == 2
    assert calls[-1][1]["paths"] == [str(f1.resolve())]


def test_cli_upload_requires_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    _record(monkeypatch)
    r = runner.invoke(app, ["upload", "2"])
    assert r.exit_code == 1 and "file path" in r.output


def test_cli_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    r = runner.invoke(app, ["wait", "0", "--state", "hidden", "--timeout", "1234"])
    assert r.exit_code == 0
    assert calls[-1][0] == "wait"
    assert calls[-1][1]["state"] == "hidden" and calls[-1][1]["timeout"] == 1234


def test_cli_expect_text(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    r = runner.invoke(app, ["expect-text", "0", "Welcome"])
    assert r.exit_code == 0
    assert calls[-1] == ("expect_text", {"index": 0, "expected_text": "Welcome"})
    r2 = runner.invoke(app, ["expect-text", "--selector", "#h", "--expected", "Hi", "--timeout",
                             "500"])
    assert r2.exit_code == 0
    assert calls[-1][1]["expected_text"] == "Hi" and calls[-1][1]["timeout"] == 500


def test_cli_expect_text_requires_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _record(monkeypatch)
    r = runner.invoke(app, ["expect-text", "--selector", "#h"])
    assert r.exit_code == 1 and "expected text" in r.output


def test_cli_tab_new_and_close(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    r = runner.invoke(app, ["tab-new", "http://x"])
    assert r.exit_code == 0 and "opened tab 1" in r.output
    assert calls[-1] == ("tab_new", {"url": "http://x"})
    r2 = runner.invoke(app, ["tab-close", "1"])
    assert r2.exit_code == 0 and "closed tab 1" in r2.output
    assert calls[-1] == ("tab_close", {"index": 1})


def test_cli_tab_close_last_tab_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session_client, "send", lambda op, args=None: {"closed": 0, "remaining": 0}
    )
    r = runner.invoke(app, ["tab-close"])
    assert r.exit_code == 0 and "session stopped" in r.output


def test_cli_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    assert runner.invoke(app, ["dialog"]).exit_code == 0
    assert calls[-1] == ("dialog", {"accept": True, "prompt_text": None})
    assert runner.invoke(app, ["dialog", "--dismiss"]).exit_code == 0
    assert calls[-1][1]["accept"] is False
    assert runner.invoke(app, ["dialog", "--prompt-text", "hi"]).exit_code == 0
    assert calls[-1][1]["prompt_text"] == "hi"


def test_cli_cookies_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _record(monkeypatch)
    r = runner.invoke(app, ["cookies"])
    assert r.exit_code == 0 and "sid=v" in r.output
    rj = runner.invoke(app, ["cookies", "--json"])
    assert json.loads(rj.output)[0]["name"] == "sid"


def test_cli_add_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    r = runner.invoke(app, ["add-cookies", '[{"name":"a","value":"b","url":"http://x"}]'])
    assert r.exit_code == 0
    assert calls[-1][0] == "add_cookies"
    assert calls[-1][1]["cookies"] == [{"name": "a", "value": "b", "url": "http://x"}]


def test_cli_add_cookies_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _record(monkeypatch)
    assert runner.invoke(app, ["add-cookies", "{not json"]).exit_code == 1
    r2 = runner.invoke(app, ["add-cookies", '{"name":"a"}'])  # not a list
    assert r2.exit_code == 1 and "JSON list" in r2.output


def test_cli_clear_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    assert runner.invoke(app, ["clear-cookies"]).exit_code == 0
    assert calls[-1][0] == "clear_cookies"


def test_cli_eval(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    r = runner.invoke(app, ["eval", "() => 1+1", "42"])
    assert r.exit_code == 0 and "evald" in r.output
    assert calls[-1][0] == "eval"
    assert calls[-1][1]["expression"] == "() => 1+1" and calls[-1][1]["arg"] == 42
    # non-JSON arg falls back to a plain string
    runner.invoke(app, ["eval", "() => x", "plainstr"])
    assert calls[-1][1]["arg"] == "plainstr"


def test_cli_read_text_and_solve_captcha(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _record(monkeypatch)
    assert runner.invoke(app, ["read-text", "0"]).exit_code == 0
    assert calls[-1] == ("read_text", {"index": 0})
    assert runner.invoke(app, ["solve-captcha", "--selector", "#c"]).exit_code == 0
    assert calls[-1][0] == "solve_captcha" and calls[-1][1]["selector"] == "#c"


def test_cli_find_image(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _record(monkeypatch)
    tpl = tmp_path / "tpl.png"
    tpl.write_bytes(b"x")
    r = runner.invoke(app, ["find-image", str(tpl), "--confidence", "0.9"])
    assert r.exit_code == 0 and "found at (10, 20)" in r.output
    assert calls[-1][0] == "find_image"
    assert calls[-1][1]["template_path"] == str(tpl.resolve())
    assert calls[-1][1]["confidence"] == 0.9
    rj = runner.invoke(app, ["find-image", str(tpl), "--json"])
    assert json.loads(rj.output)["found"] is True


def test_cli_find_image_not_found(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(session_client, "send", lambda op, args=None: {"found": False})
    tpl = tmp_path / "tpl.png"
    tpl.write_bytes(b"x")
    r = runner.invoke(app, ["find-image", str(tpl)])
    assert r.exit_code == 0 and "not found" in r.output


def test_cli_session_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session_client,
        "start_daemon",
        lambda engine, headless, url, **kw: {"pid": 42, "port": 5555},
    )
    r = runner.invoke(app, ["session", "start", "http://x", "--engine", "chrome"])
    assert r.exit_code == 0 and "pid 42" in r.output and "port 5555" in r.output


def test_cli_session_start_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **kw: Any) -> Any:
        raise session_client.SessionError("already running")

    monkeypatch.setattr(session_client, "start_daemon", boom)
    r = runner.invoke(app, ["session", "start"])
    assert r.exit_code == 1 and "already running" in r.output


def test_cli_session_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_client, "stop", lambda: "session stopped")
    r = runner.invoke(app, ["session", "stop"])
    assert r.exit_code == 0 and "session stopped" in r.output


def test_cli_session_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        session_client,
        "status",
        lambda: {"pid": 1, "port": 2, "engine": "chrome", "headless": False, "url": "http://x"},
    )
    r = runner.invoke(app, ["session", "status"])
    assert r.exit_code == 0 and "chrome" in r.output and "http://x" in r.output
    rj = runner.invoke(app, ["session", "status", "--json"])
    assert json.loads(rj.output)["pid"] == 1


def test_cli_session_status_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_client, "status", lambda: None)
    r = runner.invoke(app, ["session", "status"])
    assert r.exit_code == 1 and "no session running" in r.output


# ---------------------------------------------------------------------------
# SessionHandler action paths against a REAL headless page (browser-marked)
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_handle_real_page_list_and_index_actions(base_url: str) -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        resp = h.handle("list_fields", {"highlight": False})
        assert resp["ok"] is True
        fields = resp["result"]["fields"]
        assert fields and any(f["locator"] == "#topinput" for f in fields)
        top_idx = next(f["index"] for f in fields if f["locator"] == "#topinput")
        # fill the top input by index, then read it back via get_text on a shadow field
        assert h.handle("fill", {"index": top_idx, "text": "hi there"})["ok"] is True
        # an iframe field re-resolves via the frame chain
        iframe_idx = next(
            (f["index"] for f in fields if f["locator"] == "#iframeinput"), None
        )
        assert iframe_idx is not None
        assert h.handle("fill", {"index": iframe_idx, "text": "in frame"})["ok"] is True
    finally:
        h.close()


@pytest.mark.browser
def test_handle_real_page_deep_shadow_field_action(base_url: str) -> None:
    """End-to-end: the daemon's _resolve_field reaches an OPEN shadow root (deep=True)."""
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        resp = h.handle("list_fields", {"highlight": False, "include_hidden": True})
        assert resp["ok"] is True
        fields = resp["result"]["fields"]
        # The shadow input/button live inside an open shadow root -> deep=True locators.
        shadow_in = next(
            (f for f in fields if f["locator"] == "#shadowinput"), None
        )
        assert shadow_in is not None, "expected a #shadowinput shadow-DOM field"
        assert shadow_in["deep"] is True  # re-resolution must use a deep (piercing) query
        # Filling it proves the daemon's frame-chain + deep re-resolution actually
        # reached an OPEN shadow root: a non-deep query could never match the
        # element, so an ok:True fill is end-to-end evidence the shadow root was
        # pierced via the cached field's deep flag (not just an iframe).
        r = h.handle("fill", {"index": shadow_in["index"], "text": "deep-x"})
        assert r["ok"] is True, r
        # The shadow button is also a deep field (deep re-resolution found it).
        shadow_btn = next((f for f in fields if f["locator"] == "#shadowbtn"), None)
        assert shadow_btn is not None and shadow_btn["deep"] is True
    finally:
        h.close()


@pytest.mark.browser
def test_handler_follows_focus_to_a_new_window() -> None:
    # Opening a new tab/window must make list_fields operate on THAT window (the
    # focused one), not the original — the "detect where I'm focused" behaviour.
    from visus.web.cli.session_server import SessionHandler

    h = SessionHandler(
        engine="chrome",
        headless=True,
        url="data:text/html,<button id=firstbtn>First</button>",
    )
    try:
        r1 = h.handle("list_fields", {"highlight": False})
        assert r1["ok"] is True
        assert "#firstbtn" in {f["locator"] for f in r1["result"]["fields"]}
        # A fresh session has exactly ONE browser window (regression: new_context()
        # used to spawn a second, headed browser — the "2 browsers" bug).
        assert h.handle("status", {})["result"]["windows"] == 1

        # Open a second window with a distinct element and switch focus to it.
        driver = h._page._delegate._driver  # type: ignore[attr-defined]
        driver.switch_to.new_window("window")
        driver.get("data:text/html,<button id=secondbtn>Second</button>")

        # The handler now enumerates the NEW (focused) window, not the first.
        r2 = h.handle("list_fields", {"highlight": False})
        assert r2["ok"] is True
        locs = {f["locator"] for f in r2["result"]["fields"]}
        assert "#secondbtn" in locs, locs
        assert h.handle("status", {})["result"]["windows"] == 2
    finally:
        h.close()


@pytest.mark.browser
def test_handler_manual_tab_switch_lists_and_acts_on_chosen_tab() -> None:
    # `tabs` lists every window/tab; `tab N` switches manually so list_fields runs
    # on the chosen tab (both directions), not just the auto-followed newest.
    from visus.web.cli.session_server import SessionHandler

    h = SessionHandler(
        engine="chrome",
        headless=True,
        url="data:text/html,<button id=firstbtn>First</button>",
    )
    try:
        h.handle("list_fields", {"highlight": False})  # establishes tab 0
        driver = h._page._delegate._driver  # type: ignore[attr-defined]
        driver.switch_to.new_window("tab")
        driver.get("data:text/html,<button id=secondbtn>Second</button>")
        h.handle("list_fields", {"highlight": False})  # auto-follows the new tab

        tabs = h.handle("tabs", {})["result"]
        assert len(tabs["tabs"]) == 2

        # manual switch BACK to tab 0
        assert h.handle("tab", {"index": 0})["result"]["active"] == 0
        back = h.handle("list_fields", {"highlight": False})
        assert "#firstbtn" in {f["locator"] for f in back["result"]["fields"]}

        # manual switch to tab 1
        h.handle("tab", {"index": 1})
        fwd = h.handle("list_fields", {"highlight": False})
        assert "#secondbtn" in {f["locator"] for f in fwd["result"]["fields"]}

        # out-of-range index is a clean error, not a crash
        assert h.handle("tab", {"index": 9})["ok"] is False
    finally:
        h.close()


# ---------------------------------------------------------------------------
# New ops — REAL headless page e2e (browser-marked)
# ---------------------------------------------------------------------------


@pytest.mark.browser
def test_handle_real_back_forward_reload(base_url: str) -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        h.handle("goto", {"url": f"{base_url}/index.html"})
        back = h.handle("back", {})
        assert back["ok"] is True and back["result"].endswith("fields.html")
        fwd = h.handle("forward", {})
        assert fwd["ok"] is True and fwd["result"].endswith("index.html")
        rel = h.handle("reload", {})
        assert rel["ok"] is True and rel["result"].endswith("index.html")
    finally:
        h.close()


@pytest.mark.browser
def test_handle_real_title_url_snapshot(base_url: str) -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        assert h.handle("title", {})["result"] == "fields fixture"
        assert h.handle("url", {})["result"].endswith("fields.html")
        snap = h.handle("snapshot", {})
        assert snap["ok"] is True and isinstance(snap["result"]["elements"], list)
    finally:
        h.close()


@pytest.mark.browser
def test_handle_real_get_attribute_and_count(base_url: str) -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        href = h.handle("get_attribute", {"selector": "#lnk", "attr_name": "href"})
        assert href["ok"] is True and href["result"] == "https://example.com/"
        cnt = h.handle("count", {"selector": "input"})
        assert cnt["ok"] is True and cnt["result"] >= 5
    finally:
        h.close()


@pytest.mark.browser
def test_handle_real_hover_dblclick_focus(base_url: str) -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        assert h.handle("hover", {"selector": "#btn"})["result"] == "hovered"
        assert h.handle("dblclick", {"selector": "#btn"})["result"] == "double-clicked"
        assert h.handle("focus", {"selector": "#topinput"})["result"] == "focused"
    finally:
        h.close()


@pytest.mark.browser
def test_handle_real_eval(base_url: str) -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        title = h.handle("eval", {"expression": "() => document.title"})
        assert title["ok"] is True and title["result"]["result"] == "fields fixture"
        doubled = h.handle("eval", {"expression": "(x) => x * 2", "arg": 21})
        assert doubled["result"]["result"] == 42
    finally:
        h.close()


@pytest.mark.browser
def test_handle_real_wait_visible(base_url: str) -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        ok = h.handle("wait", {"selector": "#topinput", "state": "visible", "timeout": 3000})
        assert ok["ok"] is True and ok["result"] == "element is visible"
        # A non-existent element must never become visible -> clean timeout error.
        bad = h.handle("wait", {"selector": "#nope", "state": "visible", "timeout": 200})
        assert bad["ok"] is False and "visible" in bad["error"]
    finally:
        h.close()


@pytest.mark.browser
def test_handle_real_expect_text(base_url: str) -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        ok = h.handle("expect_text", {"selector": "h1", "expected_text": "Fields"})
        assert ok["ok"] is True and ok["result"] == "PASSED"
        bad = h.handle(
            "expect_text", {"selector": "h1", "expected_text": "Nope", "timeout": 300}
        )
        assert bad["ok"] is True and bad["result"].startswith("FAILED")
    finally:
        h.close()


@pytest.mark.browser
def test_handle_real_cookies_roundtrip(base_url: str) -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        h.handle("clear_cookies", {})
        add = h.handle(
            "add_cookies", {"cookies": [{"name": "vt", "value": "yes", "url": base_url}]}
        )
        assert add["ok"] is True and add["result"] == "added 1 cookie(s)"
        got = h.handle("cookies", {})
        assert got["ok"] is True and any(c["name"] == "vt" for c in got["result"]["cookies"])
        cleared = h.handle("clear_cookies", {})
        assert cleared["result"] == "cookies cleared"
        assert h.handle("cookies", {})["result"]["cookies"] == []
    finally:
        h.close()


@pytest.mark.browser
def test_handle_real_tab_new_and_close(base_url: str) -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        new = h.handle("tab_new", {"url": f"{base_url}/index.html"})
        assert new["ok"] is True
        # The new tab is active and enumerable.
        assert h.handle("url", {})["result"].endswith("index.html")
        assert h.handle("tabs", {})["result"]["tabs"].__len__() == 2
        closed = h.handle("tab_close", {})  # close the active (new) tab
        assert closed["ok"] is True and closed["result"]["remaining"] == 1
        # Back on the original tab.
        assert h.handle("url", {})["result"].endswith("fields.html")
    finally:
        h.close()


@pytest.mark.browser
def test_handle_real_drag(base_url: str) -> None:
    h = session_server.SessionHandler(engine="chrome", headless=True, url=f"{base_url}/fields.html")
    try:
        # Drag is a best-effort gesture; success here means no crash + ok:True.
        resp = h.handle("drag", {"selector": "#btn", "target_selector": "#topinput"})
        assert resp["ok"] is True and "dragged to" in resp["result"]
    finally:
        h.close()


def test_cli_tabs_and_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_send(op: str, args: dict[str, Any] | None = None) -> Any:
        captured["call"] = (op, args)
        if op == "tabs":
            return {
                "tabs": [
                    {"index": 0, "title": "A", "url": "u0", "active": True},
                    {"index": 1, "title": "B", "url": "u1", "active": False},
                ],
                "active": 0,
            }
        return {"active": 1, "title": "B"}

    monkeypatch.setattr(session_client, "send", lambda op, args=None: fake_send(op, args))
    r = runner.invoke(app, ["tabs"])
    assert r.exit_code == 0 and "[0]" in r.output and "[1]" in r.output and "*" in r.output
    r2 = runner.invoke(app, ["tab", "1"])
    assert r2.exit_code == 0 and "switched to tab 1" in r2.output
    assert captured["call"] == ("tab", {"index": 1})


def test_dispatch_tabs_and_tab() -> None:
    calls: list[tuple[str, Any]] = []

    def send(op: str, args: dict[str, Any]) -> Any:
        calls.append((op, args))
        if op == "tabs":
            return {"tabs": [{"index": 0, "title": "A", "url": "u", "active": True}], "active": 0}
        return {"active": 0, "title": "A"}

    assert "[0]" in console.dispatch("tabs", send)
    assert "switched to tab 0" in console.dispatch("tab 0", send)
    assert calls[-1] == ("tab", {"index": 0})


# ---------------------------------------------------------------------------
# console.dispatch — new verbs (fake send)
# ---------------------------------------------------------------------------


def _dispatch_send() -> tuple[list[tuple[str, dict[str, Any]]], Any]:
    calls: list[tuple[str, dict[str, Any]]] = []

    def send(op: str, args: dict[str, Any]) -> Any:
        calls.append((op, args))
        if op in ("back", "forward", "reload", "url", "title"):
            return "http://dest"
        if op == "snapshot":
            return {"elements": [{"role": "button", "name": "Go"}]}
        if op == "count":
            return 2
        if op == "cookies":
            return {"cookies": [{"name": "sid", "value": "v", "domain": "d"}]}
        if op == "eval":
            return {"result": "RES"}
        if op == "tab_new":
            return {"index": 1, "title": "T"}
        if op == "tab_close":
            return {"closed": 1, "remaining": 1, "active": 0}
        return "ok"

    return calls, send


def test_dispatch_navigation_and_inspect_verbs() -> None:
    calls, send = _dispatch_send()
    assert "went back to http://dest" in console.dispatch("back", send)
    assert "went forward to http://dest" in console.dispatch("forward", send)
    assert "reloaded http://dest" in console.dispatch("reload", send)
    assert console.dispatch("title", send) == "http://dest"
    assert console.dispatch("url", send) == "http://dest"
    assert "button" in console.dispatch("snapshot", send)
    assert [c[0] for c in calls] == ["back", "forward", "reload", "title", "url", "snapshot"]


def test_dispatch_hover_dblclick_focus_clear_attr_count() -> None:
    calls, send = _dispatch_send()
    console.dispatch("hover 1", send)
    console.dispatch("dblclick 2", send)
    console.dispatch("focus 3", send)
    console.dispatch("clear-input 6", send)
    console.dispatch("attr href 4", send)
    assert console.dispatch("count 5", send) == "2"
    ops = [c[0] for c in calls]
    assert ops == ["hover", "dblclick", "focus", "clear_input", "get_attribute", "count"]
    assert calls[0][1] == {"index": 1}
    assert calls[3][1] == {"index": 6}
    assert calls[4][1] == {"index": 4, "attr_name": "href"}


def test_dispatch_wait_and_expect() -> None:
    calls, send = _dispatch_send()
    console.dispatch("wait 0 hidden", send)
    console.dispatch("expect 1 Welcome back", send)
    assert calls[0] == ("wait", {"index": 0, "state": "hidden"})
    assert calls[1] == ("expect_text", {"index": 1, "expected_text": "Welcome back"})


def test_dispatch_cookies_eval_dialog() -> None:
    calls, send = _dispatch_send()
    assert "sid=v" in console.dispatch("cookies", send)
    assert console.dispatch("eval () => 1", send) == "RES"
    console.dispatch("dialog", send)
    console.dispatch("dialog dismiss", send)
    assert calls[1] == ("eval", {"expression": "() => 1"})
    assert calls[2][1]["accept"] is True
    assert calls[3][1]["accept"] is False


def test_dispatch_tab_new_and_close() -> None:
    calls, send = _dispatch_send()
    assert "opened tab 1" in console.dispatch("tab-new http://x", send)
    assert "closed tab 1" in console.dispatch("tab-close 1", send)
    assert calls[0] == ("tab_new", {"url": "http://x"})
    assert calls[1] == ("tab_close", {"index": 1})
