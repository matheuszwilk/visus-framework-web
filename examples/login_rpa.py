"""Login RPA on the public practice site, recorded → HTML report.

Drives https://practicetestautomation.com/practice-test-login/ (user: student /
pass: Password123) and showcases the field enumerator: it lists the page's
interactive fields and acts on them BY INDEX (page.field(n)) as well as by stable
selector / role — then verifies the login through a real cross-page navigation.
The observability HTML report is rendered even when a step FAILS.

Run: uv run python examples/login_rpa.py    (ENGINE: edge | chrome | firefox)
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

ENGINE = "edge"  # which browser: "chrome" | "edge" | "firefox" | "edge_ie"
HEADLESS = False  # watch the browser drive; set True for CI/headless runs


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="visus-login-"))
    zip_path = work / "run.zip"
    report_html = work / "report.html"
    report_png = work / "report.png"

    rpa_error: Exception | None = None
    # report=... renders report.html on the way out even if a step raises.
    try:
        with tracing.record(str(zip_path), report=str(report_html)):
            with launch(ENGINE, headless=HEADLESS) as browser:
                page = browser.new_page()

                # 1) abrir a página de login
                page.goto(LOGIN_URL)
                
                if page.get_by_role("link", name="Agree").count() > 0:                                                                          
                    expect(page.get_by_role("heading", name="WARNING")).to_be_visible()                                                         
                    page.get_by_role("link", name="Agree").first().click()   

                # 2) enumerar os campos e localizar usuário/senha pelo seletor estável
                fields = page.list_fields()
                by_loc = {f.locator: f for f in fields}
                expect(page.locator("#username")).to_be_visible()
                expect(page.locator("#password")).to_be_visible()

                # 3) preencher — agir POR ÍNDICE (page.field(n), a novidade da API)
                page.field(by_loc["#username"].index).fill(USERNAME)
                page.field(by_loc["#password"].index).fill(PASSWORD)

                # 4) enviar — locator semântico por role
                page.get_by_role("button", name="Submit").click()

                # 5) validar login: expect() com auto-retry atravessa a navegação real
                expect(page.get_by_role("heading", name="Logged In Successfully")).to_be_visible()
                assert "logged-in-successfully" in page.url
                print("login OK:", page.get_by_text("Congratulations").first().text_content())

                # 6) logout — locator semântico por role(link)
                page.get_by_role("link", name="Log out").click()
                expect(page.get_by_role("button", name="Submit")).to_be_visible()

    except (errors.VisusWebError, AssertionError) as exc:
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
