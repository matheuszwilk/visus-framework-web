---
name: developing-visus-web
description: Use when extending or contributing to the visus.web library itself — adding a get_by_* locator, an action, an assertion matcher, a browser plug-in, an MCP tool, or a CLI command. Covers the engine-hidden architecture (api wrappers over delegate Protocols, Selenium confined to the backend), the clean-room injected JS bundle, the actionability / expect / frame-aware resolver internals, and the real-browser test conventions (no fakes, xdist, mypy --strict, coverage gate).
---

# Developing visus.web

## Architecture in one picture

```
visus.web (public)        api/ wrappers hold a *Delegate Protocol — NEVER a selenium object
  launch()  ─► Browser ─► Context ─► Page ─► Locator / FrameLocator
                              │                 expect(locator) ─► LocatorAssertions
                              ▼
                         backends/base.py     Protocols: Backend, BrowserDelegate,
                                              ContextDelegate, PageDelegate + BrowserConfig
                              ▼
                         backends/selenium_backend.py     driver lifecycle (launch/dispose)
                         backends/selenium/
                            driver_delegate.py   SeleniumPage/ContextDelegate (the only place
                                                 selenium WebElements live)
                            resolver.py          frame-aware element resolution (shared)
                            actionability.py     deadline+backoff auto-wait loop (actions)
                            expect_engine.py     auto-retry assertion poll loop
                            js/bundle.js         OUR clean-room injected engine (window.__visus)
                         backends/browsers/      per-browser option/service/driver factories
```

**THE HIDDEN-ENGINE RULE (inviolable):** no `selenium.*` type may appear in any public signature, return, exception, or docstring. "Public" = `src/visus/web/__init__.py` and everything under `src/visus/web/api/`. Selenium imports are allowed ONLY in `backends/browsers/*.py`, `backends/selenium/*.py`, and `backends/selenium_backend.py`. Selenium exceptions are translated to `visus.web.errors` via `driver_delegate.translate_exc`. Verify with: no `selenium` import resolves inside `api/` or `__init__.py`.

## How resolution works

A `Locator` is `{delegate, steps, defaults}` where `steps` is an immutable tuple of JSON-able dicts (`{"kind":"role"|"text"|"css"|"xpath"|"label"|"placeholder"|"testid"|"alt"|"title"|"filter_has_text"|"nth"|"frame", ...}`). Builders append a step and return a NEW Locator. To act/read, the Locator JSON-encodes its steps and calls a delegate method; `resolver.resolve_elements(driver, ensure_bundle, selector_json)` runs `window.__visus.queryAll(steps)` in JS — re-injecting the bundle and `switch_to.frame`-ing for any `frame` steps (idempotent: it restarts from `default_content`; `_activate()` resets the frame context each op). Strict single-element ops use `resolver.resolve_strict`.

The clean-room `bundle.js` (`window.__visus`) is OUR code (NOT Playwright). It computes ARIA `role`, `accessibleName` (a subset of the W3C ACCNAME algorithm), normalized-text matching, `elementState` (visible/hidden/enabled/disabled/editable/checked), `checkStable` (RAF), `hitTarget`, `clickablePoint`, and `snapshot`. Extend it for new selector kinds / states.

## Recipes

### Add a `get_by_*` locator
1. `bundle.js`: add a matcher + a `queryAll` branch for the new `{"kind": ...}` step (see the `label`/`placeholder` branches).
2. `api/locator.py`: add a builder returning `self._child({"kind": ..., ...})`. Add a `Page` entry point mirroring `get_by_role`. Add to `FrameLocator` too.
3. Add a real-browser test against a fixture in `tests/`.

### Add an action (auto-waited)
1. `actionability.py`: add the action name to `_ACTION_STATES` (its required states) and, if it's pointer-like, to `_POINTER_ACTIONS`.
2. `backends/base.py`: add `locator_<action>` to `PageDelegate`. `driver_delegate.py`: implement it — call `run_action(self._driver, selector, "<name>", timeout_ms=..., force=..., dispatch=<callback>, ensure_bundle=self._ensure_bundle)`; the dispatch performs the real Selenium op (`ActionChains`, `Select`, `send_keys`, JS).
3. `api/locator.py`: add the public method (use `self._t(timeout)` for the default).
4. Update fake delegates in `tests/test_backend_protocols.py`. Add a real-browser behavior test (assert a real DOM effect; use a 250–700ms `setTimeout` in the fixture to prove the auto-wait path).

### Add an assertion matcher
1. `expect_engine.py` `_evaluate`: add a branch returning `(matches, received)`.
2. `api/assertions.py`: add `to_*` on `LocatorAssertions` calling `self._poll("<matcher>", arg, timeout)`. Negation via `.not_` is automatic (`matches != is_not`).
3. Add a real-browser test where the condition flips after a delay (proves auto-retry) + a failure case asserting `AssertionError`.

### Add a browser plug-in (Firefox/Edge/…)
1. `backends/browsers/<engine>.py`: `build_options/build_service/build_driver` (mirror `chrome.py`).
2. `registry.py`: map the `Engine` member to a `BrowserConfig`.
3. Real-browser smoke test under that engine if available in CI.

### Add an MCP tool
`src/visus/web/mcp/server.py`: a `@mcp.tool()` thin wrapper over the public API, targeting via the shared `locator(page, role=, name=, text=, selector=, frame=)` helper. Add it to the registration assertion in `tests/test_mcp_server.py` and drive it in `tests/test_e2e_mcp.py`.

### Add a CLI command
`src/visus/web/cli/main.py`: an `@app.command()` Typer function over the public API. Test with `typer.testing.CliRunner` (real browser for browser-touching commands).

## Test conventions (enforced)

- **Real browser, no fakes.** Coverage is driven by real-browser integration tests (`@pytest.mark.browser`) against local fixture pages in `tests/fixtures/`, served by the session-scoped `base_url` fixture (an ephemeral `http.server`). Pure-logic units (errors/enum/config/exception-translation/step-encoding/vision-on-generated-images) are the only non-browser tests. Test doubles isolate a unit ONLY when its real behavior is also covered by an integration test — never as the sole proof of a feature. No `skip`/`xfail`/mock-to-pass.
- **Parallel:** the suite runs under `pytest-xdist` (`-n auto`, `--dist loadfile`). Run a subset with `--no-cov` (the `--cov-fail-under=90` gate only makes sense on the full run).
- **Gates:** `uv run ruff check src tests`, `uv run mypy` (`--strict`, no weakening — cast `execute_script`/CDP `Any` returns; selenium types only inside backend files), `uv run pytest -q` (≥90% coverage on `visus.web`).
- **Commits:** small, TDD (failing test → minimal impl → green → commit).

## Layout & build
`src/`-layout namespace package (`visus.web`; no `src/visus/__init__.py`). Build: `uv` + `hatchling`. Optional extras: `[dev]`, `[vision]` (rapidocr/opencv/pillow/numpy), `[mcp]` (mcp), `[cli]` (typer). Entry points: `visus`, `visus-web-mcp`.
