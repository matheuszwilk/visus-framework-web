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
    assert any(e["action"] == "fill" and e["success"] for e in events)
    fail = [e for e in events if e["action"] == "click" and not e["success"]]
    assert fail and fail[0]["error"] and fail[0]["failure_screenshot"]
    # render report
    html_path = tmp_path / "report.html"
    tracing.render_report(str(zip_path), str(html_path))
    html = html_path.read_text(encoding="utf-8")
    assert "data:image/png;base64," in html and "fill" in html and "FAILED" in html


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
