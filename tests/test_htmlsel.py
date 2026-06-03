"""Unit tests for the pasted-element selector translator (pure, no browser)."""

from __future__ import annotations

from visus.web.api._htmlsel import _css_ident_escape, candidates, parse, translate

PASSWORD = '<input id="password" type="password" name="pwd">'
SEARCH = (
    '<input class="md-search__input" name="query" aria-label="Search" placeholder="Search" '
    'data-md-component="search-query" type="text">'
)
TAILWIND = (
    '<input class="flex w-full file:border-0 focus:ring-2 pr-[88px]" placeholder="Your User Name" '
    'type="text" value="" name="email">'
)
BUTTON = '<button class="btn primary" data-action="save">Save</button>'


def test_parse_extracts_tag_attrs_text() -> None:
    tag, attrs, text = parse(BUTTON)
    assert tag == "button"
    assert attrs["data-action"] == "save"
    assert attrs["class"] == "btn primary"
    assert text == "Save"


def test_css_ident_escape_tailwind() -> None:
    assert _css_ident_escape("file:border-0") == r"file\:border-0"
    assert _css_ident_escape("pr-[88px]") == r"pr-\[88px\]"
    assert _css_ident_escape("w-full") == "w-full"


def test_candidates_prefer_id() -> None:
    css = [c["css"] for c in candidates("input", parse(PASSWORD)[1], "") if "css" in c]
    assert css[0] == "#password"
    assert 'input[name="pwd"]' in css


def test_candidates_search_input_css_first() -> None:
    tag, attrs, text = parse(SEARCH)
    css = [c["css"] for c in candidates(tag, attrs, text) if "css" in c]
    assert css[0] == 'input[name="query"]'
    assert 'input[data-md-component="search-query"]' in css
    assert '[aria-label="Search"]' in css
    assert '[placeholder="Search"]' in css
    assert "input.md-search__input" in css


def test_candidates_tailwind_escapes_classes() -> None:
    tag, attrs, text = parse(TAILWIND)
    css = [c["css"] for c in candidates(tag, attrs, text) if "css" in c]
    assert css[0] == 'input[name="email"]'
    class_sel = next(c for c in css if c.startswith("input.flex"))
    assert r"file\:border-0" in class_sel
    assert r"pr-\[88px\]" in class_sel


def test_translate_returns_all_formats() -> None:
    r = translate(PASSWORD)
    assert r["id"] == "#password"
    assert r["css"] == "#password"
    assert r["xpath"] == '//input[@name="pwd"]'
    assert r["name"] == "pwd"

    r2 = translate(TAILWIND)
    assert r2["css"] == 'input[name="email"]'
    assert r2["xpath"] == '//input[@name="email"]'
    assert r2["id"] is None
    assert isinstance(r2["class"], str) and r2["class"].startswith("input.flex")


def test_translate_id_with_special_chars_uses_attr_selector() -> None:
    r = translate('<div id="user:name"></div>')
    assert r["id"] == '[id="user:name"]'  # not #user:name (invalid CSS)
    assert r["css"] == '[id="user:name"]'


def test_candidates_no_attrs_falls_back_to_tag() -> None:
    assert candidates("span", {}, "") == [{"css": "span"}]


def test_combined_css_needs_two_identifying_attrs() -> None:
    from visus.web.api._htmlsel import _combined_css

    assert _combined_css("input", {"name": "x"}) == ""  # only one key → no combined selector
    assert _combined_css("a", {"href": "/x", "role": "button"}) == 'a[role="button"][href="/x"]'


def test_xq_handles_quotes() -> None:
    from visus.web.api._htmlsel import _xq

    assert _xq("plain") == '"plain"'
    assert _xq('has"double') == "'has\"double'"  # fall back to single quotes
    assert _xq("a\"b'c").startswith("concat(")  # both quotes → concat()


def test_text_candidate_for_buttons() -> None:
    cands = candidates("button", {"data-action": "save"}, "Save")
    assert {"xpath": '//button[normalize-space()="Save"]'} in cands
