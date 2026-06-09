<div align="center">

# Visus Web

**Modern, Playwright-style web automation on a pure Selenium engine — semantic locators, auto-waiting actions, auto-retrying assertions, BotCity-style RPA reach, and an OCR + image-matching vision plugin.**

[![PyPI](https://img.shields.io/pypi/v/visus-web.svg)](https://pypi.org/project/visus-web/)
[![Python](https://img.shields.io/pypi/pyversions/visus-web.svg)](https://pypi.org/project/visus-web/)
[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://github.com/astral-sh/ruff)

</div>

Visus Web automates the browser the way a developer thinks about it: **semantic locators**
(`get_by_role`, `get_by_label`, `get_by_text`), **auto-waiting actions** (no `sleep`, ever), and
**web-first assertions** that auto-retry until the page settles. It pairs Playwright's developer
experience with **Selenium's compatibility** (Grid, corporate browsers, Edge IE-mode) — written from
scratch, fully typed, with **no Playwright dependency**. On top of the test-automation core it adds
**RPA reach** (frames, popups, dialogs, cookies, downloads, file upload, PDF) and an optional
**OCR + image-matching vision plugin** for captchas.

> **Part of the Visus family.** `visus-web` (import root `visus.web`) sits alongside
> [`visus-desktop`](https://pypi.org/project/visus-desktop/) (`visus.desktop`, GUI automation) under
> one planned automation ecosystem.

---

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quickstart](#quickstart)
- [Drive it from any MCP agent](#drive-it-from-any-mcp-agent)
- [Drive it from the shell — the `visus` CLI](#drive-it-from-the-shell--the-visus-cli)
- [Python usage guide](#python-usage-guide)
  - [`rpa()` — batteries-included automation](#rpa--batteries-included-automation)
  - [`launch()` — full control](#launch--full-control)
  - [Locators](#locators)
  - [Paste-an-element locator](#paste-an-element-locator)
  - [Actions](#actions)
  - [Assertions (`expect`)](#assertions-expect)
  - [Field enumeration (act by number)](#field-enumeration-act-by-number)
  - [Frames & iframes](#frames--iframes)
  - [Tabs & popups](#tabs--popups)
  - [Dialogs](#dialogs)
  - [Downloads](#downloads)
  - [Cookies & contexts](#cookies--contexts)
  - [Screenshots, PDF & JavaScript](#screenshots-pdf--javascript)
  - [Network controls](#network-controls)
  - [Low-level mouse & keyboard](#low-level-mouse--keyboard)
  - [Vision — OCR & image matching](#vision--ocr--image-matching)
  - [Tracing & HTML reports](#tracing--html-reports)
  - [Async API](#async-api)
- [Engines](#engines)
- [Configuration & environment variables](#configuration--environment-variables)
- [Error handling](#error-handling)
- [Project layout](#project-layout)
- [Development & testing](#development--testing)
- [License](#license)

---

## Features

- **🎭 Semantic locators** — `get_by_role / text / label / placeholder / test_id / alt_text / title`,
  `locator(css|xpath)`, `first / last / nth / filter`, plus `frame_locator` for cross-origin and
  nested iframes. Find elements the way a user perceives them, not by brittle CSS chains.
- **📋 Paste-an-element locator** — paste an element straight from DevTools ("Copy element") into
  `page.locator('<input name="email" class="…">')`; Visus derives an **ordered set of selectors**
  (id → `data-*` → name → aria → class → xpath, Tailwind classes escaped) and tries each until one
  matches — resilient to a changed id/class.
- **⏳ Auto-waited actions** — `click / dblclick / fill / press / hover / check / uncheck /
  set_checked / select_option / drag_to / focus / blur / clear / set_input_files` all wait for the
  element to become actionable. **No `sleep`, ever.**
- **✅ Web-first assertions** — `expect(loc).to_be_visible / to_have_text / to_have_value /
  to_have_count / to_have_role / …` with `.not_` negation; every matcher **auto-retries** until it
  passes or times out.
- **🤖 Batteries-included RPA** — `rpa()` launches the browser, **records the run**, writes a
  single-file **HTML report (even on failure)**, and prints a summary — you write only the
  automation.
- **🗂️ RPA reach** — frames, `expect_popup`, `expect_dialog`, `expect_download`, cookies, contexts,
  `evaluate`, element/full-page **screenshots**, and **PDF**.
- **🔢 Field enumerator** — `list_fields()` enumerates every interactive field (across open Shadow
  DOM and same-origin iframes), draws a numbered overlay, and lets you act **by index**
  (`page.field(7).fill(...)`) — the same model the CLI uses.
- **👁️ Vision plugin (`[vision]`)** — `read_text` / `solve_captcha` (RapidOCR) and `find_image` /
  `find_all_images` (OpenCV), plus `locator.ocr_text()` / `locator.find_image()` /
  `page.solve_captcha()`.
- **🧩 MCP server (`[mcp]`)** — `visus-web-mcp` exposes **43 tools** (navigation, accessibility
  snapshot, all actions, tabs, dialogs, cookies, screenshot, evaluate, vision) to AI agents.
- **⌨️ Full-featured CLI (`[cli]`)** — the `visus` command mirrors the whole surface in the shell
  with a persistent browser daemon, `--json` everywhere, and an interactive `console`.
- **🔌 Async API** — `visus.web.async_api` is a 100% mirror of the sync surface (same names, same
  parameters) wrapped in `asyncio.to_thread`; builders stay sync (recipe-only), reads and actions
  are `await`-able.
- **🌐 Selenium compatibility** — Chrome, Edge, Firefox, and **Edge IE-mode** (Trident) for legacy
  corporate apps.
- **🏷️ Fully typed** — ships a `py.typed` marker; no `selenium.*` type ever crosses the public API.

---

## Requirements

- **Python 3.10+**
- A supported **browser** installed (Chrome, Edge, or Firefox). Drivers are resolved automatically by
  **Selenium Manager** — no manual driver download needed (`visus install` forces a one-time resolve).
- Core dependency installed automatically: `selenium>=4.38,<5`.
- Optional extras pull in their own deps: `[vision]` (RapidOCR + OpenCV + Pillow + NumPy), `[mcp]`
  (the `mcp` package), `[cli]` (Typer + Rich).

---

## Installation

```bash
pip install visus-web                 # core (Selenium engine + Python API)
pip install "visus-web[vision]"       # + OCR (RapidOCR) + image matching (OpenCV)
pip install "visus-web[mcp]"          # + MCP server for AI agents (visus-web-mcp)
pip install "visus-web[cli]"          # + the `visus` CLI (incl. codegen)
```

Install several extras at once:

```bash
pip install "visus-web[vision,mcp,cli]"
```

Verify a browser + driver launch correctly:

```bash
visus doctor --engine chrome      # OK: chrome launches and navigates ...
```

---

## Quickstart

Batteries included — write only the automation; Visus launches the browser, records the run, writes
an HTML report (even on failure), and prints a summary:

```python
from visus.web import rpa, expect

with rpa("login", engine="chrome") as page:               # "chrome" | "edge" | "firefox" | "edge_ie"
    page.goto("https://example.com/login")
    page.get_by_label("Email").fill("ada@example.com")
    page.get_by_role("button", name="Sign in").click()    # auto-waits until actionable
    expect(page.get_by_text("Welcome")).to_be_visible()   # auto-retries until true
# → ./visus-runs/login-<timestamp>/report.html  (+ run.zip, + a printed summary)
```

Need full control (multiple pages, custom contexts)? Drop down to `launch`:

```python
from visus.web import launch, expect

with launch(headless=True) as browser:
    page = browser.new_page()
    page.goto("https://example.com")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Welcome")).to_be_visible()
```

---

## Drive it from any MCP agent

`visus-web` ships a **Model Context Protocol** server exposing **43 tools** so an AI agent
(Claude Code / Desktop, Cursor) can drive the browser end to end. Each tool carries a docstring that
teaches the agent *when and how* to use it, so it never has to read source.

```bash
pip install "visus-web[mcp]"
```

Wire it into your MCP client:

```jsonc
// claude_desktop_config.json (or ~/.claude.json / .mcp.json for Claude Code)
{
  "mcpServers": {
    "visus-web": {
      "command": "visus-web-mcp",
      "env": {
        "VISUS_WEB_ENGINE": "chrome",   // chrome | edge | firefox | edge_ie
        "VISUS_WEB_HEADLESS": "1"       // "0" to watch the browser drive
      }
    }
  }
}
```

**Tool groups (43 tools):**

| Group | Tools |
|---|---|
| Navigation | `browser_navigate`, `browser_navigate_back`, `browser_navigate_forward`, `browser_reload` |
| Inspect | `browser_snapshot` ★, `browser_list_fields`, `browser_clear_highlights`, `browser_translate_element`, `browser_title`, `browser_url`, `browser_get_text`, `browser_get_attribute`, `browser_count` |
| Actions | `browser_click`, `browser_dblclick`, `browser_fill`, `browser_press`, `browser_hover`, `browser_check`, `browser_uncheck`, `browser_select_option`, `browser_drag`, `browser_focus`, `browser_clear`, `browser_set_input_files` |
| Wait / expect | `browser_wait_for`, `browser_expect_text` |
| Tabs | `browser_tab_list`, `browser_tab_new`, `browser_tab_select`, `browser_tab_activate`, `browser_tab_close`, `browser_set_tab_follow` |
| Dialogs | `browser_handle_dialog` |
| Cookies | `browser_get_cookies`, `browser_add_cookies`, `browser_clear_cookies` |
| Media / JS | `browser_screenshot`, `browser_evaluate` |
| Vision *(`[vision]`)* | `browser_read_text`, `browser_solve_captcha`, `browser_find_image` |
| Lifecycle | `browser_close` |

**Recommended agent flow:** `browser_navigate` → `browser_snapshot` (read the role/name table) **or**
`browser_list_fields` (numbered, with ready-to-use locators) → act with `browser_click` /
`browser_fill` / … targeting by `role`+`name`, `text`, or `selector` → `browser_wait_for` /
`browser_expect_text` to synchronize.

Every action tool accepts the same **target** parameters — provide whichever you have:

| Param | Meaning |
|---|---|
| `selector` | A CSS selector, `xpath=…`, or a pasted DevTools element (`<…>`). |
| `role` + `name` | ARIA role and accessible name (e.g. `role="button"`, `name="Sign in"`). |
| `text` | Visible text content. |
| `exact` | Match `name`/`text` exactly instead of as a substring. |
| `frame` | CSS/XPath of an `<iframe>` to resolve the target inside. |

New tabs/popups are **manual** by default (`browser_set_tab_follow(False)`): a click that opens a tab
does not change your context — steer explicitly with `browser_tab_list` / `browser_tab_select`. Set
`browser_set_tab_follow(True)` for auto-follow.

> A runnable example of the exact calls an agent makes lives in
> [`examples/login_mcp.py`](examples/login_mcp.py).

---

## Drive it from the shell — the `visus` CLI

The `visus` command (install the `[cli]` extra) mirrors the automation surface in the terminal,
backed by a **persistent browser daemon** so commands share one live session. Every read command
takes `--json`.

```bash
pip install "visus-web[cli]"

visus session start https://practicetestautomation.com/practice-test-login/  # start the daemon
visus list-fields                       # enumerate + number the page's fields
visus fill 1 student                    # act by index, like the MCP list_fields flow
visus fill 2 Password123
visus click --role button --name Submit # or target by role/name/selector/text
visus expect-text --role heading "Logged In Successfully"
visus session stop                      # close the browser
```

Run `visus --help` (or `visus <command> --help`) for inline help. Use `visus console` for an
interactive REPL attached to the session.

<details>
<summary><b>Full command reference</b> (click to expand)</summary>

Targeting: most commands accept a positional **field index** (from the last `list-fields`) **or**
`--selector/-s`, `--role`, `--name`, `--text`. Nearly every read command accepts `--json`.

### Session & lifecycle

| Command | What it does |
|---|---|
| `visus session start [URL] --engine <e> --headless` | Start the persistent browser daemon (headed by default). |
| `visus session stop` | Stop the session (closes the browser). |
| `visus session status [--json]` | Show the running session's status. |
| `visus console [URL] --engine <e> --headless` | Open an interactive REPL attached to the session. |

### Navigation

| Command | What it does |
|---|---|
| `visus goto <URL>` | Navigate the session's page to a URL. |
| `visus back` / `visus forward` / `visus reload` | History navigation / reload. |

### Inspect / search the DOM

| Command | What it does |
|---|---|
| `visus snapshot [--json]` | List interactive elements as a role/name table. |
| `visus list-fields --kind <k> --all --no-highlight [--json]` | Enumerate interactive fields, numbered + highlighted. |
| `visus get-text [idx] [target]` | Print an element's text content. |
| `visus get-attribute <attr> [idx] [target]` | Print an element's attribute value. |
| `visus count [idx] [target]` | Count elements matching the target. |
| `visus title` / `visus url` | Print the page title / URL. |
| `visus translate [html] --file <f> [--json]` | Convert a pasted DevTools element into css/xpath/id/class selectors (reads the clipboard if omitted). |

### Actions

| Command | What it does |
|---|---|
| `visus click [idx] [target]` | Click a field. |
| `visus dblclick [idx] [target]` | Double-click a field. |
| `visus fill [idx] <text>` / `… -s <sel> --value <v>` | Fill an input. |
| `visus clear-input [idx] [target]` | Clear an input's value. |
| `visus check` / `visus uncheck [idx] [target]` | Check / uncheck a checkbox or radio. |
| `visus select [idx] <value>` | Select an option on a `<select>`. |
| `visus press [idx] <key>` | Press a key/chord (e.g. `Enter`, `Control+a`). |
| `visus hover` / `visus focus [idx] [target]` | Hover / focus a field. |
| `visus drag <src> <dst>` / `… --to-selector` | Drag a source element onto a target. |
| `visus upload [idx] <paths…>` | Set file(s) on a file input. |

### Wait / assert

| Command | What it does |
|---|---|
| `visus wait [idx] [target] --state <s> --timeout <ms>` | Wait for `visible`/`hidden`/`attached`/`detached`. |
| `visus expect-text [idx] <text> --timeout <ms>` | Assert an element contains text (PASSED/FAILED). |

### Tabs / windows

| Command | What it does |
|---|---|
| `visus tabs [--json]` | List open tabs/windows (active marked `*`). |
| `visus tab [idx]` | Switch to a tab by index (newest if omitted). |
| `visus tab-new [URL]` | Open a new tab and switch to it. |
| `visus tab-close [idx]` | Close a tab (active if omitted). |

### Dialogs / cookies / JS

| Command | What it does |
|---|---|
| `visus dialog --accept/--dismiss --prompt-text <t>` | Handle the next alert/confirm/prompt. |
| `visus cookies [--json]` | List cookies. |
| `visus add-cookies '<json>'` / `visus clear-cookies` | Add / clear cookies. |
| `visus eval "<fn>" [arg] [--json]` | Evaluate JS in the page (e.g. `'() => document.title'`). |

### Capture / vision / utilities

| Command | What it does |
|---|---|
| `visus screenshot <URL> -o <png> --full-page --headless --engine <e>` | Screenshot a URL to a PNG (one-off browser). |
| `visus session-screenshot [idx] -o <png> --full-page` | Screenshot the session's page or a single element. |
| `visus pdf <URL> -o <pdf>` | Print a URL to a PDF (Chromium). |
| `visus open <URL> --engine <e>` | Open a headed browser at URL until you press Enter. |
| `visus clear` | Remove the numbered field-highlight overlay. |
| `visus read-text [idx] [target]` *(`[vision]`)* | OCR an element's screenshot → recognized text. |
| `visus solve-captcha [idx] [target]` *(`[vision]`)* | OCR-solve a text CAPTCHA. |
| `visus find-image <template.png> [idx] [target] -c <conf> [--json]` *(`[vision]`)* | Find a template image inside the page/element. |

### Tooling

| Command | What it does |
|---|---|
| `visus codegen <URL> -o <file> --engine <e>` | Record interactions in a headed browser and generate `visus.web` code. |
| `visus doctor --engine <e>` | Check a browser + driver launch correctly. |
| `visus install --engine <e>` | Resolve/download the driver via Selenium Manager. |
| `visus mcp` | Start the MCP server over stdio (same as `visus-web-mcp`). |
| `visus run <script.py>` | Run a Python script with the active interpreter. |
| `visus version` | Print the `visus.web` version. |

</details>

---

## Python usage guide

Conventions:

- **Timeouts** are in **milliseconds**; omit to use the defaults (action/navigation 30 000 ms,
  `expect` 5 000 ms).
- **Locators are lazy recipes** — `get_by_*` / `locator` only build a selector chain; the live page
  is touched only when you call an action or read.
- **`backtrack`** (on actions and `goto`) replays the previous step(s) and retries on failure — pass
  `True` or an integer count.

### `rpa()` — batteries-included automation

```python
from visus.web import rpa, expect

with rpa(
    "checkout",                # run label (used in the output folder name)
    engine="chrome",           # "chrome" | "edge" | "firefox" | "edge_ie"
    headless=False,            # watch it drive; True for CI
    outdir=None,               # default: ./visus-runs/<name>-<timestamp>/
    report=True,               # render report.html on exit (even if a step fails)
    summary=True,              # print a one-block run summary on exit
    open_report=False,         # open report.html in the default browser
    reraise=False,             # True: re-raise VisusWebError for programmatic handling
) as page:
    page.goto("https://shop.example.com")
    page.get_by_role("button", name="Add to cart").click()
    expect(page.get_by_text("1 item")).to_be_visible()
# → run.zip + report.html written automatically; summary printed
```

### `launch()` — full control

```python
from visus.web import launch

with launch("firefox", headless=True) as browser:
    page = browser.new_page()
    page.goto("https://example.com")
    # ... multiple pages / contexts available via browser.new_context()
```

### Locators

```python
page.get_by_role("button", name="Sign in")     # ARIA role + accessible name
page.get_by_role("link", name="Docs", exact=True)
page.get_by_text("Welcome back")                # visible text (substring)
page.get_by_label("Email")                      # form control by its <label>
page.get_by_placeholder("Search…")
page.get_by_test_id("submit")                   # data-testid
page.get_by_alt_text("Company logo")
page.get_by_title("Close")
page.locator("#username")                       # CSS
page.locator("xpath=//button[@type='submit']")  # XPath
page.locator(".row").locator("css=button")      # chain

# Refinement
page.get_by_role("listitem").filter(has_text="In stock").first()
page.get_by_role("row").nth(2)
page.locator(".card").last()
page.locator("#shadow-host").locator("button", deep=True)   # pierce open Shadow DOM

# Reads
loc = page.locator("#total")
loc.count(); loc.is_visible(); loc.is_enabled(); loc.is_checked()
loc.text_content(); loc.get_attribute("href"); loc.input_value()
loc.all_text_contents(); [l.text_content() for l in loc.all()]
```

### Paste-an-element locator

Copy an element in DevTools ("Copy element") and paste its `outerHTML` straight in — Visus derives an
ordered candidate list (id → `data-*` → name → aria → class → xpath) and tries each:

```python
page.locator('<input name="email" class="form-control w-full" type="email">').fill("ada@x.com")
```

Preview what it would generate (no live page needed):

```python
from visus.web.api._htmlsel import translate
translate('<button id="go" class="btn">Go</button>')   # {id, css, xpath, class, candidates_*}
```

The same is available as `visus translate '<…>'` and the `browser_translate_element` MCP tool.

### Actions

Every action auto-waits for actionability. All accept `timeout=<ms>`, most accept `force=True`
(skip checks) and `backtrack`:

```python
loc.click(); loc.dblclick(); loc.hover(); loc.focus(); loc.blur()
loc.fill("hello"); loc.clear(); loc.press("Enter"); loc.press("Control+a")
loc.check(); loc.uncheck(); loc.set_checked(True)
loc.select_option(value="US")            # or label="United States" / index=0
loc.set_input_files("invoice.pdf")       # or ["a.png", "b.png"]
src.drag_to(target)
```

### Assertions (`expect`)

Web-first matchers auto-retry until they pass or time out; negate with `.not_`:

```python
from visus.web import expect

expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
expect(page.get_by_label("Email")).to_have_value("ada@example.com")
expect(page.get_by_role("listitem")).to_have_count(3)
expect(page.get_by_text("Error")).not_.to_be_visible()

# Full set:
# to_be_visible / to_be_hidden / to_be_enabled / to_be_disabled / to_be_checked / to_be_editable
# to_have_text(exact=True) / to_contain_text / to_have_value / to_have_count
# to_have_attribute(name, value) / to_have_class / to_contain_class / to_have_role
```

### Field enumeration (act by number)

`list_fields()` enumerates every interactive field (across open Shadow DOM and same-origin iframes),
draws a numbered overlay, and lets you act by index — ideal for quick/interactive scripts and the
exact model the CLI and MCP use:

```python
fields = page.list_fields(kinds=["input", "button"], include_hidden=False, highlight=True)
for f in fields:
    print(f.index, f.kind, f.name, f.locator)

page.field(0).fill("student")             # act by number (from the latest list_fields)
page.field_locator(fields[1]).fill("…")   # or by the Field object (resolves frame/shadow chain)
page.clear_highlights()
```

Each `Field` carries `index, kind, tag, type, role, name, label, placeholder, value, checked,
disabled, visible, frame, shadow, locator, locator_kind, css, xpath, code, deep` and a `.to_dict()`.
For durable automation prefer a stable selector over the positional index.

### Frames & iframes

```python
frame = page.frame_locator("#checkout-iframe")
frame.get_by_label("Card number").fill("4242 4242 4242 4242")
frame.frame_locator("#nested").get_by_role("button", name="Pay").click()   # nested iframes
```

### Tabs & popups

```python
with page.expect_popup() as popup:
    page.get_by_role("link", name="Open in new tab").click()
new_page = popup.value
new_page.goto("https://…")

# Enumerate / focus tabs without dropping to launch:
for p in page.context.pages:
    print(p.handle, p.url)
p.bring_to_front()           # alias: p.activate()
```

### Dialogs

```python
with page.expect_dialog(accept=True, prompt_text="yes") as dlg:
    page.get_by_role("button", name="Delete").click()
print(dlg.value.message, dlg.value.type)   # "alert" | "confirm" | "prompt" | "beforeunload"
```

### Downloads

```python
with page.expect_download() as dl:
    page.get_by_role("button", name="Export CSV").click()
dl.value.save_as("./reports/export.csv")    # also: dl.value.path, dl.value.suggested_filename
```

### Cookies & contexts

```python
ctx = browser.new_context()                 # isolated cookies/cache
page = ctx.new_page()
ctx.add_cookies([{"name": "session", "value": "abc", "url": "https://example.com"}])
print(ctx.cookies())
ctx.clear_cookies()
```

### Screenshots, PDF & JavaScript

```python
page.screenshot(path="page.png", full_page=True)
page.locator("#chart").screenshot(path="chart.png")
page.pdf(path="page.pdf")                    # Chromium only
host = page.evaluate("() => window.location.hostname")
doubled = page.evaluate("(x) => x * 2", 21)
```

### Network controls

Chromium-only, via CDP:

```python
page.block_urls(["*.ads.com", "*ga.js"])
page.set_extra_http_headers({"X-Debug": "1"})
page.set_offline(True); page.set_offline(False)
```

### Low-level mouse & keyboard

```python
page.mouse.move(100, 200); page.mouse.click(100, 200); page.mouse.dblclick(100, 200)
page.mouse.down(); page.mouse.up(); page.mouse.wheel(0, 300)
page.keyboard.press("Control+a"); page.keyboard.type("hello"); page.keyboard.insert_text("raw")
```

### Vision — OCR & image matching

Requires the `[vision]` extra (`pip install "visus-web[vision]"`).

```python
# Locator / page hooks
text = page.locator("#captcha").ocr_text()
solution = page.solve_captcha(page.get_by_role("img", name="CAPTCHA"))
match = page.locator("#canvas").find_image("button.png", confidence=0.9)
if match:
    page.mouse.click(match.center_x, match.center_y)

# Standalone functions on any image (path, bytes, PIL, numpy, base64)
from visus.web.vision import read_text, solve_captcha, find_image, find_all_images, Match
read_text(page.screenshot())
m = find_image(page.screenshot(), "logo.png", confidence=0.85)   # -> Match | None
ms = find_all_images(page.screenshot(), "row.png")               # -> list[Match]
```

### Tracing & HTML reports

`rpa()` does this for you, but you can record any `launch()` block too:

```python
from visus.web import tracing, launch

with tracing.record("run.zip", report="report.html"):   # report written even on exception
    with launch(headless=True) as browser:
        page = browser.new_page()
        page.goto("https://example.com")
        page.get_by_label("Search").fill("visus")

# Or render a report from a saved zip later:
tracing.render_report("run.zip", "report.html")
# Global toggles: tracing.enable() / tracing.disable() / tracing.is_enabled()
```

### Async API

`visus.web.async_api` is a **100% mirror** of the synchronous surface — same method names,
**same parameter names** — so porting sync code is a mechanical `await` insertion. The rule:

- **Builders stay sync** (`get_by_*` / `locator` / `first` / `last` / `nth` / `filter` /
  `frame_locator`) and so do **zero-I/O accessors** (`page.handle` / `page.is_closed` /
  `page.context` / `browser.contexts` / `page.mouse` / `page.keyboard` / `page.field` /
  `page.field_locator`) — they never touch the browser.
- **Everything that reaches the live browser** is `await`-able and runs in a thread, so the
  event loop never blocks.

```python
import asyncio
from visus.web.async_api import launch, expect

async def main():
    async with await launch(headless=True) as browser:
        page = await browser.new_page()
        await page.goto("https://example.com/login")
        await page.get_by_label("Email").fill("ada@example.com")     # builder sync, fill async
        await page.get_by_role("button", name="Sign in").click()
        await expect(page.get_by_text("Welcome")).to_be_visible()

asyncio.run(main())
```

Everything the sync API offers is here too — RPA, tracing, the field enumerator, low-level
mouse/keyboard, captcha solving, popup/dialog/download capture, and multi-tab navigation:

```python
from visus.web.async_api import rpa

async def login():
    # batteries-included: launch + record + report + summary, all handled
    async with rpa("login", engine="chrome", headless=True) as page:
        await page.goto("https://example.com/login")

        # field enumerator — act by number, like the CLI
        for f in await page.list_fields():
            if f.name == "Username":
                await page.field(f.index).fill("ada")

        # low-level input devices
        await page.mouse.click(120, 240)
        await page.keyboard.press("Control+a")

        # event capture (context managers propagate errors just like sync)
        async with page.expect_popup() as popup:
            await page.get_by_role("link", name="Terms").click()
        await popup.value.close()

        # multi-tab: page.context reaches the other tabs
        handles = {p.handle for p in await page.context.pages()}
```

Exports: `launch`, `rpa`, `expect`, `Engine`, `errors`, `tracing`, `Field`, `Dialog`,
`Download`, `AsyncBrowser`, `AsyncContext`, `AsyncPage`, `AsyncLocator`, `AsyncFrameLocator`,
`AsyncLocatorAssertions`, `AsyncMouse`, `AsyncKeyboard`.

---

## Engines

Pass a string or the `Engine` enum to `launch()` / `rpa()` / the CLI `--engine` / the MCP
`VISUS_WEB_ENGINE` env var.

| String | `Engine` member | Browser | Notes |
|---|---|---|---|
| `"chrome"` | `Engine.CHROME` | Google Chrome / Chromium | Default. Full feature set (PDF, CDP network controls). |
| `"edge"` | `Engine.EDGE` | Microsoft Edge | Chromium-based; same features as Chrome. |
| `"firefox"` | `Engine.FIREFOX` | Mozilla Firefox | No CDP-only features (PDF / network controls). |
| `"edge_ie"` | `Engine.EDGE_IE` | Edge in **IE mode** (Trident) | Windows-only; for legacy corporate apps. See env vars below. |

Drivers are resolved automatically by **Selenium Manager**.

---

## Configuration & environment variables

Default timeouts (`visus.web.config.Defaults`, all in ms): `action_timeout_ms = 30_000`,
`navigation_timeout_ms = 30_000`, `expect_timeout_ms = 5_000`. Override per call with `timeout=<ms>`.

| Variable | Used by | Default | Purpose |
|---|---|---|---|
| `VISUS_WEB_ENGINE` | MCP & CLI session | `chrome` | Browser engine for the daemon/MCP session. |
| `VISUS_WEB_HEADLESS` | MCP & CLI session | `1` (MCP) | `"0"` to run headed. |
| `VISUS_WEB_URL` | CLI session | — | Initial URL opened when the daemon starts. |
| `VISUS_WEB_TOKEN` | CLI session | auto | Auth token for the local daemon socket. |
| `VISUS_WEB_TRACING` | tracing | off | Enable tracing globally without code. |
| `VISUS_WEB_EDGE_BINARY` | `edge_ie` | default install path | Path to `msedge.exe`. |
| `VISUS_WEB_IE_DRIVER` | `edge_ie` | auto | Explicit IEDriverServer path (wins over auto-resolve). |
| `VISUS_WEB_IE_DRIVER_VERSION` | `edge_ie` | `4.0.0` | Pinned IEDriverServer version (4.8+ can't attach to modern Edge). |
| `VISUS_WEB_IE_TIMEOUT` | `edge_ie` | `45` | Seconds before the launch watchdog fails fast with a clear error. |

---

## Error handling

All exceptions live in `visus.web.errors` and subclass `VisusWebError`:

```python
from visus.web import rpa, errors

try:
    with rpa("flow", reraise=True) as page:   # reraise=True surfaces the error
        page.goto("https://example.com")
        page.get_by_role("button", name="Nope").click()
except errors.VisusTimeoutError:
    print("element never became actionable")
except errors.VisusWebError as exc:
    print(f"automation failed: {exc}")
```

| Exception | Raised when |
|---|---|
| `VisusWebError` | Base class for all `visus.web` errors. |
| `UnsupportedEngineError` | An unknown engine string was requested. |
| `VisusTimeoutError` | An operation exceeded its deadline (action/navigation/expect). |
| `NavigationError` | A navigation failed. |
| `TargetClosedError` | The page/context/browser is already closed. |
| `StrictModeViolation` | A strict locator matched more than one element. |
| `ElementNotFoundError` | A locator resolved to zero elements where one was required. |

Without `reraise=True`, `rpa()` catches a failed step, writes the report, prints a friendly summary,
and exits non-zero — so a failure is always debuggable from `report.html`.

---

## Project layout

```
visus-framework-web/
├── src/visus/web/              # library code (PEP 420 namespace: no __init__.py in src/visus/)
│   ├── __init__.py             # public API: launch, rpa, expect, Engine, Browser, Context, Page, Field
│   ├── rpa.py                  # rpa() batteries-included context manager
│   ├── engine.py               # Engine enum (chrome / edge / firefox / edge_ie)
│   ├── config.py               # Defaults (timeouts)
│   ├── errors.py               # exception hierarchy
│   ├── tracing.py              # tracing.record / enable / disable / render_report
│   ├── api/                    # engine-agnostic public surface
│   │   ├── page.py             # Page
│   │   ├── locator.py          # Locator
│   │   ├── frame_locator.py    # FrameLocator
│   │   ├── assertions.py       # expect() + LocatorAssertions
│   │   ├── browser.py          # Browser
│   │   ├── context.py          # Context
│   │   ├── fields.py           # Field dataclass
│   │   ├── input.py            # Mouse, Keyboard
│   │   └── events.py           # Dialog, Download
│   ├── async_api/              # async facade (AsyncPage, AsyncLocator, …)
│   ├── vision/                 # OCR + image matching ([vision] extra)
│   ├── backends/               # Selenium engine (all selenium.* confined here) + browser drivers
│   ├── cli/                    # the `visus` CLI + persistent session daemon
│   ├── mcp/                    # the visus-web-mcp server (43 tools)
│   └── observability/          # run recording + HTML report rendering
├── examples/                   # demo_rpa.py, login.py, login_rpa.py, login_mcp.py, dolar.py
├── skills/                     # using-visus-web, developing-visus-web (agent/contributor guides)
├── tests/                      # pytest suite (parallel, real headless-Chrome integration)
├── TESTING.md
├── LICENSE
└── pyproject.toml
```

---

## Development & testing

```bash
git clone https://github.com/matheuszwilk/visus-framework-web.git
cd visus-framework-web

uv venv && uv pip install -e ".[dev,vision,mcp,cli]"
uv run pytest -q          # parallel (xdist), real headless-Chrome integration tests
uv run ruff check src tests && uv run mypy
```

See [`TESTING.md`](TESTING.md) for the test matrix (including the Edge IE-mode end-to-end tests) and
the `skills/` directory for the agent-facing usage playbook (`using-visus-web`) and contributor guide
(`developing-visus-web`).

---

## License

**Proprietary — all rights reserved.** You may install and use `visus-web` as a dependency in your
own projects, but copying the source, redistributing, modifying, or reverse engineering it is **not
permitted**. See [LICENSE](LICENSE) for the full terms. For commercial or redistribution licenses,
contact the author.
