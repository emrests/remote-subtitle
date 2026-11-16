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


def test_overlay_covers_region_of_window():
    a = _overlay_app()
    a.sync_overlay((100, 50, 1920, 1080))
    assert a.overlay.shown == [({"left": 580, "top": 860, "width": 960, "height": 108}, (960, 108))]
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
