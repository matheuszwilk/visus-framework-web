---
name: using-visus-web
description: Use when writing web automation or RPA with the visus.web library — a modern, Playwright-style API (Browser/Context/Page/Locator/expect with auto-wait and web-first assertions) running on a pure Selenium engine. Covers semantic locators, auto-waited actions, web-first expect() assertions, RPA (frames/popups/dialogs/cookies/screenshots/upload/evaluate), OCR + image vision (captcha), the `visus` CLI, and the `visus-web-mcp` MCP server for AI agents.
---

# Using visus.web

`visus.web` gives you Playwright's modern ergonomics — semantic locators, **auto-waiting** actions (no `sleep`), and **auto-retrying** `expect()` assertions — on a **pure Selenium engine** (broad browser/Grid/IE-mode compatibility), plus BotCity-style RPA reach (frames, popups, dialogs, cookies, screenshots, file upload) and an **OCR + image-matching** vision plugin for captchas.

## Install

```bash
pip install visus-web                 # core (Selenium engine)
pip install "visus-web[vision]"       # + OCR (RapidOCR) and image matching (OpenCV)
pip install "visus-web[mcp]"          # + MCP server for AI agents
pip install "visus-web[cli]"          # + the `visus` CLI
```

## Quickstart

```python
from visus.web import launch, expect

with launch(headless=True) as browser:      # engine defaults to chrome
    page = browser.new_page()
    page.goto("https://example.com")
    page.get_by_role("button", name="Sign in").click()   # auto-waits until actionable
    page.get_by_label("Email").fill("ada@example.com")
    expect(page.get_by_text("Welcome")).to_be_visible()  # auto-retries until true
```

## Core principles (why it's reliable)

- **Auto-wait:** every action (`click`, `fill`, …) waits for the element to be visible / stable / enabled / editable / receiving events before acting. **Never add `sleep`.**
- **Web-first assertions:** `expect(locator).to_*()` re-checks until it passes or the timeout elapses (default 5s).
- **Lazy locators:** a `Locator` is a recipe, re-resolved on each use — no stale-element errors.
- **Strict mode:** single-element ops raise `StrictModeViolation` if the locator matches >1 element. Disambiguate with `.first()` / `.last()` / `.nth(i)`.
- **Timeouts** are in **milliseconds**; most methods accept `timeout=...` (default action 30000, assertion 5000, navigation 30000).

## Locators (prefer semantic ones)

```python
page.get_by_role("button", name="Save")        # ARIA role + accessible name (best)
page.get_by_text("Welcome back")                # visible text (substring, case-insensitive)
page.get_by_label("Email")                      # form control by its <label>
page.get_by_placeholder("Search")
page.get_by_test_id("submit")                   # [data-testid="submit"]
page.get_by_alt_text("Logo")
page.get_by_title("Close")
page.locator("css=.item")                       # css
page.locator("//button[@id='x']")               # xpath
page.get_by_role("listitem").filter(has_text="Logout").first()
menu.get_by_text("Logout")                      # chaining scopes to descendants
```
Add `exact=True` to text/role-name matchers for exact (whitespace-normalized) matching.

## Actions (all auto-waited)

```python
loc.click(); loc.dblclick()
loc.fill("text"); loc.clear()
loc.press("Enter"); loc.press("Control+a")
loc.hover()
loc.check(); loc.uncheck(); loc.set_checked(True)
loc.select_option(value="y")        # also label=... or index=...
loc.focus(); loc.blur()
loc.drag_to(page.locator("#dropzone"))
loc.set_input_files("/path/file.pdf")
loc.click(force=True)               # skip actionability checks
```

## Reads

```python
loc.count(); loc.text_content(); loc.input_value(); loc.get_attribute("href")
loc.is_visible(); loc.is_enabled(); loc.is_checked(); loc.is_editable(); loc.is_hidden()
loc.all(); loc.all_text_contents()
```

## Web-first assertions

```python
from visus.web import expect

expect(loc).to_be_visible(); expect(loc).to_be_hidden()
expect(loc).to_be_enabled(); expect(loc).to_be_disabled(); expect(loc).to_be_editable()
expect(loc).to_be_checked()
expect(loc).to_have_text("Done"); expect(loc).to_contain_text("Do")
expect(loc).to_have_value("ada"); expect(loc).to_have_attribute("type", "text")
expect(loc).to_have_class("active"); expect(loc).to_contain_class("active")
expect(loc).to_have_role("button"); expect(loc).to_have_count(3)
expect(loc).not_.to_be_visible()    # negation (also auto-retries)
```

## RPA

```python
# frames / iframes (cross-origin OK; nesting OK)
page.frame_locator("#checkout").get_by_role("button", name="Pay").click()
page.frame_locator("#a").frame_locator("#b").locator("#deep").text_content()

# popups / new tabs
with page.expect_popup() as info:
    page.get_by_role("link", name="Open").click()
popup = info.value; popup.title(); popup.close()

# dialogs (alert/confirm/prompt) — wrap the triggering action
with page.expect_dialog(accept=True, prompt_text="Ada"):
    page.get_by_role("button", name="Prompt").click()

# evaluate / screenshots / pdf
page.evaluate("() => document.title")
page.evaluate("a => a + 1", 41)                 # -> 42
png = page.screenshot(full_page=True); page.screenshot(path="shot.png")
loc.screenshot(path="el.png")
page.pdf(path="page.pdf")                        # Chromium

# cookies (on the Context)
ctx = browser.new_context(); p = ctx.new_page()
ctx.add_cookies([{"name": "k", "value": "v", "url": "https://example.com"}])
ctx.cookies(); ctx.clear_cookies()
```

## Vision (OCR text + image matching) — `[vision]` extra

```python
from visus.web.vision import read_text, solve_captcha, find_image, find_all_images

read_text(image)                 # image: path | bytes | base64 str | PIL.Image | numpy array
solve_captcha(image)             # OCR a (distorted) text captcha; collapses whitespace
find_image(haystack, needle)     # -> Match(x, y, width, height, confidence) | None
find_all_images(haystack, needle)

# integrated with the page:
page.get_by_role("img", name="captcha").ocr_text()       # OCR an element
page.solve_captcha(page.locator("#captcha"))             # solve element's text captcha
page.locator("#area").find_image("icon.png")            # locate a template inside the element
```

## CLI — `[cli]` extra

```bash
visus doctor                       # verify browser + driver
visus install                      # resolve the driver (Selenium Manager)
visus screenshot https://x.com -o shot.png [--full-page]
visus pdf https://x.com -o page.pdf
visus open https://x.com           # headed, waits for Enter
visus codegen https://x.com -o flow.py   # RECORD interactions -> generated visus.web code
visus run flow.py
visus mcp                          # start the MCP server
```

## MCP server (for AI agents) — `[mcp]` extra

Run `visus-web-mcp` (or `visus mcp`). It exposes ~38 tools: `browser_navigate`, `browser_snapshot` (accessibility role+name list — use it to choose targets), `browser_click` / `browser_fill` / `browser_press` / `browser_check` / `browser_select_option` / `browser_hover` / `browser_drag` (target by `role`+`name`, `text`, or `selector`, optionally inside a `frame`), `browser_screenshot`, `browser_evaluate`, `browser_tab_*`, `browser_handle_dialog`, `browser_*_cookies`, and the vision tools `browser_read_text` / `browser_solve_captcha` / `browser_find_image`.

Configure browser via env: `VISUS_WEB_ENGINE` (chrome/edge/firefox), `VISUS_WEB_HEADLESS` (0/1).

## Errors

`visus.web.errors`: `VisusWebError` (base), `VisusTimeoutError`, `NavigationError`, `TargetClosedError`, `StrictModeViolation`, `ElementNotFoundError`, `UnsupportedEngineError`. Failed `expect()` raises `AssertionError`.
