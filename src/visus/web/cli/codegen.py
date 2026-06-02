"""Records browser interactions and emits visus.web Python code."""

from __future__ import annotations

from typing import cast

from visus.web.api.page import Page

_RECORDER_JS = r"""
(function () {
  if (window.__visusRec) return;
  window.__visusRec = [];
  function sel(el) {
    var role = window.__visus.role(el);
    var name = window.__visus.accessibleName(el);
    if (role && name) return {kind:'role', role:role, name:name};
    if (el.id) return {kind:'css', value:'#' + el.id};
    if (el.getAttribute && el.getAttribute('data-testid'))
      return {kind:'testid', value: el.getAttribute('data-testid')};
    var tag = el.tagName.toLowerCase();
    if (el.name) return {kind:'css', value: tag + '[name="' + el.name + '"]'};
    return {kind:'css', value: tag};
  }
  document.addEventListener('click', function (e) {
    window.__visusRec.push({action:'click', target: sel(e.target)});
  }, true);
  document.addEventListener('change', function (e) {
    var t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA'))
      window.__visusRec.push({action:'fill', target: sel(t), value: t.value});
    else if (t && t.tagName === 'SELECT')
      window.__visusRec.push({action:'select_option', target: sel(t), value: t.value});
  }, true);
})();
"""


def inject_recorder(page: Page) -> None:
    """Inject the visus bundle (if needed) and then the recorder JS."""
    # Force _ensure_bundle by resolving an element — this guarantees window.__visus exists
    page.locator("html").count()
    # Now inject the recorder (which calls window.__visus.role / accessibleName)
    page.evaluate("() => { " + _RECORDER_JS + " }")


def drain(page: Page) -> list[dict]:  # type: ignore[type-arg]
    """Drain and return all recorded events, resetting the buffer."""
    script = "() => { var r = window.__visusRec || []; window.__visusRec = []; return r; }"
    result = page.evaluate(script)
    if result is None:
        return []
    return cast(list, result)  # type: ignore[type-arg]


def _target_expr(t: dict) -> str:  # type: ignore[type-arg]
    if t["kind"] == "role":
        return f"get_by_role({t['role']!r}, name={t['name']!r})"
    if t["kind"] == "testid":
        return f"get_by_test_id({t['value']!r})"
    return f"locator({t['value']!r})"


def generate_line(event: dict) -> str:  # type: ignore[type-arg]
    """Generate a single visus.web Python statement for one recorded event."""
    expr = "page." + _target_expr(event["target"])
    if event["action"] == "click":
        return f"{expr}.click()"
    if event["action"] == "fill":
        return f"{expr}.fill({event.get('value', '')!r})"
    if event["action"] == "select_option":
        return f"{expr}.select_option(value={event.get('value', '')!r})"
    return f"# unsupported: {event['action']}"


def generate_script(url: str, events: list[dict]) -> str:  # type: ignore[type-arg]
    """Generate a complete visus.web Python script from a list of recorded events."""
    lines = [
        "from visus.web import launch",
        "",
        "with launch(headless=False) as browser:",
        "    page = browser.new_page()",
        f"    page.goto({url!r})",
    ]
    for ev in events:
        lines.append("    " + generate_line(ev))
    return "\n".join(lines) + "\n"
