"""tests/test_mcp_list_fields.py — Real-browser tests for the field-enumeration MCP tools.

These drive the actual tool functions (browser_list_fields / browser_clear_highlights,
imported from visus.web.mcp.server) against the local fixture HTTP server. They
require a real headless Chrome browser.

Run subset:
    uv run pytest tests/test_mcp_list_fields.py -v --no-cov -m browser
"""

from __future__ import annotations

import os

import pytest

# Force headless before the server module is imported (session reads env at page-open time)
os.environ["VISUS_WEB_HEADLESS"] = "1"


@pytest.fixture()
def srv(base_url: str):  # type: ignore[no-untyped-def]
    """Fresh session + (server_module, base_url) pair for each test."""
    from visus.web.mcp import server

    server._session.close()  # ensure clean slate
    yield server, base_url
    server._session.close()


@pytest.mark.browser
def test_list_fields_returns_dicts_with_kinds_and_locators(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/fields.html")
    fields = server.browser_list_fields(include_hidden=True)

    assert isinstance(fields, list)
    assert len(fields) > 0
    # Each entry is a plain dict (Field.to_dict()) carrying re-resolution metadata.
    for f in fields:
        assert isinstance(f, dict)
        assert "kind" in f and "locator" in f and "frame" in f and "deep" in f

    by_locator = {f["locator"]: f for f in fields}

    # Top-level input.
    assert "#topinput" in by_locator
    assert by_locator["#topinput"]["kind"] == "input"
    assert by_locator["#topinput"]["frame"] == []

    # Same-origin iframe field carries its frame chain.
    assert "#iframeinput" in by_locator
    assert by_locator["#iframeinput"]["frame"] == ["#f1"]

    # Open shadow-DOM fields are flagged deep for re-resolution.
    assert "#shadowbtn" in by_locator
    assert by_locator["#shadowbtn"]["kind"] == "button"
    assert by_locator["#shadowbtn"]["deep"] is True
    assert by_locator["#shadowinput"]["deep"] is True


@pytest.mark.browser
def test_list_fields_kind_filter_narrows_results(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/fields.html")

    all_fields = server.browser_list_fields(include_hidden=True)
    all_kinds = {f["kind"] for f in all_fields}
    # The fixture has both inputs and a button, so an unfiltered list spans >1 kind.
    assert {"input", "button"}.issubset(all_kinds)

    buttons = server.browser_list_fields(kind="button", include_hidden=True)
    assert len(buttons) > 0
    assert all(f["kind"] == "button" for f in buttons)
    # Filtering to a single kind must drop the other kinds.
    assert len(buttons) < len(all_fields)

    # Comma-separated multi-kind filter.
    btn_input = server.browser_list_fields(kind="button,input", include_hidden=True)
    assert {f["kind"] for f in btn_input} <= {"button", "input"}
    assert all(f["kind"] in {"button", "input"} for f in btn_input)
    assert len(btn_input) >= len(buttons)


@pytest.mark.browser
def test_clear_highlights_returns_cleared(srv):  # type: ignore[no-untyped-def]
    server, base_url = srv
    server.browser_navigate(f"{base_url}/fields.html")
    # Drawing the overlay (headless no-op) then clearing must not raise.
    server.browser_list_fields(highlight=True)
    assert server.browser_clear_highlights() == "cleared"
