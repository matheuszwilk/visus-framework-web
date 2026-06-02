# visus-web

**Modern, Playwright-style web automation on a pure Selenium engine** — semantic locators, auto-waiting actions, and auto-retrying `expect()` assertions, plus BotCity-style RPA reach (frames, popups, dialogs, cookies, screenshots, file upload) and an **OCR + image-matching** vision plugin for captchas. The best of both worlds: Playwright's developer experience with Selenium's compatibility (Grid, IE-mode, corporate browsers), written from scratch, fully typed, with **no Playwright dependency**.

## Install

```bash
pip install visus-web                 # core (Selenium engine)
pip install "visus-web[vision]"       # + OCR (RapidOCR) + image matching (OpenCV)
pip install "visus-web[mcp]"          # + MCP server for AI agents
pip install "visus-web[cli]"          # + the `visus` CLI (incl. codegen)
```

## Quickstart

```python
from visus.web import launch, expect

with launch(headless=True) as browser:
    page = browser.new_page()
    page.goto("https://example.com")
    page.get_by_role("button", name="Sign in").click()    # auto-waits until actionable
    page.get_by_label("Email").fill("ada@example.com")
    expect(page.get_by_text("Welcome")).to_be_visible()   # auto-retries until true
```

## What's inside

- **Semantic locators:** `get_by_role / text / label / placeholder / test_id / alt_text / title`, `locator(css|xpath)`, `first/last/nth/filter`, `frame_locator` (cross-origin & nested iframes).
- **Auto-waited actions:** `click / dblclick / fill / press / hover / check / uncheck / set_checked / select_option / drag_to / focus / blur / clear / set_input_files` — no `sleep`, ever.
- **Web-first assertions:** `expect(loc).to_be_visible / to_have_text / to_have_value / to_have_count / to_have_role / …` with `.not_` negation; all auto-retry.
- **RPA:** `evaluate`, `screenshot` (element/full-page), `pdf`, cookies, `expect_popup`, `expect_dialog`, frames.
- **Vision (`[vision]`):** `read_text` / `solve_captcha` (RapidOCR, any image format) and `find_image` / `find_all_images` (OpenCV); plus `locator.ocr_text()`, `locator.find_image()`, `page.solve_captcha()`.
- **CLI (`[cli]`):** `visus doctor | install | screenshot | pdf | open | run | mcp | codegen` (the `codegen` recorder generates visus.web code from your interactions).
- **MCP server (`[mcp]`):** `visus-web-mcp` exposes ~38 tools (navigation, accessibility snapshot, all actions, tabs, dialogs, cookies, screenshot, evaluate, and the vision tools) to AI agents.

## Design

Engine-hidden architecture: the public `api/` layer holds engine-agnostic delegate Protocols; all Selenium code is confined to the backend, and no `selenium.*` type ever crosses the public boundary. The crown-jewel ergonomics (ARIA-role/accessible-name locators, RAF stability, actionability auto-wait, auto-retry assertions) are implemented clean-room in our own injected JS engine + a Python deadline/backoff layer — not vendored from Playwright.

## Develop

```bash
uv venv && uv pip install -e ".[dev,vision,mcp,cli]"
uv run pytest -q          # parallel (xdist), real headless-Chrome integration tests
uv run ruff check src tests && uv run mypy
```
See the `skills/` directory (`using-visus-web`, `developing-visus-web`) for agent/contributor guides, and `docs/superpowers/` for the design specs and slice-by-slice plans.

## License

MIT.
