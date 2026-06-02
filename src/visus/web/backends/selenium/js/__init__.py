"""Loads the clean-room injected JS engine (window.__visus)."""

from __future__ import annotations

from pathlib import Path

BUNDLE_JS: str = (Path(__file__).parent / "bundle.js").read_text(encoding="utf-8")
