"""Load any image input into a numpy RGB array (engine-independent)."""

from __future__ import annotations

import base64
import binascii
import io
import os
from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image

ImageInput = Union[str, Path, bytes, bytearray, "np.ndarray", Image.Image]


def _to_ndarray(image: ImageInput) -> "np.ndarray":
    if isinstance(image, np.ndarray):
        return image
    if isinstance(image, Image.Image):
        return np.array(image.convert("RGB"))
    if isinstance(image, (bytes, bytearray)):
        return np.array(Image.open(io.BytesIO(bytes(image))).convert("RGB"))
    if isinstance(image, Path):
        return np.array(Image.open(image).convert("RGB"))
    if isinstance(image, str):
        if os.path.exists(image):
            return np.array(Image.open(image).convert("RGB"))
        try:
            raw = base64.b64decode(image, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("string image is neither an existing path nor valid base64") from exc
        return np.array(Image.open(io.BytesIO(raw)).convert("RGB"))
    raise TypeError(f"unsupported image type: {type(image)!r}")


def _to_gray(image: ImageInput) -> "np.ndarray":
    import cv2

    return cv2.cvtColor(_to_ndarray(image), cv2.COLOR_RGB2GRAY)
