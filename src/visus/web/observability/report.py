"""Single-file HTML run report for visus.web (Observability Slice 2).

Reads the ``events.jsonl`` from a session zip (see
``visus.web.observability.recorder``) and renders a self-contained HTML file
suitable for emailing, attaching to a CI artefact, or pinning in a bug
ticket. Every PNG referenced by ``screenshot`` or ``failure_screenshot`` is
embedded as a base64 data URI so the report has no external dependencies.

The styling follows the design tokens documented in
``D:\\bot_vision\\DESIGN.md`` (Anthropic Claude design system):

  * cream canvas ``#faf9f5``  -- page floor
  * surface card ``#efe9de``  -- feature card backgrounds
  * dark navy ``#181715``     -- code / terminal / footer surfaces
  * coral ``#cc785c``         -- primary CTA / KPI accent
  * ink ``#141413``           -- headlines + body emphasis
  * body ``#3d3d3a``          -- running text
  * muted ``#6c6a64``         -- captions and labels
  * hairline ``#e6dfd8``      -- 1px dividers
  * EB Garamond / Tiempos / Cormorant fallback for serif display
    headlines; Inter / system sans for body; JetBrains Mono for code
"""

from __future__ import annotations

import base64
import json
import os
import zipfile
from collections.abc import Iterable
from html import escape
from pathlib import Path
from typing import Any

_EVENTS_FILE = "events.jsonl"
_SCREENSHOTS_DIR = "screenshots/"

_CSS = """
:root {
  --canvas: #faf9f5;
  --surface-card: #efe9de;
  --surface-cream-strong: #e8e0d2;
  --surface-dark: #181715;
  --surface-dark-soft: #1f1e1b;
  --ink: #141413;
  --body: #3d3d3a;
  --muted: #6c6a64;
  --muted-soft: #8e8b82;
  --hairline: #e6dfd8;
  --primary: #cc785c;
  --primary-active: #a9583e;
  --on-primary: #ffffff;
  --on-dark: #faf9f5;
  --on-dark-soft: #a09d96;
  --success: #5db872;
  --error: #c64545;
  --serif: Copernicus, 'Tiempos Headline', 'EB Garamond', 'Cormorant Garamond', Garamond, 'Times New Roman', serif;
  --sans: StyreneB, Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;
}
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--canvas);
  color: var(--body);
  font-family: var(--sans);
  font-size: 16px;
  line-height: 1.55;
}
main { max-width: 1200px; margin: 0 auto; padding: 0 32px; }
header.hero {
  padding: 96px 32px 48px;
  max-width: 1200px;
  margin: 0 auto;
}
header.hero h1 {
  font-family: var(--serif);
  font-weight: 400;
  font-size: 64px;
  line-height: 1.05;
  letter-spacing: -1.5px;
  color: var(--ink);
  margin: 0 0 16px;
}
header.hero p.lede {
  font-family: var(--sans);
  font-size: 18px;
  color: var(--muted);
  margin: 0;
}
header.hero .run-meta {
  display: flex;
  gap: 12px;
  margin-top: 24px;
  flex-wrap: wrap;
}
.badge-pill {
  display: inline-block;
  background: var(--surface-card);
  color: var(--ink);
  font-size: 13px;
  font-weight: 500;
  padding: 4px 12px;
  border-radius: 9999px;
}
.badge-coral {
  display: inline-block;
  background: var(--primary);
  color: var(--on-primary);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  padding: 4px 12px;
  border-radius: 9999px;
}
.badge-success {
  display: inline-block;
  background: var(--surface-card);
  color: var(--success);
  font-size: 13px;
  font-weight: 500;
  padding: 4px 12px;
  border-radius: 9999px;
}
.badge-failure {
  display: inline-block;
  background: var(--primary);
  color: var(--on-primary);
  font-size: 13px;
  font-weight: 500;
  padding: 4px 12px;
  border-radius: 9999px;
}
.badge-backtrack {
  display: inline-block;
  background: var(--surface-cream-strong);
  color: var(--primary-active);
  font-size: 12px;
  font-weight: 600;
  padding: 4px 12px;
  border-radius: 9999px;
  margin-top: 8px;
  white-space: nowrap;
}
section.kpis {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 96px;
}
.kpi-card {
  background: var(--surface-card);
  border-radius: 12px;
  padding: 32px;
}
.kpi-card .label {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 12px;
}
.kpi-card .value {
  font-family: var(--serif);
  font-weight: 400;
  font-size: 36px;
  line-height: 1.15;
  letter-spacing: -0.5px;
  color: var(--ink);
}
section.timeline {
  margin-bottom: 96px;
}
section.timeline h2 {
  font-family: var(--serif);
  font-weight: 400;
  font-size: 36px;
  line-height: 1.15;
  letter-spacing: -0.5px;
  color: var(--ink);
  margin: 0 0 32px;
}
article.task {
  border-top: 1px solid var(--hairline);
  padding: 24px 0;
  display: grid;
  grid-template-columns: 56px 1fr auto;
  gap: 24px;
  align-items: start;
}
article.task:first-of-type { border-top: none; }
article.task .index {
  font-family: var(--serif);
  font-weight: 400;
  font-size: 28px;
  line-height: 1.2;
  letter-spacing: -0.3px;
  color: var(--muted-soft);
}
article.task .body h3 {
  margin: 0 0 6px;
  font-size: 18px;
  font-weight: 500;
  color: var(--ink);
}
article.task .body .meta {
  font-size: 14px;
  color: var(--muted);
}
article.task .status {
  text-align: right;
  min-width: 140px;
}
article.task pre.error {
  font-family: var(--mono);
  font-size: 14px;
  line-height: 1.6;
  margin-top: 12px;
  padding: 16px 20px;
  background: var(--surface-dark);
  color: var(--on-dark);
  border-radius: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
}
.screenshot-card {
  margin-top: 16px;
  padding: 24px;
  background: var(--surface-dark);
  border-radius: 12px;
}
.screenshot-card .header {
  color: var(--on-dark-soft);
  font-family: var(--mono);
  font-size: 12px;
  margin-bottom: 12px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
}
.screenshot-card img {
  max-width: 100%;
  height: auto;
  display: block;
  border-radius: 8px;
  background: var(--surface-dark-soft);
}
footer.site {
  background: var(--surface-dark);
  color: var(--on-dark-soft);
  padding: 64px 32px;
  font-size: 14px;
}
footer.site .inner {
  max-width: 1200px;
  margin: 0 auto;
}
footer.site .wordmark {
  color: var(--on-dark);
  font-family: var(--serif);
  font-weight: 400;
  font-size: 22px;
  letter-spacing: -0.3px;
  margin-bottom: 12px;
}
.run-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 48px 0 8px;
  flex-wrap: wrap;
}
.run-header h3 {
  font-family: var(--serif);
  font-weight: 400;
  font-size: 22px;
  letter-spacing: -0.3px;
  color: var(--ink);
  margin: 0;
}
.run-header .run-sub { font-size: 13px; color: var(--muted); }
.chip {
  display: inline-block;
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--surface-cream-strong);
  color: var(--body);
  margin-right: 8px;
  vertical-align: middle;
}
article.task .body h3 code { font-family: var(--mono); font-size: 15px; }
dl.kv {
  margin: 8px 0 0;
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 2px 16px;
  font-size: 13px;
}
dl.kv dt { color: var(--muted-soft); font-family: var(--mono); }
dl.kv dd { margin: 0; color: var(--body); font-family: var(--mono); }
.screenshot-card.step { background: var(--surface-cream-strong); }
.screenshot-card.step .header { color: var(--muted); }
.screenshot-card.step img { background: var(--canvas); }
details.logs {
  margin-top: 16px;
  background: var(--surface-dark);
  border-radius: 12px;
  padding: 12px 20px;
  color: var(--on-dark-soft);
  font-family: var(--mono);
}
details.logs > summary {
  cursor: pointer;
  font-size: 12px;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--on-dark);
  padding: 4px 0;
}
details.logs > summary::marker { color: var(--primary); }
details.logs pre.log-output {
  margin: 12px 0 4px;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--on-dark);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 360px;
  overflow-y: auto;
}
details.logs pre.log-output .lvl-DEBUG { color: var(--on-dark-soft); }
details.logs pre.log-output .lvl-INFO { color: var(--on-dark); }
details.logs pre.log-output .lvl-WARNING { color: #e2b35a; }
details.logs pre.log-output .lvl-ERROR { color: #e07171; }
details.logs pre.log-output .lvl-CRITICAL { color: #e07171; font-weight: 700; }
@media (max-width: 900px) {
  section.kpis { grid-template-columns: repeat(2, 1fr); }
  header.hero h1 { font-size: 44px; letter-spacing: -1px; }
  article.task { grid-template-columns: 40px 1fr; }
  article.task .status { grid-column: 2; text-align: left; }
}
@media (max-width: 600px) {
  section.kpis { grid-template-columns: 1fr; }
  main, header.hero { padding: 48px 20px; }
}
""".strip()


def render_report(zip_path: str, output: str = "report.html") -> str:
    """Read *zip_path* and write a self-contained HTML report to *output*.

    Returns the absolute path of the written file.
    """
    events, screenshots = _read_session(Path(zip_path))
    html = _render_html(events, screenshots)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out.resolve())


def _read_session(zip_path: Path) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    """Return ``(events, {basename: png_bytes})`` from a session zip."""
    if not zip_path.exists():
        raise FileNotFoundError(zip_path)
    events: list[dict[str, Any]] = []
    screenshots: dict[str, bytes] = {}
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if _EVENTS_FILE in names:
            raw = zf.read(_EVENTS_FILE).decode("utf-8")
            for line in raw.splitlines():
                if line.strip():
                    events.append(json.loads(line))
        for name in names:
            if name.startswith(_SCREENSHOTS_DIR) and name.lower().endswith(".png"):
                screenshots[os.path.basename(name)] = zf.read(name)
    return events, screenshots


def _kpis(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compute the headline KPIs displayed in the report's KPI strip."""
    events_list = list(events)
    total = len(events_list)
    if total == 0:
        return {
            "total": 0,
            "success_rate_pct": 0,
            "total_duration_ms": 0,
            "failed": 0,
            "distinct_pages": 0,
            "backtrack_steps": 0,
        }
    succeeded = sum(1 for e in events_list if e.get("success"))
    total_duration = sum(int(e.get("duration_ms") or 0) for e in events_list)
    distinct_pages = len({e.get("url") for e in events_list if e.get("url")})
    total_backtracks = sum(int(e.get("backtrack_steps") or 0) for e in events_list)
    return {
        "total": total,
        "success_rate_pct": round(succeeded / total * 100),
        "total_duration_ms": total_duration,
        "failed": total - succeeded,
        "distinct_pages": distinct_pages,
        "backtrack_steps": total_backtracks,
    }


def _group_runs(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group events into runs (by ``run_id``), preserving first-seen order."""
    runs: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    for e in events:
        rid = str(e.get("run_id") or "n/a")
        run = index.get(rid)
        if run is None:
            run = {"run_id": rid, "events": []}
            index[rid] = run
            runs.append(run)
        run["events"].append(e)
    for run in runs:
        evs = run["events"]
        run["ts"] = evs[0].get("timestamp", "")
        run["ok"] = sum(1 for e in evs if e.get("success"))
        run["total"] = len(evs)
    return runs


def _render_html(events: list[dict[str, Any]], screenshots: dict[str, bytes]) -> str:
    kpis = _kpis(events)
    runs = _group_runs(events)
    last_ts = events[-1]["timestamp"] if events else ""
    run_label = f"{len(runs)} run{'s' if len(runs) != 1 else ''}"

    if runs:
        sections = []
        for run in runs:
            tasks_html = "\n".join(
                _render_task(e, screenshots, n + 1) for n, e in enumerate(run["events"])
            )
            failed = run["total"] - run["ok"]
            status = (
                f"{run['ok']}/{run['total']} ok"
                if not failed
                else f"{run['ok']}/{run['total']} ok &middot; {failed} failed"
            )
            sections.append(
                f'<div class="run-header"><h3>Run {escape(run["run_id"])}</h3>'
                f'<span class="run-sub">{escape(str(run["ts"]))} &middot; {status}</span></div>'
                f"{tasks_html}"
            )
        task_rows = "\n".join(sections)
    else:
        task_rows = ""

    has_failures = kpis["total"] > 0 and kpis["success_rate_pct"] < 100
    failures_badge = '<span class="badge-coral">failures present</span>' if has_failures else ""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>visus.web run report</title>
  <style>{_CSS}</style>
</head>
<body>
  <header class="hero">
    <h1>visus.web run report</h1>
    <p class="lede">A timeline of every action, with durations, backtrack steps and failure
       screenshots embedded inline.</p>
    <div class="run-meta">
      <span class="badge-pill">{run_label}</span>
      <span class="badge-pill">{escape(last_ts)}</span>
      {failures_badge}
    </div>
  </header>

  <main>
    <section class="kpis" aria-label="Run summary">
      <div class="kpi-card">
        <div class="label">Total actions</div>
        <div class="value">{kpis["total"]}</div>
      </div>
      <div class="kpi-card">
        <div class="label">Success rate</div>
        <div class="value">{kpis["success_rate_pct"]}%</div>
      </div>
      <div class="kpi-card">
        <div class="label">Total duration</div>
        <div class="value">{kpis["total_duration_ms"]} ms</div>
      </div>
      <div class="kpi-card">
        <div class="label">Failures</div>
        <div class="value">{kpis["failed"]}</div>
      </div>
      <div class="kpi-card">
        <div class="label">Distinct pages</div>
        <div class="value">{kpis["distinct_pages"]}</div>
      </div>
      <div class="kpi-card">
        <div class="label">Backtrack steps</div>
        <div class="value">{kpis["backtrack_steps"]}</div>
      </div>
    </section>

    <section class="timeline">
      <h2>Timeline</h2>
      {task_rows if task_rows else '<p style="color: var(--muted);">No actions recorded.</p>'}
    </section>
  </main>

  <footer class="site">
    <div class="inner">
      <div class="wordmark">&#10007; visus.web</div>
      <div>Generated from <code>{escape(_EVENTS_FILE)}</code>. Design system: cream canvas + coral CTA + dark navy product surfaces.</div>
    </div>
  </footer>
</body>
</html>
"""


def _render_task(event: dict[str, Any], screenshots: dict[str, bytes], number: int) -> str:
    success = bool(event.get("success"))
    badge = (
        '<span class="badge-success">SUCCESS</span>'
        if success
        else '<span class="badge-failure">FAILED</span>'
    )

    # Action chip + target display
    action = escape(str(event.get("action") or "action"))
    role = event.get("role") or ""
    name = event.get("name") or ""
    selector = event.get("selector") or ""
    url_val = event.get("url") or ""
    target_val = event.get("target") or ""

    # Prefer role=X name="Y" when role present, else selector, else url for goto
    if role:
        target_display = f"role={escape(str(role))} name=&quot;{escape(str(name))}&quot;"
    elif selector:
        target_display = escape(str(selector))
    elif target_val:
        target_display = escape(str(target_val))
    elif url_val:
        target_display = escape(str(url_val))
    else:
        target_display = ""

    title_html = f'<span class="chip">{action}</span>'
    if target_display:
        title_html += f"<code>{target_display}</code>"

    error = event.get("error")
    error_block = f'<pre class="error">{escape(str(error))}</pre>' if error else ""

    # Detail rows
    rows: list[tuple[str, str]] = [
        ("duration", f"{int(event.get('duration_ms') or 0)} ms"),
    ]
    backtrack_steps = int(event.get("backtrack_steps") or 0)
    backtrack_badge = ""
    if backtrack_steps > 0:
        verb = "recovered after replaying" if success else "backtracked (tried)"
        rows.append(("backtrack", f"{verb} {backtrack_steps} previous step(s)"))
        backtrack_badge = (
            f'<span class="badge-backtrack" title="re-ran {backtrack_steps} previous '
            f'step(s) before retrying">↻ backtrack ×{backtrack_steps}</span>'
        )
    if role:
        rows.append(("role", str(role)))
    if name:
        rows.append(("name", str(name)))
    if url_val:
        rows.append(("url", str(url_val)))
    page_title = event.get("title") or ""
    if page_title:
        rows.append(("title", str(page_title)))
    bbox = event.get("bbox")
    if bbox:
        rows.append(("bbox", str(bbox)))
    if event.get("timestamp"):
        rows.append(("time", _short_time(str(event.get("timestamp")))))

    kv = "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in rows)

    # Logs block
    log_block = _render_logs(event.get("logs") or [])

    # ARIA snapshot block
    aria_block = _render_aria_snapshot(event.get("aria_snapshot"))

    # Screenshots: render both step and failure if present
    step_shot = event.get("screenshot")
    fail_shot = event.get("failure_screenshot")
    shot_block = ""
    if step_shot:
        shot_block += _render_screenshot(step_shot, screenshots, kind="step")
    if fail_shot:
        shot_block += _render_screenshot(fail_shot, screenshots, kind="failure")

    return f"""<article class="task">
        <div class="index">#{number}</div>
        <div class="body">
          <h3>{title_html}</h3>
          <dl class="kv">{kv}</dl>
          {error_block}
          {log_block}
          {aria_block}
          {shot_block}
        </div>
        <div class="status">{badge}{backtrack_badge}</div>
      </article>"""


def _render_logs(lines: list[str]) -> str:
    """Render the per-action log lines as a collapsible ``<details>`` block.

    Lines come in shaped as ``"[LEVEL] logger.name: message"`` (set by
    the Recorder's log-tail handler). We wrap each in a ``<span>`` tagged
    with its level so CSS can colourise DEBUG / INFO / WARNING / ERROR.
    """
    if not lines:
        return ""
    rendered: list[str] = []
    for line in lines:
        level = "INFO"
        if line.startswith("[") and "]" in line:
            level = line[1 : line.index("]")] or "INFO"
        safe_class = "".join(c for c in level if c.isalnum()).upper() or "INFO"
        rendered.append(f'<span class="lvl-{safe_class}">{escape(line)}</span>')
    body = "\n".join(rendered)
    return (
        f'<details class="logs">'
        f"<summary>Logs &middot; {len(lines)} line(s)</summary>"
        f'<pre class="log-output">{body}</pre>'
        "</details>"
    )


def _render_aria_snapshot(snapshot: list[dict[str, Any]] | None) -> str:
    """Render the ARIA snapshot as a collapsible ``<details>`` block.

    The snapshot is a list of ``{role, name}`` dicts captured on failure.
    Rendered as pretty-printed JSON in the same ``details.logs`` style.
    """
    if not snapshot:
        return ""
    pretty = escape(json.dumps(snapshot, indent=2, ensure_ascii=False))
    return (
        f'<details class="logs">'
        f"<summary>ARIA snapshot &middot; {len(snapshot)} element(s)</summary>"
        f'<pre class="log-output">{pretty}</pre>'
        "</details>"
    )


def _short_time(iso_ts: str) -> str:
    """Return just HH:MM:SS from an ISO timestamp (fallback: the raw string)."""
    if "T" in iso_ts and len(iso_ts) >= 19:
        return iso_ts[11:19]
    return iso_ts


def _render_screenshot(shot_path: str, screenshots: dict[str, bytes], kind: str = "failure") -> str:
    basename = os.path.basename(shot_path)
    data = screenshots.get(basename)
    if data is None:
        return ""
    encoded = base64.b64encode(data).decode("ascii")
    label = "Step result" if kind == "step" else "Failure screenshot"
    cls = "screenshot-card step" if kind == "step" else "screenshot-card"
    return (
        f'<div class="{cls}">'
        f'<div class="header">{label} &middot; {escape(basename)}</div>'
        f'<img src="data:image/png;base64,{encoded}" alt="{kind} screenshot" />'
        "</div>"
    )
