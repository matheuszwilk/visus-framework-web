"""visus-web MCP server — comprehensive FastMCP wrapper over the full visus.web API.

Playwright-MCP parity + frames + OCR/vision extras.
Run via: uv run visus-web-mcp   (or python -m visus.web.mcp.server)
"""

from __future__ import annotations

import time

from mcp.server.fastmcp import FastMCP, Image

from visus.web import errors
from visus.web.api.assertions import expect
from visus.web.api.locator import Locator
from visus.web.mcp.session import Session, make_locator

mcp = FastMCP("visus-web")
_session = Session()


def _any_match_visible(loc: Locator) -> bool:
    """True if at least one element the locator matches is visible.

    Tolerant of mid-navigation errors (treated as "not yet visible") and of
    locators that match several elements — so an agent can wait by a loose
    target (e.g. text=) even when a hidden duplicate sorts first in the DOM.
    """
    try:
        return any(loc.nth(i).is_visible() for i in range(loc.count()))
    except errors.VisusWebError:
        return False


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


@mcp.tool()
def browser_navigate(url: str) -> str:
    """Navigate the browser to a URL and return the resulting title."""
    page = _session.page()
    page.goto(url)
    return f"navigated to {page.url!r} (title: {page.title()!r})"


@mcp.tool()
def browser_navigate_back() -> str:
    """Navigate back in browser history."""
    page = _session.page()
    page.go_back()
    return f"went back → {page.url!r}"


@mcp.tool()
def browser_navigate_forward() -> str:
    """Navigate forward in browser history."""
    page = _session.page()
    page.go_forward()
    return f"went forward → {page.url!r}"


@mcp.tool()
def browser_reload() -> str:
    """Reload the current page."""
    page = _session.page()
    page.reload()
    return f"reloaded {page.url!r}"


# ---------------------------------------------------------------------------
# Inspect
# ---------------------------------------------------------------------------


@mcp.tool()
def browser_snapshot() -> list[dict]:  # type: ignore[type-arg]
    """Return the page's interactive elements as a list of {role, name} dicts.

    Use these values to target action tools without needing CSS selectors.
    """
    return _session.page().snapshot()


@mcp.tool()
def browser_list_fields(
    kind: str | None = None,
    include_hidden: bool = False,
    highlight: bool = False,
) -> list[dict]:  # type: ignore[type-arg]
    """List all RPA-relevant interactive fields on the current page.

    Enumerates buttons, inputs, textareas, links, selects, checkboxes/radios,
    custom dropdowns, and contenteditable elements — framework-agnostically,
    across open shadow DOM and same-origin iframes. Each returned dict carries a
    ready-to-use locator plus the frame chain and a deep flag so the field can be
    re-resolved for an action (root = page; for sel in frame: root =
    root.frame_locator(sel); target = root.locator(locator, deep=deep)).

    kind is an optional comma-separated filter (e.g. "button,input") restricting
    the result to those kinds; omit it to list every kind. include_hidden also
    returns hidden/disabled fields (flagged). highlight draws the numbered
    overlay on the page (default off; a no-op when headless).
    """
    parsed = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    fields = _session.page().list_fields(
        kinds=parsed, include_hidden=include_hidden, highlight=highlight
    )
    return [f.to_dict() for f in fields]


@mcp.tool()
def browser_clear_highlights() -> str:
    """Remove the numbered field-highlight overlay drawn by browser_list_fields."""
    _session.page().clear_highlights()
    return "cleared"


@mcp.tool()
def browser_translate_element(html: str) -> dict[str, object]:
    """Translate a pasted DevTools element (Copy element) into selectors.

    Given an element's outerHTML, returns the recommended id / css / xpath / class
    selectors plus the full ordered candidate list the smart locator tries. Pure
    parsing — no live page needed. The same css/xpath also works directly via
    page.locator("<the pasted html>").
    """
    from visus.web.api._htmlsel import translate

    return translate(html)


@mcp.tool()
def browser_title() -> str:
    """Return the current page title."""
    return _session.page().title()


@mcp.tool()
def browser_url() -> str:
    """Return the current page URL."""
    return _session.page().url


@mcp.tool()
def browser_get_text(
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str | None:
    """Return the visible text content of an element."""
    page = _session.page()
    loc = make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    )
    return loc.first().text_content()  # tolerate multi-match (agent-friendly read)


@mcp.tool()
def browser_get_attribute(
    attr_name: str,
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str | None:
    """Return the value of an HTML attribute on an element."""
    page = _session.page()
    loc = make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    )
    return loc.first().get_attribute(attr_name)  # tolerate multi-match


@mcp.tool()
def browser_count(
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> int:
    """Return the count of elements matching the given target."""
    page = _session.page()
    loc = make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    )
    return loc.count()


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


@mcp.tool()
def browser_click(
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Click an element targeted by role+name, text, or css/xpath selector."""
    page = _session.page()
    make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    ).click()
    return "clicked"


@mcp.tool()
def browser_dblclick(
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Double-click an element."""
    page = _session.page()
    make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    ).dblclick()
    return "double-clicked"


@mcp.tool()
def browser_fill(
    text_value: str,
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Fill an input/textarea with the given text_value."""
    page = _session.page()
    make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    ).fill(text_value)
    return f"filled with {text_value!r}"


@mcp.tool()
def browser_press(
    key: str,
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Press a key (e.g. 'Enter', 'Tab', 'Control+a') on the focused element."""
    page = _session.page()
    make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    ).press(key)
    return f"pressed {key!r}"


@mcp.tool()
def browser_hover(
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Hover over an element."""
    page = _session.page()
    make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    ).hover()
    return "hovered"


@mcp.tool()
def browser_check(
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Check a checkbox or radio button."""
    page = _session.page()
    make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    ).check()
    return "checked"


@mcp.tool()
def browser_uncheck(
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Uncheck a checkbox."""
    page = _session.page()
    make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    ).uncheck()
    return "unchecked"


@mcp.tool()
def browser_select_option(
    value: str,
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Select an option from a <select> element by value."""
    page = _session.page()
    make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    ).select_option(value=value)
    return f"selected option {value!r}"


@mcp.tool()
def browser_drag(
    target_selector: str,
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Drag the source element to target_selector (a CSS/XPath selector)."""
    page = _session.page()
    src_loc = make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    )
    tgt_loc = page.locator(target_selector)
    src_loc.drag_to(tgt_loc)
    return f"dragged to {target_selector!r}"


@mcp.tool()
def browser_focus(
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Focus an element."""
    page = _session.page()
    make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    ).focus()
    return "focused"


@mcp.tool()
def browser_clear(
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Clear the value of an input field."""
    page = _session.page()
    make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    ).clear()
    return "cleared"


@mcp.tool()
def browser_set_input_files(
    paths: list[str],
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """Set file(s) on a file input element. Provide absolute paths."""
    page = _session.page()
    make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    ).set_input_files(paths)
    return f"set {len(paths)} file(s)"


# ---------------------------------------------------------------------------
# Wait / Expect
# ---------------------------------------------------------------------------


@mcp.tool()
def browser_wait_for(
    state: str = "visible",
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
    timeout: int | None = None,
) -> str:
    """Wait for an element to reach a state: 'visible' or 'hidden'."""
    page = _session.page()
    loc = make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    )
    ms = 5000 if timeout is None else timeout
    want_visible = state != "hidden"
    deadline = time.monotonic() + ms / 1000.0
    while True:
        if _any_match_visible(loc) == want_visible:
            return f"element is {state}"
        if time.monotonic() >= deadline:
            raise AssertionError(f"wait_for: no element became {state} within {ms}ms")
        time.sleep(0.1)


@mcp.tool()
def browser_expect_text(
    expected_text: str,
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
    timeout: int | None = None,
) -> str:
    """Assert that an element contains the expected text. Returns 'PASSED' or 'FAILED: ...'."""
    page = _session.page()
    loc = make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    )
    try:
        expect(loc.first()).to_have_text(expected_text, timeout=timeout)
        return "PASSED"
    except AssertionError as exc:
        return f"FAILED: {exc}"


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------


@mcp.tool()
def browser_tab_list() -> list[dict]:  # type: ignore[type-arg]
    """List all open tabs as [{index, handle, title, url}].

    Reflects every open tab — including ones opened by a link or window.open —
    by reconciling against the live window handles. ``handle`` is a stable id you
    can pass to browser_tab_activate.
    """
    pages = _session.pages()
    result = []
    for i, p in enumerate(pages):
        try:
            title = p.title()
            url = p.url
        except Exception:
            title = ""
            url = ""
        result.append({"index": i, "handle": p.handle, "title": title, "url": url})
    return result


@mcp.tool()
def browser_tab_new(url: str | None = None) -> str:
    """Open a new browser tab, optionally navigating to url. Returns new tab index."""
    p = _session.new_page(url)
    idx = len(_session.pages()) - 1
    return f"opened tab {idx}" + (f" at {p.url!r}" if url else "")


@mcp.tool()
def browser_tab_select(index: int) -> str:
    """Switch to a tab by its 0-based index."""
    p = _session.select(index)
    return f"switched to tab {index} ({p.url!r})"


@mcp.tool()
def browser_tab_activate(handle: str) -> str:
    """Focus a tab by its stable handle (from browser_tab_list). Survives reordering."""
    p = _session.activate(handle)
    return f"activated tab {handle} ({p.url!r})"


@mcp.tool()
def browser_tab_close(index: int | None = None) -> str:
    """Close a tab by index (default: current tab)."""
    idx = index if index is not None else None
    _session.close_tab(idx)
    return f"closed tab {idx if idx is not None else 'current'}"


@mcp.tool()
def browser_set_tab_follow(enabled: bool) -> str:
    """Choose how new tabs/popups are handled — the agent picks the mode.

    enabled=False (DEFAULT, recommended): MANUAL. A click that opens a new
    tab/popup does NOT change your context; you stay where you are and steer
    explicitly with browser_tab_list / browser_tab_select. Predictable — no
    silent context switches.

    enabled=True: AUTO-FOLLOW. Subsequent operations target the most recently
    opened tab/popup window automatically (handy for "open in new tab" flows).
    """
    on = _session.set_follow(enabled)
    return f"tab-follow {'enabled (auto)' if on else 'disabled (manual)'}"


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------


@mcp.tool()
def browser_handle_dialog(accept: bool = True, prompt_text: str | None = None) -> str:
    """Handle the next browser dialog (alert/confirm/prompt).

    Accepts or dismisses it and returns the dialog message.
    NOTE: The action that triggers the dialog must be called BEFORE this tool,
    as this tool handles the PENDING dialog immediately.
    """
    page = _session.page()
    msg, typ = page._delegate.handle_next_dialog(
        accept=accept,
        prompt_text=prompt_text,
        timeout_ms=5000,
    )
    action = "accepted" if accept else "dismissed"
    return f"{action} {typ!r} dialog: {msg!r}"


# ---------------------------------------------------------------------------
# Network / console capture (Chromium)
# ---------------------------------------------------------------------------


@mcp.tool()
def browser_network_requests(url_filter: str = "") -> list[dict]:  # type: ignore[type-arg]
    """List network responses captured so far (document, XHR/fetch, assets).

    Each entry has url, method, status, resource_type. Pass *url_filter* to keep
    only URLs containing that substring (e.g. "/api/"). Chromium engines only.
    Use it to verify that the API call behind a UI action really happened.
    """
    page = _session.page()
    out = [
        {"url": r.url, "method": r.method, "status": r.status, "resource_type": r.resource_type}
        for r in page.network_requests()
    ]
    if url_filter:
        out = [r for r in out if url_filter in str(r["url"])]
    return out


@mcp.tool()
def browser_console_messages(level: str = "") -> list[dict]:  # type: ignore[type-arg]
    """List browser console messages captured so far (console.*, uncaught errors).

    Each entry has level (SEVERE/WARNING/INFO) and text. Pass *level* to filter
    (e.g. "SEVERE" for errors only). Chromium engines only. Check this first
    when a page misbehaves with no visible cause.
    """
    page = _session.page()
    out = [{"level": m.level, "text": m.text} for m in page.console_messages()]
    if level:
        out = [m for m in out if m["level"] == level.upper()]
    return out


# ---------------------------------------------------------------------------
# Cookies
# ---------------------------------------------------------------------------


@mcp.tool()
def browser_get_cookies() -> list[dict]:  # type: ignore[type-arg]
    """Return all cookies for the current context."""
    return _session.context().cookies()


@mcp.tool()
def browser_add_cookies(cookies: list[dict]) -> str:  # type: ignore[type-arg]
    """Add cookies to the current context. Each cookie must have at least 'name', 'value', 'url'."""
    _session.context().add_cookies(cookies)
    return f"added {len(cookies)} cookie(s)"


@mcp.tool()
def browser_clear_cookies() -> str:
    """Clear all cookies in the current context."""
    _session.context().clear_cookies()
    return "cookies cleared"


# ---------------------------------------------------------------------------
# Media / JavaScript
# ---------------------------------------------------------------------------


@mcp.tool()
def browser_screenshot(
    full_page: bool = False,
    selector: str | None = None,
) -> Image:
    """Take a screenshot of the page or a specific element. Returns a PNG image."""
    page = _session.page()
    if selector is not None:
        data = page.locator(selector).screenshot()
    else:
        data = page.screenshot(full_page=full_page)
    return Image(data=data, format="png")


@mcp.tool()
def browser_evaluate(expression: str, arg: object = None) -> object:
    """Evaluate a JavaScript expression in the browser and return the result.

    The expression must be a function, e.g. '() => document.title' or '(x) => x * 2'.
    """
    return _session.page().evaluate(expression, arg)


# ---------------------------------------------------------------------------
# Vision (OCR / image matching)
# ---------------------------------------------------------------------------


@mcp.tool()
def browser_read_text(
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """OCR the screenshot of an element and return the recognized text.

    Requires the [vision] extra (rapidocr-onnxruntime + opencv).
    """
    page = _session.page()
    loc = make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    )
    return loc.ocr_text()


@mcp.tool()
def browser_solve_captcha(
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> str:
    """OCR-solve a text CAPTCHA shown in the targeted element and return the solution."""
    page = _session.page()
    loc = make_locator(
        page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
    )
    return page.solve_captcha(loc)


@mcp.tool()
def browser_find_image(
    template_path: str,
    confidence: float = 0.8,
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> dict:  # type: ignore[type-arg]
    """Find a template image inside the screenshot of the targeted element (or full page).

    Returns a dict with {found, x, y, confidence} or {found: False}.
    Requires the [vision] extra.
    """
    import numpy as np
    from PIL import Image as PILImage

    from visus.web.vision import find_image

    page = _session.page()
    if selector is not None or role is not None or text is not None:
        loc = make_locator(
            page, selector=selector, role=role, name=name, text=text, exact=exact, frame=frame
        )
        screenshot_bytes = loc.screenshot()
    else:
        screenshot_bytes = page.screenshot()

    import io

    source_img = np.array(PILImage.open(io.BytesIO(screenshot_bytes)).convert("RGB"))
    template_img = np.array(PILImage.open(template_path).convert("RGB"))

    match = find_image(source_img, template_img, confidence=confidence)
    if match is None:
        return {"found": False}
    return {"found": True, "x": match.x, "y": match.y, "confidence": match.confidence}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@mcp.tool()
def browser_close() -> str:
    """Close the browser and reset the session."""
    _session.close()
    return "browser closed"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the visus-web MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
