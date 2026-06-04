"""Persistent CLI session server (daemon).

A :class:`SessionHandler` holds a live ``Browser``/``Context``/``Page`` and maps
JSON ops to page operations. The handler is **fully unit-testable without
sockets** -- :meth:`SessionHandler.handle` takes ``(op, args)`` and returns a
plain dict.

A thin JSON-lines TCP server (bound to ``127.0.0.1`` on an ephemeral port) wraps
the handler: one JSON request per line in, one JSON response line out. Every
request must carry the session ``token``. :func:`main` is the detached-process
entrypoint: it reads engine/headless/url from argv/env, writes
``.visus/session.json`` and serves until a ``shutdown`` op arrives.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, cast

from visus.web import Engine, errors, launch
from visus.web.api.assertions import expect
from visus.web.api.browser import Browser
from visus.web.api.context import Context
from visus.web.api.fields import Field
from visus.web.api.locator import Locator
from visus.web.api.page import Page
from visus.web.backends.selenium.driver_delegate import SeleniumPageDelegate


def _any_match_visible(loc: Locator) -> bool:
    """True if at least one element the locator matches is visible.

    Local copy of the MCP helper: tolerant of mid-navigation errors (treated as
    "not yet visible") and of locators that match several elements.
    """
    try:
        return any(loc.nth(i).is_visible() for i in range(loc.count()))
    except errors.VisusWebError:
        return False


def make_locator(
    page: Page,
    *,
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> Locator:
    """Resolve a locator from the given target params.

    Local copy of the MCP helper (the cli must not import the ``mcp`` package, as
    the ``mcp`` extra may be absent).
    """
    root: Any = page if frame is None else page.frame_locator(frame)
    if role is not None:
        return cast(Locator, root.get_by_role(role, name=name, exact=exact))
    if text is not None:
        return cast(Locator, root.get_by_text(text, exact=exact))
    if selector is not None:
        return cast(Locator, root.locator(selector))
    raise ValueError("provide one of: index, role, text, selector")


class SessionHandler:
    """Holds a live browser/context/page and dispatches ops to page operations.

    Modeled on ``mcp/session.py``'s :class:`Session`: lazy ``_ensure`` reads the
    engine/headless from ctor args (falling back to env
    ``VISUS_WEB_ENGINE`` / ``VISUS_WEB_HEADLESS``). The last ``list_fields``
    result is cached so index-based ops re-resolve the stored field via the
    foundation contract (frame chain + ``deep``).
    """

    def __init__(
        self,
        *,
        engine: str | None = None,
        headless: bool | None = None,
        url: str | None = None,
    ) -> None:
        self._engine = engine or os.environ.get("VISUS_WEB_ENGINE", "chrome")
        if headless is None:
            headless = os.environ.get("VISUS_WEB_HEADLESS", "0") != "0"
        self._headless = headless
        self._url = url
        self._browser: Browser | None = None
        self._context: Context | None = None
        self._page: Page | None = None
        self._fields: list[Field] = []
        self._known_handles: list[str] = []
        self._active_handle: str | None = None

    # --- lifecycle -------------------------------------------------------
    def _ensure(self) -> None:
        if self._browser is None:
            self._browser = launch(Engine.from_str(self._engine), headless=self._headless)
            # Failure-atomic: if any step after launch raises (bad URL, etc.),
            # tear the partial browser down so the next op retries from scratch
            # instead of wedging on a non-None browser with a None page.
            try:
                # new_page() reuses the browser's DEFAULT context. Calling
                # new_context() here would spawn a SECOND WebDriver/browser window
                # (the daemon is headed) — that was the "2 browsers" bug.
                self._page = self._browser.new_page()
                if self._url:
                    self._page.goto(self._url)
            except Exception:
                self.close()
                raise

    def page(self) -> Page:
        """The page to operate on — the active window/tab.

        Auto-follows a newly-opened tab/popup window, otherwise stays on the
        last-active one (switch explicitly with the ``tab`` op). A modal/dialog is
        part of the same document, so it is already covered by the active page.
        """
        return self._active_page()

    def _driver(self) -> Any:
        return getattr(getattr(self._page, "_delegate", None), "_driver", None)

    def _active_page(self) -> Page:
        self._ensure()
        if self._page is None:
            raise RuntimeError("session page is not available")
        driver = self._driver()
        if driver is None:
            return self._page  # non-selenium page (tests) — no tab tracking
        try:
            handles = list(driver.window_handles)
        except Exception:  # noqa: BLE001
            return self._page
        if not handles:
            return self._page
        handle = self._resolve_active(handles)
        if getattr(self._page._delegate, "_handle", None) == handle:
            return self._page
        return Page(SeleniumPageDelegate(driver, handle), self._page._defaults)

    def _resolve_active(self, handles: list[str]) -> str:
        """Pick the active handle: auto-follow a newly-opened tab/window, else stay
        on the last-active one (sticky), else the newest. The ``tab`` op overrides."""
        new = [h for h in handles if h not in self._known_handles]
        self._known_handles = list(handles)
        if new:
            self._active_handle = new[-1]  # follow the newest new tab/popup
        if self._active_handle not in handles:
            self._active_handle = handles[-1]
        return self._active_handle

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
        self._browser = None
        self._context = None
        self._page = None
        self._fields = []

    def context(self) -> Context:
        """The browser context (shared with the active page) — cookies live here.

        Cookies are a CONTEXT concern, not a page one (mirrors the MCP server).
        The daemon's pages all share the launch driver's default context, so the
        first context is the right one for cookie reads/writes.
        """
        self._ensure()
        assert self._browser is not None
        contexts = self._browser.contexts
        if not contexts:
            raise RuntimeError("no browser context available")
        return contexts[0]

    # --- targeting -------------------------------------------------------
    def _resolve_field(self, index: int) -> Locator:
        """Re-resolve a cached field for an action via the foundation contract."""
        if index < 0 or index >= len(self._fields):
            raise IndexError(
                f"field index {index} out of range "
                f"(have {len(self._fields)}; run list_fields first)"
            )
        field = self._fields[index]
        root: Any = self.page()
        for sel in field.frame:
            root = root.frame_locator(sel)
        return cast(Locator, root.locator(field.locator, deep=field.deep))

    @staticmethod
    def _has_target(args: dict[str, Any]) -> bool:
        """True if args carry an explicit target (index/selector/role/target_text)."""
        if args.get("index") is not None:
            return True
        return any(args.get(k) is not None for k in ("selector", "role", "target_text"))

    def _target(self, args: dict[str, Any]) -> Locator:
        """Resolve the action target: cached index OR a make_locator target.

        Note the locator-text target is read from ``target_text`` (not ``text``)
        so it never collides with ``fill``'s ``text`` *value* payload.
        """
        if "index" in args and args["index"] is not None:
            return self._resolve_field(int(args["index"]))
        return make_locator(
            self.page(),
            selector=args.get("selector"),
            role=args.get("role"),
            name=args.get("name"),
            text=args.get("target_text"),
            exact=bool(args.get("exact", False)),
            frame=args.get("frame"),
        )

    # --- ops -------------------------------------------------------------
    def handle(self, op: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Dispatch one op. Returns ``{ok:True,result:...}`` or ``{ok:False,error:str}``."""
        args = args or {}
        try:
            method = getattr(self, f"_op_{op}", None)
            if method is None:
                raise ValueError(f"unknown op {op!r}")
            return {"ok": True, "result": method(args)}
        except Exception as exc:  # noqa: BLE001 — daemon must never crash a client
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _op_list_fields(self, args: dict[str, Any]) -> dict[str, Any]:
        kinds = args.get("kinds")
        include_hidden = bool(args.get("include_hidden", False))
        highlight = bool(args.get("highlight", True))
        fields = self.page().list_fields(
            kinds=kinds, include_hidden=include_hidden, highlight=highlight
        )
        self._fields = list(fields)
        return {"fields": [f.to_dict() for f in fields]}

    def _op_click(self, args: dict[str, Any]) -> str:
        self._target(args).click()
        return "clicked"

    def _op_fill(self, args: dict[str, Any]) -> str:
        text = args.get("text", "")
        self._target(args).fill(text)
        return f"filled with {text!r}"

    def _op_check(self, args: dict[str, Any]) -> str:
        self._target(args).check()
        return "checked"

    def _op_uncheck(self, args: dict[str, Any]) -> str:
        self._target(args).uncheck()
        return "unchecked"

    def _op_select(self, args: dict[str, Any]) -> str:
        value = args.get("value")
        self._target(args).select_option(value=value)
        return f"selected {value!r}"

    def _op_press(self, args: dict[str, Any]) -> str:
        key = args.get("key", "")
        self._target(args).press(key)
        return f"pressed {key!r}"

    def _op_get_text(self, args: dict[str, Any]) -> str | None:
        return self._target(args).first().text_content()

    def _op_goto(self, args: dict[str, Any]) -> str:
        url = args["url"]
        page = self.page()
        page.goto(url)
        return page.url

    def _op_screenshot(self, args: dict[str, Any]) -> str:
        """Screenshot the page (optionally full-page) or a single element.

        Mirrors ``browser_screenshot`` in the MCP server: when a target
        (index/selector/role/target_text) is given, screenshot that element via
        ``Locator.screenshot``; otherwise screenshot the page, honouring
        ``full_page``.
        """
        path = args.get("path") or "screenshot.png"
        if self._has_target(args):
            self._target(args).screenshot(path=path)
        else:
            self.page().screenshot(path=path, full_page=bool(args.get("full_page")))
        return str(Path(path).resolve())

    def _op_clear_highlights(self, args: dict[str, Any]) -> str:
        self.page().clear_highlights()
        return "cleared"

    # --- navigation ------------------------------------------------------
    def _op_back(self, args: dict[str, Any]) -> str:
        page = self.page()
        page.go_back()
        return page.url

    def _op_forward(self, args: dict[str, Any]) -> str:
        page = self.page()
        page.go_forward()
        return page.url

    def _op_reload(self, args: dict[str, Any]) -> str:
        page = self.page()
        page.reload()
        return page.url

    # --- inspect ---------------------------------------------------------
    def _op_title(self, args: dict[str, Any]) -> str:
        return self.page().title()

    def _op_url(self, args: dict[str, Any]) -> str:
        return self.page().url

    def _op_snapshot(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"elements": self.page().snapshot()}

    def _op_get_attribute(self, args: dict[str, Any]) -> str | None:
        name = args.get("attr_name", "")
        return self._target(args).first().get_attribute(name)

    def _op_count(self, args: dict[str, Any]) -> int:
        return self._target(args).count()

    # --- actions ---------------------------------------------------------
    def _op_hover(self, args: dict[str, Any]) -> str:
        self._target(args).hover()
        return "hovered"

    def _op_dblclick(self, args: dict[str, Any]) -> str:
        self._target(args).dblclick()
        return "double-clicked"

    def _op_focus(self, args: dict[str, Any]) -> str:
        self._target(args).focus()
        return "focused"

    def _op_clear_input(self, args: dict[str, Any]) -> str:
        """Clear an input's value (mirrors browser_clear; distinct from clear_highlights)."""
        self._target(args).clear()
        return "cleared"

    def _op_drag(self, args: dict[str, Any]) -> str:
        src = self._target(args)
        target_selector = args.get("target_selector")
        if target_selector is not None:
            tgt = self.page().locator(target_selector)
        elif args.get("target_index") is not None:
            tgt = self._resolve_field(int(args["target_index"]))
        else:
            raise ValueError("provide a drag target: target_selector or target_index")
        src.drag_to(tgt)
        if target_selector is not None:
            return f"dragged to {target_selector!r}"
        return f"dragged to field {args['target_index']}"

    def _op_upload(self, args: dict[str, Any]) -> str:
        paths = args.get("paths") or []
        self._target(args).set_input_files(paths)
        return f"set {len(paths)} file(s)"

    # --- wait / expect ---------------------------------------------------
    def _op_wait(self, args: dict[str, Any]) -> str:
        state = args.get("state") or "visible"
        loc = self._target(args)
        timeout = args.get("timeout")
        ms = 5000 if timeout is None else int(timeout)
        want_visible = state != "hidden"
        deadline = time.monotonic() + ms / 1000.0
        while True:
            if _any_match_visible(loc) == want_visible:
                return f"element is {state}"
            if time.monotonic() >= deadline:
                raise AssertionError(f"wait: no element became {state} within {ms}ms")
            time.sleep(0.1)

    def _op_expect_text(self, args: dict[str, Any]) -> str:
        expected = args.get("expected_text", "")
        loc = self._target(args)
        timeout = args.get("timeout")
        try:
            expect(loc.first()).to_have_text(
                expected, timeout=int(timeout) if timeout is not None else None
            )
            return "PASSED"
        except AssertionError as exc:
            return f"FAILED: {exc}"

    # --- new tab / close tab --------------------------------------------
    def _op_tab_new(self, args: dict[str, Any]) -> dict[str, Any]:
        """Open a new tab/window, register it, and make it the active handle."""
        self._ensure()
        driver = self._driver()
        if driver is None:
            raise RuntimeError("no live browser")
        before = list(driver.window_handles)
        driver.switch_to.new_window("tab")
        handles = list(driver.window_handles)
        new = [h for h in handles if h not in before]
        self._known_handles = handles
        self._active_handle = new[-1] if new else handles[-1]
        self._fields = []
        url = args.get("url")
        if url:
            driver.switch_to.window(self._active_handle)
            self.page().goto(url)
        idx = handles.index(self._active_handle)
        try:
            driver.switch_to.window(self._active_handle)
            title = driver.title
        except Exception:  # noqa: BLE001
            title = ""
        return {"index": idx, "title": title}

    def _op_tab_close(self, args: dict[str, Any]) -> dict[str, Any]:
        """Close a tab by index (default: the active one), resetting the active handle."""
        self._ensure()
        driver = self._driver()
        if driver is None:
            raise RuntimeError("no live browser")
        handles = list(driver.window_handles)
        idx = args.get("index")
        if idx is None:
            target = self._active_handle if self._active_handle in handles else handles[-1]
            i = handles.index(target)
        else:
            i = int(idx)
            if i < 0 or i >= len(handles):
                raise IndexError(f"tab index {i} out of range (have {len(handles)} tabs)")
            target = handles[i]
        driver.switch_to.window(target)
        driver.close()
        remaining = list(driver.window_handles)
        self._known_handles = remaining
        self._fields = []
        if not remaining:
            self.close()
            return {"closed": i, "remaining": 0}
        self._active_handle = remaining[min(i, len(remaining) - 1)]
        try:
            driver.switch_to.window(self._active_handle)
        except Exception:  # noqa: BLE001
            pass
        return {
            "closed": i,
            "remaining": len(remaining),
            "active": remaining.index(self._active_handle),
        }

    # --- dialogs ---------------------------------------------------------
    def _op_dialog(self, args: dict[str, Any]) -> str:
        """Handle the next pending dialog (mirrors browser_handle_dialog exactly)."""
        accept = bool(args.get("accept", True))
        prompt_text = args.get("prompt_text")
        page = self.page()
        msg, typ = page._delegate.handle_next_dialog(
            accept=accept,
            prompt_text=prompt_text,
            timeout_ms=5000,
        )
        action = "accepted" if accept else "dismissed"
        return f"{action} {typ!r} dialog: {msg!r}"

    # --- cookies (context-level) -----------------------------------------
    def _op_cookies(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"cookies": self.context().cookies()}

    def _op_add_cookies(self, args: dict[str, Any]) -> str:
        cookies = args.get("cookies") or []
        self.context().add_cookies(cookies)
        return f"added {len(cookies)} cookie(s)"

    def _op_clear_cookies(self, args: dict[str, Any]) -> str:
        self.context().clear_cookies()
        return "cookies cleared"

    # --- javascript ------------------------------------------------------
    def _op_eval(self, args: dict[str, Any]) -> dict[str, Any]:
        expression = args.get("expression", "")
        arg = args.get("arg")
        return {"result": self.page().evaluate(expression, arg)}

    # --- vision (requires the [vision] extra) ----------------------------
    def _op_read_text(self, args: dict[str, Any]) -> str:
        return self._target(args).ocr_text()

    def _op_solve_captcha(self, args: dict[str, Any]) -> str:
        loc = self._target(args)
        return self.page().solve_captcha(loc)

    def _op_find_image(self, args: dict[str, Any]) -> dict[str, Any]:
        import io

        import numpy as np
        from PIL import Image as PILImage

        from visus.web.vision import find_image

        template_path = args.get("template_path", "")
        confidence = float(args.get("confidence", 0.8))
        page = self.page()
        if args.get("selector") or args.get("role") or args.get("target_text") or (
            args.get("index") is not None
        ):
            screenshot_bytes = self._target(args).screenshot()
        else:
            screenshot_bytes = page.screenshot()
        source_img = np.array(PILImage.open(io.BytesIO(screenshot_bytes)).convert("RGB"))
        template_img = np.array(PILImage.open(template_path).convert("RGB"))
        match = find_image(source_img, template_img, confidence=confidence)
        if match is None:
            return {"found": False}
        return {"found": True, "x": match.x, "y": match.y, "confidence": match.confidence}

    def _op_tabs(self, args: dict[str, Any]) -> dict[str, Any]:
        """List every open tab/window with its title/url and the active marker."""
        self._ensure()
        driver = self._driver()
        if driver is None:
            return {"tabs": [], "active": None}
        handles = list(driver.window_handles)
        active = self._resolve_active(handles)
        tabs: list[dict[str, Any]] = []
        for i, h in enumerate(handles):
            try:
                driver.switch_to.window(h)
                title, url = driver.title, driver.current_url
            except Exception:  # noqa: BLE001
                title, url = "", ""
            tabs.append({"index": i, "title": title, "url": url, "active": h == active})
        try:
            driver.switch_to.window(active)  # restore the active tab
        except Exception:  # noqa: BLE001
            pass
        return {"tabs": tabs, "active": handles.index(active) if active in handles else None}

    def _op_tab(self, args: dict[str, Any]) -> dict[str, Any]:
        """Switch the active tab/window by index (omit/None → jump to the newest)."""
        self._ensure()
        driver = self._driver()
        if driver is None:
            raise RuntimeError("no live browser")
        handles = list(driver.window_handles)
        self._known_handles = list(handles)
        idx = args.get("index")
        if idx is None:
            self._active_handle = handles[-1]
        else:
            i = int(idx)
            if i < 0 or i >= len(handles):
                raise IndexError(f"tab index {i} out of range (have {len(handles)} tabs)")
            self._active_handle = handles[i]
        self._fields = []  # cached field indices belonged to the previous tab
        try:
            driver.switch_to.window(self._active_handle)
            title = driver.title
        except Exception:  # noqa: BLE001
            title = ""
        return {"active": handles.index(self._active_handle), "title": title}

    def _op_status(self, args: dict[str, Any]) -> dict[str, Any]:
        running = self._browser is not None
        info: dict[str, Any] = {
            "running": running,
            "engine": self._engine,
            "headless": self._headless,
            "fields_cached": len(self._fields),
        }
        if running:
            try:
                p = self._active_page()
                info["url"] = p.url
                info["title"] = p.title()
                info["windows"] = len(self._known_handles)
                if self._active_handle in self._known_handles:
                    info["active_tab"] = self._known_handles.index(self._active_handle)
            except Exception:  # noqa: BLE001
                pass
        return info

    def _op_shutdown(self, args: dict[str, Any]) -> str:
        self.close()
        return "shutdown"


# ---------------------------------------------------------------------------
# Session file helpers
# ---------------------------------------------------------------------------


def session_file(cwd: str | Path | None = None) -> Path:
    """Path to ``.visus/session.json`` under *cwd* (default: process cwd)."""
    base = Path(cwd) if cwd is not None else Path.cwd()
    return base / ".visus" / "session.json"


# ---------------------------------------------------------------------------
# JSON-lines TCP server
# ---------------------------------------------------------------------------


def _handle_conn(
    conn: socket.socket, handler: SessionHandler, token: str, stop: threading.Event
) -> None:
    with conn:
        f = conn.makefile("rwb")

        def _reply(resp: dict[str, Any]) -> None:
            f.write((json.dumps(resp) + "\n").encode("utf-8"))
            f.flush()

        for raw in f:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            # Wrap the whole per-line body so a malformed/odd request can never
            # silently kill this handler thread without writing a response.
            try:
                try:
                    req = json.loads(line)
                except json.JSONDecodeError as exc:
                    _reply({"ok": False, "error": f"bad json: {exc}"})
                    continue
                if not isinstance(req, dict):
                    _reply({"ok": False, "error": "bad request: expected a JSON object"})
                    continue
                if req.get("token") != token:
                    _reply({"ok": False, "error": "unauthorized: bad token"})
                    continue
                op = req.get("op", "")
                resp = handler.handle(op, req.get("args") or {})
                _reply(resp)
                if op == "shutdown" and resp.get("ok"):
                    stop.set()
                    return
            except Exception as exc:  # noqa: BLE001 — never crash the handler thread
                _reply({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


class SessionLockedError(RuntimeError):
    """Raised when another daemon already holds the session lock."""


def _claim_lock(sf: Path) -> Path:
    """Atomically claim ownership for this daemon (O_CREAT|O_EXCL lock file).

    Closes the TOCTOU between ``find_session() is None`` and ``Popen`` in the
    client: two concurrent daemons cannot both claim the lock, so the loser
    exits immediately (before serving / launching a browser) instead of running
    forever untracked with a live driver.
    """
    lock = sf.with_name(sf.name + ".lock")
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SessionLockedError(f"another daemon already holds {lock}") from exc
    try:
        os.write(fd, str(os.getpid()).encode("utf-8"))
    finally:
        os.close(fd)
    return lock


def serve(
    handler: SessionHandler,
    *,
    token: str,
    cwd: str | Path | None = None,
    host: str = "127.0.0.1",
) -> None:
    """Bind a JSON-lines TCP server, write the session file, serve until shutdown."""
    sf = session_file(cwd)
    sf.parent.mkdir(parents=True, exist_ok=True)
    # Claim ownership atomically BEFORE binding / writing session.json so a
    # concurrently-spawned duplicate daemon aborts here and never serves.
    lock = _claim_lock(sf)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, 0))
    srv.listen(8)
    srv.settimeout(0.5)
    port = srv.getsockname()[1]

    # Write atomically (tmp file in the same dir + os.replace) so a concurrent
    # find_session() can never read a half-written file and delete it as "stale".
    payload = json.dumps(
        {
            "pid": os.getpid(),
            "port": port,
            "token": token,
            "engine": handler._engine,
            "headless": handler._headless,
            "url": handler._url,
            "started_at": time.time(),
        }
    )
    tmp = sf.with_name(f"{sf.name}.{os.getpid()}.tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, sf)

    stop = threading.Event()
    threads: list[threading.Thread] = []
    try:
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except TimeoutError:
                continue
            t = threading.Thread(
                target=_handle_conn, args=(conn, handler, token, stop), daemon=True
            )
            t.start()
            threads.append(t)
    finally:
        srv.close()
        handler.close()
        try:
            sf.unlink()
        except OSError:
            pass
        try:
            lock.unlink()
        except OSError:
            pass


def main(argv: list[str] | None = None) -> None:
    """Daemon entrypoint: ``python -m visus.web.cli.session_server [engine] [headless] [url]``.

    Engine/headless/url come from argv first, then env. Logs to ``.visus/daemon.log``.
    """
    argv = sys.argv[1:] if argv is None else argv
    engine = argv[0] if len(argv) > 0 and argv[0] else os.environ.get("VISUS_WEB_ENGINE", "chrome")
    if len(argv) > 1 and argv[1]:
        headless = argv[1] not in ("0", "false", "False", "no")
    else:
        headless = os.environ.get("VISUS_WEB_HEADLESS", "0") != "0"
    url = argv[2] if len(argv) > 2 and argv[2] else os.environ.get("VISUS_WEB_URL") or None
    token = os.environ.get("VISUS_WEB_TOKEN") or secrets.token_hex(16)

    log_dir = Path.cwd() / ".visus"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / "daemon.log"

    def _log(msg: str) -> None:
        with log.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

    _log(f"daemon starting engine={engine} headless={headless} url={url!r} pid={os.getpid()}")
    handler = SessionHandler(engine=engine, headless=headless, url=url)
    try:
        serve(handler, token=token)
    except SessionLockedError as exc:
        # A duplicate daemon lost the ownership race: exit cleanly (no browser
        # was launched, the winner owns session.json) instead of crashing.
        _log(f"daemon aborting: {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        _log(f"daemon crashed: {type(exc).__name__}: {exc}")
        raise
    finally:
        _log("daemon stopped")


if __name__ == "__main__":
    main()
