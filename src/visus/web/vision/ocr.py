"""Text OCR via RapidOCR (lazy singleton)."""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
from PIL import Image

from visus.web.vision._images import ImageInput, _to_ndarray

_engine = None


def _get_engine() -> object:
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    return _engine


def read_text(image: ImageInput) -> str:
    """Extract all text from an image (any format). Returns space-joined lines."""
    arr = _to_ndarray(image)
    engine = _get_engine()
    result, _ = engine(arr)  # type: ignore[operator]
    if not result:
        return ""
    return " ".join(str(line[1]) for line in result)


def _preprocess(arr: npt.NDArray[Any]) -> npt.NDArray[Any]:
    img = Image.fromarray(arr).convert("L")
    img = img.resize((img.width * 2, img.height * 2))  # upscale helps small captchas
    return np.array(img.convert("RGB"))


def solve_captcha(image: ImageInput, *, preprocess: bool = True) -> str:
    """Read a (usually distorted) text captcha. Collapses whitespace."""
    arr = _to_ndarray(image)
    if preprocess:
        arr = _preprocess(arr)
    return "".join(read_text(arr).split())
