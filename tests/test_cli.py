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
