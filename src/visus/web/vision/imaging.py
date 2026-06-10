"""Template image matching via OpenCV."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from visus.web.vision._images import ImageInput, _to_gray

if TYPE_CHECKING:
    import numpy
    import numpy.typing as npt


@dataclass(frozen=True)
class Match:
    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2


def find_image(
    haystack: ImageInput, needle: ImageInput, *, confidence: float = 0.8
) -> Match | None:
    import cv2

    h = _to_gray(haystack)
    n = _to_gray(needle)
    if n.shape[0] > h.shape[0] or n.shape[1] > h.shape[1]:
        return None
    res = cv2.matchTemplate(h, n, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val < confidence:
        return None
    nh, nw = n.shape[:2]
    return Match(int(max_loc[0]), int(max_loc[1]), int(nw), int(nh), float(max_val))


def find_all_images(
    haystack: ImageInput, needle: ImageInput, *, confidence: float = 0.8
) -> list[Match]:
    import cv2
    import numpy as np

    h = _to_gray(haystack)
    n = _to_gray(needle)
    if n.shape[0] > h.shape[0] or n.shape[1] > h.shape[1]:
        return []
    res = cast(
        "npt.NDArray[numpy.float32]", cv2.matchTemplate(h, n, cv2.TM_CCOEFF_NORMED)
    )
    nh, nw = n.shape[:2]
    ys, xs = np.where(res >= confidence)
    candidates = sorted(
        ((int(x), int(y), float(res[y, x])) for x, y in zip(xs, ys, strict=True)),
        key=lambda c: -c[2],
    )
    accepted: list[Match] = []
    for x, y, score in candidates:
        if all(abs(x - m.x) >= nw // 2 or abs(y - m.y) >= nh // 2 for m in accepted):
            accepted.append(Match(x, y, int(nw), int(nh), score))
    return accepted
