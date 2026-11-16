"""Giriş noktası: sunucu thread'i + pywebview paneli + sistem tepsisi, tek kopya."""
import argparse
import asyncio
import ctypes
import json
import os
import threading

from . import capture
from .web import PORT, WEB_DIR, serve_app

ERROR_ALREADY_EXISTS = 183
_mutex = None  # süreç boyunca açık kalmalı


def already_running() -> bool:
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\remote-subtitle")
    return ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS


def ask_show(port: int) -> None:
    """Çalışan kopyadan panelini öne getirmesini ister."""
    from websockets.sync.client import connect
    try:
        with connect(f"ws://127.0.0.1:{port}", open_timeout=3) as ws:
            ws.send(json.dumps({"id": 1, "cmd": "show"}))
            while json.loads(ws.recv(timeout=3)).get("type") != "reply":
                pass
    except (OSError, TimeoutError):
        pass


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="remote-subtitle")
    p.add_argument("--headless", action="store_true", help="pencere ve tepsi olmadan sadece sunucu")
    p.add_argument("--port", type=int, default=PORT)
    a = p.parse_args(argv)
    capture.set_dpi_aware()

    if a.headless:
        asyncio.run(serve_app(a.port))
        return
    if already_running():
        ask_show(a.port)
        return

    import pystray
    import webview
    from PIL import Image

    holder: dict = {}
    ready = threading.Event()

    def show() -> None:
        w = holder.get("window")
        if w:
            w.show()
            w.restore()

    def serve() -> None:
        asyncio.run(serve_app(a.port, on_show=show, ready=lambda app: ready.set()))

    threading.Thread(target=serve, daemon=True).start()
    ready.wait(15)

    window = webview.create_window("remote-subtitle", f"http://127.0.0.1:{a.port}/", width=1280, height=800,
                                   min_size=(1100, 720), background_color="#12161f")
    holder["window"] = window

    def on_closing():
        window.hide()  # kapatınca tepsiye in, okuma/çeviri sürsün
        return False

    window.events.closing += on_closing

    def quit_app(icon, _item) -> None:
        icon.stop()
        os._exit(0)

    tray = pystray.Icon("remote-subtitle", Image.open(WEB_DIR / "icon.png"), "remote-subtitle",
                        menu=pystray.Menu(pystray.MenuItem("Paneli aç", lambda i, _: show(), default=True),
                                          pystray.MenuItem("Çıkış", quit_app)))
    tray.run_detached()
    webview.start()
    os._exit(0)  # pencere bir şekilde yok edilirse süreç de bitsin


if __name__ == "__main__":
    main()
