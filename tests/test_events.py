"""Unit tests for api/events.py (no browser required)."""

from dataclasses import FrozenInstanceError

import pytest

from visus.web.api.events import Dialog, Download, _ValueHolder
from visus.web.errors import VisusWebError


class TestValueHolder:
    def test_raises_before_set(self):
        h = _ValueHolder()
        with pytest.raises(VisusWebError, match="not available until the block completes"):
            _ = h.value

    def test_returns_value_after_set(self):
        h = _ValueHolder()
        h._set(42)
        assert h.value == 42

    def test_set_with_none(self):
        h = _ValueHolder()
        h._set(None)
        assert h.value is None

    def test_set_with_object(self):
        h = _ValueHolder()
        sentinel = object()
        h._set(sentinel)
        assert h.value is sentinel


class TestDialog:
    def test_fields(self):
        d = Dialog(message="hello", type="alert")
        assert d.message == "hello"
        assert d.type == "alert"

    def test_frozen(self):
        d = Dialog(message="x", type="dialog")
        with pytest.raises(FrozenInstanceError):
            d.message = "y"  # type: ignore[misc]

    def test_equality(self):
        assert Dialog("a", "b") == Dialog("a", "b")
        assert Dialog("a", "b") != Dialog("a", "c")


class TestDownload:
    def test_fields(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("hello")
        d = Download(path=str(src), suggested_filename="src.txt")
        assert d.path == str(src)
        assert d.suggested_filename == "src.txt"

    def test_save_as_copies_file(self, tmp_path):
        src = tmp_path / "source.txt"
        src.write_text("hello download")
        dst = tmp_path / "dest" / "saved.txt"
        d = Download(path=str(src), suggested_filename="source.txt")
        d.save_as(str(dst))
        assert dst.read_text() == "hello download"

    def test_save_as_overwrites_existing(self, tmp_path):
        src = tmp_path / "source.txt"
        src.write_text("new content")
        dst = tmp_path / "existing.txt"
        dst.write_text("old content")
        d = Download(path=str(src), suggested_filename="source.txt")
        d.save_as(str(dst))
        assert dst.read_text() == "new content"
