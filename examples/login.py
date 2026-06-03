"""Login RPA — the batteries-included way.

Just the automation. visus.web launches the browser, records the run, writes the
HTML report (even if a step fails), prints a summary, and opens the report — all
automatically. Compare with examples/login_rpa.py, which wires it all by hand.

Run: uv run python examples/login.py   (change ENGINE for edge/firefox)
"""

from visus.web import expect, rpa

ENGINE = "chrome"  # "chrome" | "edge" | "firefox" | "edge_ie"

with rpa("practice-login", engine=ENGINE, open_report=True) as page:
    page.goto("https://practicetestautomation.com/practice-test-login/")
    page.locator("css=#username").fill("student")
    page.locator("//input[@id='password']").fill("Password123")
    page.get_by_role("button", name="Submit").click()
    expect(page.get_by_role("heading", name="Logged In Successfully")).to_be_visible()
