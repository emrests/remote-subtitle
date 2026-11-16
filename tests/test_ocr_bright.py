import asyncio
import random

from PIL import Image, ImageDraw, ImageFont

from rsub.ocr import make_ocr, ocr, read_best


class Shot:
    def __init__(self, img):
        self.width, self.height = img.size
        self.rgb = img.convert("RGB").tobytes()
        self.size = img.size
        self.bgra = img.convert("RGBA").tobytes("raw", "BGRA")


def objective_on_snow():
    """RDR2 görev yazısı gibi: kutusuz, koyu kenarlıklı beyaz+sarı yazı, açık renkli dokulu kar zemini."""
    rnd = random.Random(1)
    img = Image.new("RGB", (470, 130))
    px = img.load()
    for y in range(130):
        for x in range(470):
            v = 150 + int(30 * ((x + y) % 23) / 23) + rnd.randint(-15, 15)
            px[x, y] = (v, v + 3, v + 6)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 30)
    d.text((70, 50), "Get to the", font=f, fill=(245, 245, 245), stroke_width=2, stroke_fill=(30, 30, 30))
    d.text((228, 50), "cliff edge", font=f, fill=(247, 238, 150), stroke_width=2, stroke_fill=(30, 30, 30))
    return img


def test_bright_text_without_box_is_read():
    shot = Shot(objective_on_snow())
    text = asyncio.run(read_best(make_ocr(), shot, set()))
    assert str(text) == "Get to the cliff edge" and text.box is not None
    x, y, w, h = text.box
    assert 50 <= x <= 90 and 35 <= y <= 70 and w > 250  # kutu orijinal ölçekte (2x değil)


def test_short_garbage_triggers_second_pass(monkeypatch):
    # gerçek RDR2 karesi: normal okuma "ffi" (düzeltmeyle "fri", puan 1.0) — tek kelimelik çöp puanı kandırıyordu
    from rsub import ocr as ocr_mod
    from rsub.ocr import OcrText

    def mk(s, box):
        t = OcrText(s)
        t.box, t.lines = box, 1
        return t
    results = iter([mk("ffi", (289, 59, 34, 32)), mk("Get to the cliff edge", (140, 100, 640, 60))])

    async def fake(engine, shot, by_color=False):
        return next(results)
    monkeypatch.setattr(ocr_mod, "ocr", fake)
    out = asyncio.run(read_best(None, Shot(objective_on_snow()), set()))
    assert str(out) == "Get to the cliff edge" and out.box == (70, 50, 320, 30)


def test_normal_subtitle_single_pass(monkeypatch):
    from rsub import ocr as ocr_mod
    from rsub.ocr import OcrText
    calls = []

    async def fake(engine, shot, by_color=False):
        calls.append(1)
        t = OcrText("We got this. We're safe.")
        t.box, t.lines = (1, 1, 10, 10), 1
        return t
    monkeypatch.setattr(ocr_mod, "ocr", fake)
    asyncio.run(read_best(None, Shot(objective_on_snow()), set()))
    assert len(calls) == 1
