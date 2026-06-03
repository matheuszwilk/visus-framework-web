"""Build a resilient *smart* locator from a pasted DevTools element snippet.

When a selector is an HTML element (e.g. copied via DevTools → "Copy element"),
this derives an ordered list of candidate selectors — CSS-first, most-likely-unique
first — that the engine tries in order until one matches.  Fault-tolerant: stale or
non-matching candidates (an id that changed, a class that moved) are skipped, and a
candidate that matches a *single* element is preferred over an ambiguous one.

Example::

    page.locator('<input name="query" aria-label="Search" class="md-search__input">')
    # tries: input[name="query"] → [aria-label="Search"] → input.md-search__input → xpath…
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_SIMPLE_IDENT = re.compile(r"^[A-Za-z_-][\w-]*$")
_TEST_HOOKS = ("data-testid", "data-test", "data-test-id", "data-qa", "data-cy")


class _FirstElement(HTMLParser):
    """Capture the tag, attributes, and text of the first element in a snippet."""

    def __init__(self) -> None:
        super().__init__()
        self.tag: str | None = None
        self.attrs: dict[str, str] = {}
        self._depth = 0
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.tag is None:
            self.tag = tag
            self.attrs = {k: (v or "") for k, v in attrs}
            self._depth = 1
        elif self._depth > 0:
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._depth > 0:
            self._depth -= 1

    def handle_data(self, data: str) -> None:
        if self.tag is not None and self._depth >= 1:
            self._text.append(data)

    @property
    def text(self) -> str:
        return " ".join("".join(self._text).split())


def parse(snippet: str) -> tuple[str | None, dict[str, str], str]:
    """Return (tag, attrs, text) for the first element in *snippet*."""
    p = _FirstElement()
    p.feed(snippet)
    return p.tag, p.attrs, p.text


def _eq(value: str) -> str:
    """Escape a value for a CSS ``[attr="value"]`` selector."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _css_ident_escape(ident: str) -> str:
    """Escape a class/id identifier for use in a CSS selector.

    Handles Tailwind-style classes such as ``file:border-0`` → ``file\\:border-0``
    or ``pr-[88px]`` → ``pr-\\[88px\\]``. ``\\w`` is unicode-aware, so accented
    class names stay intact; only ASCII punctuation is backslash-escaped.
    """
    return re.sub(r"([^\w-])", r"\\\1", ident)


def _xq(value: str) -> str:
    """Render *value* as an XPath string literal (handling embedded quotes)."""
    if '"' not in value:
        return f'"{value}"'
    if "'" not in value:
        return f"'{value}'"
    parts = value.split('"')
    return "concat(" + ", '\"', ".join(f'"{p}"' for p in parts) + ")"


def candidates(tag: str, attrs: dict[str, str], text: str) -> list[dict[str, str]]:
    """Ordered candidate selectors (CSS-first, most-likely-unique first)."""
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, value: str) -> None:
        key = (kind, value)
        if value and key not in seen:
            seen.add(key)
            out.append({kind: value})

    t = tag or "*"
    classes = (attrs.get("class") or "").split()

    if attrs.get("id"):
        aid = attrs["id"]
        add("css", f"#{aid}" if _SIMPLE_IDENT.match(aid) else f'[id="{_eq(aid)}"]')
    for k in _TEST_HOOKS:
        if attrs.get(k):
            add("css", f'[{k}="{_eq(attrs[k])}"]')
    if attrs.get("name"):
        add("css", f'{t}[name="{_eq(attrs["name"])}"]')
    for k, v in attrs.items():
        if k.startswith("data-") and v and k not in _TEST_HOOKS:
            add("css", f'{t}[{k}="{_eq(v)}"]')
    if attrs.get("aria-label"):
        add("css", f'[aria-label="{_eq(attrs["aria-label"])}"]')
    if attrs.get("placeholder"):
        add("css", f'[placeholder="{_eq(attrs["placeholder"])}"]')
    if classes:
        add("css", t + "".join("." + _css_ident_escape(c) for c in classes))
    combined = _combined_css(t, attrs)
    if combined:
        add("css", combined)
    if text:
        add("xpath", f"//{t}[normalize-space()={_xq(text)}]")
    for k in ("name", "aria-label", "placeholder"):
        if attrs.get(k):
            add("xpath", f"//{t}[@{k}={_xq(attrs[k])}]")
    if attrs.get("class"):
        add("xpath", f"//{t}[@class={_xq(attrs['class'])}]")
    if not out:
        add("css", t)
    return out


def _combined_css(tag: str, attrs: dict[str, str]) -> str:
    """A tighter CSS selector combining a couple of identifying attributes."""
    keys = [k for k in ("name", "type", "role", "href", "aria-label") if attrs.get(k)]
    if len(keys) < 2:
        return ""
    return tag + "".join(f'[{k}="{_eq(attrs[k])}"]' for k in keys[:3])


def smart_step(snippet: str) -> dict[str, object]:
    """Parse a pasted element snippet into a ``smart`` locator step."""
    tag, attrs, text = parse(snippet)
    return {"kind": "smart", "tag": tag or "*", "candidates": candidates(tag or "*", attrs, text)}


def translate(snippet: str) -> dict[str, object]:
    """Translate a pasted DevTools element into id / css / xpath / class selectors.

    Returns the recommended selector in each format plus the full ordered candidate
    list (the same order the smart locator tries them in). Powers ``visus translate``
    and the ``browser_translate_element`` MCP tool.
    """
    tag, attrs, text = parse(snippet)
    t = tag or "*"
    cands = candidates(t, attrs, text)
    css = [c["css"] for c in cands if "css" in c]
    xpath = [c["xpath"] for c in cands if "xpath" in c]
    classes = (attrs.get("class") or "").split()
    aid = attrs.get("id")
    id_sel = None
    if aid:
        id_sel = f"#{aid}" if _SIMPLE_IDENT.match(aid) else f'[id="{_eq(aid)}"]'
    class_sel = t + "".join("." + _css_ident_escape(c) for c in classes) if classes else None
    return {
        "tag": t,
        "id": id_sel,
        "name": attrs.get("name"),
        "css": css[0] if css else None,
        "xpath": xpath[0] if xpath else None,
        "class": class_sel,
        "classes": classes,
        "candidates_css": css,
        "candidates_xpath": xpath,
    }
