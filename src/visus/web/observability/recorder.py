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


class Recorder:
    """Accumulates per-action events and PNG screenshots for one tracing session."""

    def __init__(self) -> None:
        self.run_id = uuid.uuid4().hex[:8]
        self._events: list[dict[str, Any]] = []
        self._shots: dict[str, bytes] = {}
        self._step = 0

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
        backtrack_cycles: int,
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
            shot_ref = self._save(
                delegate, selector, f"{self.run_id}__{step_id}__{action}.png"
            )
        fail_ref = None
        if not success and opts.screenshot_on_failure:
            fail_ref = self._save(
                delegate, selector, f"{self.run_id}__{step_id}__failure.png"
            )
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
            "backtrack_cycles": backtrack_cycles,
            "success": success,
            "error": error,
            "screenshot": shot_ref,
            "failure_screenshot": fail_ref,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "start_ts": start_ts,
            "end_ts": end_ts,
        }
        self._events.append(event)
        events_logger.info(json.dumps(event))

    def _save(self, delegate: Any, selector: str | None, name: str) -> str | None:
        try:
            self._shots[name] = delegate.capture_annotated_screenshot(selector)
            return name
        except Exception:
            return None

    def write_zip(self, path: str) -> None:
        """Write events.jsonl + manifest.json + screenshots/*.png to a zip file."""
        failures = sum(1 for e in self._events if not e["success"])
        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "run_ids": sorted({e["run_id"] for e in self._events}),
            "counts": {"actions": len(self._events), "failures": failures},
        }
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            z.writestr(
                "events.jsonl", "\n".join(json.dumps(e) for e in self._events)
            )
            for name, data in self._shots.items():
                z.writestr(f"screenshots/{name}", data)
