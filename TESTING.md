# Testing visus.web

The test suite is **real-browser-first**: nearly every public method is proven by an integration test that drives a real headless Chromium against local fixture pages (served by an ephemeral `http.server` in `tests/conftest.py`). Pure-logic units (errors, enum, config, exception-translation, selector-step encoding) and the vision module (OCR/image on generated images) are the only non-browser tests. The async-facade wiring also has fast mock tests, but its real behaviour is covered by `tests/test_e2e_async*.py`.

## Setup

```bash
uv venv && uv pip install -e ".[dev,vision,mcp,cli]"
```
`[vision]` (RapidOCR + OpenCV) is required for the OCR/image tests; `[mcp]` and `[cli]` for the MCP/CLI tests.

## Run the suite

```bash
uv run pytest -q
```
- Runs in **parallel** via `pytest-xdist` (`-n auto`, `--dist loadfile`).
- Enforces a **90% coverage gate** on `visus.web` (`--cov-fail-under=90`).
- Browser tests are marked `@pytest.mark.browser`.

Run a single file fast (skip the coverage gate, which only makes sense on the full run):
```bash
uv run pytest tests/test_e2e_locators.py -m browser --no-cov
```

## The Edge IE-mode test (special)

`tests/test_e2e_edge_ie.py` drives **Edge in IE/Trident mode** via a local `IEDriverServer.exe` (gitignored; set `VISUS_WEB_IE_DRIVER` to its path — the test points to the repo-root copy automatically). Two caveats:

1. **It is headed by necessity** — the IE/Trident engine has **no headless mode** (headless is a Chromium-only feature), so a visible Edge-IE window appears during the test.
2. **It hangs under parallel execution** — IE-mode needs window focus, and other headless browsers running in parallel steal it; the session then blocks in a way neither the launch watchdog nor pytest-timeout can interrupt. The test therefore **skips itself automatically under xdist** (it detects `PYTEST_XDIST_WORKER`). **Run it serially**:
   ```bash
   uv run pytest tests/test_e2e_edge_ie.py -n0 --no-cov -m browser
   ```
3. **Only IEDriverServer 4.0.0 works** — 4.8+ (including the 4.14 Selenium Manager picks by default) hangs forever at `BrowserFactory.cpp Finding window handle for IE Mode on Edge`. `edge_ie.py` pins 4.0.0 via Selenium Manager; a repo-root `IEDriverServer.exe` (gitignored) or `VISUS_WEB_IE_DRIVER` overrides it, `VISUS_WEB_IE_DRIVER_VERSION` re-pins.

## Browsers covered

Chrome and Edge (Chromium) run **headless**. Edge IE-mode runs **headed** (see above). Firefox is supported by the architecture but has no plug-in yet (it is not installed in this environment) — install Firefox and a `backends/browsers/firefox.py` plug-in mirroring `chrome.py` is a few minutes' work, with Firefox-native paths for the Chromium-only RPA bits (full-page screenshot, `pdf`, download-dir).

## Quality gates

```bash
uv run ruff check src tests   # lint (and `ruff format` to format)
uv run mypy                   # strict type-check
```
