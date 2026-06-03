"""Unit tests for visus.web.tracing (no browser required)."""

from __future__ import annotations

import zipfile

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
    assert "visus.web Observability Report" in html
    assert "Actions" in html
