"""Real-browser tests for the pasted-element ("Copy element") smart locator."""

from __future__ import annotations

import pytest


@pytest.fixture
def page(browser, base_url):  # type: ignore[no-untyped-def]
    p = browser.new_page()
    p.goto(f"{base_url}/smartsel.html")
    return p


@pytest.mark.browser
def test_smart_locator_by_id(page) -> None:  # type: ignore[no-untyped-def]
    page.locator('<input id="password" type="password" name="pwd">').fill("secret")
    assert page.locator("#r").text_content() == "pwd=secret"


@pytest.mark.browser
def test_smart_locator_by_name_and_aria(page) -> None:  # type: ignore[no-untyped-def]
    snippet = '<input name="query" aria-label="Search" placeholder="Search" type="text">'
    page.locator(snippet).fill("hello")
    assert page.locator("#r").text_content() == "query=hello"


@pytest.mark.browser
def test_smart_locator_tailwind_classes(page) -> None:  # type: ignore[no-untyped-def]
    snippet = (
        '<input class="flex w-full file:border-0 focus:ring-2 pr-[88px]" '
        'placeholder="Your User Name" type="text" value="" name="email">'
    )
    page.locator(snippet).fill("ada")
    assert page.locator("#r").text_content() == "email=ada"


@pytest.mark.browser
def test_smart_locator_button_click(page) -> None:  # type: ignore[no-untyped-def]
    page.locator(
        '<button class="btn primary" data-action="save" id="saveBtn">Save</button>'
    ).click()
    assert page.locator("#r").text_content() == "saved"


@pytest.mark.browser
def test_smart_locator_is_fault_tolerant_to_stale_id(page) -> None:  # type: ignore[no-untyped-def]
    # the pasted id no longer exists, but name="email" still does → it falls through and works
    page.locator('<input id="ghost-id-123" name="email" type="text">').fill("z")
    assert page.locator("#r").text_content() == "email=z"
