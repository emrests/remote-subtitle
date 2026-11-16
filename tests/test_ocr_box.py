import asyncio

from PIL import Image, ImageDraw, ImageFont

from rsub.ocr import make_ocr, ocr


class Shot:
    def __init__(self, img):
        self.width, self.height = img.size
        self.bgra = img.convert("RGBA").tobytes("raw", "BGRA")


def test_ocr_returns_text_box():
    img = Image.new("RGB", (1200, 300), (20, 20, 20))
    ImageDraw.Draw(img).text((500, 180), "Help me now!", font=ImageFont.truetype("C:/Windows/Fonts/georgia.ttf", 40), fill="white")
    text = asyncio.run(ocr(make_ocr(), Shot(img)))
    assert text == "Help me now!"
    x, y, w, h = text.box
    assert 480 <= x <= 520 and 170 <= y <= 200 and 200 <= w <= 320 and 25 <= h <= 60
