"""Tek port: web/ klasöründen statik dosyalar, WebSocket yayını ve panel komutları."""
import asyncio
import base64
import json
import mimetypes
import socket
import subprocess
import sys
from http import HTTPStatus
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

import websockets
from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

from . import capture, store
from .models import gpu_vram_mb, installed, model_infos, ollama_up, pull
from .ocr import has_english, make_ocr
from .pipeline import Runtime, run

PORT = 8765
# PyInstaller paketinde dosyalar _MEIPASS altında
WEB_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "web"


def _is_local(ws) -> bool:
    # IP yetmez: bilgisayardaki herhangi bir web sitesi de 127.0.0.1'e bağlanabilir. Origin de bizim olmalı
    # (tarayıcı dışı istemciler Origin göndermez).
    if ws.remote_address[0] not in ("127.0.0.1", "::1"):
        return False
    origin = ws.request.headers.get("Origin")
    port = ws.local_address[1]
    return origin is None or origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")


def static_rel(raw_path: str) -> str | None:
    """İstek yolunu web/ altında güvenli göreli yola çevirir; disk erişimi yapmadan reddeder."""
    rel = unquote(raw_path.split("?")[0]).lstrip("/") or "panel.html"
    if "\\" in rel or ":" in rel or "\x00" in rel or any(part in ("", ".", "..") for part in rel.split("/")):
        return None
    return rel


is_local = _is_local  # testler değiştirebilsin


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # paket gönderilmez, sadece çıkış arayüzü seçilir
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class App:
    def __init__(self, web_dir: Path, on_show: Callable[[], None] | None):
        self.web_dir = web_dir.resolve()
        self.on_show = on_show
        settings = store.load_settings()
        self.rt = Runtime(settings, store.load_profile(settings["profile"]), self._emit)
        self.clients: set = set()
        self.port = PORT
        self.vram = None
        self.ollama = False
        self.models: set[str] = set()
        self.ocr_en = False
        self.pull_state: dict | None = None

    # --- yayın ---
    def broadcast(self, msg: dict) -> None:
        websockets.broadcast(self.clients, json.dumps(msg, ensure_ascii=False))

    def _emit(self, msg: dict) -> None:
        self.broadcast(msg)
        if msg["type"] == "lines" and any(l["speaker"] for l in msg["lines"]):
            self.broadcast({"type": "profile", "profile": self.rt.profile})  # yeni karakterler panelde görünsün

    def status(self) -> dict:
        model = self.rt.settings["model"]
        return {**self.rt.status, "ollama": self.ollama, "model": model, "modelReady": model in self.models,
                "ocrEnglish": self.ocr_en, "clients": len(self.clients), "pull": self.pull_state}

    async def status_loop(self) -> None:
        while True:
            try:
                self.ollama = await asyncio.to_thread(ollama_up)
                self.models = await asyncio.to_thread(installed) if self.ollama else set()
                self.broadcast({"type": "status", "status": self.status()})
            except Exception as e:  # durum döngüsü de sunucuyu öldürmesin
                self.rt.status["error"] = f"Durum hatası: {e}"
            await asyncio.sleep(1)

    # --- HTTP ---
    def process_request(self, conn, req):
        if "upgrade" in req.headers.get("Connection", "").lower():
            return None
        rel = static_rel(req.path)
        path = (self.web_dir / rel).resolve() if rel else None
        if path is None or not path.is_relative_to(self.web_dir) or not path.is_file():
            return conn.respond(HTTPStatus.NOT_FOUND, "Bulunamadı\n")
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith(("javascript", "json")):
            ctype += "; charset=utf-8"
        body = path.read_bytes()
        return Response(200, "OK", Headers([("Content-Type", ctype), ("Content-Length", str(len(body))),
                                            ("Cache-Control", "no-cache")]), body)

    # --- WebSocket ---
    async def handler(self, ws) -> None:
        self.clients.add(ws)
        try:
            await ws.send(json.dumps({"type": "style", "style": self.rt.profile["style"]}, ensure_ascii=False))
            await ws.send(json.dumps({"type": "status", "status": self.status()}, ensure_ascii=False))
            await ws.send(json.dumps({"type": "lines", "lines": self.rt.last_lines}, ensure_ascii=False))
            async for raw in ws:
                await self._command(ws, raw)
        except websockets.ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)

    async def _command(self, ws, raw) -> None:
        try:
            msg = json.loads(raw)
            mid = msg.get("id")
        except ValueError:
            return
        reply = {"type": "reply", "id": mid, "ok": False, "data": None, "error": None}
        if not is_local(ws):
            reply["error"] = "forbidden"
        elif (fn := getattr(self, "cmd_" + str(msg.get("cmd")), None)) is None:
            reply["error"] = "bilinmeyen komut"
        else:
            try:
                reply.update(ok=True, data=await fn(msg))
            except Exception as e:
                reply["error"] = str(e)
        await ws.send(json.dumps(reply, ensure_ascii=False))

    def _set_profile(self, profile: dict) -> None:
        self.rt.profile = profile
        self.rt.last_lines = []
        self.broadcast({"type": "style", "style": profile["style"]})

    async def cmd_get_state(self, msg):
        if self.vram is None:
            self.vram = await asyncio.to_thread(gpu_vram_mb)
        return {"settings": self.rt.settings, "profile": self.rt.profile, "profiles": store.list_profiles(),
                "models": model_infos(self.vram, self.models), "vramMb": self.vram, "ip": local_ip(),
                "port": self.port, "status": self.status()}

    async def cmd_select_profile(self, msg):
        self.rt.settings["profile"] = msg["name"]
        store.save_settings(self.rt.settings)
        self._set_profile(store.load_profile(msg["name"]))
        return self.rt.profile

    async def cmd_save_profile(self, msg):
        store.save_profile(msg["profile"])
        p = store.load_profile(msg["profile"]["name"])
        if p["name"] == self.rt.profile["name"]:
            self.rt.profile = p
            self.broadcast({"type": "style", "style": p["style"]})
        return p

    async def cmd_copy_profile(self, msg):
        return store.copy_profile(msg["name"], msg["newName"])

    async def cmd_delete_profile(self, msg):
        store.delete_profile(msg["name"])
        if msg["name"] == self.rt.profile["name"]:
            rest = store.list_profiles()
            await self.cmd_select_profile({"name": rest[0] if rest else store.DEFAULT_SETTINGS["profile"]})
        return store.list_profiles()

    async def cmd_list_sources(self, msg):
        return await asyncio.to_thread(capture.list_sources)

    async def cmd_snapshot(self, msg):
        shot = await asyncio.to_thread(capture.snapshot_png, msg["source"])
        if not shot:
            raise RuntimeError("Kaynak bulunamadı ya da küçültülmüş")
        png, w, h = shot
        return {"png": base64.b64encode(png).decode(), "width": w, "height": h}

    async def cmd_save_settings(self, msg):
        self.rt.settings.update(msg["settings"])
        store.save_settings(self.rt.settings)
        return self.rt.settings

    async def cmd_pull_model(self, msg):
        model = msg["model"]
        if self.pull_state:
            raise RuntimeError("Zaten bir indirme sürüyor")
        self.pull_state = {"model": model, "pct": 0, "error": None}

        def work():
            try:
                pull(model, lambda pct: self.pull_state.update(pct=pct))
                self.pull_state = None
            except Exception as e:
                self.pull_state = {"model": model, "pct": 0, "error": str(e)}

        async def bg():
            await asyncio.to_thread(work)
            self.models = await asyncio.to_thread(installed)
            self.broadcast({"type": "status", "status": self.status()})
            if self.pull_state and self.pull_state.get("error"):
                await asyncio.sleep(5)
                self.pull_state = None

        asyncio.create_task(bg())
        return None

    async def cmd_launch_chiaki(self, msg):
        path = self.rt.settings.get("chiakiPath")
        if not path:
            raise RuntimeError("chiaki-ng yolu ayarlanmamış")
        subprocess.Popen([path])
        return None

    async def cmd_show(self, msg):
        if self.on_show:
            self.on_show()
        return None


async def serve_app(port: int = PORT, web_dir: Path = WEB_DIR, on_show=None, ready=None) -> None:
    app = App(web_dir, on_show)
    app.ocr_en = has_english()
    app.rt.engine = make_ocr()
    async with serve(app.handler, "0.0.0.0", port, process_request=app.process_request) as server:
        app.port = server.sockets[0].getsockname()[1]
        if ready:
            ready(app)
        await asyncio.gather(run(app.rt), app.status_loop())
