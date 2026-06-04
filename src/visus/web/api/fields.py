"""The :class:`Field` descriptor returned by :meth:`Page.list_fields`.

A ``Field`` mirrors one entry of the JS engine's ``window.__visus.listFields()``
output: a framework-agnostic, RPA-relevant interactive element (input, button,
link, select, checkbox/radio, custom dropdown, contenteditable) located across the
main document, open Shadow DOM, and same-origin iframes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Field:
    """A single enumerated interactive field on the current page."""

    index: int
    kind: str
    tag: str
    type: str | None
    role: str | None
    name: str
    label: str | None
    placeholder: str | None
    value: str | None
    checked: bool | None
    disabled: bool
    visible: bool
    frame: list[str]
    shadow: bool
    locator: str
    locator_kind: str
    css: str = ""
    xpath: str = ""
    code: str = ""
    deep: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return a plain ``dict`` of the field (for JSON / MCP output)."""
        return asdict(self)
