"""CLI tests using typer.testing.CliRunner."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from visus.web.cli.main import app

runner = CliRunner()


def test_version() -> None:
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0 and "0.0.1" in r.output


def test_help_lists_commands() -> None:
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    for cmd in ("doctor", "screenshot", "pdf", "codegen", "mcp", "open", "run", "install"):
        assert cmd in r.output, f"command {cmd!r} missing from --help output"


def test_doctor_failed_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Doctor exits 1 and prints FAILED when launch raises."""
    from visus.web import errors

    def _boom(*a: object, **kw: object) -> object:
        raise errors.VisusWebError("no driver")

    monkeypatch.setattr("visus.web.cli.main.launch", _boom)
    r = runner.invoke(app, ["doctor"])
    assert r.exit_code == 1 and "FAILED" in r.output


def test_run_executes_script(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run command executes a script via runpy."""
    script = tmp_path / "hello.py"  # type: ignore[operator]
    script.write_text("import sys; sys.exit(0)")  # type: ignore[union-attr]
    r = runner.invoke(app, ["run", str(script)])
    assert r.exit_code == 0


def test_install_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """install calls launch and prints ready message."""
    import contextlib

    @contextlib.contextmanager
    def _fake_launch(*a: object, **kw: object):  # type: ignore[no-untyped-def]
        yield None

    monkeypatch.setattr("visus.web.cli.main.launch", _fake_launch)
    r = runner.invoke(app, ["install"])
    assert r.exit_code == 0 and "ready" in r.output


def test_screenshot_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory
) -> None:
    """screenshot command writes a PNG file."""

    class _FakePage:
        def goto(self, url: str, **kw: object) -> None: ...

        def screenshot(self, *, path: str | None = None, full_page: bool = False) -> bytes:
            if path:
                from pathlib import Path

                Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
            return b"\x89PNG\r\n\x1a\n" + b"\x00" * 8

    class _FakeBrowser:
        def new_page(self) -> _FakePage:
            return _FakePage()

        def __enter__(self) -> _FakeBrowser:
            return self

        def __exit__(self, *a: object) -> None: ...

    monkeypatch.setattr("visus.web.cli.main.launch", lambda *a, **kw: _FakeBrowser())
    out = tmp_path / "s.png"  # type: ignore[operator]
    r = runner.invoke(app, ["screenshot", "http://example.com", "-o", str(out)])
    assert r.exit_code == 0 and "saved" in r.output


def test_pdf_command(monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
    """pdf command writes a PDF file."""

    class _FakePage:
        def goto(self, url: str, **kw: object) -> None: ...

        def pdf(self, *, path: str | None = None) -> bytes:
            if path:
                from pathlib import Path

                Path(path).write_bytes(b"%PDF-1.4\n")
            return b"%PDF-1.4\n"

    class _FakeBrowser:
        def new_page(self) -> _FakePage:
            return _FakePage()

        def __enter__(self) -> _FakeBrowser:
            return self

        def __exit__(self, *a: object) -> None: ...

    monkeypatch.setattr("visus.web.cli.main.launch", lambda *a, **kw: _FakeBrowser())
    out = tmp_path / "s.pdf"  # type: ignore[operator]
    r = runner.invoke(app, ["pdf", "http://example.com", "-o", str(out)])
    assert r.exit_code == 0 and "saved" in r.output


@pytest.mark.browser
def test_doctor(tmp_path: pytest.TempPathFactory) -> None:
    r = runner.invoke(app, ["doctor"])
    assert r.exit_code == 0 and "OK" in r.output


@pytest.mark.browser
def test_screenshot(tmp_path: pytest.TempPathFactory, base_url: str) -> None:
    out = tmp_path / "s.png"  # type: ignore[operator]
    r = runner.invoke(app, ["screenshot", f"{base_url}/forms.html", "-o", str(out)])
    assert r.exit_code == 0
    assert out.exists()  # type: ignore[union-attr]
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"  # type: ignore[union-attr]


@pytest.mark.browser
def test_pdf(tmp_path: pytest.TempPathFactory, base_url: str) -> None:
    out = tmp_path / "s.pdf"  # type: ignore[operator]
    r = runner.invoke(app, ["pdf", f"{base_url}/forms.html", "-o", str(out)])
    assert r.exit_code == 0
    assert out.exists()  # type: ignore[union-attr]
    assert out.read_bytes()[:5] == b"%PDF-"  # type: ignore[union-attr]
