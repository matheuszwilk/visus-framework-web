"""render_report: turn a tracing zip into a self-contained HTML report."""

from __future__ import annotations

import base64
import json
import zipfile
from pathlib import Path
from typing import Any

_STYLE = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, -apple-system, sans-serif;
  background: #faf9f5;
  color: #181715;
  padding: 24px;
}
h1 { font-size: 1.5rem; margin-bottom: 16px; color: #cc785c; }
h2 { font-size: 1.1rem; margin: 20px 0 10px; color: #181715; }
.kpi-strip {
  display: flex; flex-wrap: wrap; gap: 12px;
  background: #fff; border: 1px solid #e8e4dc;
  border-radius: 8px; padding: 16px; margin-bottom: 24px;
}
.kpi { text-align: center; min-width: 110px; }
.kpi .val {
  font-size: 1.8rem; font-weight: 700;
  color: #cc785c; display: block;
}
.kpi .lbl { font-size: 0.75rem; color: #555; text-transform: uppercase; }
.step {
  background: #fff; border: 1px solid #e8e4dc;
  border-radius: 8px; margin-bottom: 12px; overflow: hidden;
}
.step-header {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; background: #f5f3ee;
  border-bottom: 1px solid #e8e4dc;
}
.chip {
  background: #cc785c; color: #fff;
  font-size: 0.7rem; font-weight: 700;
  border-radius: 4px; padding: 2px 7px; letter-spacing: .04em;
  text-transform: uppercase;
}
.badge-ok  { background: #3a7d44; color: #fff; border-radius: 4px; padding: 2px 8px; font-size: 0.75rem; font-weight: 700; }
.badge-fail{ background: #b23b3b; color: #fff; border-radius: 4px; padding: 2px 8px; font-size: 0.75rem; font-weight: 700; }
.step-body { padding: 12px 14px; }
table.meta { width: 100%; border-collapse: collapse; font-size: 0.82rem; margin-bottom: 10px; }
table.meta td { padding: 3px 6px; }
table.meta td:first-child { color: #888; width: 130px; }
pre.err {
  background: #fff0ee; border: 1px solid #f5c6c6;
  border-radius: 4px; padding: 8px; font-size: 0.75rem;
  white-space: pre-wrap; word-break: break-all; margin-bottom: 10px; color: #8b0000;
}
.shot { max-width: 100%; border: 1px solid #e8e4dc; border-radius: 4px; }
"""


def _kpi(val: object, lbl: str) -> str:
    return f'<div class="kpi"><span class="val">{val}</span><span class="lbl">{lbl}</span></div>'


def _badge(success: bool) -> str:
    if success:
        return '<span class="badge-ok">SUCCESS</span>'
    return '<span class="badge-fail">FAILED</span>'


def _step_html(event: dict[str, Any], shots: dict[str, bytes]) -> str:
    action = event.get("action", "?")
    target = event.get("target") or event.get("selector") or ""
    success = bool(event.get("success"))
    duration = event.get("duration_ms", 0)
    cycles = event.get("backtrack_cycles", 0)
    role = event.get("role") or ""
    name = event.get("name") or ""
    url = event.get("url") or ""
    title = event.get("title") or ""
    bbox = event.get("bbox")
    error = event.get("error") or ""
    shot_key = event.get("failure_screenshot") or event.get("screenshot") or ""

    rows = [
        ("duration", f"{duration} ms"),
        ("backtrack_cycles", str(cycles)),
    ]
    if role:
        rows.append(("role", role))
    if name:
        rows.append(("accessible name", name))
    if url:
        rows.append(("url", url))
    if title:
        rows.append(("title", title))
    if bbox:
        rows.append(("bbox", str(bbox)))

    meta_rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)

    target_html = f"<code>{_esc(str(target))}</code>" if target else ""
    step_id = event.get("step_id", "?")
    ts = event.get("timestamp", "")

    img_html = ""
    if shot_key and shot_key in shots:
        b64 = base64.b64encode(shots[shot_key]).decode()
        img_html = f'<img class="shot" src="data:image/png;base64,{b64}" alt="screenshot"/>'

    err_html = f"<pre class='err'>{_esc(error)}</pre>" if error else ""

    return f"""
<div class="step">
  <div class="step-header">
    <span class="chip">{_esc(action)}</span>
    {target_html}
    {_badge(success)}
    <span style="margin-left:auto;font-size:0.75rem;color:#888;">#{step_id} &nbsp; {_esc(ts[:19])}</span>
  </div>
  <div class="step-body">
    <table class="meta"><tbody>{meta_rows}</tbody></table>
    {err_html}
    {img_html}
  </div>
</div>"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def render_report(zip_path: str, output: str = "report.html") -> str:
    """Read *zip_path* and write a self-contained HTML report to *output*.

    Returns the absolute path of the written file.
    """
    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
        events_raw = z.read("events.jsonl").decode("utf-8") if "events.jsonl" in names else ""
        manifest_raw = z.read("manifest.json").decode("utf-8") if "manifest.json" in names else "{}"
        shots: dict[str, bytes] = {}
        for n in names:
            if n.startswith("screenshots/") and n.endswith(".png"):
                key = n[len("screenshots/") :]
                shots[key] = z.read(n)

    events: list[dict[str, Any]] = [
        json.loads(line) for line in events_raw.splitlines() if line.strip()
    ]
    manifest: dict[str, Any] = json.loads(manifest_raw)

    counts = manifest.get("counts", {})
    total_actions = counts.get("actions", len(events))
    failures = counts.get("failures", sum(1 for e in events if not e.get("success")))
    success_rate = (
        f"{(total_actions - failures) / total_actions * 100:.0f}%" if total_actions else "N/A"
    )
    total_duration = sum(e.get("duration_ms", 0) for e in events)
    distinct_pages = len({e.get("url") for e in events if e.get("url")})
    total_backtracks = sum(e.get("backtrack_cycles", 0) for e in events)

    kpi_strip = (
        _kpi(total_actions, "Actions")
        + _kpi(failures, "Failures")
        + _kpi(success_rate, "Success Rate")
        + _kpi(f"{total_duration} ms", "Total Duration")
        + _kpi(distinct_pages, "Distinct Pages")
        + _kpi(total_backtracks, "Backtrack Cycles")
    )

    # Group events by run_id (preserve insertion order)
    runs: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        rid = str(e.get("run_id", "unknown"))
        runs.setdefault(rid, []).append(e)

    run_sections = ""
    for rid, evts in runs.items():
        steps_html = "".join(_step_html(e, shots) for e in evts)
        run_sections += f"<h2>Run <code>{_esc(rid)}</code> — {len(evts)} action(s)</h2>{steps_html}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>visus.web Observability Report</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>visus.web Observability Report</h1>
<div class="kpi-strip">{kpi_strip}</div>
{run_sections}
</body>
</html>"""

    out_path = Path(output)
    out_path.write_text(html, encoding="utf-8")
    return str(out_path.resolve())
