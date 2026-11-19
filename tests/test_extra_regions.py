"""Ek çeviri bölgeleri: profil, zemin rengi, altyazı önceliği, PC/TV kutuları."""
import asyncio
import copy

from PIL import Image, ImageDraw

from rsub import layout, pipeline, store, web
from rsub.ocr import OcrText
from rsub.pipeline import Extra, Runtime, extra_key

P = {"name": "T", "glossary": {}, "speakers": {}, "style": {"nameColor": "#ffd166"}, "source": "x",
     "region": [0, 0.7, 1, 0.3], "extraRegions": [{"name": "Sağ üst", "region": [0.7, 0, 0.3, 0.2]}]}


def test_profile_keeps_valid_extra_regions_only():
    p = store.load_profile("A")
    assert p["extraRegions"] == []
    p["extraRegions"] = [{"name": "Sağ alt", "region": [0.7, 0.8, 0.3, 0.2]}, {"name": 5, "region": [0, 0, 1, 1]},
                         {"name": "bozuk", "region": [1, 2]}, "x"]
    store.save_profile(p)
    assert store.load_profile("A")["extraRegions"] == [{"name": "Sağ alt", "region": [0.7, 0.8, 0.3, 0.2]}]


def test_edge_color_solid_vs_scene():
    img = Image.new("RGB", (200, 50), (30, 60, 120))
    ImageDraw.Draw(img).text((20, 15), "Quest updated", fill="white")  # yazı kenara değmez
    assert layout.edge_color(img) == "#1e3c78" and layout.ink("#1e3c78") == "#ffffff"
    noisy = Image.effect_noise((200, 50), 120).convert("RGB")
    assert layout.edge_color(noisy) is None
    assert layout.ink("#f0f0f0") == "#000000"


def test_extra_waits_for_subtitle_translation(monkeypatch):
    order = []
    monkeypatch.setattr(pipeline, "target_rect", lambda src: (0, 0, 100, 100))
    monkeypatch.setattr(pipeline, "grab", lambda sct, box: None)

    async def fake_ocr(engine, shot, known=None, by_color=False):
        out = OcrText("Quest updated")
        out.box, out.lines = (5, 5, 50, 10), 1
        return out
    monkeypatch.setattr(pipeline, "ocr", fake_ocr)
    rt = Runtime(settings={"model": "m", "running": True}, profile=copy.deepcopy(P), emit=lambda m: None)
    rt.engine = object()

    def tr(en):
        order.append(("extra", rt.translating))
        return "Görev güncellendi"

    async def go():
        for _ in range(3):  # sabitlenmesi için 3 kare
            await pipeline._extras_frame(rt, None, lambda en: "x")
        rt.translating = True  # altyazı çevriliyor
        task = asyncio.create_task(pipeline._extras_frame(rt, None, tr))
        rt.extras[extra_key(P["extraRegions"][0])].state["sent"] = ""  # yeni satır gibi
        await asyncio.sleep(0.2)
        order.append(("sub done", None))
        rt.translating = False
        await task
    asyncio.run(go())
    ex = rt.extras[extra_key(P["extraRegions"][0])]
    assert ex.lines[0]["tr"] == "Görev güncellendi" and ex.box == (5, 5, 50, 10)
    assert order == [("sub done", None), ("extra", False)]  # altyazı bitmeden ek bölge çevrilmedi


class FakeOverlay:
    def __init__(self):
        self.shown, self.hidden, self.closed = [], 0, False

    def show(self, box, img):
        self.shown.append((box, img))

    def hide(self):
        self.hidden += 1

    def close(self):
        self.closed = True


def test_sync_extras_covers_with_background_color_and_hides(monkeypatch):
    a = web.App(web.WEB_DIR, None)
    made = []
    a.make_overlay = lambda: made.append(FakeOverlay()) or made[-1]
    a.rt.settings["running"] = True
    a.rt.profile["extraRegions"] = copy.deepcopy(P["extraRegions"])
    sent = []
    monkeypatch.setattr(a, "send_displays", sent.append)
    a.displays = {object()}
    key = extra_key(P["extraRegions"][0])
    ex = Extra(lines=[{"speaker": None, "color": None, "en": "Quest updated", "tr": "Görev güncellendi"}],
               box=(100, 60, 300, 40))
    region_img = Image.new("RGB", (576, 216), (200, 30, 30))  # 1920x1080'de sağ üst bölge, düz kırmızı zemin
    a.sync_extras((0, 0, 1920, 1080), [(key, P["extraRegions"][0]["region"], ex, region_img)])
    box, pic = made[0].shown[-1]
    assert box["left"] >= 1344 and pic.getpixel((pic.width // 2, 2))[:3] == (200, 30, 30)
    assert sent[-1]["id"] == key and sent[-1]["box"]
    a.sync_extras((0, 0, 1920, 1080), [(key, P["extraRegions"][0]["region"], ex, region_img)])
    assert len(made[0].shown) == 1  # değişiklik yok: yeniden çizme
    a.rt.profile["extraRegions"] = []
    a.sync_extras(None, [])
    assert made[0].hidden and made[0].closed and sent[-1] == {"type": "cover", "id": key, "box": None}
