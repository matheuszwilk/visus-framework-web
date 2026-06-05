"""Login RPA — the batteries-included way.

visus.web launches the browser, records the run, writes the HTML report (even on
failure), and prints a summary — all automatically. This logs into the public
practice site and shows off the "paste a DevTools element" locator.

Run: uv run python examples/login.py   (change ENGINE for edge/firefox)
"""

from visus.web import expect, rpa

ENGINE = "chrome"  # "chrome" | "edge" | "firefox" | "edge_ie"
USERNAME = "student"
PASSWORD = "Password123"

# add open_report=True to pop the HTML report open at the end
with rpa("practice-login", engine=ENGINE, open_report=True) as page:
    page.goto("https://practicetestautomation.com/practice-test-login/")

    # paste-an-element locators — copied straight from DevTools ("Copy element")
    page.locator('<input type="text" name="username" id="username">').fill(USERNAME)
    page.locator('<input type="password" name="password" id="password">').fill(PASSWORD)
    page.locator('<button id="submit" class="btn">Submit</button>').click()

    # verify the login worked (expect auto-retries through the real navigation)
    expect(page.get_by_role("heading", name="Logged In Successfully")).to_be_visible()
    print("login OK:", page.get_by_text("Congratulations").first().text_content())
