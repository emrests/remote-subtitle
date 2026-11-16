import asyncio
import json
import urllib.error
import urllib.request

from websockets.asyncio.client import connect

from rsub import web


async def _idle(rt, interval=0.15):
    await asyncio.Event().wait()


def with_app(test):
    """Sunucuyu rastgele portta başlatır, test(app, port) çalıştırır, sonra kapatır."""
    def wrapper(monkeypatch):
        monkeypatch.setattr(web, "run", _idle)
        monkeypatch.setattr(web, "gpu_vram_mb", lambda: 16303)

        async def main():
            ready = asyncio.get_running_loop().create_future()
            task = asyncio.create_task(web.serve_app(port=0, ready=ready.set_result))
            app = await ready
            try:
                await test(app, app.port)
            finally:
                task.cancel()
        asyncio.run(asyncio.wait_for(main(), 10))
    wrapper.__name__ = test.__name__
    return wrapper


def _get(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, ""


async def _cmd(ws, **msg):
    msg.setdefault("id", 1)
    await ws.send(json.dumps(msg))
    while True:
        m = json.loads(await ws.recv())
        if m["type"] == "reply" and m["id"] == msg["id"]:
            return m


@with_app
async def test_static_and_state(app, port):
    status, body = await asyncio.to_thread(_get, port, "/display.html")
    assert status == 200 and "subtitle.js" in body
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        r = await _cmd(ws, cmd="get_state")
        assert r["ok"] and r["data"]["settings"]["model"] == "translategemma:12b" and r["data"]["port"] == port
        assert [m["recommended"] for m in r["data"]["models"]].count(True) == 1


@with_app
async def test_new_client_gets_style_first(app, port):
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        assert json.loads(await ws.recv())["type"] == "style"


@with_app
async def test_save_profile_broadcasts_style(app, port):
    async with connect(f"ws://127.0.0.1:{port}") as a, connect(f"ws://127.0.0.1:{port}") as b:
        p = (await _cmd(a, cmd="get_state"))["data"]["profile"]
        p["style"]["size"] = 60
        assert (await _cmd(a, id=2, cmd="save_profile", profile=p))["ok"]
        while (m := json.loads(await b.recv()))["type"] != "style" or m["style"]["size"] != 60:
            pass
        assert app.rt.profile["style"]["size"] == 60


@with_app
async def test_select_and_delete_profile(app, port):
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        await _cmd(ws, cmd="copy_profile", name="Varsayılan", newName="RDR2")
        await _cmd(ws, id=2, cmd="select_profile", name="RDR2")
        assert app.rt.profile["name"] == "RDR2" and app.rt.settings["profile"] == "RDR2"
        await _cmd(ws, id=3, cmd="delete_profile", name="RDR2")
        assert app.rt.profile["name"] == "Varsayılan"


@with_app
async def test_forbidden_from_non_local(app, port, monkeypatch=None):
    web.is_local = lambda ws: False
    try:
        async with connect(f"ws://127.0.0.1:{port}") as ws:
            r = await _cmd(ws, cmd="save_settings", settings={"model": "x"})
            assert r["ok"] is False and r["error"] == "forbidden"
    finally:
        web.is_local = web._is_local


@with_app
async def test_unknown_command(app, port):
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        r = await _cmd(ws, cmd="nope")
        assert r["ok"] is False


@with_app
async def test_unknown_path_404(app, port):
    assert (await asyncio.to_thread(_get, port, "/../rsub/store.py"))[0] == 404
    assert (await asyncio.to_thread(_get, port, "/%2e%2e/rsub/store.py"))[0] == 404
    assert (await asyncio.to_thread(_get, port, "/nope.html"))[0] == 404


@with_app
async def test_foreign_origin_forbidden(app, port):
    async with connect(f"ws://127.0.0.1:{port}", origin="http://evil.example") as ws:
        r = await _cmd(ws, cmd="snapshot", source="monitor:1")
        assert r["ok"] is False and r["error"] == "forbidden"


@with_app
async def test_own_origin_allowed(app, port):
    async with connect(f"ws://127.0.0.1:{port}", origin=f"http://127.0.0.1:{port}") as ws:
        assert (await _cmd(ws, cmd="get_state"))["ok"]


@with_app
async def test_unc_and_nul_paths_404(app, port):
    import time
    t = time.perf_counter()
    assert (await asyncio.to_thread(_get, port, "/%5C%5Cevil.invalid%5Cshare%5Ca"))[0] == 404
    assert (await asyncio.to_thread(_get, port, "/C:%5CWindows%5Cwin.ini"))[0] == 404
    assert (await asyncio.to_thread(_get, port, "/a%00b"))[0] == 404
    assert time.perf_counter() - t < 2


def test_static_rel_rejects_without_touching_disk():
    assert web.static_rel("/%5C%5Cevil%5Cshare%5Ca") is None
    assert web.static_rel("/C:%5CWindows%5Cwin.ini") is None
    assert web.static_rel("/a%00b") is None
    assert web.static_rel("/../rsub/store.py") is None
    assert web.static_rel("/") == "panel.html"
    assert web.static_rel("/display.html?bg=x") == "display.html"


def test_first_run_picks_recommended_model(monkeypatch):
    monkeypatch.setattr(web, "gpu_vram_mb", lambda: 6144)
    a = web.App(web.WEB_DIR, None)
    assert a.rt.settings["model"] == "translategemma:4b"


def test_auto_pull_once_when_model_missing(monkeypatch):
    a = web.App(web.WEB_DIR, None)
    pulls = []
    monkeypatch.setattr(a, "start_pull", pulls.append)
    a.ollama, a.models = True, set()
    a.maybe_auto_pull(); a.maybe_auto_pull()
    assert pulls == [a.rt.settings["model"]]


def test_no_auto_pull_when_installed_or_ollama_down(monkeypatch):
    a = web.App(web.WEB_DIR, None)
    pulls = []
    monkeypatch.setattr(a, "start_pull", pulls.append)
    a.ollama, a.models = False, set()
    a.maybe_auto_pull()
    a.ollama, a.models = True, {a.rt.settings["model"]}
    a.maybe_auto_pull()
    assert pulls == []


def test_new_install_starts_paused():
    assert web.App(web.WEB_DIR, None).rt.settings["running"] is False


@with_app
async def test_set_running_persists(app, port):
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        r = await _cmd(ws, cmd="set_running", running=True)
        assert r["ok"] and app.rt.settings["running"] is True
    from rsub import store
    assert store.load_settings()["running"] is True


class FakeOverlay:
    def __init__(self):
        self.shown, self.hidden = [], 0

    def show(self, box, img):
        self.shown.append((box, img.size))

    def hide(self):
        self.hidden += 1


def _overlay_app():
    a = web.App(web.WEB_DIR, None)
    a.overlay = FakeOverlay()
    a.rt.settings["running"] = True
    a.rt.profile["region"] = [0.25, 0.75, 0.5, 0.1]
    a.rt.last_lines = [{"speaker": None, "color": None, "en": "Hi.", "tr": "Selam."}]
    return a


def test_overlay_centered_in_region_without_text_box():
    a = _overlay_app()  # bölge pencerede (580, 860, 960, 108)
    a.sync_overlay((100, 50, 1920, 1080))
    box, size = a.overlay.shown[0]
    assert size == (box["width"], box["height"]) and box["width"] < 960
    assert 580 <= box["left"] and box["left"] + box["width"] <= 1540 and 860 <= box["top"] and box["top"] + box["height"] <= 968
    assert abs(box["left"] + box["width"] / 2 - 1060) <= 2
    a.sync_overlay((100, 50, 1920, 1080))  # değişiklik yoksa yeniden çizme
    assert len(a.overlay.shown) == 1


def test_overlay_hidden_when_off_paused_or_no_window():
    a = _overlay_app()
    a.sync_overlay(None)
    a.rt.settings["overlay"] = False
    a.sync_overlay((0, 0, 1920, 1080))
    assert a.overlay.shown == []


def test_overlay_hides_after_being_shown():
    a = _overlay_app()
    a.sync_overlay((0, 0, 1920, 1080))
    a.rt.settings["running"] = False
    a.sync_overlay(None)
    assert len(a.overlay.shown) == 1 and a.overlay.hidden == 1


def test_overlay_rerenders_each_frame_when_blurred():
    from PIL import Image
    a = _overlay_app()
    a.rt.profile["style"]["blur"] = 16
    a.sync_overlay((0, 0, 1920, 1080), Image.new("RGB", (960, 108), "red"))
    a.sync_overlay((0, 0, 1920, 1080), Image.new("RGB", (960, 108), "blue"))
    assert len(a.overlay.shown) == 2  # arka plan değişti → yeniden çiz


def test_overlay_pill_follows_english_box():
    a = _overlay_app()  # bölge: [0.25, 0.75, 0.5, 0.1] → 1920x1080'de (480, 810, 960, 108)
    a.rt.text_box = (380, 20, 200, 60)  # bölgeye göre
    a.sync_overlay((0, 0, 1920, 1080))
    box, size = a.overlay.shown[-1]
    assert box["width"] < 960 and size == (box["width"], box["height"])
    assert abs(box["left"] + box["width"] / 2 - (480 + 480)) <= 2  # İngilizcenin merkezinde


def test_overlay_uses_original_line_count():
    a = _overlay_app()
    a.rt.profile["region"] = [0.1, 0.6, 0.8, 0.35]
    a.rt.last_lines = [{"speaker": None, "color": None, "en": "x",
                        "tr": "Pekala, geldiğimiz yolu geri takip edemeyiz. Hadi bu yolu deneyelim o zaman."}]
    a.rt.text_box, a.rt.text_lines = (500, 60, 700, 135), 3
    seen = {}
    real = web.layout.render
    web.layout.render = lambda *args, **k: (seen.update(rows=len(k["fitted"][1])), real(*args, **k))[1]
    try:
        a.sync_overlay((0, 0, 1920, 1080))
    finally:
        web.layout.render = real
    assert seen["rows"] == 3


def test_frozen_blur_renders_once_per_line():
    from PIL import Image
    a = _overlay_app()
    a.rt.profile["style"].update(blur=16, blurMode="frozen")
    a.sync_overlay((0, 0, 1920, 1080), Image.new("RGB", (960, 108), "red"))
    a.sync_overlay((0, 0, 1920, 1080), Image.new("RGB", (960, 108), "blue"))
    assert len(a.overlay.shown) == 1  # aynı satırda zemin sabit kalır
    a.rt.last_lines = [{"speaker": None, "color": None, "en": "Bye.", "tr": "Hoşça kal."}]
    a.sync_overlay((0, 0, 1920, 1080), Image.new("RGB", (960, 108), "blue"))
    assert len(a.overlay.shown) == 2  # yeni satırda yeniden hesaplanır


def test_pending_line_shows_blank_cover():
    a = _overlay_app()
    a.rt.last_lines = []
    a.rt.pending_box = ((380, 20, 200, 40), 1)
    a.sync_overlay((0, 0, 1920, 1080))
    box, size = a.overlay.shown[-1]
    assert box["left"] <= 480 + 380 and box["left"] + box["width"] >= 480 + 580  # İngilizce satır kapalı


def test_history_keeps_last_20_translations(monkeypatch):
    clock = iter(range(0, 1000, 5))  # satırlar 5 sn arayla (benzer okumalar birleşmesin)
    monkeypatch.setattr(web.time, "time", lambda: next(clock))
    a = web.App(web.WEB_DIR, None)
    for i in range(25):
        a._emit({"type": "lines", "lines": [{"speaker": None, "color": None, "en": f"Line {i}", "tr": f"Satır {i}"}]})
        a._emit({"type": "lines", "lines": []})  # silme olayları geçmişe girmez
    h = list(a.history)
    assert len(h) == 20 and h[0]["lines"][0]["en"] == "Line 5" and h[-1]["lines"][0]["tr"] == "Satır 24"
    assert "t" in h[-1]


@with_app
async def test_state_includes_history(app, port):
    app._emit({"type": "lines", "lines": [{"speaker": "Arthur", "color": "#f00", "en": "Hi.", "tr": "Selam."}]})
    async with connect(f"ws://127.0.0.1:{port}") as ws:
        r = await _cmd(ws, cmd="get_state")
        assert r["data"]["history"][-1]["lines"][0]["tr"] == "Selam."


def _line(en, tr="x"):
    return {"type": "lines", "lines": [{"speaker": None, "color": None, "en": en, "tr": tr}]}


def test_history_replaces_quick_better_reading():
    a = web.App(web.WEB_DIR, None)
    a._emit(_line("I tin ink..", "Mürekkep"))
    a._emit(_line("I think..", "Bence..."))
    assert [h["lines"][0]["en"] for h in a.history] == ["I think.."]


def test_history_skips_recent_duplicate():
    a = web.App(web.WEB_DIR, None)
    a._emit(_line("Yeah... that's him."))
    a._emit({"type": "lines", "lines": []})
    a._emit(_line("Yeah... that's him."))
    assert len(a.history) == 1


def test_cover_sent_to_tv_normalized_to_video_frame(monkeypatch):
    a = _overlay_app()
    sent = []
    monkeypatch.setattr(a, "send_displays", sent.append)
    a.displays = {object()}  # bağlı bir gösterim ekranı var
    a.rt.text_box = (380, 20, 200, 40)
    a.sync_overlay((0, 0, 1920, 1080))
    cov = [m for m in sent if m["type"] == "cover"][-1]
    x, y, w, h = cov["box"]
    box, _ = a.overlay.shown[-1]
    assert abs(x - box["left"] / 1920) < 1e-3 and abs(y - box["top"] / 1080) < 1e-3
    assert abs(w - box["width"] / 1920) < 1e-3 and cov["img"].startswith("data:image/webp;base64,")


def test_cover_sent_even_if_pc_overlay_off(monkeypatch):
    a = _overlay_app()
    a.rt.settings["overlay"] = False
    sent = []
    monkeypatch.setattr(a, "send_displays", sent.append)
    a.displays = {object()}
    a.sync_overlay((0, 0, 1920, 1080))
    assert a.overlay.shown == [] and any(m["type"] == "cover" and m["box"] for m in sent)


def test_cover_hidden_message_when_text_gone(monkeypatch):
    a = _overlay_app()
    sent = []
    monkeypatch.setattr(a, "send_displays", sent.append)
    a.displays = {object()}
    a.sync_overlay((0, 0, 1920, 1080))
    a.rt.last_lines = []
    a.sync_overlay((0, 0, 1920, 1080))
    assert sent[-1] == {"type": "cover", "box": None}


@with_app
async def test_display_path_counts_as_screen(app, port):
    async with connect(f"ws://127.0.0.1:{port}/display") as d, connect(f"ws://127.0.0.1:{port}") as panel:
        await d.recv()
        r = await _cmd(panel, cmd="get_state")
        assert r["data"]["status"]["clients"] == 1  # panel sayılmaz, yalnız gösterim ekranı
