"""visus CLI — web automation commands."""

from __future__ import annotations

import runpy
from pathlib import Path

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


@app.command()
def translate(html: str) -> None:
    """Translate a pasted DevTools element (Copy element) into css/xpath/id/class selectors."""
    from visus.web.api._htmlsel import translate as _translate

    r = _translate(html)
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
