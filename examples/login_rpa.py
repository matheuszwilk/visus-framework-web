"""Login RPA on practicetestautomation.com, fully recorded → HTML report.

Mirrors examples/demo_rpa.py, but drives the public practice-login site:
  https://practicetestautomation.com/practice-test-login/  (user: student / pass: Password123)

Showcases the whole API on a real site: CSS + XPath + semantic (role/text) locators,
auto-retrying expect() through a real cross-page navigation, native backtrack=,
a deliberate failure (FAILED card + failure screenshot), the negative test case
(invalid password → error message), and the observability HTML report.

Run: uv run python examples/login_rpa.py
Produces (temp dir, paths printed at the end): run.zip, report.html, report.png
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from visus.web import errors, expect, launch, tracing

LOGIN_URL = "https://practicetestautomation.com/practice-test-login/"
USERNAME = "student"
PASSWORD = "Password123"

HEADLESS = False  # watch the browser drive; set True for CI/headless runs


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="visus-login-"))
    zip_path = work / "run.zip"

    # ---- the RPA, fully recorded ----
    with tracing.record(str(zip_path)):
        with launch(headless=HEADLESS) as browser:
            page = browser.new_page()

            # 1) abrir a página de login
            page.goto(LOGIN_URL)
            expect(page.get_by_role("heading", name="Test login")).to_be_visible()

            # 2) preencher credenciais — CSS e XPath
            page.locator("css=#username").fill(USERNAME)  # locator por CSS
            page.locator("//input[@id='password']").fill(PASSWORD)  # locator por XPath

            # 3) enviar — locator semântico por role (+ backtrack nativo: re-executa o
            #    passo anterior e tenta de novo caso o clique falhe)
            page.get_by_role(
                "button", name="Submit"
            ).click()  # backtrack=1 implícito: re-tenta o click se a navegação falhar

            # 4) validar login: expect() com auto-retry atravessa a navegação real
            expect(page.get_by_role("heading", name="Logged In Successfully")).to_be_visible()
            assert "logged-in-successfully" in page.url
            msg = page.get_by_text("Congratulations").first().text_content()
            print("login OK:", msg)

            # 5) uma falha proposital -> card FAILED + screenshot de falha no report
            try:
                page.get_by_role("button", name="Botao Inexistente").click(timeout=800)
            except errors.VisusWebError:
                pass

            # 6) logout — locator semântico por role(link)
            page.get_by_role("link", name="Log out").click()
            expect(page.get_by_role("button", name="Submit")).to_be_visible()  # de volta ao login

            # 7) caso negativo: senha inválida -> mensagem de erro (expect em texto exato)
            page.locator("css=#username").fill(USERNAME)
            page.locator("css=#password").fill("SenhaErrada")
            page.get_by_role("button", name="Submits").click(backtrack=2)
            expect(page.locator("#error")).to_have_text("Your password is invalid!")

    # ---- render the HTML report ----
    report_html = work / "report.html"
    tracing.render_report(str(zip_path), str(report_html))

    # ---- screenshot the rendered report (open the local file, full-page) ----
    report_png = work / "report.png"
    with launch(headless=True) as browser:
        page = browser.new_page()
        page.goto(report_html.as_uri())
        page.screenshot(full_page=True, path=str(report_png))

    # ---- summary ----
    with zipfile.ZipFile(str(zip_path)) as z:
        events = [
            json.loads(line)
            for line in z.read("events.jsonl").decode().splitlines()
            if line.strip()
        ]
        shots = [n for n in z.namelist() if n.startswith("screenshots/")]
        manifest = json.loads(z.read("manifest.json"))

    print("=== LOGIN RPA RESULT ===")
    print(f"actions recorded : {len(events)}")
    print(f"failures         : {manifest['counts']['failures']}")
    print(f"screenshots      : {len(shots)}")
    print(f"backtrack steps  : {sum(e['backtrack_steps'] for e in events)}")
    print(
        "actions:",
        ", ".join(f"{e['action']}{'' if e['success'] else '(FAILED)'}" for e in events),
    )
    print("ZIP        :", zip_path)
    print("REPORT_HTML:", report_html)
    print("REPORT_PNG :", report_png)


if __name__ == "__main__":
    main()
