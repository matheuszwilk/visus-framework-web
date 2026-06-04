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

    def text_content(self) -> str:
        return f"text-of:{self._label}"


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

    def clear_highlights(self) -> None:
        self.log.append("clear_highlights")

    def screenshot(self, *, path: str | None = None) -> bytes:
        if path:
            Path(path).write_bytes(b"PNG")
        return b"PNG"


class _FakeBrowser:
    def __init__(self) -> None:
        self.closed = False

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


def test_cli_send_error_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(op: str, args: dict[str, Any] | None = None) -> Any:
        raise session_client.SessionError("no live session")

    monkeypatch.setattr(session_client, "send", boom)
    r = runner.invoke(app, ["click", "0"])
    assert r.exit_code == 1 and "no live session" in r.output


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
