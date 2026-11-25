"""EXIF Orientation 要在裁切和相框旋转之前把像素转到观看方向。"""

import sys
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from image_utils import apply_exif_orientation, open_image  # noqa: E402


def _image_with_orientation(size, orientation, marks, ext='.png'):
    img = Image.new('RGB', size, (10, 20, 200))
    for xy, color in marks.items():
        img.putpixel(xy, color)
    exif = img.getexif()
    exif[0x0112] = orientation
    buf = BytesIO()
    fmt = 'PNG' if ext == '.png' else 'JPEG'
    img.save(buf, format=fmt, exif=exif.tobytes())
    buf.seek(0)
    return buf


class ExifOrientationTest(unittest.TestCase):
    def test_orientation_8_becomes_portrait(self):
        # 索尼 A6000 竖拍：像素横着存，Orientation 8，观看时逆时针 90°
        stored = (40, 20)
        red = (255, 0, 0)
        buf = _image_with_orientation(stored, 8, {(0, 0): red})
        out = open_image(buf, '.png')

        self.assertEqual(out.size, (20, 40))
        self.assertEqual(out.getexif().get(0x0112, 1), 1)
        self.assertEqual(out.getpixel((0, 39)), red)

    def test_orientation_6_swaps_axes(self):
        green = (0, 255, 0)
        buf = _image_with_orientation((40, 20), 6, {(0, 0): green})
        out = open_image(buf, '.png')
        self.assertEqual(out.size, (20, 40))
        self.assertEqual(out.getpixel((19, 0)), green)

    def test_orientation_1_keeps_pixels(self):
        red = (255, 0, 0)
        buf = _image_with_orientation((30, 18), 1, {(0, 0): red})
        out = apply_exif_orientation(Image.open(buf))
        self.assertEqual(out.size, (30, 18))
        self.assertEqual(out.getpixel((0, 0)), red)

    def test_jpeg_orientation_8_swaps_size(self):
        buf = _image_with_orientation((40, 20), 8, {}, ext='.jpg')
        out = open_image(buf, '.jpg')
        self.assertEqual(out.size, (20, 40))
        self.assertEqual(out.getexif().get(0x0112, 1), 1)

    def test_missing_orientation_is_unchanged(self):
        img = Image.new('RGB', (12, 8), (1, 2, 3))
        out = apply_exif_orientation(img)
        self.assertEqual(out.size, (12, 8))
        self.assertIs(out, img)


if __name__ == '__main__':
    unittest.main()
