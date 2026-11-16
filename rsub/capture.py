"""Kaynak (pencere ya da monitör) bulma, oranlı bölgeyi piksele çevirme ve ekran yakalama."""
import ctypes
from ctypes import wintypes

import mss
import mss.tools

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
APP_TITLE = "remote-subtitle"
HIDDEN = {APP_TITLE, "Program Manager"}


def _cloaked(hwnd) -> bool:
    # Arka planda askıya alınmış UWP pencereleri "görünür" sayılır ama ekranda yoktur
    v = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(v), ctypes.sizeof(v))  # DWMWA_CLOAKED
    return bool(v.value)


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # monitör bazında DPI farkındalığı
    except (AttributeError, OSError):
        pass


def _windows() -> list[tuple[int, str]]:
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value not in HIDDEN and not _cloaked(hwnd):
                found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found


def list_sources() -> list[dict]:
    with mss.MSS() as s:
        mons = [{"id": f"monitor:{i}", "label": f"Monitör {i} ({m['width']}×{m['height']})"}
                for i, m in enumerate(s.monitors[1:], start=1)]
    return mons + [{"id": title, "label": title} for _, title in _windows()]


def target_rect(source: str) -> tuple[int, int, int, int] | None:
    """(left, top, width, height) sanal masaüstü pikselinde; bulunamazsa ya da küçültülmüşse None."""
    if source.startswith("monitor:"):
        with mss.MSS() as s:
            i = int(source.split(":")[1])
            if 1 <= i < len(s.monitors):
                m = s.monitors[i]
                return m["left"], m["top"], m["width"], m["height"]
        return None
    want = source.lower()
    for hwnd, title in _windows():
        if want in title.lower() and not user32.IsIconic(hwnd):
            r, p = wintypes.RECT(), wintypes.POINT(0, 0)
            user32.GetClientRect(hwnd, ctypes.byref(r))
            user32.ClientToScreen(hwnd, ctypes.byref(p))
            if r.right > 0 and r.bottom > 0:
                return p.x, p.y, r.right, r.bottom
    return None


def to_pixels(region: list[float], rect: tuple[int, int, int, int]) -> dict:
    x, y, w, h = region
    L, T, W, H = rect
    return {"left": L + round(x * W), "top": T + round(y * H),
            "width": max(1, round(w * W)), "height": max(1, round(h * H))}


def grab(sct, box: dict):
    return sct.grab(box)


def snapshot_png(source: str) -> tuple[bytes, int, int] | None:
    rect = target_rect(source)
    if not rect:
        return None
    with mss.MSS() as s:
        shot = s.grab(to_pixels([0, 0, 1, 1], rect))
    return mss.tools.to_png(shot.rgb, shot.size), shot.width, shot.height
