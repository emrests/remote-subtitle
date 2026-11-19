"""Tek port: web/ klasöründen statik dosyalar, WebSocket yayını ve panel komutları."""
import asyncio
import base64
import io
import difflib
import json
import mimetypes
import os
import socket
import subprocess
import sys
import time
from collections import deque
from http import HTTPStatus
from pathlib import Path
from typing import Callable
from urllib.parse import unquote

import websockets
from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.http11 import Response

from . import capture, layout, ps5, store, tizen_cert, tizen_device
from .tizen_sign import sign_wgt
from .models import gpu_vram_mb, installed, model_infos, ollama_up, pull, recommend, start_ollama
from .ocr import make_ocr, ocr_language
from .pipeline import Runtime, _same, extra_key, run, run_extras

PORT = 8765
# PyInstaller paketinde dosyalar _MEIPASS altında
WEB_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "web"
TV_APP_DIR = WEB_DIR.parent / "tizen"  # TV uygulamasının kaynakları (kurulumda imzalanıp TV'ye gönderilir)


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


def build_tv_package(cert, pc_ip: str, src: Path | None = None) -> bytes:
    """TV uygulamasını PC adresi içine yazılmış halde imzalar (TV'de ilk açılışta adres sorulmaz)."""
    import shutil
    import tempfile
    src = src or TV_APP_DIR
    with tempfile.TemporaryDirectory() as d:
        app = Path(d) / "app"
        shutil.copytree(src, app, ignore=shutil.ignore_patterns("README.md", "*.wgt", ".*"))
        (app / "defaults.js").write_text(f'var RSUB_DEFAULT_PC = "{pc_ip}";\n', encoding="utf-8")
        return sign_wgt(app, cert.author, cert.distributor)


def local_networks() -> list[str]:
    """Bu bilgisayarın özel ağları (/24): TV taraması için."""
    import ipaddress
    nets = set()
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private and not ip.is_loopback and not ip.is_link_local:
            nets.add(str(ipaddress.ip_network(f"{ip}/24", strict=False)))
    return sorted(nets)


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
        first_run = not store.settings_exist()
        settings = store.load_settings()
        self.vram = None
        if first_run:  # ilk açılış: ekran kartına uygun modeli seç
            self.vram = gpu_vram_mb()
            settings["model"] = recommend(self.vram)
            store.save_settings(settings)
        self.rt = Runtime(settings, store.load_profile(settings["profile"]), self._emit)
        self.rt.on_frame = self.sync_overlay
        self.rt.on_extras = self.sync_extras
        self.overlay = None  # serve_app gerçek katmanı bağlar; testler sahtesini
        self.make_overlay: Callable | None = None  # ek bölgelerin katmanları (serve_app bağlar)
        self.extra_overlays: dict = {}  # ek bölge anahtarı -> katman
        self._extra_keys: dict = {}  # ek bölge anahtarı -> gösterilen kutunun özeti (değişmediyse yeniden çizme)
        self.history: deque = deque(maxlen=20)  # paneldeki çeviri akışı
        self._overlay_key = None
        self._below_pos = None  # (satırlar, bölge, x, y): altta modunda konum satır boyunca sabit
        self._tv_cover = False  # TV'ye kutu gönderildi ve henüz kaldırılmadı
        self.clients: set = set()
        self.displays: set = set()  # /display adresinden bağlanan gösterim ekranları (TV, ikinci ekran)
        self.display_pings: dict = {}  # gösterim ekranı -> son "buradayım" bildirimi (görünür mü, kaç kutu aldı)
        self.port = PORT
        self.auto_pulled = False
        self.ollama_started = False
        self.ollama = False
        self.models: set[str] = set()
        self.ocr_lang: str | None = None
        self.pull_state: dict | None = None

    # --- yayın ---
    def broadcast(self, msg: dict) -> None:
        websockets.broadcast(self.clients, json.dumps(msg, ensure_ascii=False))

    def _emit(self, msg: dict) -> None:
        if msg["type"] == "lines" and msg["lines"]:
            entry = {"t": time.time(), "lines": msg["lines"]}
            msg = {**msg, "t": entry["t"], "feed": self._remember(entry)}  # panel akışı da aynı ayıklamayı yapsın
        self.broadcast(msg)
        if msg["type"] == "lines" and any(l["speaker"] for l in msg["lines"]):
            self.broadcast({"type": "profile", "profile": self.rt.profile})  # yeni karakterler panelde görünsün

    def send_displays(self, msg: dict) -> None:
        websockets.broadcast(self.displays, json.dumps(msg, ensure_ascii=False))

    def _hide_cover(self) -> None:
        if self._overlay_key is not None:  # yalnızca gösteriliyorsa gizle (her karede komut gönderme)
            if self.overlay is not None:
                self.overlay.hide()
            if self._tv_cover:
                self.send_displays({"type": "cover", "box": None})
                self._tv_cover = False
            self._overlay_key = None

    def sync_overlay(self, rect, backdrop=None) -> None:
        """Çeviri kutusunu çizer: PC'de kaynak pencerenin üstüne (katman), TV'ye de aynı resmi konumuyla gönderir.
        TV'deki görünüm PC'dekiyle birebir aynı olur (buzlu cam dahil: chiaki karesi = TV karesi)."""
        s, pending = self.rt.settings, self.rt.pending_box
        below = self.rt.profile["style"].get("place") == "below"
        if self.rt.profile["style"].get("cover") == "together" or below:  # boş kutu yok: kutu çeviriyle birlikte gelir
            pending = None
        # PS5 kaynağında PC'de oyun penceresi yok: katman yalnız TV'de (rect kare koordinatıdır, ekran değil)
        prof = self.rt.profile
        show_pc = (self.overlay is not None and prof.get("showPc", True)
                   and prof["source"] != ps5.SOURCE)
        show_tv = bool(self.displays) and prof.get("showTv", True)
        if not show_tv and self._tv_cover:  # "TV'de göster" kapatıldı: TV'de kalan kutuyu kaldır
            self.send_displays({"type": "cover", "box": None})
            self._tv_cover = False
        lines = [] if pending else self.rt.last_lines  # yeni satır bekliyorsa eski çeviri değil boş kapak
        anchor = pending[0] if pending else self.rt.text_box
        if rect is None or not s.get("running") or not (show_pc or show_tv) or (not pending and not any(l["tr"] for l in lines)):
            self._hide_cover()
            return
        region = capture.to_pixels(self.rt.profile["region"], rect)
        style = self.rt.profile["style"]
        scale = rect[3] / 1080
        blurred = backdrop is not None and style.get("blur", 0) > 0 and not below  # altta: zemin bölge dışında
        if below:  # OCR kutusu satır boyunca büyür/titrer: konum ilk görünüşte sabitlenir, kayma olmaz
            pin = (json.dumps(lines, sort_keys=True), tuple(region.values()))
            if not self._below_pos or self._below_pos[0] != pin:
                self._below_pos = (pin, anchor)
            anchor = self._below_pos[1]
        key = (tuple(region.values()), anchor, bool(pending), show_pc, show_tv,
               json.dumps(lines, sort_keys=True), json.dumps(style, sort_keys=True))
        live = style.get("blurMode", "live") == "live"
        if key == self._overlay_key and not (blurred and live):  # canlı bulanıklıkta zemin her karede değişir
            return
        if below:
            (x, y, w, h), fitted = layout.pill(lines, style, region["width"], region["height"], scale, None)
            x, y = layout.below((w, h), anchor, region, rect, gap=round(8 * scale))
        else:
            (x, y, w, h), fitted = layout.pill(lines, style, region["width"], region["height"], scale, anchor)
        box = {"left": region["left"] + x, "top": region["top"] + y, "width": w, "height": h}
        img = layout.render(lines, style, w, h, scale, backdrop=backdrop.crop((x, y, x + w, y + h)) if blurred else None,
                            fitted=fitted, blank=bool(pending))
        if img is None:
            self._overlay_key = key
            self._hide_cover()
            return
        if self.overlay is not None:
            self.overlay.show(box, img) if show_pc else self.overlay.hide()
        if show_tv:
            # konum, chiaki penceresindeki 16:9 oyun karesine göre (siyah şeritler hariç) 0–1 oranı: TV ekranına aynen oturur
            fx, fy, fw, fh = capture.video_frame(rect)
            buf = io.BytesIO()
            img.save(buf, "WEBP", quality=90)
            self._tv_cover = True
            self.send_displays({"type": "cover",
                                "box": [(box["left"] - fx) / fw, (box["top"] - fy) / fh, w / fw, h / fh],
                                "img": "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()})
        self._overlay_key = key

    def sync_extras(self, rect, items) -> None:
        """Ek bölgelerin çevirisi: orijinal yazının yerine, zemini düz renkse o renkle, değilse siyahla kapatır."""
        prof = self.rt.profile
        show_pc = self.make_overlay is not None and prof.get("showPc", True) and prof["source"] != ps5.SOURCE
        show_tv = bool(self.displays) and prof.get("showTv", True)
        style = prof["style"]
        shown = set()
        for key, region_rel, ex, img in items:
            if rect is None or not ex.lines or not (show_pc or show_tv) or not self.rt.settings.get("running"):
                continue
            shown.add(key)
            region = capture.to_pixels(region_rel, rect)
            sig = (tuple(region.values()), ex.box, show_pc, show_tv, json.dumps(ex.lines), json.dumps(style, sort_keys=True))
            if self._extra_keys.get(key) == sig:
                continue
            scale = rect[3] / 1080
            (x, y, w, h), _ = layout.pill(ex.lines, style, region["width"], region["height"], scale, ex.box)
            bg = (layout.edge_color(img.crop((x, y, x + w, y + h))) if img is not None else None) or "#000000"
            st = {**style, "bg": bg, "bgOpacity": 1.0, "blur": 0, "color": layout.ink(bg)}
            _, fitted = layout.pill(ex.lines, st, region["width"], region["height"], scale, ex.box)
            pic = layout.render(ex.lines, st, w, h, scale, fitted=fitted)
            if pic is None:
                shown.discard(key)
                continue
            box = {"left": region["left"] + x, "top": region["top"] + y, "width": w, "height": h}
            ov = self.extra_overlays.get(key)
            if show_pc:
                ov = self.extra_overlays.setdefault(key, ov or self.make_overlay())
                ov.show(box, pic)
            elif ov:
                ov.hide()
            if show_tv:
                fx, fy, fw, fh = capture.video_frame(rect)
                buf = io.BytesIO()
                pic.save(buf, "WEBP", quality=90)
                self.send_displays({"type": "cover", "id": key,
                                    "box": [(box["left"] - fx) / fw, (box["top"] - fy) / fh, w / fw, h / fh],
                                    "img": "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()})
            else:  # "TV'de göster" kapalı: TV'de kalan kutu kalksın
                self.send_displays({"type": "cover", "id": key, "box": None})
            self._extra_keys[key] = sig
        for key in set(self._extra_keys) - shown:  # yazısı gitti, bölge silindi ya da durduruldu
            self._extra_keys.pop(key)
            self.send_displays({"type": "cover", "id": key, "box": None})
            if key in self.extra_overlays:
                self.extra_overlays[key].hide()
        for key in set(self.extra_overlays) - {extra_key(r) for r in prof.get("extraRegions") or []}:
            self.extra_overlays.pop(key).close()  # silinen bölgenin penceresi

    def _remember(self, entry: dict) -> str:
        """Çeviri akışına ekler. 2 sn içinde gelen benzer (daha düzgün) okuma eskisinin yerine geçer;
        3 sn içinde aynı satır tekrar gelirse eklenmez. "add" | "replace" | "skip" döner."""
        en = " ".join(l["en"] for l in entry["lines"])
        for h in reversed(self.history):
            if entry["t"] - h["t"] > 3:
                break
            if _same(en, " ".join(l["en"] for l in h["lines"])):
                return "skip"
        if self.history:
            last = self.history[-1]
            prev_en = " ".join(l["en"] for l in last["lines"])
            if entry["t"] - last["t"] <= 2 and difflib.SequenceMatcher(None, prev_en.lower(), en.lower()).ratio() >= 0.6:
                self.history[-1] = entry
                return "replace"
        self.history.append(entry)
        return "add"

    def status(self) -> dict:
        model = self.rt.settings["model"]
        return {**self.rt.status, "ollama": self.ollama, "model": model, "modelReady": model in self.models,
                "ocrLang": self.ocr_lang, "clients": len(self.displays), "displays": self.display_states(),
                "pull": self.pull_state}

    def display_states(self) -> list[dict]:
        """Her gösterim ekranının iletişim durumu: age = son bildirimden beri saniye (None: hiç bildirmedi)."""
        now = time.monotonic()
        out = []
        for ws in list(self.displays):
            p = self.display_pings.get(ws)
            out.append({"age": round(now - p["t"], 1), "visible": p["visible"], "tv": p["tv"], "covers": p["covers"]}
                       if p else {"age": None, "visible": None, "tv": None, "covers": 0})
        return out

    async def status_loop(self) -> None:
        while True:
            try:
                self.ollama = await asyncio.to_thread(ollama_up)
                if not self.ollama and not self.ollama_started:
                    self.ollama_started = await asyncio.to_thread(start_ollama)
                self.models = await asyncio.to_thread(installed) if self.ollama else set()
                self.rt.model_ready = self.rt.settings["model"] in self.models
                if self.rt.model_ready and self.rt.status["error"] and "hazır değil" in self.rt.status["error"]:
                    self.rt.status["error"] = None
                self.maybe_auto_pull()
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
        if ws.request.path.split("?")[0].rstrip("/") == "/display":
            self.displays.add(ws)
            self._overlay_key = None  # yeni ekran mevcut kutuyu da alsın
            self._extra_keys = dict.fromkeys(self._extra_keys)  # ek bölge kutuları da
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
            self.displays.discard(ws)
            self.display_pings.pop(ws, None)

    async def _command(self, ws, raw) -> None:
        try:
            msg = json.loads(raw)
            mid = msg.get("id")
        except ValueError:
            return
        if msg.get("type") == "displayPing":  # gösterim ekranından (TV) yanıt beklemeyen bildirim
            if ws in self.displays:
                self.display_pings[ws] = {"t": time.monotonic(), "visible": bool(msg.get("visible")),
                                          "tv": bool(msg.get("tv")), "covers": int(msg.get("covers") or 0)}
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
                "port": self.port, "status": self.status(), "history": list(self.history)}

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
        found = await asyncio.to_thread(capture.list_sources)
        host = self.rt.settings.get("ps5Host")
        return ([{"id": ps5.SOURCE, "label": f"PS5 — doğrudan ({host})", "group": "PS5"}] if host else []) + found

    async def cmd_snapshot(self, msg):
        if msg["source"] == ps5.SOURCE:
            img = await asyncio.to_thread(ps5.stream.wait_frame, self.rt.settings.get("ps5Host", ""))
            if img is None:
                raise RuntimeError(ps5.stream.error or "PS5'ten görüntü gelmedi; PS5 açık mı?")
            shot = await asyncio.to_thread(capture.jpeg, img)
        else:
            shot = await asyncio.to_thread(capture.snapshot_jpeg, msg["source"])
        if not shot:
            raise RuntimeError("Kaynak bulunamadı ya da küçültülmüş")
        jpg, w, h = shot
        return {"image": "data:image/jpeg;base64," + base64.b64encode(jpg).decode(), "width": w, "height": h}

    async def cmd_save_settings(self, msg):
        self.rt.settings.update(msg["settings"])
        store.save_settings(self.rt.settings)
        return self.rt.settings

    def maybe_auto_pull(self) -> None:
        """Seçili model kurulu değilse bir kez kendiliğinden indirmeye başla (kullanıcı bir şeye basmasın)."""
        model = self.rt.settings["model"]
        if self.auto_pulled or not self.ollama or model in self.models or self.pull_state:
            return
        self.auto_pulled = True
        self.start_pull(model)

    async def cmd_pull_model(self, msg):
        if self.pull_state:
            raise RuntimeError("Zaten bir indirme sürüyor")
        self.start_pull(msg["model"])
        return None

    def start_pull(self, model: str) -> None:
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

    async def cmd_set_running(self, msg):
        self.rt.settings["running"] = bool(msg["running"])
        store.save_settings(self.rt.settings)
        self.rt.status["running"] = self.rt.settings["running"]
        self.broadcast({"type": "status", "status": self.status()})
        return self.rt.settings["running"]

    # --- PS5 eşleştirme (Bağlantı sekmesi) ---
    async def cmd_ps5_state(self, msg):
        host = msg.get("host", self.rt.settings.get("ps5Host", ""))
        st = await asyncio.to_thread(ps5.status, host) if host else None
        if st and st["paired"] and host != self.rt.settings.get("ps5Host"):  # daha önce eşleşmiş PS5: PIN gerekmez
            self.rt.settings["ps5Host"] = host
            store.save_settings(self.rt.settings)
        return {"account": await asyncio.to_thread(ps5.account), "host": host, "ps5": st,
                "connected": ps5.stream.connected, "error": ps5.stream.error}

    async def cmd_ps5_connect(self, msg):
        host = self.rt.settings.get("ps5Host", "")
        if not host:
            raise ValueError("Önce PS5'i eşleştirin")
        if not await asyncio.to_thread(ps5.stream.retry, host):
            raise ValueError(ps5.stream.error or "PS5'ten görüntü gelmedi")
        return True

    async def cmd_ps5_open_login(self, msg):
        os.startfile(ps5.login_url())  # Sony'nin kendi giriş sayfası, varsayılan tarayıcıda
        return None

    async def cmd_ps5_add_account(self, msg):
        return await asyncio.to_thread(ps5.add_account, msg["url"])

    async def cmd_ps5_pair(self, msg):
        host = msg["host"].strip()
        name = await asyncio.to_thread(ps5.pair, host, msg["pin"])
        self.rt.settings["ps5Host"] = host
        store.save_settings(self.rt.settings)
        return {"name": name, "settings": self.rt.settings}

    # --- TV kurulumu (Kurulum sekmesi): sertifika, TV bulma, kurma ---
    def _tvs(self) -> list[dict]:
        return self.rt.settings.setdefault("tvs", [])

    def _remember_tv(self, tv: dict) -> None:
        same = lambda t: t.get("duid") == tv["duid"] or t.get("ip") == tv["ip"]
        old = next((t for t in self._tvs() if same(t)), {})
        self.rt.settings["tvs"] = [t for t in self._tvs() if not same(t)] + [{**old, **tv}]  # "installed" korunur
        store.save_settings(self.rt.settings)

    async def cmd_tv_state(self, msg):
        cert = await asyncio.to_thread(tizen_cert.load)
        return {"cert": cert.info() if cert else None, "tvs": self._tvs(), "pcIp": local_ip(),
                "sdb": tizen_device.sdb_path() is not None, "busy": getattr(self, "tv_busy", None)}

    async def cmd_tv_scan(self, msg):
        ips = await asyncio.to_thread(tizen_device.scan, local_networks())
        if msg.get("ip"):
            ips = sorted(set(ips) | {msg["ip"].strip()})
        found = []
        for ip in ips:
            try:
                tv = await asyncio.to_thread(tizen_device.info, ip)
            except Exception as e:  # noqa: BLE001 — bir TV'nin hatası taramayı durdurmasın
                found.append({"ip": ip, "error": str(e)})
                continue
            if tv["duid"]:
                self._remember_tv(tv)
            found.append(tv)
        return {"found": found, "tvs": self._tvs()}

    async def cmd_tv_import_tizen(self, msg):
        folder = Path(msg.get("path") or Path.home() / "SamsungCertificate")
        if not (folder / "distributor.p12").exists():  # klasör seçilmediyse: tek profil varsa onu al
            subs = [p for p in folder.glob("*") if (p / "distributor.p12").exists()]
            if len(subs) != 1:
                raise RuntimeError(f"Tizen Studio sertifikası bulunamadı ({folder})")
            folder = subs[0]
        cert = await asyncio.to_thread(tizen_cert.import_tizen_studio, folder)
        return cert.info()

    async def cmd_tv_create_cert(self, msg):
        """Samsung girişi (tarayıcı) + sertifika; bilinen bütün TV'ler sertifikaya eklenir."""
        cur = await asyncio.to_thread(tizen_cert.load)
        duids = sorted({t["duid"] for t in self._tvs() if t.get("duid")} | set(msg.get("duids") or [])
                       | set(cur.duids if cur else []))
        if not duids:
            raise RuntimeError("Önce TV'yi bulun: sertifika, TV'nin kimliğiyle oluşturulur")
        self.tv_busy = "Samsung girişi bekleniyor (tarayıcıda)…"
        try:
            access = await asyncio.to_thread(tizen_cert.login)
            if msg.get("email") and not access.email:
                access.email = msg["email"]
            self.tv_busy = "Sertifika oluşturuluyor…"
            cert = await asyncio.to_thread(tizen_cert.add_tvs, access, duids)
        finally:
            self.tv_busy = None
        return cert.info()

    async def cmd_tv_install(self, msg):
        ip = msg["ip"].strip()
        tv = await asyncio.to_thread(tizen_device.info, ip)
        cert = await asyncio.to_thread(tizen_cert.load)
        if cert is None:
            raise RuntimeError("Sertifika yok: önce 'Samsung ile giriş yap ve sertifika oluştur'")
        if tv["duid"] not in cert.duids:
            raise RuntimeError(f"Bu TV ({tv['duid']}) sertifikada yok: 'Samsung ile giriş yap' ile sertifikayı yenileyin")
        self._remember_tv(tv)
        wgt = await asyncio.to_thread(build_tv_package, cert, local_ip())
        await asyncio.to_thread(tizen_device.permit, ip, cert.device_profile)
        await asyncio.to_thread(tizen_device.install, ip, wgt)
        await asyncio.to_thread(tizen_device.launch, ip)
        self._remember_tv({**tv, "installed": True})
        return {"tv": tv}

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
    app.ocr_lang = ocr_language()
    app.rt.engine = make_ocr()
    app.rt.extra_engine = make_ocr()
    from .overlay import Overlay
    app.overlay = Overlay()
    app.make_overlay = Overlay
    if app.rt.engine is None:
        app.rt.status["error"] = "Windows'ta Latin alfabeli bir OCR dili bulunamadı (Ayarlar > Dil'den İngilizce ya da Türkçe ekleyin)." 
    async with serve(app.handler, "0.0.0.0", port, process_request=app.process_request) as server:
        app.port = server.sockets[0].getsockname()[1]
        if ready:
            ready(app)
        await asyncio.gather(run(app.rt), run_extras(app.rt), app.status_loop())
