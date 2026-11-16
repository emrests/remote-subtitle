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
