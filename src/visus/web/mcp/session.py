"""Session singleton + locator helper for the visus-web MCP server."""

from __future__ import annotations

import os
from typing import Any, cast

from visus.web import Engine, launch
from visus.web.api.browser import Browser
from visus.web.api.context import Context
from visus.web.api.locator import Locator
from visus.web.api.page import Page
from visus.web.backends.selenium.driver_delegate import SeleniumPageDelegate


class Session:
    """Manages a single browser + multi-tab page list for the MCP server."""

    def __init__(self) -> None:
        self._browser: Browser | None = None
        self._context: Context | None = None
        self._pages: list[Page] = []
        self._current_idx: int = 0
        # Tab-follow mode (opt-in). Manual by default: a click that opens a new
        # tab/popup does NOT silently change the active context — the agent steers
        # with tab_list/tab_select (predictable). When enabled, page() auto-follows
        # the most recently opened window/tab (like the CLI daemon).
        self._follow: bool = False
        self._known_handles: list[str] = []
        self._active_handle: str | None = None

    def _ensure(self) -> None:
        if self._browser is None:
            engine_str = os.environ.get("VISUS_WEB_ENGINE", "chrome")
            headless = os.environ.get("VISUS_WEB_HEADLESS", "1") != "0"
            self._browser = launch(Engine.from_str(engine_str), headless=headless)
            self._context = self._browser.new_context()
            first = self._context.new_page()
            self._pages = [first]
            self._current_idx = 0

    def page(self) -> Page:
        self._ensure()
        base = self._pages[self._current_idx]
        if not self._follow:
            return base  # manual (default): explicit tab control via tab_select
        driver = getattr(getattr(base, "_delegate", None), "_driver", None)
        if driver is None:
            return base
        try:
            handles = list(driver.window_handles)
        except Exception:  # noqa: BLE001
            return base
        if not handles:
            return base
        new = [h for h in handles if h not in self._known_handles]
        self._known_handles = list(handles)
        active = new[-1] if new else self._active_handle  # follow the newest new tab/popup
        if active is None or active not in handles:
            active = handles[-1]
        self._active_handle = active
        if getattr(base._delegate, "_handle", None) == active:
            return base
        return Page(SeleniumPageDelegate(driver, active), base._defaults)

    def set_follow(self, enabled: bool) -> bool:
        """Toggle auto-follow of newly-opened tabs/popups (default off = manual)."""
        self._follow = bool(enabled)
        if not self._follow:
            self._active_handle = None
        return self._follow

    def context(self) -> Context:
        self._ensure()
        assert self._context is not None
        return self._context

    def new_page(self, url: str | None = None) -> Page:
        self._ensure()
        assert self._context is not None
        p = self._context.new_page()
        self._pages.append(p)
        self._current_idx = len(self._pages) - 1
        if url is not None:
            p.goto(url)
        return p

    def pages(self) -> list[Page]:
        self._ensure()
        assert self._context is not None
        # Surface tabs opened outside our tracking (a link / window.open) by
        # reconciling against the live window handles — additive, dedup by handle.
        seen = {p.handle for p in self._pages}
        for p in self._context.adopt_open_windows():
            if p.handle not in seen:
                self._pages.append(p)
                seen.add(p.handle)
        return list(self._pages)

    def select(self, index: int) -> Page:
        self._ensure()
        if index < 0 or index >= len(self._pages):
            raise IndexError(f"tab index {index} out of range (have {len(self._pages)} tabs)")
        self._current_idx = index
        return self._pages[index]

    def activate(self, handle: str) -> Page:
        """Focus a tab by its stable window handle (reconciles external tabs first)."""
        self.pages()  # reconcile so externally-opened tabs are selectable
        for i, p in enumerate(self._pages):
            if p.handle == handle:
                p.bring_to_front()
                self._current_idx = i
                return p
        raise ValueError(f"no open tab with handle {handle!r}")

    def close_tab(self, index: int | None = None) -> None:
        self._ensure()
        idx = self._current_idx if index is None else index
        if idx < 0 or idx >= len(self._pages):
            raise IndexError(f"tab index {idx} out of range")
        self._pages[idx].close()
        self._pages.pop(idx)
        if not self._pages:
            # all tabs closed — reset
            self.close()
        else:
            self._current_idx = min(idx, len(self._pages) - 1)

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
        self._browser = None
        self._context = None
        self._pages = []
        self._current_idx = 0
        self._follow = False
        self._known_handles = []
        self._active_handle = None


def make_locator(
    page: Page,
    *,
    selector: str | None = None,
    role: str | None = None,
    name: str | None = None,
    text: str | None = None,
    exact: bool = False,
    frame: str | None = None,
) -> Locator:
    """Resolve a locator from the given target params."""
    root: Any = page if frame is None else page.frame_locator(frame)
    if role is not None:
        return cast(Locator, root.get_by_role(role, name=name, exact=exact))
    if text is not None:
        return cast(Locator, root.get_by_text(text, exact=exact))
    if selector is not None:
        return cast(Locator, root.locator(selector))
    raise ValueError("provide one of: role, text, selector")
