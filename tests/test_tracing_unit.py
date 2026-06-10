"""Unit tests for visus.web.tracing (no browser required)."""

from __future__ import annotations

import zipfile

import pytest

from visus.web import tracing
from visus.web.tracing import _env_on

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _reset() -> None:
    """Put tracing back to a known default state after each test."""
    tracing.disable()
    tracing._STATE.recorder = None


# ---------------------------------------------------------------------------
# enable / disable
# ---------------------------------------------------------------------------


def test_disable_makes_is_enabled_false():
    _reset()
    tracing.disable()
    assert not tracing.is_enabled()


def test_enable_makes_is_enabled_true():
    _reset()
    tracing.enable()
    assert tracing.is_enabled()
    _reset()


def test_enable_then_disable_returns_false():
    _reset()
    tracing.enable()
    tracing.disable()
    assert not tracing.is_enabled()


def test_enable_sets_custom_options():
    _reset()
    tracing.enable(screenshot_each_action=False, screenshot_on_failure=False)
    opts = tracing.options()
    assert not opts.screenshot_each_action
    assert not opts.screenshot_on_failure
    # restore
    tracing.enable(screenshot_each_action=True, screenshot_on_failure=True)
    _reset()


# ---------------------------------------------------------------------------
# current_recorder outside a session
# ---------------------------------------------------------------------------


def test_current_recorder_is_none_outside_session():
    _reset()
    assert tracing.current_recorder() is None


# ---------------------------------------------------------------------------
# record() context manager
# ---------------------------------------------------------------------------


def test_record_context_sets_recorder(tmp_path):
    _reset()
    zip_path = str(tmp_path / "t.zip")
    with tracing.record(zip_path) as rec:
        assert tracing.current_recorder() is rec
        assert tracing.is_enabled()
    # after exit
    assert tracing.current_recorder() is None


def test_record_context_restores_previous_enabled_state(tmp_path):
    _reset()
    # tracing is OFF before the session
    assert not tracing.is_enabled()
    zip_path = str(tmp_path / "t.zip")
    with tracing.record(zip_path):
        pass
    assert not tracing.is_enabled()


def test_record_context_restores_state_on_exception(tmp_path):
    _reset()
    zip_path = str(tmp_path / "t.zip")
    try:
        with tracing.record(zip_path):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert tracing.current_recorder() is None
    assert not tracing.is_enabled()


def test_record_writes_zip_with_required_members(tmp_path):
    _reset()
    zip_path = str(tmp_path / "t.zip")
    with tracing.record(zip_path):
        pass  # no actions → empty recorder
    assert zipfile.is_zipfile(zip_path)
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
    assert "events.jsonl" in names
    assert "manifest.json" in names


# ---------------------------------------------------------------------------
# VISUS_WEB_TRACING env variable
# ---------------------------------------------------------------------------


def test_env_on_with_truthy_values(monkeypatch):
    for val in ("1", "true", "True", "yes", "YES"):
        monkeypatch.setenv("VISUS_WEB_TRACING", val)
        assert _env_on() is True


def test_env_on_with_falsy_values(monkeypatch):
    for val in ("0", "", "false", "False", "no", "NO"):
        monkeypatch.setenv("VISUS_WEB_TRACING", val)
        assert _env_on() is False


def test_env_off_when_not_set(monkeypatch):
    monkeypatch.delenv("VISUS_WEB_TRACING", raising=False)
    assert _env_on() is False


# ---------------------------------------------------------------------------
# render_report smoke test (no real browser — uses empty zip)
# ---------------------------------------------------------------------------


def test_render_report_produces_html_from_empty_zip(tmp_path):
    _reset()
    zip_path = str(tmp_path / "empty.zip")
    with tracing.record(zip_path):
        pass

    html_path = str(tmp_path / "report.html")
    tracing.render_report(zip_path, html_path)
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "visus.web run report" in html
    assert "actions" in html.lower()


# ---------------------------------------------------------------------------
# record(report=...) — auto-render the HTML report on exit, even on failure
# ---------------------------------------------------------------------------


def test_record_report_param_renders_on_success(tmp_path):
    _reset()
    zip_path = str(tmp_path / "run.zip")
    report_path = tmp_path / "report.html"
    with tracing.record(zip_path, report=str(report_path)):
        pass
    assert report_path.exists()
    assert "visus.web run report" in report_path.read_text(encoding="utf-8")
    _reset()


def test_record_report_param_renders_even_when_body_raises(tmp_path):
    _reset()
    zip_path = tmp_path / "run.zip"
    report_path = tmp_path / "report.html"
    # the body raises, yet both the zip AND the report are written before it propagates
    with pytest.raises(RuntimeError):
        with tracing.record(str(zip_path), report=str(report_path)):
            raise RuntimeError("rpa blew up")
    assert zip_path.exists()
    assert report_path.exists()
    assert "visus.web run report" in report_path.read_text(encoding="utf-8")
    _reset()


def test_rpa_print_summary_renders_failure(capsys, tmp_path):
    from pathlib import Path

    from visus.web.rpa import _print_summary

    class _Rec:
        def summary(self):
            return {
                "steps": [("click", True), ("fill", False)],
                "failures": 1,
                "total": 2,
                "backtrack_steps": 1,
            }

    _print_summary(
        _Rec(), tmp_path, Path(tmp_path) / "report.html", error=RuntimeError("boom\nline2")
    )
    out = capsys.readouterr().out
    assert "FAILED" in out
    assert "fill(FAILED)" in out
    assert "boom" in out and "line2" in out
    assert "report" in out


def test_rpa_print_summary_ok_without_report(capsys, tmp_path):
    from visus.web.rpa import _print_summary

    class _Rec:
        def summary(self):
            return {"steps": [], "failures": 0, "total": 0, "backtrack_steps": 0}

    _print_summary(_Rec(), tmp_path, None)
    out = capsys.readouterr().out
    assert "[OK]" in out
    assert "report" not in out


def test_rpa_forwards_launch_options(monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    import visus.web

    captured = {}

    class _B:
        def new_page(self):
            return MagicMock()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    def fake_launch(engine, *, headless=False, slow_mo=0, user_data_dir=None, remote_url=None):
        captured.update(
            engine=engine,
            headless=headless,
            slow_mo=slow_mo,
            user_data_dir=user_data_dir,
            remote_url=remote_url,
        )
        return _B()

    monkeypatch.setattr(visus.web, "launch", fake_launch)
    from visus.web import rpa

    with rpa(
        "fwd",
        headless=True,
        slow_mo=5,
        user_data_dir="C:/perfil/erp",
        remote_url="http://grid:4444/wd/hub",
        outdir=str(tmp_path),
        report=False,
        summary=False,
    ):
        pass
    assert captured["user_data_dir"] == "C:/perfil/erp"
    assert captured["remote_url"] == "http://grid:4444/wd/hub"
    assert captured["slow_mo"] == 5 and captured["headless"] is True
