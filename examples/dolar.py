"""Cotação do dólar (USD → BRL) — RPA baterias-incluídas.

O Google bloqueia buscas automatizadas com CAPTCHA (a página /sorry), então este
script lê a cotação do dolarhoje.com, que é amigável a automação. A visus.web
lança o navegador, grava a execução e gera o relatório HTML automaticamente.

Rode: uv run python examples/dolar.py
"""

from visus.web import rpa

with rpa("cotacao-dolar", engine="chrome", headless=False) as page:
    page.goto("https://dolarhoje.com/")
    valor = page.locator('<input type="text" id="nacional" value="5,06" style="width: 2.3em;">').get_attribute("value")  # ex.: "5,06"
    print(f"\n>>> Cotacao do dolar (USD/BRL): R$ {valor}\n")
