"""Recorder: buffers events + annotated screenshots, writes a zip on session close."""

from __future__ import annotations

import json
import logging
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any

from visus.web import tracing

events_logger = logging.getLogger("visus.web.events")

# Third-party loggers too noisy to be useful in a run report.
# Records from these (and their children) are dropped from the captured log tail.
_NOISY_LOG_PREFIXES = (
    "selenium",
    "urllib3",
    "PIL",
    "onnxruntime",
    "websocket",
    "asyncio",
    "trio",
    "hpack",
    "h2",
    "charset_normalizer",
)


class _LogTailHandler(logging.Handler):
    """Capture log records (with timestamps) emitted during a recording.

    Attached to the ROOT logger so it captures the full trail of a run.
    We drop:

      * the dedicated ``visus.web.events`` logger (its JSON already lives in
        ``events.jsonl``), and
      * known-noisy third-party loggers -- selenium, urllib3, PIL, etc.
        (see ``_NOISY_LOG_PREFIXES``).
    """

    def __init__(self) -> None:
        super().__init__()
        self.records: list[tuple[float, str, str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        name = record.name
        if name == events_logger.name:
            return
        if any(name == p or name.startswith(p + ".") for p in _NOISY_LOG_PREFIXES):
            return
        try:
            self.records.append(
                (
                    record.created,
                    record.levelname,
                    name,
                    record.getMessage(),
                )
            )
        except Exception:  # pragma: no cover - defensive
            pass


class Recorder:
    """Accumulates per-action events and PNG screenshots for one tracing session."""

    def __init__(self) -> None:
        self.run_id = uuid.uuid4().hex[:8]
        self._events: list[dict[str, Any]] = []
        self._shots: dict[str, bytes] = {}
        self._step = 0
        # Log tail handler attached to root logger while recording
        self._log_handler = _LogTailHandler()
        self._prior_visus_level: int = logging.NOTSET
        # Attach to root logger to capture all records
        root_logger = logging.getLogger()
        root_logger.addHandler(self._log_handler)
        # Bump visus.web tree to DEBUG so narrative logs flow through
        visus_logger = logging.getLogger("visus.web")
        self._prior_visus_level = visus_logger.level
        if self._prior_visus_level == logging.NOTSET or self._prior_visus_level > logging.DEBUG:
            visus_logger.setLevel(logging.DEBUG)

    def _detach(self) -> None:
        """Remove the log handler and restore logger levels."""
        root_logger = logging.getLogger()
        root_logger.removeHandler(self._log_handler)
        visus_logger = logging.getLogger("visus.web")
        visus_logger.setLevel(self._prior_visus_level)

    def record_action(
        self,
        delegate: Any,
        *,
        action: str,
        selector: str | None,
        target: str | None,
        start_ts: float,
        end_ts: float,
        duration_ms: int,
        success: bool,
        error: str | None,
        backtrack_steps: int,
    ) -> None:
        self._step += 1
        step_id = self._step
        opts = tracing.options()
        meta: dict[str, Any] = {}
        try:
            meta = delegate.step_meta(selector)
        except Exception:
            meta = {}
        shot_ref = None
        if success and opts.screenshot_each_action:
            shot_ref = self._save(delegate, selector, f"{self.run_id}__{step_id}__{action}.png")
        fail_ref = None
        if not success and opts.screenshot_on_failure:
            fail_ref = self._save(delegate, selector, f"{self.run_id}__{step_id}__failure.png")

        # ARIA snapshot on failure: best-effort
        aria_snapshot: list[dict[str, Any]] | None = None
        if not success:
            try:
                aria_snapshot = delegate.snapshot()
            except Exception:
                aria_snapshot = None

        event: dict[str, Any] = {
            "run_id": self.run_id,
            "step_id": step_id,
            "action": action,
            "selector": selector,
            "target": target,
            "role": meta.get("role"),
            "name": meta.get("name"),
            "url": meta.get("url"),
            "title": meta.get("title"),
            "bbox": meta.get("bbox"),
            "duration_ms": duration_ms,
            "backtrack_steps": backtrack_steps,
            "success": success,
            "error": error,
            "screenshot": shot_ref,
            "failure_screenshot": fail_ref,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "start_ts": start_ts,
            "end_ts": end_ts,
        }
        if aria_snapshot is not None:
            event["aria_snapshot"] = aria_snapshot
        self._events.append(event)
        events_logger.info(json.dumps(event))

    def summary(self) -> dict[str, Any]:
        """Lightweight in-memory run summary (no zip parsing needed).

        Steps are ordered chronologically by start time, so a backtrack's replayed
        steps sit after the action that triggered them (matching the report).
        """
        ev = sorted(self._events, key=lambda e: e.get("start_ts") or 0.0)
        return {
            "total": len(ev),
            "failures": sum(1 for e in ev if not e.get("success")),
            "backtrack_steps": sum(int(e.get("backtrack_steps") or 0) for e in ev),
            "steps": [(str(e.get("action")), bool(e.get("success"))) for e in ev],
        }

    def _save(self, delegate: Any, selector: str | None, name: str) -> str | None:
        try:
            self._shots[name] = delegate.capture_annotated_screenshot(selector)
            return name
        except Exception:
            return None

    def write_zip(self, path: str) -> None:
        """Write events.jsonl + manifest.json + screenshots/*.png to a zip file."""
        # Attach correlated logs to each event before writing
        enriched = _attach_logs_to_events(self._events, self._log_handler.records)

        # Detach handler and restore log levels now that we're done recording
        self._detach()

        failures = sum(1 for e in enriched if not e.get("success"))
        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "run_ids": sorted({str(e.get("run_id", "")) for e in enriched}),
            "counts": {"actions": len(enriched), "failures": failures},
        }
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            z.writestr("events.jsonl", "\n".join(json.dumps(e) for e in enriched))
            for name, data in self._shots.items():
                z.writestr(f"screenshots/{name}", data)


def _attach_logs_to_events(
    events: list[dict[str, Any]],
    log_records: list[tuple[float, str, str, str]],
) -> list[dict[str, Any]]:
    """Inject a ``logs`` array into each event.

    Walks events in order and claims all log records whose timestamp
    falls inside ``(start_ts - 1e-3, end_ts + 1e-3]`` as belonging to
    the current action.
    """
    if not log_records:
        for event in events:
            event.setdefault("logs", [])
        return events
    sorted_logs = sorted(log_records, key=lambda r: r[0])
    for event in events:
        start_ts = float(event.get("start_ts") or 0.0)
        end_ts = float(event.get("end_ts") or 0.0)
        window_start = start_ts - 0.001
        window_end = end_ts + 0.001
        event["logs"] = [
            f"[{lvl}] {name}: {msg}"
            for ts, lvl, name, msg in sorted_logs
            if window_start < ts <= window_end
        ]
    return events
