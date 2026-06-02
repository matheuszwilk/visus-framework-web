"""visus.web.vision — optional OCR + image-matching plugin (requires [vision] extra)."""

from visus.web.vision.imaging import Match, find_all_images, find_image
from visus.web.vision.ocr import read_text, solve_captcha

__all__ = ["Match", "find_all_images", "find_image", "read_text", "solve_captcha"]
