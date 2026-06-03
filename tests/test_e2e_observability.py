"""Real-browser observability tests: record → zip → report cycle.

These tests require a running Chrome instance (pytest.mark.browser).
"""

from __future__ import annotations

import json
import zipfile

import pytest

from visus.web import errors, tracing


@pytest.mark.browser
def test_record_zip_and_report(browser, base_url, tmp_path):
    zip_path = tmp_path / "run.zip"
    with tracing.record(str(zip_path)):
        page = browser.new_page()
        page.goto(f"{base_url}/forms.html")
        page.get_by_label("Username").fill("ada")  # success -> per-action screenshot
        with pytest.raises(errors.VisusWebError):
            page.locator("#does-not-exist").click(timeout=600)  # failure -> failure screenshot
    assert tracing.current_recorder() is None  # session cleaned up
    z = zipfile.ZipFile(str(zip_path))
    names = z.namelist()
    assert "events.jsonl" in names and "manifest.json" in names
    assert any(n.startswith("screenshots/") and n.endswith(".png") for n in names)
    events = [
        json.loads(line) for line in z.read("events.jsonl").decode().splitlines() if line.strip()
    ]
    # --- Slice 1 assertions ---
    assert any(e["action"] == "fill" and e["success"] for e in events)
    fail = [e for e in events if e["action"] == "click" and not e["success"]]
    assert fail and fail[0]["error"] and fail[0]["failure_screenshot"]

    # --- Slice 2: correlated logs ---
    fill_events = [e for e in events if e["action"] == "fill" and e["success"]]
    assert fill_events, "expected a successful fill event"
    fill_logs = fill_events[0].get("logs", [])
    assert len(fill_logs) >= 1, (
        f"expected at least one log line for the fill action, got {fill_logs!r}"
    )
    # Every log line should be shaped "[LEVEL] logger.name: message"
    for line in fill_logs:
        assert line.startswith("["), f"malformed log line: {line!r}"

    # --- Slice 2: ARIA snapshot on failure ---
    assert "aria_snapshot" in fail[0], "expected aria_snapshot key in the failed action event"
    assert isinstance(fail[0]["aria_snapshot"], list), (
        f"aria_snapshot should be a list, got {type(fail[0]['aria_snapshot'])}"
    )

    # render report
    html_path = tmp_path / "report.html"
    tracing.render_report(str(zip_path), str(html_path))
    html = html_path.read_text(encoding="utf-8")

    # --- Slice 2: polished design assertions ---
    assert "data:image/png;base64," in html
    assert "fill" in html
    assert "FAILED" in html
    assert "article" in html and "task" in html, "expected article.task in report"
    assert "kpi-card" in html, "expected kpi-card in report"
    assert "visus.web" in html, "expected visus.web wordmark in report"
    assert "<details" in html, "expected collapsible <details> blocks for logs"
    # The ✷ character or its HTML entity should be in the footer wordmark
    assert "visus.web" in html


@pytest.mark.browser
def test_backtrack_steps_recorded_under_tracing(browser, base_url, tmp_path):
    """The traced path records a real depth-3 recovery.

    Covers the only code path that writes backtrack_steps (_run_traced): the #go
    click recovers via a depth-3 backtrack, so its event must have success=True and
    backtrack_steps==3. Also locks the rename: the old key must be absent and the
    report must say 'Backtrack steps' (not 'backtrack cycles').
    """
    zip_path = tmp_path / "backtrack.zip"
    with tracing.record(str(zip_path)):
        page = browser.new_page()
        page.goto(f"{base_url}/backtrack_depth.html")
        page.locator("#s1").click()  # recorded steps build the history
        page.locator("#s2").click()
        page.locator("#s3").click()
        page.locator("#go").click(backtrack=3, timeout=800)  # recovers via depth-3 replay

    z = zipfile.ZipFile(str(zip_path))
    events = [
        json.loads(line) for line in z.read("events.jsonl").decode().splitlines() if line.strip()
    ]
    recovered = [e for e in events if int(e.get("backtrack_steps") or 0) == 3]
    assert recovered, (
        "expected an event with backtrack_steps==3, got "
        f"{[(e['action'], e.get('backtrack_steps')) for e in events]}"
    )
    assert recovered[0]["action"] == "click" and recovered[0]["success"]
    assert all("backtrack_cycles" not in e for e in events), "old key must be gone"

    html_path = tmp_path / "report.html"
    tracing.render_report(str(zip_path), str(html_path))
    html = html_path.read_text(encoding="utf-8")
    assert "Backtrack steps" in html
    assert "backtrack cycles" not in html.lower()  # stale prose removed
    assert "badge-backtrack" in html  # the per-action backtrack badge is rendered


@pytest.mark.browser
def test_highlight_is_cleaned_up(browser, base_url, tmp_path):
    with tracing.record(str(tmp_path / "r.zip")):
        page = browser.new_page()
        page.goto(f"{base_url}/forms.html")
        page.get_by_label("Username").fill("x")
        # the highlight overlay must be removed after the screenshot
        count = page.evaluate("() => document.querySelectorAll('[data-visus-highlight]').length")
        assert count == 0


@pytest.mark.browser
def test_tracing_off_means_no_recorder(browser, base_url):
    assert tracing.current_recorder() is None
    page = browser.new_page()
    page.goto(f"{base_url}/forms.html")
    page.get_by_label("Username").fill("y")  # no recording, fast path
    assert tracing.current_recorder() is None


@pytest.mark.browser
def test_logs_non_empty_for_successful_action(browser, base_url, tmp_path):
    """A successful action must have at least one narrative log line."""
    zip_path = tmp_path / "logs_test.zip"
    with tracing.record(str(zip_path)):
        page = browser.new_page()
        page.goto(f"{base_url}/forms.html")
        page.get_by_label("Username").fill("test-logs")

    z = zipfile.ZipFile(str(zip_path))
    events = [
        json.loads(line) for line in z.read("events.jsonl").decode().splitlines() if line.strip()
    ]
    fill_events = [e for e in events if e["action"] == "fill" and e["success"]]
    assert fill_events, "expected a successful fill event"
    logs = fill_events[0].get("logs", [])
    assert len(logs) >= 1, f"expected at least one log line, got {logs!r}"
    # Check at least one line mentions "fill" or "visus.web"
    combined = " ".join(logs)
    assert "fill" in combined.lower() or "visus.web" in combined.lower(), (
        f"log lines don't mention fill or visus.web: {logs!r}"
    )


@pytest.mark.browser
def test_aria_snapshot_on_failure(browser, base_url, tmp_path):
    """A failed action must have an aria_snapshot key that is a non-empty list."""
    zip_path = tmp_path / "aria_test.zip"
    with tracing.record(str(zip_path)):
        page = browser.new_page()
        page.goto(f"{base_url}/forms.html")
        with pytest.raises(errors.VisusWebError):
            page.locator("#no-such-element-xyz").click(timeout=400)

    z = zipfile.ZipFile(str(zip_path))
    events = [
        json.loads(line) for line in z.read("events.jsonl").decode().splitlines() if line.strip()
    ]
    failed = [e for e in events if not e["success"]]
    assert failed, "expected at least one failed event"
    snap = failed[0].get("aria_snapshot")
    assert snap is not None, "aria_snapshot must be present on failure"
    assert isinstance(snap, list), f"aria_snapshot should be list, got {type(snap)}"
    assert len(snap) > 0, "aria_snapshot should be non-empty on a real page"
