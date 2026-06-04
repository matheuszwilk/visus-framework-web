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
  goto url             navigate to url
  text N               print field N's text content
  screenshot [path]    save a screenshot (default screenshot.png)
  clear                remove the field highlight overlay
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
        if cmd == "goto":
            return f"navigated to {send('goto', {'url': rest[0]})}"
        if cmd in ("text", "get-text"):
            return str(send("get_text", _idx(rest[0])))
        if cmd == "screenshot":
            args = {"path": rest[0]} if rest else {}
            return f"saved {send('screenshot', args)}"
        if cmd == "clear":
            return str(send("clear_highlights", {}))
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
