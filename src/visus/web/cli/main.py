"""visus CLI — web automation commands."""

from __future__ import annotations

import json as _json
import runpy
from pathlib import Path
from typing import Any

import typer

from visus.web import Engine, launch

app = typer.Typer(
    help="visus.web — Playwright-style web automation on Selenium.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the visus.web version."""
    from visus.web import __version__

    typer.echo(__version__)


def _read_clipboard() -> str | None:
    """Best-effort read of the OS clipboard (so 'Copy element' → translate just works)."""
    import subprocess
    import sys

    cmd = {
        "win32": ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
        "darwin": ["pbpaste"],
    }.get(sys.platform, ["xclip", "-selection", "clipboard", "-o"])
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout or None
    except Exception:
        return None


@app.command()
def translate(
    html: str | None = typer.Argument(
        None, help="Element outerHTML. Omit to read the clipboard; or use --file / pipe via stdin."
    ),
    file: str | None = typer.Option(
        None, "--file", "-f", help="Read the element HTML from a file."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON (handy for scripts / AI)."),
) -> None:
    """Translate a pasted DevTools element into css/xpath/id/class selectors.

    Easiest on Windows (the shell mangles <, >, "): copy the element in DevTools
    (Copy element), then run ``visus translate`` with no argument — it reads your
    clipboard. You can also pass --file <path> or pipe the HTML via stdin.
    """
    import sys

    from visus.web.api._htmlsel import translate as _translate

    src = html
    if file:
        src = Path(file).read_text(encoding="utf-8")
    elif src is None:
        src = (None if sys.stdin.isatty() else sys.stdin.read()) or _read_clipboard()
    if not src or "<" not in src:
        typer.echo(
            "No element HTML found. Pass it as an argument, use --file <path>, pipe it via "
            "stdin, or copy the element to your clipboard first."
        )
        raise typer.Exit(2)

    r = _translate(src)
    if as_json:
        import json

        typer.echo(json.dumps(r, indent=2, ensure_ascii=False))
        return
    typer.echo(f"tag    : {r['tag']}")
    if r["id"]:
        typer.echo(f"id     : {r['id']}")
    if r["name"]:
        typer.echo(f"name   : {r['name']}")
    if r["css"]:
        typer.echo(f"css    : {r['css']}")
    if r["xpath"]:
        typer.echo(f"xpath  : {r['xpath']}")
    if r["class"]:
        typer.echo(f"class  : {r['class']}")
    typer.echo("candidates (the smart locator tries these in order):")
    for c in [*r["candidates_css"], *r["candidates_xpath"]]:  # type: ignore[misc]
        typer.echo(f"  - {c}")


@app.command()
def doctor(engine: str = "chrome") -> None:
    """Check that a browser + driver launch correctly."""
    try:
        with launch(Engine.from_str(engine), headless=True) as b:
            p = b.new_page()
            p.goto("data:text/html,<title>ok</title>")
            typer.echo(f"OK: {engine} launches and navigates (title: {p.title()!r})")
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"FAILED: {exc}")
        raise typer.Exit(1) from exc


@app.command()
def install(engine: str = "chrome") -> None:
    """Resolve/download the driver via Selenium Manager (by launching once)."""
    with launch(Engine.from_str(engine), headless=True):
        typer.echo(f"{engine} driver is ready (Selenium Manager).")


@app.command()
def screenshot(
    url: str,
    output: str = typer.Option("screenshot.png", "-o", "--output"),
    full_page: bool = False,
    headless: bool = True,
    engine: str = "chrome",
) -> None:
    """Screenshot a URL to a PNG file."""
    with launch(Engine.from_str(engine), headless=headless) as b:
        p = b.new_page()
        p.goto(url)
        p.screenshot(path=output, full_page=full_page)
    typer.echo(f"saved {output}")


@app.command()
def pdf(
    url: str,
    output: str = typer.Option("page.pdf", "-o", "--output"),
    engine: str = "chrome",
) -> None:
    """Print a URL to a PDF (Chromium)."""
    with launch(Engine.from_str(engine), headless=True) as b:
        p = b.new_page()
        p.goto(url)
        p.pdf(path=output)
    typer.echo(f"saved {output}")


@app.command()
def open(url: str, engine: str = "chrome") -> None:  # noqa: A001
    """Open a headed browser at URL and wait until you press Enter."""
    with launch(Engine.from_str(engine), headless=False) as b:
        b.new_page().goto(url)
        typer.echo("Browser open. Press Enter to close...")
        input()


@app.command()
def run(script: str) -> None:
    """Run a Python script (convenience)."""
    runpy.run_path(script, run_name="__main__")


@app.command()
def mcp() -> None:
    """Start the visus.web MCP server (stdio)."""
    from visus.web.mcp.server import main as mcp_main

    mcp_main()


@app.command()
def codegen(
    url: str,
    output: str | None = typer.Option(None, "-o", "--output"),
    engine: str = "chrome",
) -> None:
    """Record interactions in a headed browser and generate visus.web code."""
    from visus.web.cli.codegen import drain, generate_script, inject_recorder

    events: list[dict] = []  # type: ignore[type-arg]
    with launch(Engine.from_str(engine), headless=False) as b:
        p = b.new_page()
        p.goto(url)
        inject_recorder(p)
        typer.echo("Recording... interact with the page, then press Enter to finish.")
        try:
            input()
        finally:
            events = drain(p)
    code = generate_script(url, events)
    if output:
        Path(output).write_text(code, encoding="utf-8")
        typer.echo(f"saved {output}")
    else:
        typer.echo(code)


# ---------------------------------------------------------------------------
# Persistent session: daemon + thin client commands + REPL
# ---------------------------------------------------------------------------

session_app = typer.Typer(help="Manage the persistent browser session (daemon).")
app.add_typer(session_app, name="session")


def _send(op: str, args: dict[str, Any] | None = None) -> Any:
    """Send an op to the running daemon, mapping failures to a clean Exit(1)."""
    from visus.web.cli import session_client

    try:
        return session_client.send(op, args or {})
    except session_client.SessionError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(1) from exc


def _format_fields(fields: list[dict[str, Any]]) -> str:
    from visus.web.cli.console import format_fields

    return format_fields(fields)


def _target_args(
    index: int | None,
    selector: str | None,
    role: str | None,
    name: str | None,
    text: str | None,
) -> dict[str, Any]:
    """Build the {index|selector|role|name|text} target dict for an action op."""
    if index is not None:
        return {"index": index}
    if not (selector or role or text):
        typer.echo("error: provide an index, or --selector / --role / --text")
        raise typer.Exit(1)
    return {"selector": selector, "role": role, "name": name, "target_text": text}


@session_app.command("start")
def session_start(
    url: str = typer.Argument(None, help="URL to open once the browser starts."),
    engine: str = typer.Option("chrome", "--engine", "-e"),
    headless: bool = typer.Option(False, "--headless", help="Run headless (default: headed)."),
) -> None:
    """Start a persistent browser session (detached daemon)."""
    from visus.web.cli import session_client

    try:
        info = session_client.start_daemon(engine, headless, url)
    except session_client.SessionError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(1) from exc
    typer.echo(f"session started (pid {info['pid']}, port {info['port']}, engine {engine})")


@session_app.command("stop")
def session_stop() -> None:
    """Stop the running session (closes the browser)."""
    from visus.web.cli import session_client

    typer.echo(session_client.stop())


@session_app.command("status")
def session_status(
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
) -> None:
    """Show the running session's status."""
    from visus.web.cli import session_client

    info = session_client.status()
    if info is None:
        typer.echo("no session running")
        raise typer.Exit(1)
    if as_json:
        typer.echo(_json.dumps(info, indent=2, ensure_ascii=False))
        return
    keys = ("pid", "port", "engine", "headless", "url", "title", "windows", "active_tab",
            "fields_cached")
    for k in keys:
        if k in info:
            typer.echo(f"{k:14}: {info[k]}")


@app.command("list-fields")
def list_fields(
    kind: str = typer.Option(None, "--kind", help="Comma-separated kinds (e.g. input,button)."),
    show_all: bool = typer.Option(False, "--all", help="Include hidden/disabled fields."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
    no_highlight: bool = typer.Option(False, "--no-highlight", help="Skip the numbered overlay."),
) -> None:
    """Enumerate interactive fields on the current page (numbered, highlighted)."""
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    result = _send(
        "list_fields",
        {"kinds": kinds, "include_hidden": show_all, "highlight": not no_highlight},
    )
    fields = result.get("fields", [])
    if as_json:
        typer.echo(_json.dumps(fields, indent=2, ensure_ascii=False))
        return
    typer.echo(_format_fields(fields))


@app.command()
def click(
    index: int = typer.Argument(None, help="Field index from the last list-fields."),
    selector: str = typer.Option(None, "--selector", "-s"),
    role: str = typer.Option(None, "--role"),
    name: str = typer.Option(None, "--name"),
    text: str = typer.Option(None, "--text"),
) -> None:
    """Click a field by index or by --selector/--role/--text."""
    typer.echo(_send("click", _target_args(index, selector, role, name, text)))


@app.command()
def fill(
    index: int = typer.Argument(None, help="Field index from the last list-fields."),
    text: str = typer.Argument(None, help="Text to fill, e.g. `visus fill 7 hello`."),
    selector: str = typer.Option(None, "--selector", "-s"),
    role: str = typer.Option(None, "--role"),
    name: str = typer.Option(None, "--name"),
    by_text: str = typer.Option(None, "--text", help="Target a field by its visible text."),
    value: str = typer.Option(
        None, "--value", help="Text to fill when targeting by --selector/--role/--text."
    ),
) -> None:
    """Fill a field. By index: `visus fill 7 hello`. By selector: `-s "#u" --value hello`."""
    args = _target_args(index, selector, role, name, by_text)
    fill_value = text if text is not None else value
    if fill_value is None:
        typer.echo("error: no text to fill — use `visus fill <index> <text>` or `--value`")
        raise typer.Exit(1)
    args["text"] = fill_value
    typer.echo(_send("fill", args))


@app.command()
def check(
    index: int = typer.Argument(None),
    selector: str = typer.Option(None, "--selector", "-s"),
    role: str = typer.Option(None, "--role"),
    name: str = typer.Option(None, "--name"),
) -> None:
    """Check a checkbox/radio field."""
    typer.echo(_send("check", _target_args(index, selector, role, name, None)))


@app.command()
def uncheck(
    index: int = typer.Argument(None),
    selector: str = typer.Option(None, "--selector", "-s"),
    role: str = typer.Option(None, "--role"),
    name: str = typer.Option(None, "--name"),
) -> None:
    """Uncheck a checkbox field."""
    typer.echo(_send("uncheck", _target_args(index, selector, role, name, None)))


@app.command()
def select(
    index: int = typer.Argument(None, help="Field index from the last list-fields."),
    value: str = typer.Argument(None, help="Option value, e.g. `visus select 5 US`."),
    selector: str = typer.Option(None, "--selector", "-s"),
    role: str = typer.Option(None, "--role"),
    name: str = typer.Option(None, "--name"),
    by_text: str = typer.Option(None, "--text", help="Target a field by its visible text."),
    option_value: str = typer.Option(
        None, "--value", help="Option value when targeting by --selector/--role/--text."
    ),
) -> None:
    """Select an option on a <select> field. By index: `visus select 5 US`."""
    args = _target_args(index, selector, role, name, by_text)
    val = value if value is not None else option_value
    if val is None:
        typer.echo("error: no option value — use `visus select <index> <value>` or `--value`")
        raise typer.Exit(1)
    args["value"] = val
    typer.echo(_send("select", args))


@app.command()
def press(
    index: int = typer.Argument(None, help="Field index from the last list-fields."),
    key: str = typer.Argument(None, help="Key to press, e.g. `visus press 7 Enter`."),
    selector: str = typer.Option(None, "--selector", "-s"),
    role: str = typer.Option(None, "--role"),
    name: str = typer.Option(None, "--name"),
    by_text: str = typer.Option(None, "--text", help="Target a field by its visible text."),
    key_value: str = typer.Option(
        None, "--key", help="Key when targeting by --selector/--role/--text."
    ),
) -> None:
    """Press a key on a field (e.g. Enter, Tab, Control+a). By index: `visus press 7 Enter`."""
    args = _target_args(index, selector, role, name, by_text)
    k = key if key is not None else key_value
    if k is None:
        typer.echo("error: no key — use `visus press <index> <key>` or `--key`")
        raise typer.Exit(1)
    args["key"] = k
    typer.echo(_send("press", args))


@app.command()
def goto(url: str = typer.Argument(..., help="URL to navigate to.")) -> None:
    """Navigate the session's page to a URL."""
    typer.echo(f"navigated to {_send('goto', {'url': url})}")


@app.command("get-text")
def get_text(
    index: int = typer.Argument(None),
    selector: str = typer.Option(None, "--selector", "-s"),
    role: str = typer.Option(None, "--role"),
    name: str = typer.Option(None, "--name"),
    text: str = typer.Option(None, "--text"),
) -> None:
    """Print a field's text content."""
    typer.echo(_send("get_text", _target_args(index, selector, role, name, text)))


@app.command("session-screenshot")
def session_screenshot(
    output: str = typer.Option("screenshot.png", "-o", "--output"),
) -> None:
    """Screenshot the session's current page to a PNG file."""
    # Resolve the path against the CLIENT's cwd (not the daemon's) so the PNG
    # lands where the user invoked the command, not under the daemon's base dir.
    abs_output = str(Path(output).resolve())
    typer.echo(f"saved {_send('screenshot', {'path': abs_output})}")


@app.command("clear")
def clear_highlights() -> None:
    """Remove the numbered field-highlight overlay."""
    typer.echo(_send("clear_highlights", {}))


@app.command()
def tabs(as_json: bool = typer.Option(False, "--json", help="Emit JSON.")) -> None:
    """List open tabs/windows (the active one is marked with *)."""
    result = _send("tabs", {})
    if as_json:
        typer.echo(_json.dumps(result, indent=2, ensure_ascii=False))
        return
    items = result.get("tabs", [])
    if not items:
        typer.echo("(no tabs)")
        return
    for t in items:
        mark = "*" if t.get("active") else " "
        typer.echo(f"{mark} [{t['index']}] {str(t.get('title', ''))!r}  {t.get('url', '')}")


@app.command()
def tab(
    index: int = typer.Argument(None, help="Tab/window index from `visus tabs` (omit = newest)."),
) -> None:
    """Switch the session to a tab/window by index (or the newest if omitted)."""
    result = _send("tab", {"index": index})
    typer.echo(f"switched to tab {result['active']}: {str(result.get('title', ''))!r}")


@app.command()
def console(
    url: str = typer.Argument(None, help="Optional URL to open."),
    engine: str = typer.Option("chrome", "--engine", "-e"),
    headless: bool = typer.Option(False, "--headless"),
) -> None:
    """Open an interactive REPL attached to the session (starts one if none)."""
    from visus.web.cli.console import run_console

    run_console(url, engine=engine, headless=headless)
