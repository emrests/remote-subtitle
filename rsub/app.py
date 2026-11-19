"""Giriş noktası: sunucu thread'i + pywebview paneli, tek kopya. Pencere kapanınca uygulama tamamen kapanır."""
import argparse
import asyncio
import ctypes
import html
import json
import os
import threading

from . import capture
from .capture import APP_TITLE
from .web import PORT, WEB_DIR, serve_app

ERROR_ALREADY_EXISTS = 183
_mutex = None  # süreç boyunca açık kalmalı


def already_running() -> bool:
    global _mutex
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\remote-subtitle")
    return ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS


def set_window_icon(title: str, ico) -> None:
    """Pencere ve görev çubuğu simgesi. Kaynaktan (python.exe) çalışınca Windows Python simgesini gösteriyordu;
    ayrı uygulama kimliği görev çubuğunda Python'la aynı gruba düşmesini de önler."""
    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return
    for which, size in ((1, 0), (0, 16)):  # ICON_BIG (sistem boyutu), ICON_SMALL
        h = user32.LoadImageW(None, str(ico), 1, size, size, 0x10 | (0x40 if not size else 0))  # LR_LOADFROMFILE
        if h:
            user32.SendMessageW(hwnd, 0x80, which, h)  # WM_SETICON


def ask_show(port: int) -> None:
    """Çalışan kopyadan panelini öne getirmesini ister."""
    from websockets.sync.client import connect
    try:
        with connect(f"ws://127.0.0.1:{port}", open_timeout=3) as ws:
            ws.send(json.dumps({"id": 1, "cmd": "show"}))
            while json.loads(ws.recv(timeout=3)).get("type") != "reply":
                pass
    except Exception:  # çalışan kopya yanıt vermiyorsa sessizce çık
        pass


def error_page(message: str) -> str:
    return ('<!doctype html><meta charset="utf-8"><body style="background:#12161f;color:#e8ecf4;'
            'font:15px Segoe UI,sans-serif;padding:48px;max-width:640px">'
            '<h2 style="font-weight:600">Altyazı sunucusu başlatılamadı</h2>'
            f'<p style="color:#e5675c">{html.escape(message)}</p>'
            '<p style="color:#8e9ab3">Genellikle 8765 numaralı bağlantı noktasını başka bir program kullandığında olur. '
            'Bilgisayarı yeniden başlatıp uygulamayı tekrar açın; sorun sürerse bu mesajı paylaşın.</p></body>')


CLOSE_TITLE = "Remote Subtitle (TR) kapatılıyor"
CLOSE_TEXT = ("Ollama da kapatılsın mı?\n\n"
              "Evet: Ollama tamamen kapanır, arka planda çalışmaz.\n"
              "Hayır: Yalnızca bu uygulama kapanır; Ollama'yı kullanan başka bir program varsa çalışmaya devam eder.\n"
              "İptal: Uygulama açık kalır.\n\n"
              "Her iki durumda da çeviri modeli ekran kartı belleğinden boşaltılır.")
IDYES, IDNO = 6, 7
MB_YESNOCANCEL, MB_ICONQUESTION, MB_TOPMOST, MB_SETFOREGROUND = 0x3, 0x20, 0x40000, 0x10000


def ask_close() -> str | None:
    """Kapatırken sorar: "ollama" (Ollama da kapansın), "app" (yalnız uygulama) ya da None (iptal).
    Sahip pencere verilmez: pywebview kapanış olayını ayrı iş parçacığında çalıştırır, panel penceresine bağlı kutu
    iki iş parçacığını kilitleyebilirdi."""
    r = ctypes.windll.user32.MessageBoxW(None, CLOSE_TEXT, CLOSE_TITLE,
                                         MB_YESNOCANCEL | MB_ICONQUESTION | MB_TOPMOST | MB_SETFOREGROUND)
    return {IDYES: "ollama", IDNO: "app"}.get(r)


def shutdown(choice: str | None) -> None:
    """Kaynakları bırakır: model her durumda boşaltılır, istenirse Ollama da kapatılır."""
    unload_model()
    if choice == "ollama":
        from .models import stop_ollama
        stop_ollama()


def unload_model() -> None:
    """Kapanışta çeviri modelini Ollama'dan boşalt: oyun ekran kartı belleğini hemen geri alsın."""
    from . import store
    from .translate import unload
    unload(store.load_settings()["model"])


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="remote-subtitle")
    p.add_argument("--headless", action="store_true", help="pencere olmadan sadece sunucu")
    p.add_argument("--port", type=int, default=PORT)
    a = p.parse_args(argv)
    capture.set_dpi_aware()
    try:  # görev çubuğunda kendi simgesi ve grubu (python.exe ile karışmasın)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RemoteSubtitle.TR")
    except (AttributeError, OSError):
        pass

    if a.headless:
        asyncio.run(serve_app(a.port))
        return
    if already_running():
        ask_show(a.port)
        return

    import webview

    holder: dict = {}
    ready = threading.Event()

    def show() -> None:
        w = holder.get("window")
        if w:
            w.show()
            w.restore()

    def serve() -> None:
        try:
            asyncio.run(serve_app(a.port, on_show=show, ready=lambda app: ready.set()))
        except Exception as e:  # ör. port kullanımda: pencere boş kalmasın, nedeni göstersin
            holder["error"] = str(e) or type(e).__name__
            ready.set()

    threading.Thread(target=serve, daemon=True).start()
    if not ready.wait(15):
        holder["error"] = "Sunucu 15 saniye içinde yanıt vermedi."

    page = {"html": error_page(holder["error"])} if "error" in holder else {"url": f"http://127.0.0.1:{a.port}/"}
    window = webview.create_window(APP_TITLE, width=1280, height=800, min_size=(1100, 720),
                                   background_color="#12161f", **page)
    holder["window"] = window

    def on_closing():
        choice = ask_close()
        if choice is None:
            return False  # İptal: açık kalsın
        holder["close"] = choice
        return True

    window.events.closing += on_closing
    window.events.shown += lambda: set_window_icon(APP_TITLE, WEB_DIR / "icon.ico")
    webview.start()  # pencere kapanınca döner
    shutdown(holder.get("close", "app"))  # model boşalır; istendiyse Ollama da kapanır
    os._exit(0)  # katman pencereleri ve sunucu iş parçacıklarıyla birlikte tamamen kapan


if __name__ == "__main__":
    main()
