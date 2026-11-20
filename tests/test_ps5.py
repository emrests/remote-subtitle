import asyncio
import copy

from PIL import Image

from rsub import pipeline, ps5
from rsub.pipeline import Runtime, run

P = {"name": "T", "source": "ps5", "region": [0.0, 0.5, 1.0, 0.5], "style": {"nameColor": "#fff"},
     "glossary": {}, "speakers": {}}


def test_crop_gives_ocr_ready_shot():
    img = Image.new("RGB", (1920, 1080), (10, 20, 30))
    img.putpixel((5, 600), (200, 100, 50))
    s = ps5.crop(img, {"left": 0, "top": 540, "width": 1920, "height": 540})
    assert (s.width, s.height) == s.size == (1920, 540)
    assert len(s.rgb) == 1920 * 540 * 3 and len(s.bgra) == 1920 * 540 * 4
    i = (60 * 1920 + 5) * 4
    assert s.bgra[i:i + 4] == bytes([50, 100, 200, 255])


class FakeStream:
    def __init__(self, img):
        self.img, self.asked, self.idle_checks, self.connected, self.error = img, [], 0, True, None

    def latest(self, host):
        self.asked.append(host)
        return self.img

    def stop_if_idle(self):
        self.idle_checks += 1


def _run(rt, t=0.3):
    try:
        asyncio.run(asyncio.wait_for(run(rt, interval=0.01), t))
    except TimeoutError:
        pass


def test_ps5_source_reads_region_of_stream_frame(monkeypatch):
    fake = FakeStream(Image.new("RGB", (1920, 1080)))
    monkeypatch.setattr(ps5, "stream", fake)
    monkeypatch.setattr(pipeline, "target_rect", lambda src: (_ for _ in ()).throw(AssertionError("pencere aranmamalı")))
    shots = []
    async def fake_ocr(engine, shot, known=None, by_color=False):
        shots.append(shot.size)
        return ""
    monkeypatch.setattr(pipeline, "ocr", fake_ocr)
    rects = []
    rt = Runtime(settings={"model": "m", "running": True, "ps5Host": "192.168.1.50"},
                 profile=copy.deepcopy(P), emit=lambda m: None)
    rt.on_frame = lambda rect, img=None: rects.append(rect)
    _run(rt)
    assert fake.asked[0] == "192.168.1.50"
    assert shots and shots[0] == (1920, 540)
    assert rects[0] == (0, 0, 1920, 1080) and rt.status["window"] is True


def test_ps5_without_frame_yet_waits(monkeypatch):
    fake = FakeStream(None)
    monkeypatch.setattr(ps5, "stream", fake)
    async def fake_ocr(*a, **k):
        raise AssertionError("kare yokken okunmamalı")
    monkeypatch.setattr(pipeline, "ocr", fake_ocr)
    rt = Runtime(settings={"model": "m", "running": True, "ps5Host": "h"}, profile=copy.deepcopy(P), emit=lambda m: None)
    _run(rt, 0.2)
    assert fake.asked and rt.status["window"] is False


def test_paused_does_not_connect_and_releases_idle(monkeypatch):
    fake = FakeStream(Image.new("RGB", (1920, 1080)))
    monkeypatch.setattr(ps5, "stream", fake)
    rt = Runtime(settings={"model": "m", "running": False, "ps5Host": "h"}, profile=copy.deepcopy(P), emit=lambda m: None)
    _run(rt, 0.5)
    assert fake.asked == [] and fake.idle_checks >= 1


def test_frozen_stream_reconnects(monkeypatch):
    """Oturum açık görünüp kare gelmiyorsa (sessiz kopma) bağlantı kapatılıp yeniden açılmalı."""
    class Rec:
        frame = object()
        def get_latest_video_frame(self):
            return self.frame
    class Sess:
        is_running = True
    class Dev:
        session = Sess()
    s = ps5.Stream()
    s.host, s._device, s._receiver = "h", Dev(), Rec()
    stopped, clock = [], [100.0]
    monkeypatch.setattr(ps5.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(s, "stop", lambda: stopped.append(1))
    s._frame_at = clock[0]
    s._receiver.frame = type("F", (), {"to_image": lambda self: "img"})()
    assert s.latest("h") == "img"          # yeni kare
    clock[0] += ps5.STALL - 1
    assert s.latest("h") == "img" and not stopped
    clock[0] += 2
    assert s.latest("h") is None and stopped  # aynı kare STALL'dan uzun: yeniden bağlan
