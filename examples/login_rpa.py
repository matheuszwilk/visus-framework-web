"""Login RPA on practicetestautomation.com, fully recorded → HTML report.

Mirrors examples/demo_rpa.py, but drives the public practice-login site:
  https://practicetestautomation.com/practice-test-login/  (user: student / pass: Password123)

Showcases the whole API on a real site: CSS + XPath + semantic (role/text) locators,
auto-retrying expect() through a real cross-page navigation, native backtrack=, the
negative test case (invalid password → error), the friendly action-error messages,
and the observability HTML report — which is rendered even when a step FAILS, because
tracing.record(..., report=...) writes it on the way out no matter what.

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

ENGINE = "chrome"  # which browser: "chrome" | "edge" | "firefox" | "edge_ie"
HEADLESS = False  # watch the browser drive; set True for CI/headless runs
DEMO_FAILURE = True  # end on a deliberately broken step to prove the report is still
#                      generated — and to show the friendly "did you mean?" error.


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="visus-login-"))
    zip_path = work / "run.zip"
    report_html = work / "report.html"
    report_png = work / "report.png"

    rpa_error: Exception | None = None
    # report=... renders report.html on the way out even if a step raises, so a
    # broken run is always debuggable — no try/finally needed around the report.
    try:
        with tracing.record(str(zip_path), report=str(report_html)):
            with launch(ENGINE, headless=HEADLESS) as browser:
                page = browser.new_page()

                # 1) abrir a página de login
                page.goto(LOGIN_URL)
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
                page.get_by_role("button", name="Submits").click(backtrack=2, timeout=5000)
                expect(page.locator("#error")).to_have_text("Your password is invalid!")

                # 7) falha proposital NÃO tratada: o botão "Submits" não existe. backtrack=2
                #    re-executa os 2 passos anteriores e tenta de novo; como não existe, falha
                #    com uma mensagem amigável ("did you mean: 'Submit'?") — e o relatório
                #    ainda é gerado para você debugar.

    except errors.VisusWebError as exc:
        rpa_error = exc
        print(f"\nRPA stopped on a failed step:\n{exc}\n")

    # report.html já foi gerado pelo record(report=...); agora tira um screenshot dele
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
    if rpa_error:
        print("note: RPA ended early — the failed step is the last card in the report")
    print("ZIP        :", zip_path)
    print("REPORT_HTML:", report_html)
    print("REPORT_PNG :", report_png)


if __name__ == "__main__":
    main()
