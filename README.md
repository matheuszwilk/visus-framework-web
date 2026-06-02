# visus-web

Modern, Playwright-style web automation on a **pure Selenium engine**, with BotCity RPA reach.

## Install (dev)

    uv venv && uv pip install -e ".[dev]"

## Quickstart

    from visus.web import launch

    with launch(headless=True) as browser:
        page = browser.new_page()
        page.goto("https://example.com")
        print(page.title())

## Status

Slice S0 (foundation: backend seam + launch + navigation) complete.
Next: S1 — lazy Locators, auto-wait/actionability, and auto-retrying `expect()`.
