"""Tests for the batteries-included rpa() session."""

from __future__ import annotations

import pytest

from visus.web import errors, rpa
from visus.web.rpa import _slug


def test_slug_is_filesystem_safe() -> None:
    assert _slug("My Login!") == "My-Login"
    assert _slug("a/b c") == "a-b-c"
    assert _slug("") == "run"
    assert _slug("keep-this_ok") == "keep-this_ok"


@pytest.mark.browser
def test_rpa_writes_zip_and_report(base_url, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """rpa() handles launch + record + report with zero plumbing in user code."""
    out = tmp_path / "out"
    with rpa("t", headless=True, outdir=str(out), summary=False) as page:
        page.goto(f"{base_url}/forms.html")
        page.get_by_label("Username").fill("ada")
    assert (out / "run.zip").exists()
    assert (out / "report.html").exists()
    assert "visus.web run report" in (out / "report.html").read_text(encoding="utf-8")


@pytest.mark.browser
def test_rpa_reports_even_on_failure(base_url, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A failing step still produces the report (then the error propagates)."""
    out = tmp_path / "out"
    with pytest.raises(errors.VisusWebError):
        with rpa("t", headless=True, outdir=str(out), summary=False) as page:
            page.goto(f"{base_url}/forms.html")
            page.locator("#nope-xyz").click(timeout=400)
    assert (out / "report.html").exists()  # report written despite the failure
    assert (out / "run.zip").exists()
