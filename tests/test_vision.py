"""Standalone OCR + image-match tests (no browser required, fully deterministic)."""

from __future__ import annotations

import base64
import io

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from visus.web.vision import Match, find_all_images, find_image, read_text, solve_captcha


def _text_img(text: str, size: tuple[int, int] = (600, 130)) -> Image.Image:
    """Render text at 60px on a white background — wide enough for RapidOCR."""
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=60)
    d.text((20, 20), text, fill="black", font=font)
    return img


def _norm(s: str) -> str:
    return "".join(ch for ch in s.upper() if ch.isalnum())


# ---------------------------------------------------------------------------
# OCR tests
# ---------------------------------------------------------------------------


def test_read_text_clear() -> None:
    result = read_text(_text_img("HELLOWORLD"))
    print(f"[OCR] HELLOWORLD -> {result!r}")
    assert _norm(result) == "HELLOWORLD"


def test_solve_captcha_text() -> None:
    result = solve_captcha(_text_img("VISUS"))
    print(f"[OCR] VISUS -> {result!r}")
    assert _norm(result) == "VISUS"


def test_read_text_accepts_bytes_and_base64() -> None:
    buf = io.BytesIO()
    _text_img("ABCDEF").save(buf, format="PNG")
    raw = buf.getvalue()
    r_bytes = read_text(raw)
    r_b64 = read_text(base64.b64encode(raw).decode())
    print(f"[OCR] ABCDEF bytes -> {r_bytes!r}, b64 -> {r_b64!r}")
    assert _norm(r_bytes) == "ABCDEF"
    assert _norm(r_b64) == "ABCDEF"


# ---------------------------------------------------------------------------
# Image-matching helpers
# ---------------------------------------------------------------------------


def _make_patterned_needle(size: int = 40) -> np.ndarray:
    """Non-uniform 40×40 needle: white border + red inner block.

    TM_CCOEFF_NORMED requires internal variance in the needle; a solid-colour
    template has zero variance and the OpenCV normalisation collapses to 1.0
    everywhere.  This helper creates a needle with two distinct grey values so
    the correlation is well-defined and the match is exact.
    """
    n = np.full((size, size, 3), 255, np.uint8)  # white background
    n[8:-8, 8:-8, :] = 0  # black inner square
    n[8:-8, 8:-8, 0] = 200  # tint red so it is visually distinct
    return n


def _haystack_with_needle(
    positions: list[tuple[int, int]],
) -> tuple[np.ndarray, np.ndarray]:
    """Build a 300×300 white canvas with patterned 40×40 blocks at each position."""
    hay = np.full((300, 300, 3), 255, np.uint8)
    needle = _make_patterned_needle()
    for x, y in positions:
        hay[y : y + 40, x : x + 40] = needle
    return hay, needle


# ---------------------------------------------------------------------------
# Image-matching tests
# ---------------------------------------------------------------------------


def test_find_image_locates_template() -> None:
    hay, needle = _haystack_with_needle([(100, 80)])
    m = find_image(hay, needle, confidence=0.9)
    assert m is not None
    assert abs(m.x - 100) <= 2 and abs(m.y - 80) <= 2
    assert m.confidence > 0.95
    assert m.center_x == m.x + 20


def test_find_image_absent_returns_none() -> None:
    """A patterned needle not present in the haystack returns None.

    A SOLID-colour needle must NOT be used here: TM_CCOEFF_NORMED computes
    normalised cross-correlation, and a constant template (zero variance) causes
    OpenCV to return 1.0 everywhere (0/0 → 1).  This test uses a patterned
    needle (border + inner block) so the correlation is well-defined and truly
    absent from the plain white haystack.
    """
    hay = np.full((100, 100, 3), 255, np.uint8)
    # Patterned needle: black border + red inner square — not present on white canvas
    needle = np.zeros((20, 20, 3), np.uint8)
    needle[5:15, 5:15, 0] = 200  # inner 10×10 is dark-red; rest is black
    assert find_image(hay, needle, confidence=0.9) is None


def test_find_all_images() -> None:
    hay, needle = _haystack_with_needle([(20, 20), (200, 50), (120, 220)])
    matches = find_all_images(hay, needle, confidence=0.9)
    assert len(matches) == 3
    assert all(isinstance(m, Match) for m in matches)


def test_match_center_properties() -> None:
    m = Match(x=100, y=80, width=40, height=40, confidence=0.99)
    assert m.center_x == 120
    assert m.center_y == 100


def test_find_image_needle_larger_than_haystack_returns_none() -> None:
    """When needle > haystack, find_image returns None immediately."""
    hay = np.full((10, 10, 3), 255, np.uint8)
    needle = np.full((50, 50, 3), 0, np.uint8)
    assert find_image(hay, needle) is None


def test_find_all_images_needle_larger_than_haystack_returns_empty() -> None:
    hay = np.full((10, 10, 3), 255, np.uint8)
    needle = np.full((50, 50, 3), 0, np.uint8)
    assert find_all_images(hay, needle) == []


def test_read_text_accepts_pil_image() -> None:
    img = _text_img("VISUS")
    r = read_text(img)
    assert _norm(r) == "VISUS"


def test_read_text_accepts_ndarray() -> None:
    import numpy as np

    img = _text_img("ABCDEF")
    arr = np.array(img)
    r = read_text(arr)
    assert _norm(r) == "ABCDEF"


def test_read_text_empty_image_returns_empty_string() -> None:
    """Blank white image has no text — should return empty string, not raise."""
    img = Image.new("RGB", (200, 60), "white")
    result = read_text(img)
    assert isinstance(result, str)


def test_loader_type_error() -> None:
    from visus.web.vision._images import _to_ndarray

    with pytest.raises(TypeError, match="unsupported image type"):
        _to_ndarray(12345)  # type: ignore[arg-type]


def test_loader_invalid_base64() -> None:
    from visus.web.vision._images import _to_ndarray

    with pytest.raises(ValueError, match="valid base64"):
        _to_ndarray("this-is-not-a-file-and-not-base64!!!")
