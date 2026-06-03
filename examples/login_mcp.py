"""Login automation driven through the visus-web MCP server tools.

Same site/credentials as examples/login_rpa.py, but every step goes through the
MCP tool functions (browser_navigate / browser_snapshot / browser_fill /
browser_click / browser_wait_for / browser_get_text) — exactly the calls an LLM
agent makes against the visus-web MCP server.

Run: uv run python examples/login_mcp.py
"""

import os
import tempfile

os.environ.setdefault("VISUS_WEB_HEADLESS", "1")  # the MCP session is headless by default

from visus.web.mcp import server as mcp  # noqa: E402

URL = "https://practicetestautomation.com/practice-test-login/"


def main() -> None:
    print("NAVIGATE :", mcp.browser_navigate(URL))

    print("SNAPSHOT (what the agent sees):")
    for e in mcp.browser_snapshot():
        if e.get("name") or e["role"] in ("textbox", "button"):
            print(f"   - {e['role']:>8}: {e['name']!r}")

    # fill + submit the login form
    print("FILL user:", mcp.browser_fill("student", selector="#username"))
    print("FILL pass:", mcp.browser_fill("Password123", selector="#password"))
    print("CLICK    :", mcp.browser_click(selector="#submit"))

    # wait_for waits for a *visible* match — robust even though the success
    # heading text is duplicated in a hidden element on this page.
    print("WAIT     :", mcp.browser_wait_for(role="heading", name="Logged In Successfully"))
    print("HEADING  :", mcp.browser_get_text(selector="h1"))
    print("URL      :", mcp.browser_url())
    print("LOGOUT   :", mcp.browser_count(role="link", name="Log out"), "link(s)")

    # browser_screenshot() returns an Image to the agent; also save a copy to disk
    mcp.browser_screenshot(full_page=False)
    shot = tempfile.NamedTemporaryFile(suffix="_login.png", delete=False).name
    mcp._session.page().screenshot(path=shot)
    print("SHOT     :", shot)

    print("CLOSE    :", mcp.browser_close())


if __name__ == "__main__":
    main()
