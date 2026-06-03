"""Login RPA — the batteries-included way.

Just the automation. visus.web launches the browser, records the run, writes the
HTML report (even if a step fails), and prints a summary — all automatically.
(Pass open_report=True to also pop the report open.) Compare with
examples/login_rpa.py, which wires all of that by hand.

Run: uv run python examples/login.py   (change ENGINE for edge/firefox)
"""

from visus.web import expect, rpa

ENGINE = "chrome"  # "chrome" | "edge" | "firefox" | "edge_ie"

with rpa("practice-login", engine=ENGINE) as page:  # add open_report=True to auto-open the report
    page.goto("https://practicetestautomation.com/practice-test-login/")
    page.locator("css=#username").fill("student")
    page.locator("//input[@id='password']").fill("Password123")
    page.get_by_role("button", name="Submit").click()
    expect(page.get_by_role("heading", name="Logged In Successfully")).to_be_visible()
