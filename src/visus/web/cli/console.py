"""Interactive REPL attached to a persistent CLI session.

The per-line command parsing/dispatch is a **pure function**
(:func:`dispatch(line, send_callable) -> str`) so it is fully testable with a
fake ``send``. :func:`run_console` wires that to a real session (starting one if
none is running) and the stdin read loop.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from visus.web.cli import session_client

# A send callable: (op, args) -> result (the daemon's `result` payload).
SendFn = Callable[[str, dict[str, Any]], Any]

_HELP = """commands:
  list                 enumerate + highlight interactive fields
  click N              click field N (or a previous list index)
  fill N text          fill field N with text
  check N              check field N
  uncheck N            uncheck field N
  select N value       select option `value` on field N
  press N key          press key on field N
  hover N              hover over field N
  dblclick N           double-click field N
  focus N              focus field N
  clear-input N        clear field N's value
  goto url             navigate to url
  back                 navigate back in history
  forward              navigate forward in history
  reload               reload the current page
  title                print the page title
  url                  print the current URL
  snapshot             list interactive elements (role/name)
  text N               print field N's text content
  attr name N          print field N's `name` attribute
  count N              count elements matching field N
  wait N [state]       wait until field N is visible/hidden
  expect N text...     assert field N contains text (PASSED/FAILED)
  cookies              list cookies for the context
  eval expr            evaluate a JS expression
  dialog [dismiss]     handle the next dialog (accept by default)
  screenshot [path]    save a screenshot (default screenshot.png)
  clear                remove the field highlight overlay
  tabs                 list open tabs/windows (active marked *)
  tab N                switch to tab/window N (omit N = newest)
  tab-new [url]        open a new tab (optionally at url)
  tab-close [N]        close tab N (omit N = active)
  help                 show this help
  quit                 exit the console (the session stays alive)"""


def format_fields(fields: list[dict[str, Any]], *, width: int | None = None) -> str:
    """Render fields as a pretty table: #, KIND, NAME, the ready VISUS call, CSS, XPATH.

    The VISUS column is copy-paste-ready and *frame-aware* — for an element inside
    an iframe it is wrapped in ``frame_locator(...)`` so a click/fill actually
    reaches it (a bare css/xpath would not). An ASCII box is used so the table
    renders correctly on any console encoding.
    """
    if not fields:
        return "(no fields found)"
    from rich import box
    from rich.console import Console
    from rich.table import Table

    table = Table(box=box.ASCII, header_style="bold", pad_edge=False, show_lines=True)
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("KIND", no_wrap=True)
    table.add_column("NAME", overflow="fold")
    table.add_column("VISUS (copy-paste)", overflow="fold", style="green")
    table.add_column("CSS", overflow="fold")
    table.add_column("XPATH", overflow="fold")
    for f in fields:
        name = str(f.get("name") or f.get("label") or f.get("placeholder") or "")
        table.add_row(
            str(f.get("index", "")),
            str(f.get("kind", "")),
            name,
            str(f.get("code", "")),
            str(f.get("css", "")),
            str(f.get("xpath", "")),
        )
    # Console() auto-detects the real terminal width (wide tables use the full
    # screen) and colour (TTY only); capture() preserves both. On a narrow pipe
    # rich folds long cells. `width` lets tests pin a deterministic size.
    console = Console(width=width) if width else Console()
    with console.capture() as cap:
        console.print(table)
    return cap.get().rstrip("\n")


def dispatch(line: str, send: SendFn) -> str:
    """Parse one REPL line, run it via *send*, and return printable output.

    Pure aside from the injected *send* callable -- the unit of testing.
    """
    line = line.strip()
    if not line:
        return ""
    parts = line.split()
    cmd = parts[0].lower()
    rest = parts[1:]

    def _idx(token: str) -> dict[str, Any]:
        return {"index": int(token)}

    try:
        if cmd in ("help", "?"):
            return _HELP
        if cmd in ("quit", "exit", "q"):
            return "__QUIT__"
        if cmd in ("list", "ls"):
            result = send("list_fields", {})
            return format_fields(result.get("fields", []))
        if cmd == "click":
            return str(send("click", _idx(rest[0])))
        if cmd == "fill":
            return str(send("fill", {**_idx(rest[0]), "text": " ".join(rest[1:])}))
        if cmd == "check":
            return str(send("check", _idx(rest[0])))
        if cmd == "uncheck":
            return str(send("uncheck", _idx(rest[0])))
        if cmd == "select":
            return str(send("select", {**_idx(rest[0]), "value": " ".join(rest[1:])}))
        if cmd == "press":
            return str(send("press", {**_idx(rest[0]), "key": " ".join(rest[1:])}))
        if cmd == "hover":
            return str(send("hover", _idx(rest[0])))
        if cmd == "dblclick":
            return str(send("dblclick", _idx(rest[0])))
        if cmd == "focus":
            return str(send("focus", _idx(rest[0])))
        if cmd == "clear-input":
            return str(send("clear_input", _idx(rest[0])))
        if cmd == "goto":
            return f"navigated to {send('goto', {'url': rest[0]})}"
        if cmd == "back":
            return f"went back to {send('back', {})}"
        if cmd == "forward":
            return f"went forward to {send('forward', {})}"
        if cmd == "reload":
            return f"reloaded {send('reload', {})}"
        if cmd == "title":
            return str(send("title", {}))
        if cmd == "url":
            return str(send("url", {}))
        if cmd == "snapshot":
            elements = send("snapshot", {}).get("elements", [])
            if not elements:
                return "(no elements)"
            return "\n".join(
                f"{str(e.get('role', '')):16} {e.get('name', '')}" for e in elements
            )
        if cmd in ("text", "get-text"):
            return str(send("get_text", _idx(rest[0])))
        if cmd in ("attr", "get-attribute"):
            return str(send("get_attribute", {**_idx(rest[1]), "attr_name": rest[0]}))
        if cmd == "count":
            return str(send("count", _idx(rest[0])))
        if cmd == "wait":
            args: dict[str, Any] = _idx(rest[0])
            if len(rest) > 1:
                args["state"] = rest[1]
            return str(send("wait", args))
        if cmd in ("expect", "expect-text"):
            return str(
                send("expect_text", {**_idx(rest[0]), "expected_text": " ".join(rest[1:])})
            )
        if cmd == "cookies":
            items = send("cookies", {}).get("cookies", [])
            if not items:
                return "(no cookies)"
            return "\n".join(
                f"{c.get('name', '')}={c.get('value', '')}  ({c.get('domain', '')})"
                for c in items
            )
        if cmd == "eval":
            return str(send("eval", {"expression": " ".join(rest)}).get("result"))
        if cmd == "dialog":
            accept = not (rest and rest[0].lower() in ("dismiss", "cancel", "no"))
            return str(send("dialog", {"accept": accept, "prompt_text": None}))
        if cmd == "screenshot":
            args = {"path": rest[0]} if rest else {}
            return f"saved {send('screenshot', args)}"
        if cmd == "clear":
            return str(send("clear_highlights", {}))
        if cmd == "tabs":
            items = send("tabs", {}).get("tabs", [])
            if not items:
                return "(no tabs)"
            return "\n".join(
                ("* " if t.get("active") else "  ")
                + f"[{t['index']}] {str(t.get('title', ''))!r}  {t.get('url', '')}"
                for t in items
            )
        if cmd == "tab":
            r = send("tab", {"index": int(rest[0]) if rest else None})
            return f"switched to tab {r['active']}: {str(r.get('title', ''))!r}"
        if cmd == "tab-new":
            r = send("tab_new", {"url": rest[0] if rest else None})
            return f"opened tab {r['index']}: {str(r.get('title', ''))!r}"
        if cmd == "tab-close":
            r = send("tab_close", {"index": int(rest[0]) if rest else None})
            if r.get("remaining", 0) == 0:
                return "closed the last tab — session stopped"
            return f"closed tab {r['closed']} ({r['remaining']} remaining)"
        return f"unknown command {cmd!r} (try `help`)"
    except IndexError:
        return f"missing argument for `{cmd}` (try `help`)"
    except session_client.SessionError as exc:
        return f"error: {exc}"


def run_console(
    url: str | None = None,
    *,
    engine: str = "chrome",
    headless: bool = False,
    start_dir: Any = None,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    """Attach to a session (start one if none) and run the REPL until `quit`."""
    info = session_client.find_session(start_dir)
    if info is None:
        output_fn("starting a new session...")
        session_client.start_daemon(engine, headless, url, cwd=start_dir)
    elif url:
        session_client.send("goto", {"url": url}, start_dir=start_dir)

    def _send(op: str, args: dict[str, Any]) -> Any:
        return session_client.send(op, args, start_dir=start_dir)

    output_fn("visus console — type `help` for commands, `quit` to exit.")
    while True:
        try:
            line = input_fn("visus> ")
        except (EOFError, KeyboardInterrupt):
            output_fn("")
            break
        out = dispatch(line, _send)
        if out == "__QUIT__":
            break
        if out:
            output_fn(out)
