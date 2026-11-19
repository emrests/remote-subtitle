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


def test_ocr_reports_line_count():
    img = Image.new("RGB", (1200, 300), (20, 20, 20))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype("C:/Windows/Fonts/georgia.ttf", 40)
    d.text((300, 100), "We can't go back the way we came.", font=f, fill="white")
    d.text((300, 160), "Let's try this way.", font=f, fill="white")
    text = asyncio.run(ocr(make_ocr(), Shot(img)))
    assert text.lines == 2 and text.box[3] >= 90


def test_name_color_read_from_pixels():
    import time
    from types import SimpleNamespace as NS
    from PIL import Image, ImageDraw
    from rsub.ocr import _Frame, name_colors
    img = Image.new("RGB", (400, 40), (10, 10, 10))
    d = ImageDraw.Draw(img)
    d.rectangle([5, 10, 80, 30], fill=(214, 140, 230))  # "Stranger:" pembe-mor
    d.rectangle([90, 10, 200, 30], fill=(240, 240, 240))  # replik beyaz
    r = lambda x, w: NS(x=x, y=5, width=w, height=30)
    line = NS(words=[NS(text="Stranger:", bounding_rect=r(0, 85)), NS(text="Okay...", bounding_rect=r(88, 115))])
    t = time.perf_counter()
    got = name_colors(_Frame(img), [line])
    assert got == {"Stranger": "#d68ce6"} and time.perf_counter() - t < 0.01
    assert name_colors(_Frame(img), [NS(words=[NS(text="Okay...", bounding_rect=r(88, 115))])]) == {}


def test_stray_hud_text_does_not_stretch_box():
    # bölgenin üstündeki arayüz sayısı kutuyu oraya kadar uzatıyordu: tek satır çeviri 3 satırlık kutuda kalıyordu
    for stray, x, y in (("47", 60, 20), ("$1,250", 40, 30), ("ffi", 900, 30)):
        img = Image.new("RGB", (1200, 324), (40, 50, 60))
        d = ImageDraw.Draw(img)
        d.text((350, 250), "Where the hell were you?", font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 40), fill="white")
        d.text((x, y), stray, font=ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 28), fill="white")
        text = asyncio.run(ocr(make_ocr(), Shot(img)))
        assert text == "Where the hell were you?" and text.lines == 1, stray
        assert text.box[1] >= 240 and text.box[3] <= 60, (stray, text.box)


def test_subtitle_lines_keeps_adjacent_lines_drops_far_ones():
    from types import SimpleNamespace as NS
    from rsub.ocr import subtitle_lines
    line = lambda text, y, h=40: NS(text=text, words=[NS(text=text, bounding_rect=NS(x=0, y=y, width=100, height=h))])
    name, a, b, hud = line("Lenny:", 140), line("We can't go back the way we came.", 190), line("Let's go.", 245), line("47", 0, 28)
    assert [l.text for l in subtitle_lines([b, hud, a, name])] == ["Lenny:", a.text, b.text]
    assert subtitle_lines([]) == [] and subtitle_lines([hud]) == [hud]
