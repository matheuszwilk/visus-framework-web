"""Login RPA — the batteries-included way.

Just the automation. visus.web launches the browser, records the run, writes the
HTML report (even if a step fails), and prints a summary — all automatically.
(Pass open_report=True to also pop the report open.) Compare with
examples/login_rpa.py, which wires all of that by hand.

Run: uv run python examples/login.py   (change ENGINE for edge/firefox)
"""

from visus.web import expect, rpa

ENGINE = "chrome"  # "chrome" | "edge" | "firefox" | "edge_ie"
USERNAME = "student"
PASSWORD = "Password123"

with rpa("practice-login", engine=ENGINE, open_report=True) as page:  # add open_report=True to auto-open the report
    page.goto("https://practicetestautomation.com/practice-test-login/")
    expect(page.get_by_role("heading", name="Test login")).to_be_visible()

                # 2) preencher credenciais — CSS e XPath
    page.locator("css=#username").fill(USERNAME)  # locator por CSS
    page.locator("//input[@id='password']").fill(PASSWORD)  # locator por XPath

    # 3) enviar — locator semântico por role
    page.get_by_role("button", name="Submit").click()

    # 4) validar login: expect() com auto-retry atravessa a navegação real
    expect(page.get_by_role("heading", name="Logged In Successfully")).to_be_visible()
    assert "logged-in-successfully" in page.url
    print("login OK:", page.get_by_text("Congratulations").first().text_content())

    # 5) logout — locator semântico por role(link)
    page.get_by_role("link", name="Log out").click()
    expect(page.get_by_role("button", name="Submit")).to_be_visible()

    # 6) caso negativo: senha inválida -> mensagem de erro (expect em texto exato)
    page.locator("css=#username").fill(USERNAME)
    page.locator("css=#password").fill("SenhaErrada")
    page.get_by_role("button", name="Submits").click(backtrack=2, timeout=100)
    expect(page.locator("#error")).to_have_text("Your password is invalid!")
