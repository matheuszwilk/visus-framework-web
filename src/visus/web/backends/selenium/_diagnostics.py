"""Human- and AI-friendly diagnostics for failed actions.

Turns a JSON selector + the actionability failure reason into a readable,
structured message that tells a developer (or an AI agent) exactly what was
looked for, where, why it failed, and what to try next — including a fuzzy
"did you mean" when an accessible-name target is misspelt.

``describe_target`` is pure (no driver) so it is unit-testable without a browser;
``build_action_error`` additionally queries the live page best-effort for context
and suggestions, and never raises (diagnostics must not mask the real failure).
"""

from __future__ import annotations

import difflib
import json
from typing import Any

from selenium.webdriver.remote.webdriver import WebDriver


def _q(value: Any) -> str:
    return f'"{value}"'


def _describe_step(step: dict[str, Any]) -> str:
    kind = step.get("kind")
    if kind == "role":
        name = step.get("name")
        base = f"role {_q(step.get('role'))}"
        return base + (f" named {_q(name)}" if name else "")
    if kind in ("text", "label", "placeholder", "alt", "title", "testid"):
        label = {"alt": "alt text", "testid": "test-id"}.get(str(kind), str(kind))
        return f"{label} {_q(step.get('value'))}"
    if kind in ("css", "xpath"):
        return f"{kind} {_q(step.get('value'))}"
    if kind == "filter_has_text":
        return f"filtered by text {_q(step.get('value'))}"
    if kind == "nth":
        idx = step.get("index")
        which = {0: "first", -1: "last"}.get(idx, f"index {idx}")  # type: ignore[arg-type]
        return f"({which})"
    if kind == "smart":
        cands = step.get("candidates") or []
        tag = step.get("tag") or "element"
        first = ""
        if cands and isinstance(cands[0], dict):
            first = str(cands[0].get("css") or cands[0].get("xpath") or "")
        suffix = f" (best: {first})" if first else ""
        return f"<{tag}> pasted element, {len(cands)} candidate selector(s){suffix}"
    if kind == "frame":
        return "inside frame"
    return str(kind)


def describe_target(selector: str) -> str:
    """Render a JSON selector as a readable target, e.g. ``role "button" named "Submit"``."""
    try:
        steps = json.loads(selector)
    except (ValueError, TypeError):
        return selector
    if not isinstance(steps, list):
        return selector
    parts = [_describe_step(s) for s in steps if isinstance(s, dict)]
    parts = [p for p in parts if p]
    return " » ".join(parts) if parts else selector


def _snapshot(driver: WebDriver) -> list[dict[str, Any]]:
    try:
        snap = driver.execute_script("return window.__visus.snapshot();")
    except Exception:
        return []
    return snap if isinstance(snap, list) else []


def _suggest(driver: WebDriver, steps: list[dict[str, Any]]) -> str | None:
    """Best-effort 'did you mean' / 'available targets' line built from the live page."""
    snap = _snapshot(driver)
    if not snap:
        return None

    role_step = next((s for s in reversed(steps) if s.get("kind") == "role"), None)
    name_step = next(
        (s for s in reversed(steps) if s.get("kind") in ("text", "label", "placeholder")),
        None,
    )

    if role_step is not None:
        role = role_step.get("role")
        want = str(role_step.get("name") or "")
        names = [str(e.get("name")) for e in snap if e.get("role") == role and e.get("name")]
        names = list(dict.fromkeys(names))  # de-dup, preserve order
        if want and names:
            close = difflib.get_close_matches(want, names, n=3, cutoff=0.4)
            if close:
                return "did you mean: " + ", ".join(_q(c) for c in close) + "?"
        if names:
            return f"{role}s on this page: " + ", ".join(_q(n) for n in names[:8])

    if name_step is not None:
        want = str(name_step.get("value") or "")
        names = [str(e.get("name")) for e in snap if e.get("name")]
        close = difflib.get_close_matches(want, list(dict.fromkeys(names)), n=3, cutoff=0.4)
        if close:
            return "did you mean: " + ", ".join(_q(c) for c in close) + "?"

    labels = [f"{e.get('role')} {_q(e.get('name'))}" for e in snap if e.get("name")][:8]
    if labels:
        return "interactive elements here: " + "; ".join(labels)
    return None


def build_action_error(
    driver: WebDriver, selector: str, name: str, timeout_ms: int, last_reason: str
) -> str:
    """Compose a friendly, structured failure message for a timed-out action.

    Best-effort: any page query failure degrades gracefully to the basic message.
    """
    target = describe_target(selector)
    not_found = "not found" in last_reason
    if not_found:
        headline = f"{name}: could not find {target} within {timeout_ms}ms"
    else:
        headline = f"{name}: {target} never became actionable within {timeout_ms}ms ({last_reason})"
    lines = [headline]

    try:
        lines.append(f"  page:   {driver.title!r} — {driver.current_url}")
    except Exception:
        pass

    lines.append(f"  status: {last_reason}")

    try:
        steps = json.loads(selector)
        if isinstance(steps, list):
            hint = _suggest(driver, steps)
            if hint:
                lines.append(f"  {hint}")
    except (ValueError, TypeError):
        pass

    if not_found:
        lines.append(
            "  try:    check the name/spelling (or pass exact=False for a substring); "
            "if it renders after an async step, raise timeout= or assert with expect(); "
            "if it is inside an <iframe>, target it via page.frame_locator(...)."
        )
    else:
        lines.append(
            "  try:    raise timeout=, or check for an overlay/animation covering it; "
            "pass force=True to bypass actionability checks if that is intentional."
        )
    return "\n".join(lines)
