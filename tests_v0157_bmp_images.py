"""Regression tests for BMP intake and source-preserving image previews."""
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from petrolab.services.image_service import (
    ImagePayload,
    SUPPORTED_IMAGE_SUFFIXES,
    _write_image_file,
    image_preview_bytes,
)
from petrolab.ui.universal_intake import _IMAGE_SUFFIXES, _KIND_IMAGE, _guessed_kind


def _bmp_bytes(size: tuple[int, int] = (7, 5)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (120, 80, 40)).save(buffer, format="BMP")
    return buffer.getvalue()


class BmpImageRegressionTests(unittest.TestCase):
    def test_bmp_is_recognized_as_an_image_everywhere(self) -> None:
        self.assertIn(".bmp", SUPPORTED_IMAGE_SUFFIXES)
        self.assertIn(".bmp", _IMAGE_SUFFIXES)
        self.assertEqual(_guessed_kind("thin-section.BMP"), _KIND_IMAGE)

    def test_bmp_preview_is_png_without_changing_source_bytes(self) -> None:
        source = _bmp_bytes()
        payload = ImagePayload("scan.bmp", source)

        preview = image_preview_bytes(payload)

        self.assertEqual(source[:2], b"BM")
        self.assertTrue(preview.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(payload.data, source)
        with Image.open(io.BytesIO(preview)) as opened:
            self.assertEqual(opened.format, "PNG")
            self.assertEqual(opened.size, (7, 5))

    def test_stored_bmp_remains_byte_for_byte_original(self) -> None:
        source = _bmp_bytes((4, 3))
        payload = ImagePayload("microscope.BMP", source)
        with tempfile.TemporaryDirectory(prefix="petrolab_bmp_") as tmp:
            path = _write_image_file(Path(tmp), payload)
            self.assertEqual(path.suffix, ".bmp")
            self.assertEqual(path.read_bytes(), source)

    def test_fake_bmp_is_rejected_before_preview(self) -> None:
        with self.assertRaises(ValueError):
            image_preview_bytes(ImagePayload("broken.bmp", b"not a bitmap"))


if __name__ == "__main__":
    unittest.main()
