"""Demo RPA exercising visus.web's new features under tracing, then rendering the HTML report.

Run: uv run python examples/demo_rpa.py
Produces (in a temp dir, paths printed at the end): run.zip, report.html, report.png
"""

from __future__ import annotations

import functools
import http.server
import socketserver
import tempfile
import threading
import zipfile
from pathlib import Path

from visus.web import errors, expect, launch, tracing

DEMO_HTML = """<!doctype html>
<html lang="pt"><head><meta charset="utf-8"><title>Demo Visus</title>
<style>
 body{font-family:system-ui,Segoe UI,sans-serif;max-width:680px;margin:1.5rem auto;padding:1rem;color:#181715}
 h1{color:#cc785c} .hidden{display:none} label{display:block;margin:.6rem 0 .2rem;font-weight:600}
 input,select{padding:.45rem;width:100%;box-sizing:border-box;border:1px solid #ccc;border-radius:6px}
 button{margin:.5rem .4rem .5rem 0;padding:.55rem 1rem;border:0;border-radius:6px;background:#cc785c;color:#fff;cursor:pointer}
 iframe{width:100%;height:110px;border:1px solid #ddd;border-radius:6px;margin-top:1rem}
 #status,#alvores,#enviores{color:#2a7;font-weight:600;min-height:1.2em}
</style></head>
<body>
 <h1>Cadastro Visus</h1>
 <label for="nome">Nome</label><input id="nome" type="text">
 <label for="email">Email</label><input id="email" type="email">
 <label><input type="checkbox" id="termos"> Aceito os termos</label>
 <label for="plano">Plano</label>
 <select id="plano"><option value="free">Free</option><option value="pro">Pro</option></select>

 <button id="carregar" onclick="setTimeout(function(){var d=document.getElementById('status');d.textContent='Dados carregados';d.classList.remove('hidden');},800)">Carregar dados</button>
 <div id="status" class="hidden"></div>

 <button id="preparar" onclick="window.c=(window.c||0)+1; if(window.c>=2 && !document.getElementById('alvo')){var b=document.createElement('button');b.id='alvo';b.textContent='Alvo';b.onclick=function(){document.getElementById('alvores').textContent='alvo clicado';};document.body.appendChild(b);}">Preparar</button>
 <div id="alvores"></div>

 <button id="enviar" onclick="document.getElementById('enviores').textContent='enviado';">Enviar</button>
 <div id="enviores"></div>

 <iframe id="painel" src="inner.html"></iframe>
</body></html>
"""

INNER_HTML = """<!doctype html>
<html lang="pt"><head><meta charset="utf-8"><title>Painel</title>
<style>body{font-family:system-ui;color:#181715}button{padding:.5rem 1rem;background:#cc785c;color:#fff;border:0;border-radius:6px}</style>
</head><body><p>Painel interno (iframe)</p>
<button id="confirmar" onclick="document.getElementById('r').textContent='confirmado'">Confirmar</button>
<div id="r" style="color:#2a7;font-weight:600"></div></body></html>
"""


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="visus-demo-"))
    (work / "demo.html").write_text(DEMO_HTML, encoding="utf-8")
    (work / "inner.html").write_text(INNER_HTML, encoding="utf-8")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(work))
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    httpd.daemon_threads = True
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    zip_path = work / "run.zip"

    # ---- the RPA, fully recorded ----
    with tracing.record(str(zip_path)):
        with launch(headless=False) as browser:
            page = browser.new_page()
            page.goto(f"{base}/demo.html")
            expect(page.get_by_role("heading", name="Cadastro Visus")).to_be_visible()

            page.get_by_label("Nome").fill("Ada Lovelace")
            page.get_by_label("Email").fill("ada@visus.dev")
            page.get_by_role("checkbox", name="Aceito os termos").check()
            page.get_by_label("Plano").select_option(label="Free")

            page.get_by_role("button", name="Carregar dados").click()
            expect(page.get_by_text("Dados carregados")).to_be_visible()  # auto-retry (appears @800ms)

            # inside the iframe
            page.frame_locator("#painel").get_by_role("button", name="Confirmar").click()

            # backtrack: #alvo only appears after Preparar is clicked twice
            page.get_by_role("button", name="Preparar").click()
            page.locator("#alvo").click(backtrack=True, timeout=1000)

            # a deliberate failure -> FAILED card + failure screenshot in the report
            try:
                page.get_by_role("button", name="Botao Inexistente").click(timeout=800)
            except errors.VisusWebError:
                pass

            page.get_by_role("button", name="Enviar").click()

    # ---- render the HTML report ----
    report_html = work / "report.html"
    tracing.render_report(str(zip_path), str(report_html))

    # ---- screenshot the rendered report (open it in a browser, full-page) ----
    report_png = work / "report.png"
    with launch(headless=True) as browser:
        page = browser.new_page()
        page.goto(f"{base}/report.html")
        page.screenshot(full_page=True, path=str(report_png))

    httpd.shutdown()

    # ---- summary ----
    with zipfile.ZipFile(str(zip_path)) as z:
        import json

        events = [json.loads(line) for line in z.read("events.jsonl").decode().splitlines() if line.strip()]
        shots = [n for n in z.namelist() if n.startswith("screenshots/")]
        manifest = json.loads(z.read("manifest.json"))

    print("=== RPA DEMO RESULT ===")
    print(f"actions recorded : {len(events)}")
    print(f"failures         : {manifest['counts']['failures']}")
    print(f"screenshots      : {len(shots)}")
    print(f"backtrack cycles : {sum(e['backtrack_cycles'] for e in events)}")
    print("actions:", ", ".join(f"{e['action']}{'' if e['success'] else '(FAILED)'}" for e in events))
    print("ZIP        :", zip_path)
    print("REPORT_HTML:", report_html)
    print("REPORT_PNG :", report_png)


if __name__ == "__main__":
    main()
