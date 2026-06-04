import pytest

# The set of kinds the enumeration core is allowed to emit (spec section 3.3).
KINDS = {
    "input",
    "textarea",
    "select",
    "button",
    "link",
    "checkbox",
    "radio",
    "dropdown",
    "editable",
    "other",
}


@pytest.fixture
def page(browser, base_url):
    p = browser.new_page()
    p.goto(f"{base_url}/fields.html")
    return p


def _by_locator(fields):
    return {f.locator: f for f in fields}


@pytest.mark.browser
def test_default_list_fields_includes_same_origin_iframe_field(page):
    # Regression: cross-realm isVisible() used to treat iframe-realm elements as
    # hidden (el instanceof Element is false against the top realm), silently
    # dropping visible same-origin iframe fields from the DEFAULT (visible-only) list.
    fields = page.list_fields(highlight=False)
    names = {f.locator for f in fields}
    assert "#topinput" in names
    assert "#iframeinput" in names  # must appear in DEFAULT visible-only enumeration
    iframe_field = next(f for f in fields if f.locator == "#iframeinput")
    assert iframe_field.visible is True
    assert iframe_field.frame == ["#f1"]


@pytest.mark.browser
def test_shadow_dom_fields_locator_is_resolvable_via_deep(page):
    fields = page.list_fields(highlight=False, include_hidden=True)
    shadow = [f for f in fields if f.shadow]
    locs = {f.locator for f in shadow}
    assert "#shadowbtn" in locs
    assert "#shadowinput" in locs
    for f in shadow:
        assert f.deep is True
        # A plain (non-piercing) query cannot reach shadow roots...
        assert page.locator(f.locator).count() == 0
        # ...but a deep (shadow-piercing) re-resolution finds exactly the field.
        assert page.locator(f.locator, deep=f.deep).count() == 1


@pytest.mark.browser
def test_every_field_kind_is_within_the_allowed_vocabulary(page):
    # Including hidden surfaces the widest set of fields (e.g. native <option>s).
    fields = page.list_fields(highlight=False, include_hidden=True)
    assert fields, "fixture should enumerate at least one field"
    for f in fields:
        assert f.kind in KINDS, f"unexpected kind {f.kind!r} for {f.locator}"


@pytest.mark.browser
def test_kind_classification_of_varied_native_controls(page):
    fields = page.list_fields(highlight=False, include_hidden=True)
    by_loc = _by_locator(fields)
    # text-like native inputs classify as "input"
    for loc in ("#text_in", "#email_in", "#password_in", "#number_in", "#range_in", "#file_in"):
        assert by_loc[loc].kind == "input", loc
    # checkbox / radio get their own kinds (not the generic "input")
    assert by_loc["#checkbox_in"].kind == "checkbox"
    assert by_loc["#radio_in"].kind == "radio"
    # textarea, native select, real button, real link
    assert by_loc["#ta"].kind == "textarea"
    assert by_loc["#sel"].kind == "select"
    assert by_loc["#btn"].kind == "button"
    assert by_loc["#lnk"].kind == "link"


@pytest.mark.browser
def test_contenteditable_classifies_as_editable(page):
    fields = page.list_fields(highlight=False, include_hidden=True)
    editable = _by_locator(fields)["#editable_div"]
    assert editable.kind == "editable"
    assert editable.tag == "div"


@pytest.mark.browser
def test_combobox_with_haspopup_classifies_as_dropdown(page):
    fields = page.list_fields(highlight=False, include_hidden=True)
    dropdown = _by_locator(fields)["#dropdown_div"]
    assert dropdown.kind == "dropdown"
    assert dropdown.role == "combobox"


@pytest.mark.browser
def test_locator_ranking_picks_the_highest_priority_hook(page):
    # Ranking priority: id -> data-testid -> name -> aria-label -> role+name.
    fields = page.list_fields(highlight=False, include_hidden=True)
    by_loc = _by_locator(fields)

    # id wins -> locator_kind "css", locator "#id"
    css_field = by_loc["#topinput"]
    assert css_field.locator_kind == "css"
    assert css_field.locator == "#topinput"

    # data-testid only -> locator_kind "testid"
    testid_field = by_loc['[data-testid="rank-testid"]']
    assert testid_field.locator_kind == "testid"

    # name only -> locator_kind "name"
    name_field = by_loc['input[name="rank_name"]']
    assert name_field.locator_kind == "name"

    # aria-label only -> locator_kind "label"
    label_field = by_loc['[aria-label="rank-label"]']
    assert label_field.locator_kind == "label"

    # role + accessible-name only -> locator_kind "role"
    role_field = by_loc['role=button[name="rank-role-name"]']
    assert role_field.locator_kind == "role"
    assert role_field.role == "button"
    assert role_field.name == "rank-role-name"


@pytest.mark.browser
def test_include_hidden_controls_visibility_of_display_none_field(page):
    # A display:none input is dropped from the DEFAULT (visible-only) enumeration...
    visible = page.list_fields(highlight=False)
    assert "#hidden_in" not in {f.locator for f in visible}

    # ...but appears with include_hidden=True, flagged visible=False.
    everything = page.list_fields(highlight=False, include_hidden=True)
    hidden_field = _by_locator(everything)["#hidden_in"]
    assert hidden_field.visible is False


@pytest.mark.browser
def test_fields_carry_css_xpath_and_frame_aware_visus_code(page):
    fields = page.list_fields(highlight=False, include_hidden=True)
    by_loc = _by_locator(fields)

    # Top-level field: css + xpath present, code is a plain page.locator(...).
    top = by_loc["#topinput"]
    assert top.css == "#topinput"
    assert top.xpath == '//*[@id="topinput"]'
    assert top.code == 'page.locator("#topinput")'

    # Iframe field: the code MUST be frame-aware (wrapped in frame_locator) so a
    # click/fill actually reaches the element inside the iframe.
    iframe_field = by_loc["#iframeinput"]
    assert iframe_field.frame == ["#f1"]
    assert iframe_field.code == 'page.frame_locator("#f1").locator("#iframeinput")'

    # Shadow-DOM field: the code pierces the open shadow root (deep=True).
    shadow_in = by_loc["#shadowinput"]
    assert shadow_in.code == 'page.locator("#shadowinput", deep=True)'

    # A role-ranked field emits get_by_role(...) rather than locator(...).
    role_field = by_loc['role=button[name="rank-role-name"]']
    assert role_field.code == 'page.get_by_role("button", name="rank-role-name")'


@pytest.mark.browser
def test_numbered_highlight_overlay_matches_field_indices_then_clears(page):
    # Overlay nodes carry data-visus-field and are injected even in headless,
    # so we can verify the numbered badges directly via page.evaluate.
    fields = page.list_fields(highlight=True)
    assert fields, "expected visible fields to highlight"

    overlay_count = page.evaluate(
        "() => document.querySelectorAll('[data-visus-field]').length"
    )
    assert overlay_count > 0

    # The set of badge texts must equal the set of enumerated field indices.
    badge_texts = page.evaluate(
        "() => Array.prototype.slice"
        ".call(document.querySelectorAll('[data-visus-field]'))"
        ".map(e => e.textContent).filter(t => t !== '')"
    )
    assert {int(t) for t in badge_texts} == {f.index for f in fields}

    # Clearing removes every overlay node.
    page.clear_highlights()
    assert (
        page.evaluate("() => document.querySelectorAll('[data-visus-field]').length")
        == 0
    )
